from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel

from app.models.enums import ClaimCategory
from app.models.extraction import ExtractedDocument, LineItem
from app.models.policy import MemberRecord, PolicyConfig
from app.models.submission import ClaimSubmission
from app.utils.diagnosis_map import map_diagnosis_to_condition, matches_exclusion
from app.utils.names import hospital_name_match


class PolicyEvaluation(BaseModel):
    initial_waiting_period_passed: bool = True
    specific_waiting_period_passed: bool = True
    matched_specific_condition: Optional[str] = None
    eligible_from_date: Optional[date] = None
    diagnosis_excluded: bool = False
    excluded_reason: Optional[str] = None
    pre_auth_required: bool = False
    pre_auth_provided: bool = False
    per_claim_limit_exceeded: bool = False
    per_claim_limit_value: Decimal = Decimal("0")
    sub_limit_value: Decimal = Decimal("0")
    sub_limit_exceeded: bool = False
    copay_percent: Decimal = Decimal("0")
    network_discount_percent: Decimal = Decimal("0")
    is_network_hospital: bool = False
    deadline_exceeded: bool = False
    deadline_days: int = 30        # carried from policy so the message is accurate
    below_minimum: bool = False
    member_active: bool = True
    excluded_line_items: List[LineItem] = []
    eligible_line_items: List[LineItem] = []


def _primary_diagnosis(extracted: List[ExtractedDocument]) -> str:
    for doc in extracted:
        if doc.diagnosis:
            return doc.diagnosis
    return ""


def _treatment_text(extracted: List[ExtractedDocument]) -> str:
    parts = []
    for doc in extracted:
        if doc.treatment:
            parts.append(doc.treatment)
    return " ".join(parts)


def _collect_line_items(extracted: List[ExtractedDocument]) -> List[LineItem]:
    items: List[LineItem] = []
    for doc in extracted:
        items.extend(doc.line_items)
    return items


class PolicyEvaluationAgent:
    name = "PolicyEvaluation"

    def execute(
        self,
        submission: ClaimSubmission,
        extracted: List[ExtractedDocument],
        policy: PolicyConfig,
        member: MemberRecord,
        reference_date: Optional[date] = None,
    ) -> PolicyEvaluation:
        ev = PolicyEvaluation()

        ev.member_active = policy.policy_holder.renewal_status.upper() == "ACTIVE"

        ev.deadline_days = policy.submission_rules.deadline_days_from_treatment
        today = reference_date or date.today()
        days_since_treatment = (today - submission.treatment_date).days
        ev.deadline_exceeded = days_since_treatment > policy.submission_rules.deadline_days_from_treatment

        ev.below_minimum = submission.claimed_amount < policy.submission_rules.minimum_claim_amount

        diagnosis = _primary_diagnosis(extracted)
        treatment = _treatment_text(extracted)
        full_text = (diagnosis + " " + treatment).strip()

        matched_excl = matches_exclusion(full_text)
        if matched_excl:
            ev.diagnosis_excluded = True
            ev.excluded_reason = matched_excl

        join_date = member.join_date or policy.policy_holder.policy_start_date
        days_since_join = (submission.treatment_date - join_date).days
        ev.initial_waiting_period_passed = days_since_join >= policy.waiting_periods.initial_waiting_period_days

        condition = map_diagnosis_to_condition(diagnosis)
        if condition and condition in policy.waiting_periods.specific_conditions:
            required_days = policy.waiting_periods.specific_conditions[condition]
            ev.matched_specific_condition = condition
            ev.specific_waiting_period_passed = days_since_join >= required_days
            ev.eligible_from_date = join_date + timedelta(days=required_days)
        else:
            ev.specific_waiting_period_passed = True

        if submission.claim_category == ClaimCategory.DIAGNOSTIC:
            diag_cfg = policy.get_opd_category("diagnostic")
            if diag_cfg:
                all_items = _collect_line_items(extracted)
                threshold = (
                    diag_cfg.pre_auth_threshold
                    if diag_cfg.pre_auth_threshold is not None
                    else Decimal("10000")
                )
                for item in all_items:
                    for test in diag_cfg.high_value_tests_requiring_pre_auth:
                        if test.lower() in item.description.lower() and item.amount > threshold:
                            ev.pre_auth_required = True
                            break
                    if ev.pre_auth_required:
                        break
            ev.pre_auth_provided = submission.pre_authorization_ref is not None

        # Per-claim hard cap applies only to consultation, diagnostic, and pharmacy.
        # Dental, vision, and alternative medicine are governed by their category sub-limits.
        _PER_CLAIM_LIMIT_CATEGORIES = {
            ClaimCategory.CONSULTATION,
            ClaimCategory.DIAGNOSTIC,
            ClaimCategory.PHARMACY,
        }
        ev.per_claim_limit_value = policy.coverage.per_claim_limit
        ev.per_claim_limit_exceeded = (
            submission.claim_category in _PER_CLAIM_LIMIT_CATEGORIES
            and submission.claimed_amount > ev.per_claim_limit_value
        )

        cat_key = submission.claim_category.value.lower()
        cat_cfg = policy.get_opd_category(cat_key)
        if cat_cfg:
            ev.sub_limit_value = cat_cfg.sub_limit
            ev.copay_percent = cat_cfg.copay_percent

        if submission.hospital_name and cat_cfg:
            for h in policy.network_hospitals:
                if hospital_name_match(submission.hospital_name, h):
                    ev.is_network_hospital = True
                    ev.network_discount_percent = cat_cfg.network_discount_percent
                    break

        if cat_cfg:
            excluded_list: List[str] = []
            if submission.claim_category == ClaimCategory.DENTAL:
                excluded_list = cat_cfg.excluded_procedures
            elif submission.claim_category == ClaimCategory.VISION:
                excluded_list = cat_cfg.excluded_items

            all_items = _collect_line_items(extracted)
            for item in all_items:
                item_copy = item.model_copy()
                matched = next(
                    (excl for excl in excluded_list
                     if excl.lower() in item.description.lower()),
                    None,
                )
                if matched:
                    item_copy.is_excluded = True
                    item_copy.exclusion_reason = f"Excluded procedure: {matched}"
                    ev.excluded_line_items.append(item_copy)
                else:
                    ev.eligible_line_items.append(item_copy)

        return ev


def safe_default_policy_evaluation(submission: ClaimSubmission, policy: PolicyConfig) -> PolicyEvaluation:
    ev = PolicyEvaluation()
    ev.member_active = True
    ev.initial_waiting_period_passed = True
    ev.specific_waiting_period_passed = True
    ev.per_claim_limit_value = policy.coverage.per_claim_limit
    ev.per_claim_limit_exceeded = submission.claimed_amount > ev.per_claim_limit_value

    cat_key = submission.claim_category.value.lower()
    cat_cfg = policy.get_opd_category(cat_key)
    if cat_cfg:
        ev.sub_limit_value = cat_cfg.sub_limit
        ev.copay_percent = cat_cfg.copay_percent
    return ev
