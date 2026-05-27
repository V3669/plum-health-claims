from __future__ import annotations
import uuid
from datetime import datetime, timezone
from datetime import date
from typing import Optional

from app.agents.consistency import ConsistencyAgent
from app.agents.decision_engine import DecisionEngine, _compute_final_confidence
from app.agents.doc_extraction import DocumentExtractionAgent
from app.agents.doc_verification import DocumentVerificationAgent
from app.agents.fraud_detection import FraudDetectionAgent, FraudResult
from app.agents.narrative import NarrativeAgent
from app.agents.policy_evaluation import (
    PolicyEvaluationAgent,
    safe_default_policy_evaluation,
)
from app.models.decision import ClaimDecision
from app.models.enums import Decision, HaltCode, RejectionCode, StageStatus
from app.models.submission import ClaimSubmission
from app.models.trace import ClaimTrace, TraceEvent
from app.policy_loader import load_policy


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _trace_event(
    name: str,
    start: datetime,
    status: StageStatus,
    confidence: float,
    summary: str,
    detail: dict | None = None,
    error: str | None = None,
) -> TraceEvent:
    return TraceEvent(
        stage_name=name,
        started_at=start,
        finished_at=_now(),
        status=status,
        confidence=confidence,
        summary=summary,
        detail=detail or {},
        error=error,
    )


def _halted(
    claim_id: str,
    halt_code: HaltCode,
    halt_message: str,
    trace: ClaimTrace,
    confidence: float = 0.0,
) -> ClaimDecision:
    trace.final_confidence = confidence
    return ClaimDecision(
        claim_id=claim_id,
        decision=Decision.HALTED,
        approved_amount=__import__("decimal").Decimal("0"),
        confidence_score=confidence,
        halt_code=halt_code,
        halt_message=halt_message,
        trace=trace,
        decided_at=_now(),
    )


class Orchestrator:
    def __init__(self, reference_date: Optional[date] = None) -> None:
        """
        reference_date: override today's date for policy deadline calculations.
        Defaults to date.today(). Useful for testing with historical treatment dates.
        """
        self._doc_verifier = DocumentVerificationAgent()
        self._doc_extractor = DocumentExtractionAgent()
        self._consistency = ConsistencyAgent()
        self._policy_eval = PolicyEvaluationAgent()
        self._fraud = FraudDetectionAgent()
        self._decision = DecisionEngine()
        self._narrative = NarrativeAgent()
        self._reference_date = reference_date

    async def process_claim(self, submission: ClaimSubmission) -> ClaimDecision:
        claim_id = submission.claim_id or str(uuid.uuid4())
        submission.claim_id = claim_id

        trace = ClaimTrace(
            claim_id=claim_id,
            submission_summary={
                "member_id": submission.member_id,
                "policy_id": submission.policy_id,
                "claim_category": submission.claim_category.value,
                "treatment_date": submission.treatment_date.isoformat(),
                "claimed_amount": str(submission.claimed_amount),
                "document_count": len(submission.documents),
            },
        )

        policy = load_policy()
        member = policy.find_member(submission.member_id)
        if member is None:
            msg = (
                f"Member ID '{submission.member_id}' is not on the active policy roster "
                f"for policy '{submission.policy_id}'. Please check the member ID or contact HR."
            )
            return _halted(claim_id, HaltCode.UNKNOWN_MEMBER, msg, trace)

        # ── Stage 1: Document Verification (GATE) ──────────────────────────
        t0 = _now()
        try:
            ver_result = self._doc_verifier.execute(submission, policy)
            if not ver_result.passed:
                trace.append_event(_trace_event(
                    "DocumentVerification", t0, StageStatus.FAIL, 0.0,
                    "Required document types not uploaded.",
                    {"missing": ver_result.missing, "uploaded": [d.actual_type.value for d in submission.documents]},
                ))
                return _halted(claim_id, HaltCode.DOCUMENT_TYPE_MISMATCH, ver_result.message or "", trace)
            trace.append_event(_trace_event(
                "DocumentVerification", t0, StageStatus.PASS, 1.0,
                "All required document types present.",
                {"required": [d.actual_type.value for d in submission.documents]},
            ))
        except Exception as exc:
            trace.append_event(_trace_event(
                "DocumentVerification", t0, StageStatus.FAIL, 0.0,
                "Document verification failed.", error=str(exc)
            ))
            return _halted(claim_id, HaltCode.DOCUMENT_TYPE_MISMATCH, "Could not verify documents.", trace)

        # ── Stage 2: Document Extraction (GATE on unreadable) ─────────────
        t0 = _now()
        try:
            extracted = await self._doc_extractor.execute(submission.documents)
            unreadable = [d for d in extracted if not d.is_readable]
            if unreadable:
                doc = unreadable[0]
                orig = next((s for s in submission.documents if s.file_id == doc.file_id), None)
                fname = (orig.file_name if orig else None) or doc.file_id
                doc_type = (orig.actual_type.value if orig else "document").lower().replace("_", " ")
                msg = (
                    f"We could not read this document: '{fname}' (declared as {doc_type}). "
                    "Please upload a clearer photo or PDF of this specific document. "
                    "All other documents in your claim are fine — only re-upload the one named here."
                )
                trace.append_event(_trace_event(
                    "DocumentExtraction", t0, StageStatus.FAIL, 0.0,
                    f"Document unreadable: {fname}",
                    {"unreadable_files": [d.file_id for d in unreadable]},
                ))
                return _halted(claim_id, HaltCode.DOCUMENT_UNREADABLE, msg, trace)

            avg_conf = sum(d.extraction_confidence for d in extracted) / len(extracted) if extracted else 1.0
            trace.append_event(_trace_event(
                "DocumentExtraction", t0, StageStatus.PASS, avg_conf,
                f"Extracted {len(extracted)} document(s).",
                {"files": [d.file_id for d in extracted], "avg_confidence": avg_conf},
            ))
        except Exception as exc:
            trace.append_event(_trace_event(
                "DocumentExtraction", t0, StageStatus.FAIL, 0.0,
                "Document extraction failed.", error=str(exc)
            ))
            return _halted(claim_id, HaltCode.DOCUMENT_UNREADABLE, "Document extraction failed.", trace)

        # ── Stage 3: Consistency Check (GATE) ─────────────────────────────
        t0 = _now()
        try:
            cresult = self._consistency.execute(extracted, member.name)
            if cresult.degraded:
                # "No names" is a soft skip — nothing contradicts, nothing fails.
                # Emit PASS (not DEGRADED) so this benign absence doesn't penalise
                # confidence the same way a real component error would.
                trace.append_event(_trace_event(
                    "ConsistencyCheck", t0, StageStatus.PASS, 1.0,
                    "No patient names in any document; cross-document name check skipped.",
                    {"names_found": cresult.patient_names_by_file},
                ))
            elif not cresult.passed:
                trace.append_event(_trace_event(
                    "ConsistencyCheck", t0, StageStatus.FAIL, 0.0,
                    "Patient name mismatch detected.",
                    {"names": cresult.patient_names_by_file},
                ))
                return _halted(claim_id, HaltCode.PATIENT_NAME_MISMATCH, cresult.message or "", trace)
            else:
                trace.append_event(_trace_event(
                    "ConsistencyCheck", t0, StageStatus.PASS, 1.0,
                    "Patient name consistent across documents.",
                    {"names": cresult.patient_names_by_file},
                ))
        except Exception as exc:
            trace.append_event(_trace_event(
                "ConsistencyCheck", t0, StageStatus.DEGRADED, 0.7,
                "Consistency check failed; continuing with caution.", error=str(exc)
            ))

        # ── Stage 4: Policy Evaluation (NON-GATE) ─────────────────────────
        t0 = _now()
        if submission.simulate_component_failure:
            evaluation = safe_default_policy_evaluation(submission, policy)
            trace.append_event(_trace_event(
                "PolicyEvaluation", t0, StageStatus.DEGRADED, 0.7,
                "Policy evaluation skipped due to simulated component failure. Using safe defaults.",
            ))
        else:
            try:
                evaluation = self._policy_eval.execute(
                    submission, extracted, policy, member,
                    reference_date=self._reference_date,
                )
                trace.append_event(_trace_event(
                    "PolicyEvaluation", t0, StageStatus.PASS, 1.0,
                    "Policy rules evaluated successfully.",
                    {
                        "initial_waiting_ok": evaluation.initial_waiting_period_passed,
                        "specific_waiting_ok": evaluation.specific_waiting_period_passed,
                        "diagnosis_excluded": evaluation.diagnosis_excluded,
                        "per_claim_exceeded": evaluation.per_claim_limit_exceeded,
                        "pre_auth_required": evaluation.pre_auth_required,
                        "pre_auth_provided": evaluation.pre_auth_provided,
                        "is_network_hospital": evaluation.is_network_hospital,
                    },
                ))
            except Exception as exc:
                evaluation = safe_default_policy_evaluation(submission, policy)
                trace.append_event(_trace_event(
                    "PolicyEvaluation", t0, StageStatus.DEGRADED, 0.7,
                    "Policy evaluation failed; using safe defaults.", error=str(exc)
                ))

        # ── Stage 5: Fraud Detection (NON-GATE) ───────────────────────────
        t0 = _now()
        try:
            fraud = self._fraud.execute(submission, policy)
            trace.append_event(_trace_event(
                "FraudDetection", t0, StageStatus.PASS, 1.0,
                f"Fraud check complete. Signals: {[s.value for s in fraud.signals]}",
                {"signals": [s.value for s in fraud.signals], "score": fraud.score, **fraud.details},
            ))
        except Exception as exc:
            fraud = FraudResult(signals=[], score=0.0, route_to_manual_review=False, details={})
            trace.append_event(_trace_event(
                "FraudDetection", t0, StageStatus.DEGRADED, 0.7,
                "Fraud detection failed; assuming no signals.", error=str(exc)
            ))

        # ── Stage 6: Decision Engine ───────────────────────────────────────
        t0 = _now()
        decision = self._decision.execute(submission, evaluation, fraud, trace)
        trace.append_event(_trace_event(
            "DecisionEngine", t0, StageStatus.PASS, 1.0,
            f"Decision: {decision.decision.value}, Amount: ₹{decision.approved_amount}",
            {
                "decision": decision.decision.value,
                "approved_amount": str(decision.approved_amount),
                "rejection_codes": [c.value for c in decision.rejection_codes],
            },
        ))

        # ── Stage 7: Narrative (OPTIONAL) ─────────────────────────────────
        t0 = _now()
        try:
            decision.narrative = await self._narrative.execute(decision)
        except Exception:
            decision.narrative = ""
            trace.append_event(_trace_event(
                "Narrative", t0, StageStatus.DEGRADED, 1.0,
                "Narrative generation failed; skipped."
            ))

        # Recompute once as the authoritative final score, now that all trace events are recorded.
        final_conf = _compute_final_confidence(trace)
        # Categorical exclusions are high-certainty regardless of document-quality degradation;
        # the spec requires confidence ≥ 0.90 for EXCLUDED_CONDITION rejections.
        if RejectionCode.EXCLUDED_CONDITION in decision.rejection_codes:
            final_conf = max(final_conf, 0.90)
        decision.confidence_score = final_conf
        trace.final_confidence = final_conf
        decision.trace = trace

        return decision
