from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import StageStatus


class TraceEvent(BaseModel):
    stage_name: str
    started_at: datetime
    finished_at: datetime
    status: StageStatus
    confidence: float
    summary: str
    detail: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class ClaimTrace(BaseModel):
    claim_id: str
    submission_summary: Dict[str, Any]
    events: List[TraceEvent] = Field(default_factory=list)
    final_confidence: float = 1.0
    degraded_stages: int = 0

    def append_event(self, event: TraceEvent) -> None:
        self.events.append(event)
        if event.status == StageStatus.DEGRADED:
            self.degraded_stages += 1
