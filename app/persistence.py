from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models.decision import ClaimDecision

_DB_PATH = Path("claims.db")
_TRACES_DIR = Path("traces")


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    _TRACES_DIR.mkdir(exist_ok=True)
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS claims (
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
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_claims_member ON claims(member_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_claims_decided ON claims(decided_at)")


def save_decision(decision: ClaimDecision, submission_json: dict) -> None:
    _TRACES_DIR.mkdir(exist_ok=True)
    trace_path = str(_TRACES_DIR / f"{decision.claim_id}.json")

    decision_dict = decision.model_dump(mode="json")
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(decision_dict, f, indent=2, default=str)

    with _db() as conn:
        existing = conn.execute(
            "SELECT claim_id FROM claims WHERE claim_id = ?", (decision.claim_id,)
        ).fetchone()
        if existing:
            return

        conn.execute(
            """INSERT INTO claims
               (claim_id, member_id, submitted_at, decided_at, decision,
                approved_amount, confidence, submission_json, decision_json, trace_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                decision.claim_id,
                submission_json.get("member_id", ""),
                datetime.now(timezone.utc).isoformat(),
                decision.decided_at.isoformat() if decision.decided_at else None,
                decision.decision.value,
                float(decision.approved_amount),
                decision.confidence_score,
                json.dumps(submission_json, default=str),
                json.dumps(decision_dict, default=str),
                trace_path,
            ),
        )


def get_decision(claim_id: str) -> Optional[ClaimDecision]:
    with _db() as conn:
        row = conn.execute(
            "SELECT decision_json FROM claims WHERE claim_id = ?", (claim_id,)
        ).fetchone()
    if row is None:
        return None
    data = json.loads(row["decision_json"])
    return ClaimDecision.model_validate(data)


def list_claims(limit: int = 50, offset: int = 0) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            """SELECT claim_id, member_id, submitted_at, decided_at, decision,
                      approved_amount, confidence
               FROM claims ORDER BY submitted_at DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]
