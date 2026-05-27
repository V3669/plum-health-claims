from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class FamilyFloater(BaseModel):
    enabled: bool
    combined_limit: Decimal
    covered_relationships: List[str]

    @field_validator("combined_limit", mode="before")
    @classmethod
    def coerce(cls, v: Any) -> Decimal:
        return Decimal(str(v))


class Coverage(BaseModel):
    sum_insured_per_employee: Decimal
    annual_opd_limit: Decimal
    per_claim_limit: Decimal
    family_floater: FamilyFloater

    @field_validator("sum_insured_per_employee", "annual_opd_limit", "per_claim_limit", mode="before")
    @classmethod
    def coerce(cls, v: Any) -> Decimal:
        return Decimal(str(v))


class OpdCategory(BaseModel):
    sub_limit: Decimal
    copay_percent: Decimal = Decimal("0")
    network_discount_percent: Decimal = Decimal("0")
    branded_drug_copay_percent: Optional[Decimal] = None
    generic_mandatory: bool = False
    requires_prescription: bool = False
    requires_pre_auth: bool = False
    pre_auth_threshold: Optional[Decimal] = None
    high_value_tests_requiring_pre_auth: List[str] = Field(default_factory=list)
    covered: bool = True
    covered_procedures: List[str] = Field(default_factory=list)
    excluded_procedures: List[str] = Field(default_factory=list)
    covered_items: List[str] = Field(default_factory=list)
    excluded_items: List[str] = Field(default_factory=list)
    covered_systems: List[str] = Field(default_factory=list)
    max_sessions_per_year: Optional[int] = None
    requires_dental_report: bool = False
    requires_registered_practitioner: bool = False

    @field_validator("sub_limit", "copay_percent", "network_discount_percent",
                     "branded_drug_copay_percent", "pre_auth_threshold", mode="before")
    @classmethod
    def coerce(cls, v: Any) -> Optional[Decimal]:
        if v is None:
            return None
        return Decimal(str(v))


class WaitingPeriods(BaseModel):
    initial_waiting_period_days: int
    pre_existing_conditions_days: int
    specific_conditions: Dict[str, int]


class Exclusions(BaseModel):
    conditions: List[str]
    dental_exclusions: List[str] = Field(default_factory=list)
    vision_exclusions: List[str] = Field(default_factory=list)


class FraudThresholds(BaseModel):
    same_day_claims_limit: int
    monthly_claims_limit: int
    high_value_claim_threshold: Decimal
    auto_manual_review_above: Decimal
    fraud_score_manual_review_threshold: float

    @field_validator("high_value_claim_threshold", "auto_manual_review_above", mode="before")
    @classmethod
    def coerce(cls, v: Any) -> Decimal:
        return Decimal(str(v))


class SubmissionRules(BaseModel):
    deadline_days_from_treatment: int
    minimum_claim_amount: Decimal
    currency: str = "INR"

    @field_validator("minimum_claim_amount", mode="before")
    @classmethod
    def coerce(cls, v: Any) -> Decimal:
        return Decimal(str(v))


class DocumentRequirement(BaseModel):
    required: List[str]
    optional: List[str] = Field(default_factory=list)


class PolicyHolder(BaseModel):
    company_name: str
    employee_count: int
    policy_start_date: date
    policy_end_date: date
    renewal_status: str


class MemberRecord(BaseModel):
    member_id: str
    name: str
    date_of_birth: date
    gender: str
    relationship: str
    join_date: Optional[date] = None
    dependents: List[str] = Field(default_factory=list)
    primary_member_id: Optional[str] = None


class PolicyConfig(BaseModel):
    policy_id: str
    policy_name: str
    insurer: str
    policy_holder: PolicyHolder
    coverage: Coverage
    opd_categories: Dict[str, OpdCategory]
    waiting_periods: WaitingPeriods
    exclusions: Exclusions
    pre_authorization: Dict[str, Any]
    network_hospitals: List[str]
    submission_rules: SubmissionRules
    document_requirements: Dict[str, DocumentRequirement]
    fraud_thresholds: FraudThresholds
    members: List[MemberRecord]

    def find_member(self, member_id: str) -> Optional[MemberRecord]:
        for m in self.members:
            if m.member_id == member_id:
                return m
        return None

    def get_opd_category(self, claim_category: str) -> Optional[OpdCategory]:
        return self.opd_categories.get(claim_category.lower())
