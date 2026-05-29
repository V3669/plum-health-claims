from __future__ import annotations
import json
import shutil
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, List

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import UPLOAD_DIR
from app.models.decision import ClaimDecision
from app.models.enums import ClaimCategory, DocumentType
from app.models.submission import ClaimSubmission, DocumentSubmission
from app.orchestrator import Orchestrator
from app.persistence import get_decision, init_db, list_claims, save_decision
from app.policy_loader import load_policy

app = FastAPI(title="Plum Claims Processing System", version="0.1.0")

templates = Jinja2Templates(directory="app/ui/templates")

static_dir = Path("app/ui/static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

_orchestrator = Orchestrator()


@app.on_event("startup")
async def startup() -> None:
    init_db()
    UPLOAD_DIR.mkdir(exist_ok=True)
    Path("traces").mkdir(exist_ok=True)


# ── HTML UI routes ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    claims = list_claims(limit=10)
    return templates.TemplateResponse("submit.html", {
        "request": request,
        "categories": [c.value for c in ClaimCategory],
        "doc_types": [d.value for d in DocumentType if d != DocumentType.UNKNOWN],
        "recent_claims": claims,
    })


@app.get("/claims/{claim_id}/view", response_class=HTMLResponse)
async def view_claim(request: Request, claim_id: str) -> HTMLResponse:
    decision = get_decision(claim_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return templates.TemplateResponse("decision.html", {
        "request": request,
        "decision": decision,
        "trace_events": decision.trace.events,
    })


@app.get("/claims", response_class=HTMLResponse)
async def claims_list(request: Request) -> HTMLResponse:
    claims = list_claims(limit=50)
    return templates.TemplateResponse("claims_list.html", {
        "request": request,
        "claims": claims,
    })


# ── JSON API ──────────────────────────────────────────────────────────────────

@app.post("/api/claims", response_model=None)
async def submit_claim(submission: ClaimSubmission) -> JSONResponse:
    decision = await _orchestrator.process_claim(submission)
    save_decision(decision, submission.model_dump(mode="json"))
    return JSONResponse(content=_serialize(decision))


@app.get("/api/claims/{claim_id}")
async def get_claim(claim_id: str) -> JSONResponse:
    decision = get_decision(claim_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return JSONResponse(content=_serialize(decision))


@app.get("/api/claims")
async def list_claims_api(limit: int = 50, offset: int = 0) -> JSONResponse:
    return JSONResponse(content=list_claims(limit=limit, offset=offset))


@app.get("/api/policy")
async def get_policy() -> JSONResponse:
    policy = load_policy()
    return JSONResponse(content=policy.model_dump(mode="json"))


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/submit-form", response_class=HTMLResponse)
async def submit_form(
    request: Request,
    member_id: str = Form(...),
    policy_id: str = Form(...),
    claim_category: str = Form(...),
    treatment_date: str = Form(...),
    claimed_amount: str = Form(...),
    hospital_name: str = Form(""),
    pre_authorization_ref: str = Form(""),
    files: List[UploadFile] = File(default=[]),
    doc_types: List[str] = Form(default=[]),
) -> HTMLResponse:
    docs: List[DocumentSubmission] = []
    accepted = 0
    for i, f in enumerate(files):
        if not f.filename:
            accepted += 1  # keep in sync with doc_types index
            continue
        fid = str(uuid.uuid4())
        dest = UPLOAD_DIR / fid
        with open(dest, "wb") as out:
            shutil.copyfileobj(f.file, out)
        doc_type_str = doc_types[accepted] if accepted < len(doc_types) else "UNKNOWN"
        accepted += 1
        try:
            actual_type = DocumentType(doc_type_str)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown document type: '{doc_type_str}'. "
                       f"Valid types: {[t.value for t in DocumentType if t != DocumentType.UNKNOWN]}",
            )
        docs.append(DocumentSubmission(
            file_id=fid,
            file_name=f.filename,
            actual_type=actual_type,
            file_path=str(dest),
        ))

    if not docs:
        docs.append(DocumentSubmission(
            file_id="placeholder",
            actual_type=DocumentType.UNKNOWN,
        ))

    try:
        category = ClaimCategory(claim_category)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown claim category: '{claim_category}'. "
                   f"Valid categories: {[c.value for c in ClaimCategory]}",
        )

    submission = ClaimSubmission(
        member_id=member_id,
        policy_id=policy_id,
        claim_category=category,
        treatment_date=date.fromisoformat(treatment_date),
        claimed_amount=Decimal(claimed_amount),
        hospital_name=hospital_name or None,
        pre_authorization_ref=pre_authorization_ref or None,
        documents=docs,
    )

    decision = await _orchestrator.process_claim(submission)
    save_decision(decision, submission.model_dump(mode="json"))

    return templates.TemplateResponse("decision.html", {
        "request": request,
        "decision": decision,
        "trace_events": decision.trace.events,
    })


def _serialize(obj: Any) -> Any:
    if isinstance(obj, ClaimDecision):
        return json.loads(obj.model_dump_json())
    return obj
