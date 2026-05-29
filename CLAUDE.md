# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run server (dev)
uvicorn app.main:app --reload

# Run all tests
pytest

# Run single test file
pytest tests/unit/test_fraud_detection.py -v

# Run eval suite (12 test cases from test_cases.json)
python tests/eval/run_eval.py

# Run integration tests only
pytest tests/integration/ -v
```

Environment variable setup (via `.env` file):
```bash
# Create/edit .env file in project root:
GEMINI_API_KEY=AIza...your_api_key_here...

# Get free API key from: https://aistudio.google.com
```
The system automatically loads from `.env` on startup via `python-dotenv`.

Optional override:
```bash
set POLICY_FILE=policy_terms.json  # default; override to swap policy data
```

## Architecture

Multi-agent pipeline with a single `Orchestrator` (`app/orchestrator.py`) coordinating 7 sequential stages. Stages 1–3 are **gates** (halt on failure); stages 4–7 are **non-gates** (degrade gracefully).

```
ClaimSubmission
  → DocumentVerificationAgent   [GATE]   checks right doc types uploaded
  → DocumentExtractionAgent     [GATE]   calls Gemini vision API per doc (asyncio.gather)
  → ConsistencyAgent            [GATE]   patient name cross-doc match
  → PolicyEvaluationAgent       [soft]   applies policy_terms.json rules
  → FraudDetectionAgent         [soft]   heuristic signal scoring
  → DecisionEngine              [always] produces APPROVED/PARTIAL/REJECTED/MANUAL_REVIEW
  → NarrativeAgent              [always] Gemini-generated plain-English explanation
→ ClaimDecision (persisted to SQLite via persistence.py)
```

**Key design points:**

- `Orchestrator` builds a `ClaimTrace` (list of `TraceEvent`) throughout — every stage appends a timestamped event with `status`, `confidence`, and `detail`. Final `confidence_score` on `ClaimDecision` is derived from the trace via `compute_final_confidence()`.
- LLM calls (Gemini `gemini-3.5-flash` via `google-genai` SDK) are isolated to `DocumentExtractionAgent` and `NarrativeAgent`. Both tolerate API absence — extraction falls back to structured mock data, narrative falls back to a hardcoded string. Check `has_api_key()` before assuming LLM is live. (Originally used Anthropic Claude; migrated to Gemini.)
- Policy rules are loaded from `policy_terms.json` at request time via `policy_loader.py` into typed `Policy` + `Member` Pydantic models. No hardcoded policy logic anywhere else.
- Persistence is SQLite (`claims.db`) via `app/persistence.py` — no ORM, raw `sqlite3`. `ClaimDecision` is stored as JSON blob with a few indexed columns.
- UI is HTMX + Jinja2 templates in `app/ui/templates/`. Form submission hits `/submit-form`; JSON API is at `/api/claims`.

## Models layout

```
app/models/
  enums.py         — Decision, ClaimCategory, DocumentType, HaltCode, RejectionCode, StageStatus
  submission.py    — ClaimSubmission, DocumentSubmission, HistoricalClaim
  extraction.py    — ExtractedDocument, LineItem
  decision.py      — ClaimDecision
  trace.py         — ClaimTrace, TraceEvent
  policy.py        — Policy, Member, CoverageCategory, ...
```

## Test layout

```
tests/unit/         — pure unit tests, no I/O, no LLM
tests/integration/  — orchestrator end-to-end with mock submissions
tests/eval/         — run_eval.py replays test_cases.json and prints pass/fail
```

Integration and eval tests use `DocumentSubmission.content` or `patient_name_on_doc` fields to inject pre-extracted data, bypassing actual LLM calls. This means tests pass without an API key.
