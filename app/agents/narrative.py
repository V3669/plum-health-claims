from __future__ import annotations
import asyncio

from google.genai import types

from app.llm_client import get_client
from app.models.decision import ClaimDecision

_NARRATIVE_MODEL = "gemini-2.0-flash"


class NarrativeAgent:
    name = "Narrative"

    async def execute(self, decision: ClaimDecision) -> str:
        client = get_client()
        if client is None:
            return self._fallback_narrative(decision)

        prompt = (
            f"Write a 2-4 sentence plain-English summary for this insurance claim decision.\n"
            f"Decision: {decision.decision.value}\n"
            f"Approved amount: ₹{decision.approved_amount}\n"
            f"Reasons: {'; '.join(decision.reasons)}\n"
            f"Confidence: {decision.confidence_score:.0%}\n"
            "Write from the perspective of the insurance system explaining the outcome to the member."
        )
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=_NARRATIVE_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(max_output_tokens=200),
                ),
                timeout=10.0,
            )
            return (response.text or "").strip()
        except Exception:
            return self._fallback_narrative(decision)

    def _fallback_narrative(self, decision: ClaimDecision) -> str:
        d = decision.decision.value
        amount = decision.approved_amount
        if d == "APPROVED":
            return f"Your claim has been approved for ₹{amount}. The amount will be processed shortly."
        elif d == "PARTIAL":
            return (
                f"Your claim has been partially approved for ₹{amount}. "
                "Some line items were excluded per your policy terms."
            )
        elif d == "REJECTED":
            reason = decision.reasons[0] if decision.reasons else "policy terms not met"
            return f"Your claim has been rejected. Reason: {reason}"
        elif d == "MANUAL_REVIEW":
            return "Your claim has been flagged for manual review. Our team will contact you shortly."
        else:
            return "Your claim is being processed."
