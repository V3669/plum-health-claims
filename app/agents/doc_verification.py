from typing import List, Optional

from pydantic import BaseModel

from app.agents.base import UnknownCategoryError
from app.models.policy import PolicyConfig
from app.models.submission import ClaimSubmission


class DocumentVerificationResult(BaseModel):
    passed: bool
    missing: List[str]
    unexpected: List[str]
    message: Optional[str]


class DocumentVerificationAgent:
    name = "DocumentVerification"

    def execute(self, submission: ClaimSubmission, policy: PolicyConfig) -> DocumentVerificationResult:
        category_key = submission.claim_category.value
        doc_req = policy.document_requirements.get(category_key)
        if doc_req is None:
            raise UnknownCategoryError(f"Unknown claim category: {category_key}")

        required = doc_req.required
        uploaded_types = [d.actual_type.value for d in submission.documents]

        uploaded_counts: dict[str, int] = {}
        for t in uploaded_types:
            uploaded_counts[t] = uploaded_counts.get(t, 0) + 1

        missing = [r for r in required if r not in uploaded_types]

        if missing:
            uploaded_desc = ", ".join(
                f"{count} {dtype.lower().replace('_', ' ')}(s)"
                for dtype, count in sorted(uploaded_counts.items())
            )
            required_list = ", ".join(r.lower().replace("_", " ") for r in required)
            missing_list = ", ".join(m.lower().replace("_", " ") for m in missing)
            msg = (
                f"Your {category_key.lower()} claim requires the following documents: {required_list}. "
                f"You uploaded: {uploaded_desc}. "
                f"Please upload the missing document(s): {missing_list} and resubmit. "
                f"You do not need to re-upload the documents that are already correct."
            )
            return DocumentVerificationResult(
                passed=False, missing=missing, unexpected=[], message=msg
            )

        return DocumentVerificationResult(passed=True, missing=[], unexpected=[], message=None)
