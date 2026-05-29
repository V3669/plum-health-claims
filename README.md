# Plum Claims Processing System

A multi-agent OPD health insurance claims pipeline built with FastAPI, Pydantic v2, and Claude.

## Architecture

Seven deterministic stages coordinated by a single `Orchestrator`. Gate stages halt the pipeline early with an actionable message; non-gate stages degrade gracefully and continue with safe defaults.

```
DocumentVerification → DocumentExtraction → ConsistencyCheck   ← gate stages
  → PolicyEvaluation → FraudDetection → DecisionEngine         ← non-gate stages
  → Narrative                                                   ← optional
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions and [CONTRACTS.md](CONTRACTS.md) for per-agent input/output contracts.

---

## Prerequisites

- Python 3.11+
- An Anthropic API key (only required for real image/PDF extraction; all 12 eval cases work without one)

---

## Setup

```bash
python -m venv venv
# Windows:  venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -e ".[dev]"
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | For real images | — | Set in `.env` file (not terminal). Get free key at [aistudio.google.com](https://aistudio.google.com) |
| `POLICY_FILE` | No | `policy_terms.json` | Path to policy config |

---

## Running the Server

```bash
uvicorn app.main:app --reload
# Server: http://localhost:8000
```

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Claim submission form (UI) |
| `GET` | `/claims/{id}/view` | Decision + trace viewer (UI) |
| `GET` | `/claims` | Recent claims list (UI) |
| `POST` | `/api/claims` | Submit claim (JSON) |
| `GET` | `/api/claims/{id}` | Get decision by ID |
| `GET` | `/api/claims` | List claims (supports `limit`, `offset`) |
| `GET` | `/api/policy` | View loaded policy |
| `GET` | `/api/health` | Health check |
| `POST` | `/submit-form` | Submit claim (multipart form + file upload) |

---

## Running Tests

```bash
pytest tests/ -v          # 53 unit + integration tests — no API key needed
pytest tests/unit/        # unit tests only
pytest tests/integration/ # integration tests (mocked extraction)
python tests/eval/run_eval.py  # 12 eval scenarios → EVAL_REPORT.md
```

---

## Example API Request

```bash
curl -X POST http://localhost:8000/api/claims \
  -H "Content-Type: application/json" \
  -d '{
    "member_id": "EMP001",
    "policy_id": "PLUM_GHI_2024",
    "claim_category": "CONSULTATION",
    "treatment_date": "2024-11-01",
    "claimed_amount": "1500",
    "hospital_name": "Apollo Clinic",
    "documents": [
      {
        "file_id": "rx1",
        "actual_type": "PRESCRIPTION",
        "content": {"patient_name": "Arjun Sharma", "diagnosis": "Acute Gastritis",
                    "doctor_name": "Dr. Mehta", "date": "2024-11-01"}
      },
      {
        "file_id": "bill1",
        "actual_type": "HOSPITAL_BILL",
        "content": {"patient_name": "Arjun Sharma", "total": 1500, "date": "2024-11-01"}
      }
    ]
  }'
```

---

## Policy & Members

All rules, limits, and member data live in `policy_terms.json`.

| Rule | Value |
|---|---|
| Policy period | 2024-07-01 to 2025-06-30 |
| Initial waiting period | 30 days |
| Per-claim limit (OPD) | ₹5,000 |
| Claim submission deadline | 30 days from treatment |

Valid test member IDs: `EMP001`, `EMP002`, `EMP003`

---

## Project Structure

```
plum-assignment/
├── app/
│   ├── agents/
│   │   ├── base.py               # AgentError, SyncAgent/AsyncAgent protocols
│   │   ├── doc_verification.py   # Stage 1 — gate
│   │   ├── doc_extraction.py     # Stage 2 — gate (LLM)
│   │   ├── consistency.py        # Stage 3 — gate
│   │   ├── policy_evaluation.py  # Stage 4 — non-gate, rules engine
│   │   ├── fraud_detection.py    # Stage 5 — non-gate
│   │   ├── decision_engine.py    # Stage 6 — non-gate
│   │   └── narrative.py          # Stage 7 — optional
│   ├── models/                   # Pydantic models
│   ├── utils/                    # Shared utilities
│   ├── orchestrator.py           # Pipeline coordinator
│   ├── main.py                   # FastAPI application
│   ├── persistence.py            # SQLite + JSON trace storage
│   ├── policy_loader.py          # policy_terms.json loader with mtime cache
│   └── config.py                 # Path constants and env config
├── tests/
│   ├── unit/                     # 41 unit tests
│   ├── integration/              # 12 integration tests
│   └── eval/run_eval.py          # Eval harness → EVAL_REPORT.md
├── policy_terms.json
├── test_cases.json
├── ARCHITECTURE.md
└── CONTRACTS.md
```
