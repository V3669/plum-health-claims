# Agent Contracts — Plum Claims Processing System

This document specifies the input/output contract for each agent in the pipeline. All types are Pydantic models unless noted.

---

## Stage 1 — DocumentVerificationAgent

**File:** `app/agents/doc_verification.py`
**Type:** Synchronous, pure Python

### Input

```python
submission: ClaimSubmission   # The full claim submission
policy: PolicyConfig          # Loaded policy configuration
```

Key fields used:
- `submission.claim_category` — looked up in `policy.document_requirements`
- `submission.documents[*].actual_type` — compared against required types

### Output

```python
@dataclass
class VerificationResult:
    passed: bool             # True if all required types are present
    missing: list[str]       # Required types not found in submission (as str values)
    message: str | None      # Human-readable message if failed
```

### Exceptions

Never raises. All errors produce `VerificationResult(passed=False, ...)`.

### Example — Pass

```python
# Input: CONSULTATION claim with PRESCRIPTION + HOSPITAL_BILL
# Output:
VerificationResult(passed=True, missing=[], message=None)
```

### Example — Fail (TC001)

```python
# Input: CONSULTATION claim with only LAB_REPORT
# Output:
VerificationResult(
    passed=False,
    missing=["PRESCRIPTION", "HOSPITAL_BILL"],
    message="Required document types not uploaded. Missing: PRESCRIPTION, HOSPITAL_BILL. Uploaded: LAB_REPORT."
)
```

---

## Stage 2 — DocumentExtractionAgent

**File:** `app/agents/doc_extraction.py`
**Type:** Async, calls Claude claude-sonnet-4-5 API (or uses `content` field as fallback)

### Input

```python
documents: list[DocumentSubmission]
```

Key fields per document:
- `file_id: str` — used as stable identifier in output
- `actual_type: DocumentType` — hints to LLM what to extract
- `quality: DocumentQuality` — GOOD / BLURRY / DAMAGED
- `content: str | None` — pre-extracted text (used instead of LLM if present)
- `patient_name_on_doc: str | None` — overrides LLM for name-only test cases

### Output

```python
list[ExtractedDocument]
```

Per-document fields:
```python
class ExtractedDocument(BaseModel):
    file_id: str
    declared_type: DocumentType
    inferred_type: DocumentType
    is_readable: bool                    # False if quality too low
    extraction_confidence: float         # 0.0–1.0
    patient_name: str | None
    date: date | None
    diagnosis: str | None
    doctor_name: str | None
    doctor_registration: str | None
    hospital_name: str | None
    line_items: list[LineItem]
    total_amount: Decimal | None
    treatment: str | None
    extraction_warnings: list[str]
```

### Exceptions

Raises on total system failure (network error after retries). Per-document failures set `is_readable=False` on that document.

### Fallback Hierarchy

1. If `patient_name_on_doc` is set → return minimal extraction with that name (confidence 0.70)
2. If `content` is set → parse `content` as pre-extracted text (no LLM call)
3. If `GEMINI_API_KEY` present → call Gemini gemini-2.0-flash
4. Else → return minimal document with `is_readable=True`, empty fields, confidence 0.50

### Example — Pass (TC004, pre-supplied content)

```python
# Input document with content field
ExtractedDocument(
    file_id="rx_tc004",
    declared_type=DocumentType.PRESCRIPTION,
    is_readable=True,
    extraction_confidence=0.95,
    patient_name="Rajan Mehta",
    diagnosis="Acute Gastritis",
    doctor_name="Dr. Sharma",
    line_items=[],
)
```

### Example — Fail (TC002, blurry document)

```python
ExtractedDocument(
    file_id="blurry_bill",
    declared_type=DocumentType.PHARMACY_BILL,
    is_readable=False,
    extraction_confidence=0.0,
    extraction_warnings=["Document quality too low to extract reliably."],
)
```

---

## Stage 3 — ConsistencyAgent

**File:** `app/agents/consistency.py`
**Type:** Synchronous, pure Python (uses RapidFuzz)

### Input

```python
extracted: list[ExtractedDocument]
member_name: str    # From MemberRecord.name
```

### Output

```python
@dataclass
class ConsistencyResult:
    passed: bool                                    # True if no name contradiction
    degraded: bool                                  # True if no names found in any doc
    patient_names_by_file: dict[str, str | None]    # file_id → name found
    message: str | None                             # Populated if passed=False
```

### Decision Logic

| Names found | All match (fuzzy ≥ 85) | Result |
|---|---|---|
| 0 | N/A | `degraded=True, passed=True` |
| ≥ 1 | Yes | `passed=True` |
| ≥ 1 | No | `passed=False` |

### Exceptions

On exception, the orchestrator catches and emits `DEGRADED` trace event; processing continues.

### Example — No names (TC004, TC011, TC012)

```python
ConsistencyResult(
    passed=True,
    degraded=True,
    patient_names_by_file={"rx1": None, "bill1": None},
    message=None
)
```

### Example — Mismatch (TC003)

```python
ConsistencyResult(
    passed=False,
    degraded=False,
    patient_names_by_file={"doc1": "Rajan Mehta", "doc2": "Priya Singh"},
    message="Patient name mismatch: 'Rajan Mehta' vs 'Priya Singh'."
)
```

---

## Stage 4 — PolicyEvaluationAgent

**File:** `app/agents/policy_evaluation.py`
**Type:** Synchronous, pure Python

### Input

```python
submission: ClaimSubmission
extracted: list[ExtractedDocument]
policy: PolicyConfig
member: MemberRecord
reference_date: date | None     # Override today for deadline checks (default: date.today())
```

### Output

```python
class PolicyEvaluation(BaseModel):
    member_active: bool = True
    initial_waiting_period_passed: bool = True
    specific_waiting_period_passed: bool = True
    matched_specific_condition: str | None = None
    eligible_from_date: date | None = None
    diagnosis_excluded: bool = False
    excluded_reason: str | None = None
    pre_auth_required: bool = False
    pre_auth_provided: bool = False
    per_claim_limit_exceeded: bool = False
    per_claim_limit_value: Decimal = Decimal("0")
    sub_limit_value: Decimal = Decimal("0")
    copay_percent: Decimal = Decimal("0")
    network_discount_percent: Decimal = Decimal("0")
    is_network_hospital: bool = False
    deadline_exceeded: bool = False
    deadline_days: int = 30
    below_minimum: bool = False
    excluded_line_items: list[LineItem] = []
    eligible_line_items: list[LineItem] = []
```

### Evaluation Order (internal)

1. `member_active` — from `policy.policy_holder.renewal_status`
2. `deadline_exceeded` — `(reference_date - treatment_date).days > deadline_days`
3. `below_minimum` — `claimed_amount < policy.submission_rules.minimum_claim_amount`
4. `diagnosis_excluded` — `matches_exclusion(diagnosis + treatment)`
5. `initial_waiting_period_passed` — `(treatment_date - join_date).days >= 30`
6. `specific_waiting_period_passed` — condition-specific lookup
7. `pre_auth_required/provided` — DIAGNOSTIC category only
8. `per_claim_limit_exceeded` — CONSULTATION/DIAGNOSTIC/PHARMACY only
9. `copay_percent`, `network_discount_percent`, `is_network_hospital` — from OPD category config
10. `excluded_line_items` / `eligible_line_items` — DENTAL/VISION only

### Exceptions

On exception, `safe_default_policy_evaluation()` is called, which returns conservative pass-through defaults (no rejections, copay from policy).

### Example — TC004 (Clean Consultation)

```python
PolicyEvaluation(
    member_active=True,
    initial_waiting_period_passed=True,
    specific_waiting_period_passed=True,
    diagnosis_excluded=False,
    per_claim_limit_exceeded=False,   # ₹1500 < ₹5000 limit
    copay_percent=Decimal("10"),
    is_network_hospital=False,
)
```

---

## Stage 5 — FraudDetectionAgent

**File:** `app/agents/fraud_detection.py`
**Type:** Synchronous, pure Python

### Input

```python
submission: ClaimSubmission    # Uses claims_history, claimed_amount, treatment_date
policy: PolicyConfig           # Uses fraud_thresholds
```

### Output

```python
@dataclass
class FraudResult:
    signals: list[FraudSignal]          # Triggered fraud signal enum values
    score: float                         # Computed fraud score (0.0–1.0)
    route_to_manual_review: bool         # True if score >= threshold
    details: dict                        # Extra context for trace
```

### Signal Detection

| Signal | Trigger |
|---|---|
| `SAME_DAY_CLAIMS` | ≥ `fraud_thresholds.same_day_claims_limit` claims on treatment_date in history |
| `MONTHLY_FREQUENCY` | ≥ `fraud_thresholds.monthly_claims_limit` claims in same month |
| `HIGH_VALUE_CLAIM` | `claimed_amount > fraud_thresholds.high_value_claim_threshold` |

Fraud score = `len(signals) / 3` (normalised to [0, 1]).

### Exceptions

On exception, returns `FraudResult(signals=[], score=0.0, route_to_manual_review=False, details={})`.

### Example — TC009 (Same-day fraud)

```python
FraudResult(
    signals=[FraudSignal.SAME_DAY_CLAIMS],
    score=0.33,
    route_to_manual_review=False,   # score < 0.75 threshold
    details={"same_day_count": 3, "treatment_date": "2024-10-15"}
)
```

---

## Stage 6 — DecisionEngine

**File:** `app/agents/decision_engine.py`
**Type:** Synchronous, pure Python

### Input

```python
submission: ClaimSubmission
evaluation: PolicyEvaluation
fraud: FraudResult
trace: ClaimTrace     # Read-only input for confidence calculation
```

### Output

```python
class ClaimDecision(BaseModel):
    claim_id: str
    decision: Decision              # APPROVED | PARTIAL | REJECTED | MANUAL_REVIEW | HALTED
    approved_amount: Decimal
    confidence_score: float
    reasons: list[str]
    rejection_codes: list[RejectionCode]
    fraud_signals: list[FraudSignal]
    financial_breakdown: FinancialBreakdown | None
    requires_manual_review: bool
    decided_at: datetime
    narrative: str                  # Filled by Stage 7
    trace: ClaimTrace               # Attached by orchestrator
```

### Decision Priority Order

1. `member_active=False` → REJECTED (INACTIVE_POLICY)
2. `deadline_exceeded=True` → REJECTED (DEADLINE_EXCEEDED)
3. `below_minimum=True` → REJECTED (BELOW_MIN_AMOUNT)
4. `diagnosis_excluded=True` → REJECTED (EXCLUDED_CONDITION)
5. `pre_auth_required and not pre_auth_provided` → REJECTED (PRE_AUTH_MISSING)
6. `not specific_waiting_period_passed` → REJECTED (WAITING_PERIOD)
7. `not initial_waiting_period_passed` → REJECTED (WAITING_PERIOD)
8. `per_claim_limit_exceeded=True` → REJECTED (PER_CLAIM_EXCEEDED)
9. `fraud.route_to_manual_review=True` → MANUAL_REVIEW
10. `confidence < 0.60` → MANUAL_REVIEW
11. `excluded_items and no eligible_items` → REJECTED (EXCLUDED_LINE_ITEM)
12. `excluded_items and some eligible_items` → PARTIAL (with financial breakdown)
13. Otherwise → APPROVED (with financial breakdown)

### Financial Breakdown Formula

```
base = eligible_line_items total (or claimed_amount if no line items)
discount = base × network_discount_percent / 100   (if network hospital)
after_discount = base - discount
copay = after_discount × copay_percent / 100
final = after_discount - copay
```

`sub_limit_value` is recorded for reporting but NOT applied as a per-claim cap.

### Exceptions

Never raises (pure logic over already-validated Pydantic models).

---

## Stage 7 — NarrativeAgent

**File:** `app/agents/narrative.py`
**Type:** Async, calls Claude claude-sonnet-4-5

### Input

```python
decision: ClaimDecision    # The completed decision object
```

### Output

```python
str    # 2–4 sentence plain-English explanation of the decision
```

### Exceptions

On any exception, the orchestrator catches it and sets `decision.narrative = ""`. The decision is unaffected.

---

## Supporting Models

### `ClaimTrace`

```python
class ClaimTrace(BaseModel):
    claim_id: str
    submission_summary: dict
    events: list[TraceEvent]       # Ordered; appended by orchestrator
    degraded_stages: int           # Auto-incremented for DEGRADED events
    final_confidence: float        # Set by orchestrator at end
```

### `TraceEvent`

```python
class TraceEvent(BaseModel):
    stage_name: str
    started_at: datetime
    finished_at: datetime
    status: StageStatus            # PASS | FAIL | DEGRADED | SKIPPED
    confidence: float
    summary: str
    detail: dict
    error: str | None
```

### `FinancialBreakdown`

```python
class FinancialBreakdown(BaseModel):
    claimed_amount: Decimal
    excluded_line_items_total: Decimal    # Sum of excluded items
    network_discount_applied: Decimal     # Discount from network hospital
    amount_after_discount: Decimal
    copay_applied: Decimal
    amount_after_copay: Decimal
    sub_limit_cap_applied: Decimal        # Always 0 (sub-limit ≠ per-claim cap)
    final_approved_amount: Decimal
```

---

## Halt Codes (Early Termination)

| Code | Triggering Condition |
|---|---|
| `UNKNOWN_MEMBER` | `member_id` not found in policy roster |
| `DOCUMENT_TYPE_MISMATCH` | Required document types not uploaded |
| `DOCUMENT_UNREADABLE` | A document cannot be read; names the specific file |
| `PATIENT_NAME_MISMATCH` | Contradicting patient names across documents |

---

## Rejection Codes

| Code | Condition |
|---|---|
| `INACTIVE_POLICY` | `member_active=False` |
| `DEADLINE_EXCEEDED` | Treatment date > 30 days before reference date |
| `BELOW_MIN_AMOUNT` | `claimed_amount < minimum_claim_amount` |
| `EXCLUDED_CONDITION` | Diagnosis matches policy exclusion list |
| `PRE_AUTH_MISSING` | Diagnostic test requires pre-auth; none provided |
| `WAITING_PERIOD` | Treatment within initial (30d) or specific condition waiting period |
| `PER_CLAIM_EXCEEDED` | OPD claim > ₹5,000 per-claim limit |
| `EXCLUDED_LINE_ITEM` | All line items excluded (e.g., all cosmetic dental) |
