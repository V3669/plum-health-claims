"""Runs all 12 test cases and writes EVAL_REPORT.md."""
import asyncio
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models.enums import ClaimCategory, DocumentQuality, DocumentType
from app.models.submission import ClaimSubmission, DocumentSubmission, HistoricalClaim
from app.orchestrator import Orchestrator

# All test-case treatment dates are in Oct–Nov 2024; use a fixed reference date
# close to the treatments so that deadline checks pass during eval.
_EVAL_REFERENCE_DATE = date(2024, 11, 12)


def _build_submission(inp: dict) -> ClaimSubmission:
    docs = []
    for d in inp.get("documents", []):
        docs.append(DocumentSubmission(
            file_id=d["file_id"],
            file_name=d.get("file_name"),
            actual_type=DocumentType(d["actual_type"]),
            quality=DocumentQuality(d.get("quality", "GOOD")),
            content=d.get("content"),
            patient_name_on_doc=d.get("patient_name_on_doc"),
        ))
    history = [
        HistoricalClaim(
            claim_id=h["claim_id"],
            date=date.fromisoformat(h["date"]),
            amount=Decimal(str(h["amount"])),
            provider=h.get("provider"),
        )
        for h in inp.get("claims_history", [])
    ]
    return ClaimSubmission(
        member_id=inp["member_id"],
        policy_id=inp["policy_id"],
        claim_category=ClaimCategory(inp["claim_category"]),
        treatment_date=date.fromisoformat(inp["treatment_date"]),
        claimed_amount=Decimal(str(inp["claimed_amount"])),
        hospital_name=inp.get("hospital_name"),
        ytd_claims_amount=Decimal(str(inp.get("ytd_claims_amount", 0))),
        claims_history=history,
        pre_authorization_ref=inp.get("pre_authorization_ref"),
        simulate_component_failure=inp.get("simulate_component_failure", False),
        documents=docs,
    )


def _check(decision, expected: dict) -> tuple[bool, str]:
    exp_decision = expected.get("decision")
    if exp_decision is None:
        # Early halt expected
        if decision.decision.value == "HALTED":
            return True, "Correctly halted before decision"
        return False, f"Expected HALT but got {decision.decision.value}"

    if decision.decision.value != exp_decision:
        return False, f"Expected {exp_decision}, got {decision.decision.value}"

    exp_amount = expected.get("approved_amount")
    if exp_amount is not None:
        if decision.approved_amount != Decimal(str(exp_amount)):
            return False, f"Amount mismatch: expected ₹{exp_amount}, got ₹{decision.approved_amount}"

    exp_conf = expected.get("confidence_score")
    if exp_conf == "above 0.85" and decision.confidence_score <= 0.85:
        return False, f"Confidence {decision.confidence_score:.2f} not above 0.85"
    if exp_conf == "above 0.90" and decision.confidence_score <= 0.90:
        return False, f"Confidence {decision.confidence_score:.2f} not above 0.90"

    exp_codes = expected.get("rejection_reasons", [])
    actual_codes = [c.value for c in decision.rejection_codes]
    for code in exp_codes:
        if code not in actual_codes:
            return False, f"Expected rejection code {code} not found; got {actual_codes}"

    return True, "All assertions passed"


async def main():
    root = Path(__file__).parent.parent.parent
    test_cases_file = root / "test_cases.json"
    test_cases = json.loads(test_cases_file.read_text())["test_cases"]

    orchestrator = Orchestrator(reference_date=_EVAL_REFERENCE_DATE)
    rows = []

    for tc in test_cases:
        case_id = tc["case_id"]
        case_name = tc["case_name"]
        expected = tc["expected"]
        exp_decision = expected.get("decision", "HALTED")

        try:
            sub = _build_submission(tc["input"])
            decision = await orchestrator.process_claim(sub)
            passed, note = _check(decision, expected)
            actual_decision = decision.decision.value
            actual_amount = f"₹{decision.approved_amount}" if decision.approved_amount else "—"
            actual_conf = f"{decision.confidence_score:.2f}"
        except Exception as exc:
            passed = False
            actual_decision = "ERROR"
            actual_amount = "—"
            actual_conf = "—"
            note = str(exc)

        rows.append({
            "case_id": case_id,
            "case_name": case_name,
            "expected": exp_decision or "HALTED",
            "actual": actual_decision,
            "amount": actual_amount,
            "confidence": actual_conf,
            "match": "✓" if passed else "✗",
            "notes": note,
        })
        status = "PASS" if passed else "FAIL"
        print(f"  {status}  {case_id}: {case_name}")

    passed_count = sum(1 for r in rows if r["match"] == "✓")
    total = len(rows)

    report_lines = [
        "# Eval Report — Plum Claims Processing System",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"**{passed_count}/{total} test cases passed.**",
        "",
        "| Case ID | Case Name | Expected | Actual | Amount | Confidence | Match | Notes |",
        "|---------|-----------|----------|--------|--------|-----------|-------|-------|",
    ]
    for r in rows:
        report_lines.append(
            f"| {r['case_id']} | {r['case_name']} | {r['expected']} | {r['actual']} "
            f"| {r['amount']} | {r['confidence']} | {r['match']} | {r['notes']} |"
        )

    report_lines += [
        "",
        "## Notes",
        "",
        "- TC001–TC003 produce `HALTED` decisions (early gate failures), not `null`.",
        "- TC004 approved amount ₹1350 = ₹1500 − 10% co-pay.",
        "- TC006 partial approval ₹8000; Teeth Whitening (₹4000) excluded as cosmetic.",
        "- TC010 approved amount ₹3240 = ₹4500 × 80% (network) × 90% (co-pay).",
        "- TC011 confidence is reduced due to degraded policy evaluation stage.",
        "- TC012 bariatric exclusion detected from diagnosis + treatment text.",
    ]

    report_path = root / "EVAL_REPORT.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\nEval report written to {report_path}")
    print(f"Result: {passed_count}/{total} passed")
    return passed_count == total


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
