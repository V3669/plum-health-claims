# Plum Claims Processing System

A multi-agent OPD health insurance claims pipeline built with FastAPI, Pydantic v2, and Google Gemini.

> **LLM backend history:** The system was initially prototyped with Anthropic Claude (`claude-sonnet-4-5`). It was subsequently migrated to Google Gemini (`gemini-2.5-flash`) for document extraction (Stage 2) and narrative generation (Stage 7). All business logic (Stages 1, 3–6) remains pure Python with no LLM dependency.

## Architecture

Seven deterministic stages coordinated by a single `Orchestrator`. Gate stages halt the pipeline early with an actionable message; non-gate stages degrade gracefully and continue with safe defaults.

```
DocumentVerification → DocumentExtraction → ConsistencyCheck   ← gate stages
  → PolicyEvaluation → FraudDetection → DecisionEngine         ← non-gate stages
  → Narrative                                                   ← optional (Gemini)
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions and [CONTRACTS.md](CONTRACTS.md) for per-agent input/output contracts.

---

## Prerequisites

- Python 3.11+
- A Google Gemini API key (only required for real image/PDF extraction; all 12 eval cases work without one — they use pre-supplied `content` fields)

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
| `GEMINI_API_KEY` | For real images/PDFs | — | Set in `.env` file (not terminal). Get free key at [aistudio.google.com](https://aistudio.google.com) |
| `POLICY_FILE` | No | `policy_terms.json` | Path to policy config |

Create a `.env` file in the project root:

```bash
GEMINI_API_KEY=AIza...your_key_here...
```

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

## Using the UI

After running the server, open **http://localhost:8000** in your browser.

### What you can upload

The UI accepts real scanned documents or photos. Each claim type requires specific document types:

| Claim Type | Required Documents |
|---|---|
| **CONSULTATION** | Prescription (doctor's Rx) + Hospital/Clinic Bill |
| **DIAGNOSTIC** | Lab Report + Hospital Bill (+ pre-authorization ref for MRI/CT) |
| **PHARMACY** | Prescription + Pharmacy Bill |
| **DENTAL** | Dental Prescription + Dental Bill |
| **VISION** | Eye Prescription + Optician/Hospital Bill |
| **ALTERNATIVE_MEDICINE** | Prescription + Bill |

### Supported file formats

`.jpg`, `.jpeg`, `.png`, `.pdf`, `.webp`, `.gif`, `.tiff`

### Demo flow

1. Go to `http://localhost:8000`
2. Fill in **Member ID** (use `EMP001`, `EMP002`, or `EMP003`)
3. Set **Policy ID** to `PLUM_GHI_2024`
4. Choose a **Claim Category** (e.g., CONSULTATION)
5. Set **Treatment Date** within the policy period (`2024-07-01` to `2025-06-30`)
6. Enter **Claimed Amount** in ₹
7. Upload document files and select each document's type from the dropdown
8. Click **Submit** — the system calls Gemini to extract text from your images/PDFs
9. The decision page shows: outcome (APPROVED/PARTIAL/REJECTED/MANUAL_REVIEW), financial breakdown, and a full pipeline trace

### Generating demo documents with Gemini

You can ask Gemini (or ChatGPT) to generate sample Indian medical documents as text, then convert them to PDF/image:

**Consultation claim demo:**
```
Generate a realistic Indian doctor's prescription for:
- Patient: Arjun Sharma, 35M
- Doctor: Dr. Meena Pillai, MBBS MD (Internal Medicine), Reg: KA/45678/2015
- Clinic: Apollo Clinic, MG Road, Bengaluru
- Date: 2024-11-01
- Diagnosis: Acute Gastritis
- Medicines: Pantoprazole 40mg 1-0-1 x 7 days, Domperidone 10mg 0-0-1 x 5 days
Format as plain text suitable for printing.
```

Then generate the matching bill:
```
Generate a clinic bill for the same visit:
- Total: ₹1500 (Consultation ₹500 + Medicines ₹1000)
- Same patient and date as above
```

Paste each into a text file, convert to PDF (many online tools or `wkhtmltopdf`), and upload.

---

## Running Tests

```bash
pytest tests/ -v                       # 53 unit + integration tests — no API key needed
pytest tests/unit/                     # unit tests only
pytest tests/integration/              # integration tests (mocked extraction)
python tests/eval/run_eval.py          # 12 eval scenarios → EVAL_REPORT.md
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

Pass `"content": {...}` to inject pre-extracted data (no API key needed). Omit `content` and set `file_path` to have Gemini extract from a real file.

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
│   │   ├── doc_extraction.py     # Stage 2 — gate (Gemini vision)
│   │   ├── consistency.py        # Stage 3 — gate
│   │   ├── policy_evaluation.py  # Stage 4 — non-gate, rules engine
│   │   ├── fraud_detection.py    # Stage 5 — non-gate
│   │   ├── decision_engine.py    # Stage 6 — non-gate
│   │   └── narrative.py          # Stage 7 — optional (Gemini text)
│   ├── models/                   # Pydantic models
│   ├── utils/                    # Shared utilities
│   ├── llm_client.py             # Google Gemini client singleton
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
