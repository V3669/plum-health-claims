# Master Implementation Plan: Plum Claims Processing System

**Document type:** Architectural source-of-truth for downstream coding agent.
**Scope:** Full system covering all 12 test cases in `test_cases.json`, all rules in `policy_terms.json`, and all five deliverables.
**Authority:** This document supersedes any contradictory implementation instinct. Where this plan is silent, the agent must stop and ask. Where this plan is explicit, the agent must follow literally.

---

## 1. Requirement Mapping

### 1.1 Functional Requirements

| ID | Requirement | Source |
|---|---|---|
| **REQ-F01** | Accept a claim submission containing member_id, policy_id, claim_category, treatment_date, claimed_amount, and one or more documents (image or PDF). | assignment.md §"What the System Must Do" #1 |
| **REQ-F02** | Validate, before any downstream processing, that the uploaded documents match the `document_requirements[claim_category].required` list from policy_terms.json. If they do not match, halt the pipeline and return a message naming both the uploaded document type and the required document type. | assignment.md #2; TC001 |
| **REQ-F03** | Detect documents that cannot be read with sufficient confidence (e.g., blurry pharmacy bill). Halt and return a specific message asking for re-upload of the named document. The claim must not be auto-rejected. | assignment.md #2; TC002 |
| **REQ-F04** | Detect when documents in the same claim reference different patient names. Halt and return a message naming the conflicting names found. | TC003 |
| **REQ-F05** | Extract structured fields from each document: patient name, date, diagnosis, doctor name + registration, line items with amounts, hospital name, totals. Handle handwriting, stamps over text, low contrast, and missing fields gracefully. | assignment.md #3 |
| **REQ-F06** | Produce one of four decisions for every claim that passes the early gates: `APPROVED`, `PARTIAL`, `REJECTED`, `MANUAL_REVIEW`. Each decision includes approved_amount (if any), reason(s), and confidence_score. | assignment.md #4 |
| **REQ-F07** | Enforce category-specific sub-limits, co-pay percentages, network discount percentages, generic-drug rules, sessions-per-year caps, and excluded items/procedures from `policy_terms.json.opd_categories`. | TC004, TC006, TC010 |
| **REQ-F08** | Enforce per-claim limit (₹5,000) as a hard rejection when claimed_amount exceeds it. Do not cap; reject. | TC008 |
| **REQ-F09** | Enforce waiting periods: 30-day initial, 365-day pre-existing, and `specific_conditions` lookup keyed by diagnosis (diabetes 90d, hypertension 90d, thyroid 90d, joint replacement 730d, maternity 270d, mental health 180d, obesity 365d, hernia 365d, cataract 365d). Compute eligibility from member's `join_date`. | TC005 |
| **REQ-F10** | Enforce exclusions in two places: (a) full-claim rejection when diagnosis matches `exclusions.conditions` (e.g., obesity, bariatric); (b) line-item rejection within otherwise-valid categories (e.g., teeth whitening within dental). | TC006, TC012 |
| **REQ-F11** | Enforce pre-authorization: reject when claim_category is DIAGNOSTIC and any line item names a test in `diagnostic.high_value_tests_requiring_pre_auth` AND amount > `pre_auth_threshold` AND no pre-auth reference is present in the submission. Message must tell the member how to resubmit. | TC007 |
| **REQ-F12** | Apply network discount **before** co-pay when `hospital_name` matches `network_hospitals` (case-insensitive substring match). The trace must show the intermediate amount after discount and the final amount after co-pay separately. | TC010 |
| **REQ-F13** | Detect fraud signals: same-day claims count ≥ `fraud_thresholds.same_day_claims_limit`, monthly claims ≥ `monthly_claims_limit`, claim > `high_value_claim_threshold`, computed fraud_score ≥ `fraud_score_manual_review_threshold`. Any trigger routes to MANUAL_REVIEW, never to REJECTED. The triggering signals must be enumerated in the output. | TC009 |
| **REQ-F14** | Emit a complete, ordered trace for every claim. Every stage that runs (or is skipped, or fails) appears in the trace with its inputs summary, outputs summary, status, confidence, duration, and a human-readable explanation. | assignment.md #5 |
| **REQ-F15** | When any non-gate stage raises an unhandled exception, the pipeline must continue with conservative defaults, mark the stage as `DEGRADED` in the trace, lower system confidence by a multiplicative penalty, and append a recommendation for manual review. | assignment.md #6; TC011 |
| **REQ-F16** | Provide a UI for (a) submitting a claim with file uploads + form fields, and (b) reviewing the decision with the full trace expanded. | assignment.md Deliverables #1 |
| **REQ-F17** | Read all policy rules and member data from `policy_terms.json` at request time (or with file-mtime invalidation). No policy logic may be hardcoded in Python. | assignment.md §"Policy and Member Data" |
| **REQ-F18** | Produce an eval report that runs all 12 test cases and reports actual vs. expected for each. | assignment.md Deliverables #4 |

### 1.2 Non-Functional Requirements

| ID | Requirement |
|---|---|
| **REQ-N01** | No single component failure may crash the pipeline. All inter-agent calls are wrapped in fault boundaries. |
| **REQ-N02** | Every significant component has unit tests. Coverage target: ≥80% on the orchestrator, policy engine, fraud detector, and decision engine. |
| **REQ-N03** | Document extraction is async; multiple documents in one claim are extracted concurrently. |
| **REQ-N04** | All inter-component payloads are Pydantic models. Type errors are caught at boundary, not deep in business logic. |
| **REQ-N05** | The trace must be JSON-serializable in its entirety so it can be persisted, shown in the UI, and replayed. |
| **REQ-N06** | LLM output must be schema-validated. Free-form LLM text never enters the decision path. |
| **REQ-N07** | The system must run locally with a single command (`uvicorn app.main:app` or `docker compose up`) given an `ANTHROPIC_API_KEY` env var. |
| **REQ-N08** | Every decision response includes a stable `claim_id` (UUIDv4) and `decided_at` (UTC ISO 8601). |

### 1.3 Implicit Engineering Prerequisites

| ID | Prerequisite |
|---|---|
| **PRE-01** | A serialization boundary between the LLM (string-in, string-out) and the typed core (Pydantic). All LLM responses pass through `instructor` (or equivalent) for schema enforcement. |
| **PRE-02** | A name-normalization utility (lowercase, strip whitespace, strip honorifics like "Mr./Mrs./Dr.", collapse internal spaces, optional fuzzy match via RapidFuzz token_set_ratio ≥ 85). Used for patient-name cross-doc check and hospital-name network match. |
| **PRE-03** | A date-parsing utility that accepts multiple Indian formats (`01-Nov-2024`, `01/11/2024`, `2024-11-01`, `1 Nov 2024`) and returns `datetime.date`. |
| **PRE-04** | A diagnosis-to-condition mapper that maps free-text diagnoses to the policy's `specific_conditions` keys. E.g., "Type 2 Diabetes Mellitus" → "diabetes"; "Morbid Obesity" → "obesity_treatment"; "Lumbar Disc Herniation" → none. Built as a keyword dictionary with regex patterns; LLM-classified as fallback only. |
| **PRE-05** | A confidence calculator that combines per-stage confidences with documented arithmetic (see §3.5). |
| **PRE-06** | A trace-builder that is the single object passed by reference through the orchestrator. Each agent appends to it; no agent reads from it (one-way data flow). |
| **PRE-07** | A configurable LLM client wrapper with timeout (15s), 1 retry on transient errors, and explicit fallback behavior when no `ANTHROPIC_API_KEY` is configured (returns deterministic mock extractions from the `content` field in test cases). |
| **PRE-08** | An idempotency layer: same `claim_id` submitted twice returns the first decision. In-memory dict for assignment scope; Redis at 10x. |

---

## 2. Architectural Decision Records

### ADR-01: Pipeline Topology

**Context.** The system must run document checks, extraction, consistency checks, policy evaluation, fraud checks, and decision synthesis. Early stages can halt the pipeline; later stages must continue past component failure.

**Options.**
- **Option A — Deterministic Staged DAG.** A fixed ordered pipeline of agents. The Orchestrator invokes each in sequence. Each stage emits a status; gate stages can halt; non-gate stages can degrade. Inter-stage payloads are strongly typed.
- **Option B — Free-form Agent Graph (LLM router).** An LLM acts as a router that decides which agent to invoke next based on the current state.

**Trade-offs.**

| Dimension | Option A | Option B |
|---|---|---|
| Latency | Predictable; bounded by slowest stage; supports concurrency for extraction step | Unbounded; each routing decision is an extra LLM call |
| Maintainability | High — every path is in code, every transition testable | Low — emergent behavior; debugging requires replaying LLM decisions |
| Failure domains | Isolated per stage; orchestrator owns recovery | Diffuse — router failures cascade unpredictably |
| Explainability | Trace is a literal log of code execution | Trace must reconstruct LLM reasoning, often post-hoc |

**Verdict. Option A — Deterministic Staged DAG.** The assignment's explicit demand for explainability ("someone on the operations team must be able to look at the system's output and understand exactly what happened") makes Option B disqualifying. The "multi-agentic" bonus is preserved by having multiple specialized agent classes with distinct responsibilities, not by giving an LLM control of the pipeline.

### ADR-02: Where LLMs Are Used

**Context.** LLMs are powerful for unstructured-to-structured conversion but unreliable for arithmetic, rule interpretation, and conditional logic.

**Options.**
- **Option A — LLM at every decision point.** A single agent reads policy, reads documents, makes the decision.
- **Option B — LLM only for extraction and narrative.** Deterministic Python evaluates policy rules. LLM is used (1) inside the Document Extraction Agent to turn document images/text into structured JSON, and (2) optionally inside a Narrative Agent that converts the deterministic trace into a human-friendly summary.

**Trade-offs.**

| Dimension | Option A | Option B |
|---|---|---|
| Latency | Slower — every claim hits LLM in critical path | Faster — rules evaluated in microseconds |
| Maintainability | Brittle — policy changes require prompt engineering and re-eval | High — policy changes are JSON edits |
| Failure domains | LLM outage = pipeline outage | LLM outage = degraded narrative only; decisions still produced |
| Correctness | Non-deterministic on edge cases (TC008, TC010 math) | Deterministic; financial calc is unit-testable |

**Verdict. Option B — LLM only for extraction and narrative.** Decisions must be reproducible and auditable. Putting an LLM in the decision path violates REQ-F14 in spirit even if the trace is honest.

### ADR-03: Document Verification Strategy

**Context.** REQ-F02 requires detecting wrong document types **before** extraction. We know `actual_type` in test cases as a field, but in production this would need to be inferred from the document itself.

**Options.**
- **Option A — Trust client-supplied `actual_type`.** Use the field directly.
- **Option B — Re-classify every document via LLM.** Send each document to a vision model, ask "is this a PRESCRIPTION, HOSPITAL_BILL, LAB_REPORT, etc.?"
- **Option C — Hybrid.** Accept client-supplied `actual_type` as the primary signal, but cross-validate during extraction. If extracted content doesn't match the declared type (e.g., declared as HOSPITAL_BILL but no line items found), raise a `DOCUMENT_TYPE_MISMATCH` after extraction.

**Trade-offs.**

| Dimension | A | B | C |
|---|---|---|---|
| Latency | Instant | +1 LLM call per doc | Same as A for valid docs; +verification cost for invalid |
| Maintainability | Simplest | Most complex | Moderate |
| Failure mode | Trusts client lie | Robust but expensive | Catches lies during extraction |

**Verdict. Option C — Hybrid.** The test cases supply `actual_type`, so the system uses it. The Document Verification Agent compares this against the policy's required list. The Document Extraction Agent then validates that extracted fields are consistent with the declared type, raising a `DOCUMENT_TYPE_INCONSISTENT` warning that the Decision Engine treats as a confidence reducer (not a halt).

### ADR-04: State and Persistence

**Context.** The assignment is graded in 2–3 days. We need just enough persistence for the eval report and the UI.

**Options.**
- **Option A — In-memory only.** All state lives in process memory. Eval report is generated by a script that POSTs all 12 cases.
- **Option B — SQLite + file-backed traces.** Claims persist in SQLite; uploaded files in `./uploads/`; traces in `./traces/{claim_id}.json`.
- **Option C — Postgres + S3.** Production-grade.

**Trade-offs.**

| Dimension | A | B | C |
|---|---|---|---|
| Setup time | Zero | Minimal | Significant |
| Survives restart | No | Yes | Yes |
| Demoable | UI needs server up the whole time | Yes | Yes |
| 10x scalability | None | Limited | Native |

**Verdict. Option B — SQLite + file-backed traces.** Sufficient for the demo and eval report; survives a restart so the reviewer can inspect past decisions. 10x story is addressed in the Architecture Document section, not the build.

### ADR-05: Concurrency Model

**Context.** A single claim may have 4+ documents requiring OCR/extraction. Sequential extraction would dominate latency.

**Options.**
- **Option A — Sequential extraction.** Process documents one at a time.
- **Option B — `asyncio.gather` over documents.** Each document is its own coroutine; the Document Extraction Agent fans out and awaits all.

**Trade-offs.**

| Dimension | A | B |
|---|---|---|
| Latency | O(N × per-doc-latency) | O(per-doc-latency) |
| Failure isolation | One bad doc blocks rest | One bad doc fails its own coroutine; others complete |
| Complexity | Trivial | Standard asyncio pattern |

**Verdict. Option B — Concurrent extraction within a single agent.** Use `asyncio.gather(*[extract(doc) for doc in docs], return_exceptions=True)` so partial failures don't lose successful extractions.

### ADR-06: Confidence Aggregation

**Context.** Each agent emits a confidence score. The system needs one final confidence per decision.

**Options.**
- **Option A — Product.** `final = c1 × c2 × … × cN`. Penalizes any weak stage heavily.
- **Option B — Minimum.** `final = min(c1, c2, …, cN)`. Surfaces the weakest link.
- **Option C — Minimum with degradation penalty.** `final = min(successful_stages) × (0.7 ** num_degraded_stages)`.

**Trade-offs.**

| Dimension | A | B | C |
|---|---|---|---|
| Interpretability | Hard | Easy | Easy |
| Sensitivity to weak link | Too sensitive (everything drops to ~0) | Just right | Just right, plus penalizes degradation |
| Matches TC011 expectation | Drops too low | Doesn't penalize skipped stages | Matches expectation: lower than full-pipeline but still actionable |

**Verdict. Option C.** Implement as `final_confidence = min([s.confidence for s in successful_stages]) * (0.7 ** degraded_count)`.

### ADR-07: Tech Stack

**Verdict (no options needed; this is a delivery-velocity decision).**
- **Backend:** Python 3.11+, FastAPI, Pydantic v2, instructor (or `response_format` with JSON schema), Anthropic SDK, RapidFuzz, python-dateutil, SQLite (via sqlmodel or raw sqlite3), pytest, pytest-asyncio.
- **Frontend:** Single-page app via FastAPI templates + HTMX, OR React + Vite if the candidate is more productive there. Both are acceptable; the agent must pick one and not mix. **Default: HTMX + Jinja2** for lower complexity.
- **LLM:** Claude (any current model — `claude-sonnet-4-5` recommended for the extraction step) via the Anthropic SDK.
- **Packaging:** `pyproject.toml`, no monorepo, single FastAPI app.

---

## 3. Technical Specification

### 3.1 System Topology

```
                                ┌──────────────────────┐
                                │   FastAPI HTTP API   │
                                └──────────┬───────────┘
                                           │
                                ┌──────────▼───────────┐
                                │     Orchestrator     │
                                │  (deterministic DAG) │
                                └──────────┬───────────┘
                                           │
        ┌───────────┬──────────────┬───────┴────────┬──────────────┬───────────────┐
        │           │              │                │              │               │
   ┌────▼────┐ ┌────▼────┐  ┌──────▼──────┐  ┌──────▼──────┐ ┌─────▼─────┐  ┌──────▼──────┐
   │ DocVer  │ │ DocExt  │  │ Consistency │  │   Policy    │ │   Fraud   │  │  Decision   │
   │ Agent   │ │ Agent   │  │   Agent     │  │   Agent     │ │   Agent   │  │   Engine    │
   └────┬────┘ └────┬────┘  └──────┬──────┘  └──────┬──────┘ └─────┬─────┘  └──────┬──────┘
        │           │              │                │              │               │
        │   (gate)  │  (concurrent)│   (gate)       │ (rules)      │ (signals)     │
        │           │              │                │              │               │
        └───────────┴──────────────┴────────────────┴──────────────┴───────────────┘
                                           │
                                ┌──────────▼───────────┐
                                │    TraceBuilder      │
                                │   (single source     │
                                │    of audit truth)   │
                                └──────────────────────┘
```

Agents are stateless. Each agent reads its declared inputs, performs its work, returns a typed output, and (via the orchestrator) appends a TraceEvent. Agents never read other agents' outputs directly — the orchestrator routes data.

### 3.2 Data Architecture

#### 3.2.1 Core Domain Models (Pydantic)

```python
# app/models/enums.py
class ClaimCategory(str, Enum):
    CONSULTATION = "CONSULTATION"
    DIAGNOSTIC = "DIAGNOSTIC"
    PHARMACY = "PHARMACY"
    DENTAL = "DENTAL"
    VISION = "VISION"
    ALTERNATIVE_MEDICINE = "ALTERNATIVE_MEDICINE"

class DocumentType(str, Enum):
    PRESCRIPTION = "PRESCRIPTION"
    HOSPITAL_BILL = "HOSPITAL_BILL"
    LAB_REPORT = "LAB_REPORT"
    PHARMACY_BILL = "PHARMACY_BILL"
    DIAGNOSTIC_REPORT = "DIAGNOSTIC_REPORT"
    DENTAL_REPORT = "DENTAL_REPORT"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    UNKNOWN = "UNKNOWN"

class DocumentQuality(str, Enum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    UNREADABLE = "UNREADABLE"

class Decision(str, Enum):
    APPROVED = "APPROVED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    HALTED = "HALTED"  # internal — for early-halt before any decision

class RejectionCode(str, Enum):
    WAITING_PERIOD = "WAITING_PERIOD"
    PER_CLAIM_EXCEEDED = "PER_CLAIM_EXCEEDED"
    SUM_INSURED_EXCEEDED = "SUM_INSURED_EXCEEDED"
    OPD_LIMIT_EXCEEDED = "OPD_LIMIT_EXCEEDED"
    SUB_LIMIT_EXCEEDED = "SUB_LIMIT_EXCEEDED"
    EXCLUDED_CONDITION = "EXCLUDED_CONDITION"
    EXCLUDED_LINE_ITEM = "EXCLUDED_LINE_ITEM"
    PRE_AUTH_MISSING = "PRE_AUTH_MISSING"
    NON_COVERED_RELATIONSHIP = "NON_COVERED_RELATIONSHIP"
    INACTIVE_POLICY = "INACTIVE_POLICY"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    BELOW_MIN_AMOUNT = "BELOW_MIN_AMOUNT"

class HaltCode(str, Enum):
    DOCUMENT_TYPE_MISMATCH = "DOCUMENT_TYPE_MISMATCH"
    DOCUMENT_UNREADABLE = "DOCUMENT_UNREADABLE"
    PATIENT_NAME_MISMATCH = "PATIENT_NAME_MISMATCH"
    UNKNOWN_MEMBER = "UNKNOWN_MEMBER"
    UNKNOWN_CATEGORY = "UNKNOWN_CATEGORY"

class FraudSignal(str, Enum):
    SAME_DAY_LIMIT = "SAME_DAY_LIMIT"
    MONTHLY_LIMIT = "MONTHLY_LIMIT"
    HIGH_VALUE = "HIGH_VALUE"
    SCORE_THRESHOLD = "SCORE_THRESHOLD"

class StageStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"          # halt-fast stages
    SKIPPED = "SKIPPED"
    DEGRADED = "DEGRADED"  # ran with errors but produced output
```

#### 3.2.2 Submission Models

```python
class DocumentSubmission(BaseModel):
    file_id: str
    file_name: Optional[str] = None
    actual_type: DocumentType            # declared by client OR inferred from file
    quality: DocumentQuality = DocumentQuality.GOOD
    file_path: Optional[str] = None       # local path after upload
    content: Optional[Dict[str, Any]] = None  # for test cases — pre-extracted JSON

class ClaimSubmission(BaseModel):
    claim_id: Optional[str] = None        # auto-generated if missing
    member_id: str
    policy_id: str
    claim_category: ClaimCategory
    treatment_date: date
    claimed_amount: Decimal               # use Decimal for money; never float
    hospital_name: Optional[str] = None
    ytd_claims_amount: Decimal = Decimal("0")
    claims_history: List["HistoricalClaim"] = []
    pre_authorization_ref: Optional[str] = None
    documents: List[DocumentSubmission]
    simulate_component_failure: bool = False  # test hook for TC011

class HistoricalClaim(BaseModel):
    claim_id: str
    date: date
    amount: Decimal
    provider: Optional[str] = None
```

#### 3.2.3 Extraction Models

```python
class LineItem(BaseModel):
    description: str
    amount: Decimal
    is_excluded: bool = False
    exclusion_reason: Optional[str] = None

class ExtractedDocument(BaseModel):
    file_id: str
    declared_type: DocumentType
    inferred_type: DocumentType            # may differ — surface as inconsistency
    patient_name: Optional[str] = None
    document_date: Optional[date] = None
    diagnosis: Optional[str] = None
    secondary_diagnoses: List[str] = []
    medicines: List[str] = []
    tests_ordered: List[str] = []
    doctor_name: Optional[str] = None
    doctor_registration: Optional[str] = None
    hospital_name: Optional[str] = None
    line_items: List[LineItem] = []
    total_amount: Optional[Decimal] = None
    extraction_confidence: float           # 0.0 – 1.0
    extraction_warnings: List[str] = []
    is_readable: bool = True
```

#### 3.2.4 Trace Model

```python
class TraceEvent(BaseModel):
    stage_name: str                        # e.g., "DocumentVerification"
    started_at: datetime
    finished_at: datetime
    status: StageStatus
    confidence: float                      # 0.0 – 1.0
    summary: str                           # one-line human explanation
    detail: Dict[str, Any] = {}            # arbitrary stage-specific payload
    error: Optional[str] = None            # exception message if any

class ClaimTrace(BaseModel):
    claim_id: str
    submission_summary: Dict[str, Any]
    events: List[TraceEvent] = []
    final_confidence: float = 1.0
    degraded_stages: int = 0
```

#### 3.2.5 Decision Models

```python
class FinancialBreakdown(BaseModel):
    claimed_amount: Decimal
    network_discount_applied: Decimal = Decimal("0")
    amount_after_discount: Decimal
    copay_applied: Decimal = Decimal("0")
    amount_after_copay: Decimal
    excluded_line_items_total: Decimal = Decimal("0")
    sub_limit_cap_applied: Decimal = Decimal("0")
    final_approved_amount: Decimal

class ClaimDecision(BaseModel):
    claim_id: str
    decision: Decision
    approved_amount: Decimal = Decimal("0")
    confidence_score: float
    reasons: List[str] = []
    rejection_codes: List[RejectionCode] = []
    fraud_signals: List[FraudSignal] = []
    halt_code: Optional[HaltCode] = None
    halt_message: Optional[str] = None     # member-facing
    financial_breakdown: Optional[FinancialBreakdown] = None
    trace: ClaimTrace
    narrative: Optional[str] = None        # LLM-generated, optional
    decided_at: datetime
    requires_manual_review: bool = False
```

#### 3.2.6 SQLite Schema

```sql
CREATE TABLE claims (
  claim_id      TEXT PRIMARY KEY,
  member_id     TEXT NOT NULL,
  submitted_at  TEXT NOT NULL,
  decided_at    TEXT,
  decision      TEXT,
  approved_amount NUMERIC,
  confidence    REAL,
  submission_json TEXT NOT NULL,
  decision_json   TEXT,
  trace_path    TEXT
);

CREATE INDEX idx_claims_member ON claims(member_id);
CREATE INDEX idx_claims_decided_at ON claims(decided_at);
```

Traces are written to `./traces/{claim_id}.json`; the table stores the path. This keeps the DB small.

#### 3.2.7 State Transitions

```
RECEIVED ─► DOCS_CLASSIFIED ─► DOCS_EXTRACTED ─► DOCS_CONSISTENT ─► POLICY_EVALUATED ─► FRAUD_CHECKED ─► DECIDED
   │             │                   │                  │                  │                 │
   └─► HALTED ◄──┴──► HALTED ◄───────┴──► HALTED ◄──────┘                  │                 │
                                                                            │                 │
                                                              MANUAL_REVIEW ◄┴─────────────────┘
```

**Allowed transitions only.** Any attempt to skip a state is a programming error and raises `IllegalStateTransition`.

### 3.3 Component Contracts

Every agent implements:

```python
class Agent(Protocol[InputT, OutputT]):
    name: str
    async def execute(self, input: InputT, trace: ClaimTrace) -> OutputT: ...
```

#### Agent 1 — DocumentVerificationAgent

**Responsibility:** Compare uploaded document types against `policy.document_requirements[category].required`.

**Input.** `ClaimSubmission`, `PolicyConfig`.
**Output.** `DocumentVerificationResult(passed: bool, missing: List[DocumentType], unexpected: List[DocumentType], message: Optional[str])`.
**Halt condition:** `passed == False` → orchestrator emits HALTED with `halt_code=DOCUMENT_TYPE_MISMATCH` and `halt_message` naming uploaded vs required.
**Errors raised:** `UnknownCategoryError` if `claim_category` not in `policy.opd_categories`.

**Halt message template** (member-facing):
> "Your {category} claim requires the following documents: {required_list}. You uploaded {uploaded_list}. Please upload the missing document(s): {missing_list} and resubmit."

#### Agent 2 — DocumentExtractionAgent

**Responsibility:** Convert each `DocumentSubmission` into an `ExtractedDocument`. Uses LLM with structured-output enforcement for image/PDF inputs. For test cases supplying `content`, bypasses LLM and constructs the model from the content directly.

**Input.** `List[DocumentSubmission]`.
**Output.** `List[ExtractedDocument]`.
**Halt condition:** If ANY document has `is_readable == False` AND `quality == UNREADABLE`, orchestrator emits HALTED with `halt_code=DOCUMENT_UNREADABLE`, `halt_message` naming the specific unreadable file.
**Errors raised:** none — extraction failures convert to `ExtractedDocument(is_readable=False, extraction_confidence=0.0)`.

**Halt message template:**
> "We could not read your {document_type} (file: {file_name}). Please upload a clearer photo or PDF of this document and resubmit. All other documents you uploaded are fine and do not need to be re-uploaded."

**Concurrency:** uses `asyncio.gather(..., return_exceptions=True)`.

#### Agent 3 — ConsistencyAgent

**Responsibility:** Cross-document patient-name match.

**Input.** `List[ExtractedDocument]`, expected `member_name` (from policy roster).
**Output.** `ConsistencyResult(passed: bool, patient_names_by_file: Dict[str, str], message: Optional[str])`.

**Logic:**
1. Collect all non-null `patient_name` values from extracted documents.
2. Normalize each (lowercase, strip, remove honorifics).
3. If multiple distinct normalized names exist with fuzzy ratio < 85, `passed=False`.
4. If single distinct name but doesn't match member's name in roster with ratio ≥ 85, `passed=False`.

**Halt condition:** `passed == False` → `halt_code=PATIENT_NAME_MISMATCH`. Message names every file and the name found on it.

#### Agent 4 — PolicyEvaluationAgent

**Responsibility:** Apply every policy rule deterministically. Produces a structured ruling that the Decision Engine converts into a financial outcome.

**Input.** `ClaimSubmission`, `List[ExtractedDocument]`, `PolicyConfig`, `MemberRecord`.
**Output.** `PolicyEvaluation` (see below).
**Errors raised:** none — all failures become structured failure records.

```python
class PolicyEvaluation(BaseModel):
    initial_waiting_period_passed: bool
    specific_waiting_period_passed: bool
    matched_specific_condition: Optional[str] = None   # e.g., "diabetes"
    eligible_from_date: Optional[date] = None
    diagnosis_excluded: bool
    excluded_reason: Optional[str] = None
    pre_auth_required: bool
    pre_auth_provided: bool
    per_claim_limit_exceeded: bool
    per_claim_limit_value: Decimal
    sub_limit_value: Decimal
    sub_limit_exceeded: bool
    copay_percent: Decimal
    network_discount_percent: Decimal                  # 0 if not network
    is_network_hospital: bool
    deadline_exceeded: bool
    below_minimum: bool
    member_active: bool
    excluded_line_items: List[LineItem] = []
    eligible_line_items: List[LineItem] = []
```

**Detailed rule application order** (see §3.4.4 for full algorithm).

#### Agent 5 — FraudDetectionAgent

**Responsibility:** Compute fraud signals from claim history and current submission. Never rejects; only flags.

**Input.** `ClaimSubmission`, `PolicyConfig`.
**Output.** `FraudResult(signals: List[FraudSignal], score: float, route_to_manual_review: bool, details: Dict)`.

**Signal computation:**
- `SAME_DAY_LIMIT`: `count(claims_history where date == treatment_date) + 1 > policy.fraud_thresholds.same_day_claims_limit`
- `MONTHLY_LIMIT`: `count(claims_history within 30d) + 1 > policy.fraud_thresholds.monthly_claims_limit`
- `HIGH_VALUE`: `claimed_amount > policy.fraud_thresholds.high_value_claim_threshold`
- `SCORE_THRESHOLD`: computed score (sum of weighted signal flags) ≥ `policy.fraud_thresholds.fraud_score_manual_review_threshold`

**Scoring:** Each triggered signal contributes a weight (SAME_DAY: 0.5, MONTHLY: 0.3, HIGH_VALUE: 0.25). Score is clipped to 1.0. `route_to_manual_review = any signal triggered`.

#### Agent 6 — DecisionEngine

**Responsibility:** Combine PolicyEvaluation, FraudResult, and confidences into a final ClaimDecision.

**Input.** `ClaimSubmission`, `PolicyEvaluation`, `FraudResult`, `ClaimTrace`.
**Output.** `ClaimDecision`.

**Decision logic (in order):**

1. If `member_active == False` → REJECTED + `INACTIVE_POLICY`.
2. If `deadline_exceeded` → REJECTED + `DEADLINE_EXCEEDED`.
3. If `below_minimum` → REJECTED + `BELOW_MIN_AMOUNT`.
4. If `diagnosis_excluded` → REJECTED + `EXCLUDED_CONDITION`. Confidence ≥ 0.90 because exclusions are categorical.
5. If `pre_auth_required and not pre_auth_provided` → REJECTED + `PRE_AUTH_MISSING`. Include resubmission guidance.
6. If `not specific_waiting_period_passed` → REJECTED + `WAITING_PERIOD`. Include `eligible_from_date`.
7. If `not initial_waiting_period_passed` → REJECTED + `WAITING_PERIOD` with initial-period reason.
8. If `per_claim_limit_exceeded` → REJECTED + `PER_CLAIM_EXCEEDED`. State both the limit and the claimed amount.
9. If `fraud.route_to_manual_review` → MANUAL_REVIEW with signals enumerated.
10. If `claimed_amount > policy.fraud_thresholds.auto_manual_review_above` → MANUAL_REVIEW.
11. If `final_confidence < 0.60` → MANUAL_REVIEW.
12. Compute financial breakdown (§3.4.5). If `excluded_line_items` non-empty AND `eligible_line_items` non-empty → PARTIAL with itemized rejection list.
13. Otherwise → APPROVED with full breakdown.

#### Agent 7 — NarrativeAgent (optional, gracefully skipped)

**Responsibility:** Generate a 2–4 sentence human-readable explanation from the trace. LLM-powered. Failure does not affect decision.

**Input.** `ClaimDecision` (without narrative).
**Output.** `str`.
**Failure behavior:** returns empty string; orchestrator logs DEGRADED.

#### Orchestrator

**Responsibility:** Run agents in order, manage state, build trace, handle failures.

**Method signature:**

```python
async def process_claim(self, submission: ClaimSubmission) -> ClaimDecision: ...
```

**Errors raised:** Never. All exceptions are caught and converted to trace events. The decision returned reflects the best outcome possible given partial information.

#### HTTP API

```
POST  /api/claims                    → returns ClaimDecision
GET   /api/claims/{claim_id}         → returns stored ClaimDecision
GET   /api/claims                    → list (paginated)
POST  /api/claims/{claim_id}/files   → upload additional document
GET   /api/policy                    → returns PolicyConfig (read-only)
GET   /api/health                    → liveness probe
```

**Error envelope:**

```json
{
  "error": {
    "code": "VALIDATION_ERROR | UNKNOWN_MEMBER | INTERNAL_ERROR",
    "message": "human-readable",
    "details": { ... }
  }
}
```

HTTP status codes: 200 (decision returned, including HALTED), 400 (malformed input), 404 (unknown claim_id), 500 (orchestrator itself crashed — should never happen).

### 3.4 Control Flow — Deterministic Pseudo-Algorithms

#### 3.4.1 Orchestrator main loop

```
function process_claim(submission):
    claim_id := submission.claim_id or generate_uuid()
    trace := new ClaimTrace(claim_id, summarize(submission))
    policy := load_policy()                  # cached, mtime-invalidated
    member := policy.find_member(submission.member_id)
    if member is None:
        return halted(claim_id, UNKNOWN_MEMBER,
                      "Member ID {id} not found in policy roster.", trace)

    # ─── Stage 1: Document Verification (GATE) ───
    try:
        result := DocumentVerificationAgent.execute(submission, policy)
        trace.append(PASS or FAIL event)
        if not result.passed:
            return halted(claim_id, DOCUMENT_TYPE_MISMATCH, result.message, trace)
    except Exception as e:
        trace.append(FAIL event with error)
        return halted(claim_id, DOCUMENT_TYPE_MISMATCH,
                      "Could not verify documents.", trace)

    # ─── Stage 2: Document Extraction (GATE on unreadable) ───
    try:
        extracted := await DocumentExtractionAgent.execute(submission.documents)
        unreadable := [d for d in extracted if not d.is_readable]
        if unreadable:
            msg := build_unreadable_message(unreadable, extracted)
            trace.append(FAIL event)
            return halted(claim_id, DOCUMENT_UNREADABLE, msg, trace)
        trace.append(PASS event with avg confidence)
    except Exception as e:
        # extraction itself crashed → can't proceed, treat as halt
        trace.append(FAIL event)
        return halted(claim_id, DOCUMENT_UNREADABLE,
                      "Document extraction failed.", trace)

    # ─── Stage 3: Consistency Check (GATE) ───
    try:
        cresult := ConsistencyAgent.execute(extracted, member.name)
        if not cresult.passed:
            trace.append(FAIL event)
            return halted(claim_id, PATIENT_NAME_MISMATCH, cresult.message, trace)
        trace.append(PASS event)
    except Exception as e:
        trace.append(DEGRADED event)
        trace.degraded_stages += 1
        # Do NOT halt — continue with caution

    # ─── Stage 4: Policy Evaluation (NON-GATE) ───
    if submission.simulate_component_failure:
        # TC011 test hook — skip with degraded marker
        evaluation := safe_default_policy_evaluation(submission, policy)
        trace.append(DEGRADED event "Policy evaluation skipped due to component failure")
        trace.degraded_stages += 1
    else:
        try:
            evaluation := PolicyEvaluationAgent.execute(submission, extracted, policy, member)
            trace.append(PASS event)
        except Exception as e:
            evaluation := safe_default_policy_evaluation(submission, policy)
            trace.append(DEGRADED event with error)
            trace.degraded_stages += 1

    # ─── Stage 5: Fraud Detection (NON-GATE) ───
    try:
        fraud := FraudDetectionAgent.execute(submission, policy)
        trace.append(PASS event)
    except Exception as e:
        fraud := FraudResult(signals=[], score=0.0, route_to_manual_review=False)
        trace.append(DEGRADED event)
        trace.degraded_stages += 1

    # ─── Stage 6: Decision Synthesis ───
    decision := DecisionEngine.execute(submission, evaluation, fraud, trace)
    trace.append(PASS event)

    # ─── Stage 7: Narrative (OPTIONAL) ───
    try:
        decision.narrative := await NarrativeAgent.execute(decision)
    except Exception:
        decision.narrative := ""
        trace.append(DEGRADED event)

    # ─── Finalize ───
    decision.confidence_score := compute_final_confidence(trace)
    decision.trace := trace
    persist(decision)
    return decision
```

#### 3.4.2 Document Verification Algorithm

```
function verify(submission, policy):
    required := policy.document_requirements[submission.claim_category].required
    uploaded := [d.actual_type for d in submission.documents]

    # Check every required type is present at least once
    missing := []
    for r in required:
        if r not in uploaded:
            missing.append(r)

    # Detect "wrong document" — uploaded but none of required types present
    # This is TC001: two PRESCRIPTIONs uploaded for CONSULTATION (needs PRESCRIPTION + HOSPITAL_BILL)
    # missing = [HOSPITAL_BILL], uploaded = [PRESCRIPTION, PRESCRIPTION]
    if missing:
        msg := format(
            "Your {category} claim requires {required_list}. "
            "You uploaded {uploaded_count_by_type}. "
            "Please upload: {missing_list} and resubmit."
        )
        return DocumentVerificationResult(passed=False, missing=missing,
                                          unexpected=[], message=msg)

    return DocumentVerificationResult(passed=True, missing=[], unexpected=[], message=None)
```

**Critical detail:** `uploaded_count_by_type` is a dict like `{"PRESCRIPTION": 2}`. The message must say "You uploaded 2 prescriptions but a hospital bill is also required." Do NOT say "you uploaded the wrong document" — the test expects specificity.

#### 3.4.3 Document Extraction Algorithm

```
function extract_one(doc):
    if doc.content is not None:
        # Test-mode shortcut: build ExtractedDocument from supplied content
        return build_from_content(doc)
    if doc.quality == UNREADABLE:
        return ExtractedDocument(file_id=doc.file_id, is_readable=False,
                                 extraction_confidence=0.0,
                                 declared_type=doc.actual_type,
                                 inferred_type=UNKNOWN,
                                 extraction_warnings=["Document marked unreadable on upload."])
    # Real extraction via Claude vision model
    image_b64 := base64(read(doc.file_path))
    prompt := build_extraction_prompt(doc.actual_type)
    response := await claude_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2048,
        timeout=15,
        messages=[{role: user, content: [
            {type: image, source: {type: base64, data: image_b64}},
            {type: text, text: prompt}
        ]}],
        tools=[{type: "custom", name: "emit_extraction", input_schema: ExtractedDocument_schema}]
    )
    extracted := parse_tool_call(response, ExtractedDocument)
    return extracted

function extract_all(documents):
    results := await asyncio.gather(*[extract_one(d) for d in documents],
                                    return_exceptions=True)
    return [r if not isinstance(r, Exception)
              else ExtractedDocument(is_readable=False, extraction_confidence=0.0, ...)
            for r in results]
```

#### 3.4.4 Policy Evaluation Algorithm

```
function evaluate(submission, extracted, policy, member):
    eval := new PolicyEvaluation()

    # 1. Member active?
    eval.member_active := policy.policy_holder.renewal_status == "ACTIVE"

    # 2. Deadline check
    days_since_treatment := (today - submission.treatment_date).days
    eval.deadline_exceeded := days_since_treatment > policy.submission_rules.deadline_days_from_treatment

    # 3. Minimum amount
    eval.below_minimum := submission.claimed_amount < policy.submission_rules.minimum_claim_amount

    # 4. Diagnosis exclusion (full-claim)
    diagnosis := extract_primary_diagnosis(extracted)   # from any prescription/discharge
    treatment := extract_treatment_text(extracted)
    full_text := lowercase(diagnosis + " " + treatment)
    for excl in policy.exclusions.conditions:
        if excl_match(full_text, excl):
            eval.diagnosis_excluded := True
            eval.excluded_reason := excl
            break

    # 5. Initial waiting period
    days_since_join := (submission.treatment_date - member.join_date).days
    eval.initial_waiting_period_passed := days_since_join >= policy.waiting_periods.initial_waiting_period_days

    # 6. Specific condition waiting period
    condition := map_diagnosis_to_condition(diagnosis)
    if condition and condition in policy.waiting_periods.specific_conditions:
        required_days := policy.waiting_periods.specific_conditions[condition]
        eval.matched_specific_condition := condition
        eval.specific_waiting_period_passed := days_since_join >= required_days
        eval.eligible_from_date := member.join_date + required_days days
    else:
        eval.specific_waiting_period_passed := True

    # 7. Pre-auth check (DIAGNOSTIC only)
    if submission.claim_category == DIAGNOSTIC:
        for item in collect_line_items(extracted):
            for high_value_test in policy.opd_categories.diagnostic.high_value_tests_requiring_pre_auth:
                if high_value_test.lower() in item.description.lower() and \
                   item.amount > policy.opd_categories.diagnostic.pre_auth_threshold:
                    eval.pre_auth_required := True
                    break
        eval.pre_auth_provided := submission.pre_authorization_ref is not None

    # 8. Per-claim limit
    eval.per_claim_limit_value := policy.coverage.per_claim_limit
    eval.per_claim_limit_exceeded := submission.claimed_amount > eval.per_claim_limit_value

    # 9. Sub-limit for category
    cat_config := policy.opd_categories[submission.claim_category]
    eval.sub_limit_value := cat_config.sub_limit
    eval.copay_percent := cat_config.copay_percent

    # 10. Network hospital
    eval.is_network_hospital := submission.hospital_name is not None and \
        any(network_match(submission.hospital_name, h) for h in policy.network_hospitals)
    if eval.is_network_hospital:
        eval.network_discount_percent := cat_config.network_discount_percent
    else:
        eval.network_discount_percent := 0

    # 11. Line-item exclusions (within category)
    excluded_list := cat_config.excluded_procedures if claim_category == DENTAL else \
                     cat_config.excluded_items if claim_category == VISION else []
    for item in collect_line_items(extracted):
        if any(excl.lower() in item.description.lower() for excl in excluded_list):
            item.is_excluded := True
            item.exclusion_reason := matched_exclusion
            eval.excluded_line_items.append(item)
        else:
            eval.eligible_line_items.append(item)

    return eval
```

#### 3.4.5 Financial Calculation Algorithm

```
function compute_financial_breakdown(submission, eval):
    fb := new FinancialBreakdown(claimed_amount=submission.claimed_amount)

    # Step 1: Strip excluded line items (TC006)
    if eval.excluded_line_items:
        fb.excluded_line_items_total := sum(item.amount for item in eval.excluded_line_items)
        base := sum(item.amount for item in eval.eligible_line_items)
    else:
        base := submission.claimed_amount

    # Step 2: Apply network discount FIRST (TC010)
    if eval.is_network_hospital:
        fb.network_discount_applied := base * eval.network_discount_percent / 100
        fb.amount_after_discount := base - fb.network_discount_applied
    else:
        fb.amount_after_discount := base

    # Step 3: Apply co-pay on the post-discount amount (TC004, TC010)
    fb.copay_applied := fb.amount_after_discount * eval.copay_percent / 100
    fb.amount_after_copay := fb.amount_after_discount - fb.copay_applied

    # Step 4: Cap at sub-limit
    if fb.amount_after_copay > eval.sub_limit_value:
        fb.sub_limit_cap_applied := fb.amount_after_copay - eval.sub_limit_value
        fb.final_approved_amount := eval.sub_limit_value
    else:
        fb.final_approved_amount := fb.amount_after_copay

    # Round to 2 decimal places using ROUND_HALF_EVEN (banker's rounding)
    fb.final_approved_amount := quantize(fb.final_approved_amount, "0.01")
    return fb
```

**Verification against test cases:**
- TC004: claimed 1500, base 1500, not network → after_discount 1500 → copay 10% = 150 → after_copay 1350 → under 2000 sub-limit → **1350.** ✓
- TC006: claimed 12000, excluded 4000 (whitening) → base 8000 → not network → after_discount 8000 → copay 0% → after_copay 8000 → under 10000 sub-limit → **8000.** ✓
- TC010: claimed 4500, base 4500, network 20% → after_discount 3600 → copay 10% = 360 → after_copay 3240 → under sub-limit → **3240.** ✓

#### 3.4.6 Confidence Aggregation

```
function compute_final_confidence(trace):
    successful := [e.confidence for e in trace.events if e.status == PASS]
    if not successful:
        return 0.0
    base := min(successful)
    penalty := 0.7 ** trace.degraded_stages
    return round(base * penalty, 4)
```

#### 3.4.7 Diagnosis-to-Condition Mapping

```python
DIAGNOSIS_CONDITION_MAP = {
    "diabetes":           [r"\b(diabetes|t2dm|t1dm|dm\s*type)\b"],
    "hypertension":       [r"\b(hypertension|htn|high\s*blood\s*pressure)\b"],
    "thyroid_disorders":  [r"\b(thyroid|hypothyroid|hyperthyroid|goiter)\b"],
    "joint_replacement":  [r"\b(joint\s*replacement|knee\s*replacement|hip\s*replacement|arthroplasty)\b"],
    "maternity":          [r"\b(pregnan|maternity|antenatal|postnatal|delivery)\b"],
    "mental_health":      [r"\b(depression|anxiety|bipolar|schizo|psychiatric)\b"],
    "obesity_treatment":  [r"\b(obesity|bariatric|morbid\s*obes)\b"],
    "hernia":             [r"\bhernia\b"],
    "cataract":           [r"\bcataract\b"],
}

EXCLUSION_KEYWORDS = {
    "Obesity and weight loss programs": [r"\bobesity\b", r"\bweight\s*loss\b", r"\bmorbid\s*obes"],
    "Bariatric surgery":                  [r"\bbariatric\b"],
    "Infertility and assisted reproduction": [r"\binfertil", r"\bivf\b", r"\bart\s*treatment"],
    # ... derived from policy.exclusions.conditions
}
```

#### 3.4.8 Member-Facing Halt Messages

Each halt code maps to a template. The orchestrator never returns a bare halt code without a message.

| HaltCode | Template (filled at runtime) |
|---|---|
| `DOCUMENT_TYPE_MISMATCH` | "Your {category} claim requires {required}. We received: {received}. Please upload: {missing} and resubmit. You do not need to re-upload the documents that are already correct." |
| `DOCUMENT_UNREADABLE` | "We could not read this document: '{file_name}' (declared as {type}). Please upload a clearer photo or PDF of this specific document. All other documents in your claim are fine — only re-upload the one named here." |
| `PATIENT_NAME_MISMATCH` | "The documents in this claim appear to belong to different patients. We found the name '{name_a}' on '{file_a}' and '{name_b}' on '{file_b}'. Please verify the documents and resubmit with documents belonging to the same patient." |
| `UNKNOWN_MEMBER` | "Member ID '{member_id}' is not on the active policy roster for policy '{policy_id}'. Please check the member ID or contact HR." |

### 3.5 Repository Layout

```
plum_claims/
├── pyproject.toml
├── README.md                       # setup, run, demo, architecture
├── ARCHITECTURE.md                 # the architecture document deliverable
├── CONTRACTS.md                    # the component contracts deliverable
├── EVAL_REPORT.md                  # the eval report deliverable
├── policy_terms.json               # copied from project
├── test_cases.json                 # copied from project
├── app/
│   ├── main.py                     # FastAPI app factory + routes
│   ├── config.py                   # settings, env vars
│   ├── models/
│   │   ├── enums.py
│   │   ├── submission.py
│   │   ├── extraction.py
│   │   ├── trace.py
│   │   ├── decision.py
│   │   └── policy.py
│   ├── agents/
│   │   ├── base.py                 # Agent protocol, exceptions
│   │   ├── doc_verification.py
│   │   ├── doc_extraction.py
│   │   ├── consistency.py
│   │   ├── policy_evaluation.py
│   │   ├── fraud_detection.py
│   │   ├── decision_engine.py
│   │   └── narrative.py
│   ├── orchestrator.py             # process_claim()
│   ├── policy_loader.py            # cached, mtime-invalidated
│   ├── llm_client.py               # Anthropic wrapper with retry/timeout
│   ├── persistence.py              # SQLite + trace files
│   ├── utils/
│   │   ├── names.py                # normalize, fuzzy match
│   │   ├── dates.py
│   │   ├── diagnosis_map.py
│   │   └── money.py                # Decimal quantization helpers
│   └── ui/
│       ├── templates/              # Jinja2
│       │   ├── base.html
│       │   ├── submit.html
│       │   ├── decision.html
│       │   └── trace.html
│       └── static/
├── tests/
│   ├── unit/
│   │   ├── test_doc_verification.py
│   │   ├── test_consistency.py
│   │   ├── test_policy_evaluation.py
│   │   ├── test_fraud_detection.py
│   │   ├── test_decision_engine.py
│   │   ├── test_financial_calc.py
│   │   ├── test_diagnosis_map.py
│   │   └── test_confidence.py
│   ├── integration/
│   │   └── test_orchestrator.py
│   └── eval/
│       └── run_eval.py             # runs all 12 test cases, produces EVAL_REPORT.md
└── scripts/
    └── seed_db.py
```

---

## 4. Execution Rules

These are imperative. The coding agent must implement them literally.

### 4.1 General Rules

1. The agent must use Python 3.11 or higher and Pydantic v2.
2. The agent must use `Decimal` for every monetary value end-to-end. The agent must never use `float` for money. Conversions from JSON numbers happen at the Pydantic boundary using `Decimal` field types.
3. The agent must round monetary values to 2 decimal places using `Decimal.quantize(Decimal("0.01"), ROUND_HALF_EVEN)`.
4. The agent must use `datetime.date` (not `datetime.datetime`) for treatment dates, join dates, and policy dates. Use `datetime.datetime` with `timezone.utc` for timestamps.
5. The agent must never let an exception propagate out of `Orchestrator.process_claim`. Every `try` block must have an `except Exception` that converts to a trace event and either halts or degrades.
6. The agent must read `policy_terms.json` through `policy_loader.load_policy()` which caches by file mtime. The agent must not call `json.load` on the policy file from any other module.
7. The agent must implement an idempotency check in `persistence.save_decision`: if `claim_id` already exists, return the stored decision instead of overwriting.
8. The agent must persist every decision (including HALTED ones) to SQLite and write the trace JSON to `./traces/{claim_id}.json`.

### 4.2 Document Verification Rules

9. The agent must derive the required-documents list ONLY from `policy.document_requirements[claim_category].required`. The agent must not hardcode required types.
10. The agent must count uploaded documents per type. If a required type has zero uploads, it goes in `missing`.
11. The agent's halt message must name (a) the claim category, (b) the full list of required types, (c) the count and types of what was uploaded, (d) the specific missing types. The message must not say "wrong documents"; it must say what's missing.
12. The agent must allow extra documents — uploading both `LAB_REPORT` and `HOSPITAL_BILL` for a consultation is fine if both `PRESCRIPTION` and `HOSPITAL_BILL` (required) are present.

### 4.3 Document Extraction Rules

13. The agent must check `doc.content` first. If present, the agent must construct `ExtractedDocument` directly from it with `extraction_confidence = 0.95` and skip the LLM call. (This is the test-mode path.)
14. The agent must treat `quality == UNREADABLE` as an automatic `is_readable=False` outcome regardless of any other field.
15. The agent must call extraction for all documents concurrently using `asyncio.gather(..., return_exceptions=True)`.
16. The agent must use `instructor` or the Anthropic SDK's tool-use mechanism to enforce that the LLM response conforms to the `ExtractedDocument` schema. The agent must not parse free-form text.
17. The agent must set per-call timeout to 15 seconds. On timeout, the agent must return `ExtractedDocument(is_readable=False, extraction_confidence=0.0, extraction_warnings=["LLM timeout"])`.
18. The agent must allow the system to run without an `ANTHROPIC_API_KEY` set. In that case, the agent must extract from `doc.content` and fail with a clear error if `content` is missing for any document.

### 4.4 Consistency Rules

19. The agent must normalize names by: lowercasing, stripping whitespace, removing leading honorifics from this set: `["mr.", "mrs.", "ms.", "miss", "dr.", "shri", "smt."]`, collapsing multiple spaces to one.
20. The agent must compare names using `rapidfuzz.fuzz.token_set_ratio`. The threshold for "same person" is 85.
21. If only one document has a `patient_name`, the agent must compare it to `member.name`. If neither has a name, the agent must emit DEGRADED, not FAIL.
22. The halt message must list every file with its extracted name.

### 4.5 Policy Evaluation Rules

23. The agent must compute waiting periods from the member's `join_date`, NOT from `policy_holder.policy_start_date`. (Critical for TC005 where the member joined later.)
24. The agent must map diagnosis text to a specific condition using the regex map in §3.4.7. If no condition matches, `specific_waiting_period_passed = True` (no specific condition applies).
25. The agent must check the full diagnosis text AND the treatment text against `policy.exclusions.conditions`. For TC012, "Bariatric Consultation" in treatment must trigger the bariatric exclusion. The agent must match using lowercased keyword presence with the patterns in `EXCLUSION_KEYWORDS`.
26. The agent must apply line-item exclusions ONLY within DENTAL and VISION categories (the only categories with line-item exclusion lists in the policy).
27. The agent must perform substring match for excluded line items: case-insensitive, the exclusion phrase appearing anywhere in the line item description triggers exclusion. ("Teeth Whitening" in line item "Teeth Whitening" → match.)
28. The agent must check pre-authorization only for DIAGNOSTIC category. The agent must look for the high-value test name anywhere in any line item description AND must verify `item.amount > policy.opd_categories.diagnostic.pre_auth_threshold`.
29. The agent must treat `submission.pre_authorization_ref` being non-null as proof of pre-auth. (The system does not validate the reference itself in scope.)
30. The agent must perform network hospital match using normalized substring: lowercase both sides, then check if the policy hospital name is a substring of the submission hospital name OR vice versa. ("Apollo Hospitals" matches "Apollo Hospitals, Bengaluru" and "Apollo Hospitals".)

### 4.6 Financial Calculation Rules

31. The agent must apply operations in this order: (1) strip excluded line items, (2) apply network discount, (3) apply co-pay, (4) cap at sub-limit. The agent must store each intermediate value in `FinancialBreakdown` so the trace shows the full math.
32. The agent must compute the base amount as `sum(eligible_line_items)` when any line items are excluded. Otherwise, the agent must use `submission.claimed_amount` as the base.
33. The agent must apply `per_claim_limit_exceeded` as a HARD REJECT, never as a cap. If `claimed_amount > per_claim_limit`, the agent must return REJECTED with `PER_CLAIM_EXCEEDED` regardless of all other rules. (TC008.)
34. The agent must NOT exceed `policy.coverage.sum_insured_per_employee` or `policy.coverage.annual_opd_limit` when combined with `ytd_claims_amount`. If exceeded, cap at the remaining budget and add the appropriate rejection code if the result is zero.

### 4.7 Fraud Detection Rules

35. The agent must include the current submission when counting same-day and monthly claims. (`count(history same-day) + 1`.)
36. The agent must NEVER let the fraud agent set the decision to REJECTED. The fraud agent's output influences only MANUAL_REVIEW routing.
37. The agent must enumerate every triggered signal in the decision output's `fraud_signals` list. The trace must include the underlying counts/amounts.
38. The agent must route to MANUAL_REVIEW if `claimed_amount > policy.fraud_thresholds.high_value_claim_threshold` (₹25,000), independent of other fraud signals. (`auto_manual_review_above` from policy.)

### 4.8 Decision Engine Rules

39. The agent must apply decision rules in the strict order specified in §3.3 Agent 6. The first matching rule wins. The order matters: a claim that hits both `EXCLUDED_CONDITION` and `WAITING_PERIOD` must report `EXCLUDED_CONDITION` because it precedes waiting-period checks (rule #4 vs rule #6).
40. The agent must include a member-facing `reasons` array containing one human-readable sentence per code triggered.
41. The agent must always populate `financial_breakdown` for APPROVED and PARTIAL decisions. The agent may leave it null for REJECTED and MANUAL_REVIEW.
42. The agent must set `requires_manual_review = True` whenever (a) decision is MANUAL_REVIEW, OR (b) decision is APPROVED/PARTIAL but `trace.degraded_stages > 0` OR `final_confidence < 0.75`.

### 4.9 Confidence Rules

43. The agent must compute `final_confidence` as `min(confidences of successful stages) × 0.7^degraded_count`.
44. The agent must set extraction confidence as the minimum across all documents' `extraction_confidence`.
45. The agent must set policy evaluation confidence to 1.0 when all rules ran cleanly, 0.7 when run with safe defaults (TC011 path), 0.0 when not run at all.
46. The agent must force MANUAL_REVIEW when `final_confidence < 0.60`, regardless of the rules-based decision.

### 4.10 UI Rules

47. The agent must build two pages: a submission form (file upload + claim fields) and a decision view (status badge, financial breakdown, full collapsible trace).
48. The agent must render the trace as an expandable list where each event shows stage_name, status, confidence, and a "Detail" toggle that reveals the JSON `detail` field.
49. The agent must color-code statuses: PASS green, FAIL red, DEGRADED amber, SKIPPED grey.
50. The agent must show the halt message prominently for HALTED claims and hide the financial breakdown section (since none exists).

### 4.11 Testing Rules

51. The agent must write a unit test for every test case in `test_cases.json`. Each test calls `process_claim` with the test input and asserts every claim made in `expected`.
52. The agent must write unit tests for the financial calculator covering: network + non-network, full exclusion list (dental), zero co-pay (dental/vision/pharmacy), 10% co-pay (consultation), 30% branded-drug co-pay (pharmacy).
53. The agent must write unit tests for the diagnosis-to-condition mapper covering at least diabetes, hypertension, obesity, cataract, maternity, and a no-match case.
54. The agent must produce `EVAL_REPORT.md` by running `scripts/run_eval.py`. The script must POST each test case to the running app (or call `process_claim` directly) and write a Markdown table: case_id, expected_decision, actual_decision, match (✓/✗), notes.

### 4.12 Deliverable Rules

55. The agent must write `ARCHITECTURE.md` covering: overview diagram (ASCII or image), component responsibilities, data flow, failure handling philosophy, "what I considered and rejected" section, "limitations and 10x story" section.
56. The agent must write `CONTRACTS.md` containing, for each agent: name, responsibility, input schema (Pydantic), output schema, exceptions, and one example input/output pair.
57. The agent must write `README.md` covering: setup instructions, env var requirements, run commands, test commands, eval-report generation, demo walkthrough.
58. The agent must commit in logical units with descriptive messages: scaffolding, models, each agent, orchestrator, UI, tests, eval, docs.

### 4.13 Traceability Matrix

| REQ-ID | Section in Tech Spec |
|---|---|
| REQ-F01 | §3.2.2 (ClaimSubmission), §3.3 (HTTP API), §3.4.1 (Orchestrator entry) |
| REQ-F02 | §3.3 Agent 1, §3.4.2, Rule 9–12 |
| REQ-F03 | §3.3 Agent 2, §3.4.3, Rule 14, Halt message template §3.4.8 |
| REQ-F04 | §3.3 Agent 3, Rule 19–22, Halt template §3.4.8 |
| REQ-F05 | §3.3 Agent 2, §3.2.3 (ExtractedDocument), Rule 13–18 |
| REQ-F06 | §3.2.5 (ClaimDecision), §3.3 Agent 6, Rule 39–42 |
| REQ-F07 | §3.3 Agent 4, §3.4.4, §3.4.5, Rule 23–32 |
| REQ-F08 | §3.3 Agent 6 step 8, §3.4.4 step 8, Rule 33 |
| REQ-F09 | §3.4.4 steps 5–6, §3.4.7, Rule 23–24 |
| REQ-F10 | §3.4.4 steps 4 and 11, Rule 25–27 |
| REQ-F11 | §3.4.4 step 7, Rule 28–29 |
| REQ-F12 | §3.4.5, §3.4.4 step 10, Rule 30–31 |
| REQ-F13 | §3.3 Agent 5, Rule 35–38 |
| REQ-F14 | §3.2.4 (ClaimTrace), §3.4.1, Rule 8 |
| REQ-F15 | §3.4.1 (stage 4–7 try/except), §3.4.6, Rule 5, 45 |
| REQ-F16 | §3.5 (ui/), Rule 47–50 |
| REQ-F17 | §3.2 (PolicyConfig), Rule 6, 9, 23 |
| REQ-F18 | §3.5 (tests/eval/), Rule 54 |
| REQ-N01 | §3.4.1 try/except wrappers, Rule 5 |
| REQ-N02 | Rule 51–53 |
| REQ-N03 | §3.4.3, Rule 15 |
| REQ-N04 | §3.2 (all models), Rule 1 |
| REQ-N05 | §3.2.4 (Pydantic models throughout), Rule 8 |
| REQ-N06 | Rule 16 |
| REQ-N07 | Rule 18, §3.5 (README) |
| REQ-N08 | §3.4.1 (UUID generation), §3.2.5 (decided_at) |
| PRE-01 | Rule 16 |
| PRE-02 | §3.5 (utils/names.py), Rule 19–20, 30 |
| PRE-03 | §3.5 (utils/dates.py) |
| PRE-04 | §3.4.7 |
| PRE-05 | §3.4.6, Rule 43–46 |
| PRE-06 | §3.2.4, §3.4.1 |
| PRE-07 | §3.5 (llm_client.py), Rule 17–18 |
| PRE-08 | Rule 7 |

---

**End of Master Implementation Plan.**

The downstream agent must implement strictly to this document. If any requirement, ADR, or rule is ambiguous, the agent must stop and surface the ambiguity rather than guess. The financial ordering in §3.4.5 and the decision-rule ordering in §3.3 Agent 6 are particularly load-bearing — verify behavior against the test case math before committing each agent.
