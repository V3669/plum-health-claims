# Plum Claims Processing System

A multi-agent health insurance claims processing pipeline built with FastAPI, Pydantic v2, and Claude claude-sonnet-4-5.

## System Overview

The system processes OPD health insurance claims through a 7-stage deterministic pipeline:

```
DocumentVerification → DocumentExtraction → ConsistencyCheck
  → PolicyEvaluation → FraudDetection → DecisionEngine → Narrative
```

Gate stages (1–3) can halt the pipeline early. Non-gate stages (4–7) degrade gracefully on failure and continue with safe defaults.

---

## Prerequisites

- Python 3.11+
- An **Anthropic API key** (for real document image extraction)

### Getting an Anthropic API Key

1. Visit [console.anthropic.com](https://console.anthropic.com)
2. Sign up / log in → **API Keys** → **Create Key**
3. Copy the key (shown only once)

The free tier gives $5 in credits — enough for hundreds of document extractions.

> **No API key?** The system still works for all 12 eval test cases because they supply a `content` field (pre-extracted text) or `patient_name_on_doc` directly. The LLM is only called when a real image/PDF is uploaded with no pre-supplied content.

---

## Setup

```bash
# Clone / unzip the project
cd plum-assignment

# Create virtual environment
python -m venv venv

# Activate
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

---

## Environment Variables

Create a `.env` file in the project root (or export in your shell):

```env
# Required for real document image extraction via Claude claude-sonnet-4-5
ANTHROPIC_API_KEY=sk-ant-...

# Optional overrides (defaults shown)
DATABASE_URL=sqlite:///./claims.db
TRACES_DIR=traces
UPLOADS_DIR=uploads
LOG_LEVEL=INFO
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | For real images | — | Claude API key for document extraction |
| `DATABASE_URL` | No | `sqlite:///./claims.db` | SQLite DB path |
| `TRACES_DIR` | No | `traces/` | Directory for per-claim JSON trace files |
| `UPLOADS_DIR` | No | `uploads/` | Directory for uploaded document files |
| `LOG_LEVEL` | No | `INFO` | Python logging level |

---

## Running the Server

```bash
# With .env file present:
uvicorn app.main:app --reload

# Or with key inline:
ANTHROPIC_API_KEY=sk-ant-... uvicorn app.main:app --reload
```

Server starts at **http://localhost:8000**

### UI Pages

| URL | Description |
|---|---|
| `http://localhost:8000/` | Claim submission form |
| `http://localhost:8000/claims/{claim_id}/view` | Decision + full trace viewer |

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/claims` | Submit claim (JSON) |
| `GET` | `/api/claims/{id}` | Get decision by claim ID |
| `GET` | `/api/claims` | List all claims |
| `GET` | `/api/policy` | View loaded policy config |
| `GET` | `/api/health` | Health check |
| `POST` | `/submit-form` | Submit claim (multipart form with file uploads) |

---

## Running Tests

```bash
# All unit + integration tests (53 tests, no API key needed)
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests only (uses mocked extraction, no API key needed)
pytest tests/integration/ -v

# Eval report (runs all 12 test scenarios, writes EVAL_REPORT.md)
python tests/eval/run_eval.py
```

All tests use pre-supplied `content` fields in documents — no API key required.

---

## Testing with Real Documents

To test the full end-to-end flow with actual scanned medical documents:

### Document Types Required (by claim category)

| Category | Required Documents |
|---|---|
| `CONSULTATION` | Doctor Prescription + Hospital Bill |
| `PHARMACY` | Doctor Prescription + Pharmacy Bill |
| `DIAGNOSTIC` | Doctor Prescription + Lab Report + Lab Bill |
| `DENTAL` | Hospital Bill (dental clinic invoice) |
| `VISION` | Doctor Prescription + Optical Bill |
| `ALTERNATIVE_MEDICINE` | Doctor Prescription + Hospital Bill |

### Sample Indian Medical Documents

The Claude model understands standard Indian medical document formats:

- **Doctor Prescription**: Letterhead with doctor name + MCI registration, patient name, date, Rx diagnosis + medicines
- **Hospital/Clinic Bill**: Patient name, date of service, itemized charges, GST, total
- **Lab Report**: Patient name, test name(s), values, reference ranges, lab letterhead
- **Pharmacy Bill**: Patient name, medicine names, quantities, amounts

You can use:
- Your own scanned documents (any Indian clinic/hospital)
- Sample documents from stock photo sites (search "Indian medical prescription sample")
- The `sample_documents_guide.md` file (included in the original assignment) for format guidance

### Submitting via UI

1. Start the server: `uvicorn app.main:app --reload`
2. Open `http://localhost:8000`
3. Fill in the form (member ID must be from `policy_terms.json`, e.g. `EMP001`)
4. Upload document images (JPG/PNG/PDF)
5. Submit → view decision + trace

### Submitting via API

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
        "file_name": "prescription.jpg",
        "actual_type": "PRESCRIPTION",
        "quality": "GOOD",
        "content": "Patient: John Doe. Date: 01-Nov-2024. Diagnosis: Acute Gastritis. Dr. Sharma (MCI 12345)."
      },
      {
        "file_id": "bill1",
        "file_name": "bill.jpg",
        "actual_type": "HOSPITAL_BILL",
        "quality": "GOOD",
        "content": "Patient: John Doe. Date: 01-Nov-2024. Consultation: Rs 1500. Total: Rs 1500."
      }
    ]
  }'
```

---

## Policy & Member Data

All policy rules, coverage limits, and member roster are in `policy_terms.json`. Key values:

| Rule | Value |
|---|---|
| Policy start date | 2024-07-01 |
| Initial waiting period | 30 days |
| Per-claim limit (OPD) | ₹5,000 |
| Claim submission deadline | 30 days from treatment |
| Fraud review threshold | score ≥ 0.75 |

Valid member IDs for testing: `EMP001`, `EMP002`, `EMP003` (see `policy_terms.json` for details).

---

## Eval Report

After running `python tests/eval/run_eval.py`, see `EVAL_REPORT.md` for the full results table.

Current result: **12/12 test cases pass**.

---

## Project Structure

```
plum-assignment/
├── app/
│   ├── agents/
│   │   ├── doc_verification.py   # Stage 1: gate — checks document types
│   │   ├── doc_extraction.py     # Stage 2: gate — LLM extraction
│   │   ├── consistency.py        # Stage 3: gate — cross-doc name check
│   │   ├── policy_evaluation.py  # Stage 4: non-gate — rules engine
│   │   ├── fraud_detection.py    # Stage 5: non-gate — fraud signals
│   │   ├── decision_engine.py    # Stage 6: non-gate — final decision
│   │   └── narrative.py          # Stage 7: non-gate — human explanation
│   ├── models/                   # Pydantic data models
│   ├── utils/                    # Name matching, date parsing, money, diagnosis map
│   ├── orchestrator.py           # Pipeline coordinator
│   ├── main.py                   # FastAPI app
│   ├── persistence.py            # SQLite + file trace storage
│   ├── policy_loader.py          # policy_terms.json loader with mtime cache
│   └── llm_client.py             # Anthropic async client wrapper
├── tests/
│   ├── unit/                     # 41 unit tests (no I/O)
│   ├── integration/              # 12 integration tests (full pipeline, mocked LLM)
│   └── eval/run_eval.py          # Eval harness → EVAL_REPORT.md
├── policy_terms.json             # Policy configuration + member roster
├── test_cases.json               # 12 test scenarios
├── EVAL_REPORT.md                # Generated eval results
├── ARCHITECTURE.md               # System design + decisions
└── CONTRACTS.md                  # Per-agent input/output contracts
```
