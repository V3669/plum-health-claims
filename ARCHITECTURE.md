# Architecture — Plum Claims Processing System

## 1. High-Level Overview

```
                           ┌──────────────────────────────────────┐
                           │           FastAPI (main.py)          │
                           │  POST /api/claims  GET /api/claims   │
                           │  POST /submit-form  GET /ui          │
                           └──────────────┬───────────────────────┘
                                          │ ClaimSubmission
                                          ▼
                           ┌──────────────────────────────────────┐
                           │          Orchestrator                │
                           │  (orchestrator.py)                   │
                           │                                      │
                           │  ① DocVerification  ← GATE           │
                           │  ② DocExtraction    ← GATE (Gemini)  │
                           │  ③ ConsistencyCheck ← GATE           │
                           │  ④ PolicyEvaluation ← non-gate       │
                           │  ⑤ FraudDetection   ← non-gate       │
                           │  ⑥ DecisionEngine   ← non-gate       │
                           │  ⑦ NarrativeAgent   ← optional (Gemini) │
                           └──────────────┬───────────────────────┘
                                          │ ClaimDecision
                                          ▼
                           ┌──────────────────────────────────────┐
                           │         Persistence Layer            │
                           │  SQLite (claims table)               │
                           │  File store (traces/{id}.json)       │
                           └──────────────────────────────────────┘
```

## 2. Pipeline Stages

### Stage Classification

| # | Stage | Type | On Failure |
|---|-------|------|-----------|
| 1 | DocumentVerification | **GATE** | Halt → `HALTED` |
| 2 | DocumentExtraction | **GATE** (unreadable only) | Halt → `HALTED` |
| 3 | ConsistencyCheck | **GATE** (mismatch only) | Degrade on exception |
| 4 | PolicyEvaluation | **Non-gate** | Safe defaults + DEGRADED |
| 5 | FraudDetection | **Non-gate** | Zero signals + DEGRADED |
| 6 | DecisionEngine | **Non-gate** | Never fails (pure logic) |
| 7 | NarrativeAgent | **Optional** | Empty string, no trace event |

### Gate vs Non-Gate

- **Gate stages**: A failing assertion stops the pipeline. The member receives an actionable `HALTED` response explaining exactly what to fix (e.g., "re-upload document X").
- **Non-gate stages**: Exceptions are caught, logged as `DEGRADED` in the trace, conservative defaults are used, and processing continues. The final confidence score is penalised proportionally.

---

## 3. Architectural Decisions

### ADR-01: Deterministic Staged DAG (not LLM router)

**Decision:** Use a fixed, ordered pipeline of agents coordinated by a single Orchestrator.

**Why:** An LLM router adds latency (each routing step = one LLM call), produces emergent behaviour that is hard to test, and makes the trace non-deterministic. A deterministic DAG gives bounded latency, a literal execution trace, and 100% branch testability.

### ADR-02: LLM Only at Document Extraction and Narrative Boundaries

**Decision:** The Gemini LLM (`gemini-3.5-flash`) is called only in Stage 2 (DocumentExtraction) and Stage 7 (NarrativeAgent). All policy logic, fraud checks, and decision logic are pure Python.

**Why:** LLM reasoning is probabilistic and not auditable. Insurance decisions must be explainable and reproducible. Putting all business logic in Python means the system can be unit-tested exhaustively and its behaviour can be formally verified.

> **LLM backend history:** The system was initially prototyped with Anthropic Claude (`claude-sonnet-4-5`). It was migrated to Google Gemini (`gemini-3.5-flash`) — the `google-genai` SDK is used throughout. Both stages tolerate API absence — extraction falls back to structured mock data, narrative falls back to a hardcoded string.

### ADR-03: Pydantic v2 for All Inter-Agent Payloads

**Decision:** Every agent input and output is a Pydantic `BaseModel`.

**Why:** Type errors caught at the Pydantic boundary, not deep in business logic. JSON serialisability of all payloads is guaranteed by construction. Schema documentation is auto-generated.

### ADR-04: Decimal for All Monetary Values

**Decision:** `decimal.Decimal` with `ROUND_HALF_EVEN` (banker's rounding) throughout.

**Why:** IEEE 754 float cannot represent ₹0.10 exactly. A ₹5,000 per-claim limit check with floats risks ₹4999.99999... passing when it shouldn't. Decimal eliminates this class of bug entirely.

### ADR-05: Sub-limit as Annual OPD Tracking, Not Per-Claim Cap

**Decision:** `sub_limit` in `opd_categories` is stored and reported but never applied as a per-claim hard cap. The per-claim hard cap is `coverage.per_claim_limit`.

**Why:** TC010 expects ₹3,240 approved on a ₹4,500 claim where the OPD sub-limit is ₹2,000. Treating sub-limit as a per-claim cap would produce ₹2,000, which is wrong. Sub-limits track annual spend aggregates; the per-claim cap is the hard ceiling.

### ADR-06: Per-Claim Limit Only for CONSULTATION, DIAGNOSTIC, PHARMACY

**Decision:** The ₹5,000 per-claim hard cap does not apply to DENTAL, VISION, or ALTERNATIVE_MEDICINE categories.

**Why:** TC006 is a DENTAL claim for ₹12,000 which expects `PARTIAL` approval (not `REJECTED`). Dental and vision are governed by their category sub-limits and excluded-item logic, not the OPD per-claim cap.

### ADR-07: Confidence Aggregation Formula

```
confidence = min(PASS-stage confidences) × (0.7 ^ degraded_count)
```

- **min()** of PASS confidences: the weakest confident stage is the bottleneck.
- **0.7 ^ n** penalty: each degraded stage multiplies confidence by 0.7 (compounding).
- EXCLUDED_CONDITION rejections get a floor of 0.90 (categorical certainty, regardless of document quality).
- No-names ConsistencyCheck is emitted as `PASS(1.0)`, not `DEGRADED`, because absence of evidence is not evidence of mismatch.

### ADR-08: reference_date Injection for Deadline Testability

**Decision:** `Orchestrator` and `PolicyEvaluationAgent` accept an optional `reference_date: Optional[date]` parameter, defaulting to `date.today()`.

**Why:** All 12 test cases have treatment dates in Oct–Nov 2024. Running the eval today (2026) would cause every claim to fail with DEADLINE_EXCEEDED. Injecting a reference date makes the eval hermetic and reproducible.

---

## 4. Component Responsibilities

### `app/orchestrator.py` — Pipeline Coordinator
- Creates the `ClaimTrace` object (passed by reference through all stages)
- Invokes agents in sequence; handles gate vs non-gate semantics
- Owns the single authoritative confidence recomputation at the end
- Does NOT contain any policy logic

### `app/agents/doc_verification.py` — Document Verification
- Checks that uploaded document types satisfy `policy_terms.json:document_requirements[category].required`
- Pure Python; no I/O
- Returns `VerificationResult(passed, missing, message)`

### `app/agents/doc_extraction.py` — Document Extraction (Gemini)
- Calls Gemini `gemini-3.5-flash` concurrently for each document using `asyncio.gather`
- Falls back to `content` field (pre-extracted dict) or `patient_name_on_doc` when no API key
- Returns list of `ExtractedDocument` with structured fields
- Schema-validates all LLM output via JSON parsing into Pydantic

### `app/agents/consistency.py` — Cross-Document Consistency
- Extracts patient names from all documents
- Fuzzy-matches against each other and against member name (RapidFuzz token_set_ratio ≥ 85)
- "No names found" → `degraded=True` (treated as PASS, not failure)
- "Contradicting names" → `passed=False` → pipeline halts

### `app/agents/policy_evaluation.py` — Policy Rules Engine
- Evaluates all policy rules: member active, deadline, minimum amount, exclusions, waiting periods, pre-auth, per-claim limit, sub-limits, co-pay, network discount, line-item exclusions
- Reads all thresholds from `PolicyConfig` (never hardcoded)
- Returns `PolicyEvaluation` — a complete snapshot of the evaluation result

### `app/agents/fraud_detection.py` — Fraud Detection
- Evaluates same-day claims, monthly claim count, high-value threshold, fraud score
- All thresholds from `policy_terms.json:fraud_thresholds`
- Never produces REJECTED — always routes to MANUAL_REVIEW

### `app/agents/decision_engine.py` — Decision Engine
- Applies evaluation results in priority order: inactive → deadline → minimum → excluded → pre-auth → waiting period → per-claim limit → fraud → confidence → all-excluded → financial breakdown
- Computes `FinancialBreakdown` (discount → co-pay → final amount)
- Sets `requires_manual_review=True` on any degraded or low-confidence approvals

### `app/agents/narrative.py` — Narrative Generator
- Calls Gemini `gemini-3.5-flash` to generate a human-readable explanation of the decision
- Optional stage; failure produces a hardcoded fallback string without affecting the decision

### `app/llm_client.py` — LLM Client
- Module-level singleton `genai.Client` (google-genai SDK)
- Returns `None` when `GEMINI_API_KEY` is absent so callers can fall back gracefully
- Used by Stage 2 and Stage 7 only

### `app/policy_loader.py` — Policy Loader
- Loads `policy_terms.json` with file-mtime caching (re-reads if file changes)
- Never cached globally at import time (supports hot-reload in development)

### `app/persistence.py` — Persistence
- SQLite for claim decisions (idempotent: same claim_id returns first decision)
- JSON file per trace in `traces/` directory
- Idempotency guard: if `claim_id` already exists, returns immediately without overwriting

---

## 5. Data Flow

```
ClaimSubmission (Pydantic)
    │
    ├─→ VerificationResult       (doc types ok?)
    ├─→ List[ExtractedDocument]  (structured fields from Gemini or content fallback)
    ├─→ ConsistencyResult        (names match?)
    ├─→ PolicyEvaluation         (all rules evaluated)
    ├─→ FraudResult              (fraud signals + score)
    ├─→ ClaimDecision            (final decision + financial breakdown)
    │       └── narrative str    (Gemini-generated explanation or fallback)
    └─→ ClaimTrace               (ordered list of TraceEvents)
```

All payloads are Pydantic models. The `ClaimTrace` is passed by reference through the orchestrator and appended to by each stage. No agent reads from the trace (one-way data flow).

---

## 6. Failure Handling

### Early Gate Failures (Stages 1–3)
Return a `ClaimDecision` with `decision=HALTED` and a `HaltCode`. The member sees an actionable message:
- `UNKNOWN_MEMBER` → member not on policy roster
- `DOCUMENT_TYPE_MISMATCH` → wrong document types uploaded
- `DOCUMENT_UNREADABLE` → specific document cannot be read; names the file
- `PATIENT_NAME_MISMATCH` → contradicting patient names; lists both names

### Non-Gate Stage Failures (Stages 4–5)
Caught exceptions result in:
- `StageStatus.DEGRADED` appended to trace
- Conservative defaults applied (safe_default_policy_evaluation / zero-signal FraudResult)
- Confidence multiplied by 0.7 per degraded stage
- `requires_manual_review=True` set on the final decision

### Confidence-Based Safety Net
If final confidence < 0.60, the decision engine routes to `MANUAL_REVIEW` regardless of policy outcome.

---

## 7. Scalability Notes (10x Story)

At 10x load, the following changes would be made:

| Component | Change |
|---|---|
| Persistence | Replace SQLite with PostgreSQL; add connection pooling |
| Idempotency | Replace in-memory check with Redis `SETNX` |
| Document storage | Replace local `uploads/` with S3 |
| LLM extraction | Add per-member rate limiting; cache repeated identical documents |
| Policy loader | Add Redis cache with pub/sub invalidation on `policy_terms.json` update |
| Orchestrator | Run as background task queue (Celery/RQ); return `claim_id` immediately |
| Observability | OpenTelemetry traces per stage; Prometheus metrics for latency + error rate |

The core business logic (agents 1–6) requires no changes at 10x — it is stateless and horizontally scalable.
