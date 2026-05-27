from datetime import datetime, timezone
from app.agents.decision_engine import compute_final_confidence as _compute_final_confidence
from app.models.enums import StageStatus
from app.models.trace import ClaimTrace, TraceEvent


def _ev(status, conf, name="Stage"):
    now = datetime.now(timezone.utc)
    return TraceEvent(
        stage_name=name, started_at=now, finished_at=now,
        status=status, confidence=conf, summary="test"
    )


def make_trace(events, degraded=0):
    t = ClaimTrace(claim_id="test", submission_summary={})
    t.events = events
    t.degraded_stages = degraded
    return t


def test_all_pass_full_confidence():
    trace = make_trace([_ev(StageStatus.PASS, 1.0), _ev(StageStatus.PASS, 0.95)])
    assert _compute_final_confidence(trace) == 0.95


def test_one_degraded_stage():
    trace = make_trace([_ev(StageStatus.PASS, 1.0), _ev(StageStatus.DEGRADED, 0.7)], degraded=1)
    conf = _compute_final_confidence(trace)
    assert conf == round(1.0 * (0.7 ** 1), 4)


def test_two_degraded_stages():
    trace = make_trace(
        [_ev(StageStatus.PASS, 1.0), _ev(StageStatus.DEGRADED, 0.7), _ev(StageStatus.DEGRADED, 0.7)],
        degraded=2
    )
    conf = _compute_final_confidence(trace)
    assert conf == round(1.0 * (0.7 ** 2), 4)


def test_no_pass_events():
    trace = make_trace([_ev(StageStatus.DEGRADED, 0.7)], degraded=1)
    conf = _compute_final_confidence(trace)
    assert conf == 0.5


def test_min_confidence_used():
    trace = make_trace([_ev(StageStatus.PASS, 0.9), _ev(StageStatus.PASS, 0.6)])
    assert _compute_final_confidence(trace) == 0.6
