from typing import Dict, List, Optional

from pydantic import BaseModel

from app.models.extraction import ExtractedDocument
from app.utils.names import normalize_name, names_match


class ConsistencyResult(BaseModel):
    passed: bool
    patient_names_by_file: Dict[str, str]
    message: Optional[str]
    degraded: bool = False


class ConsistencyAgent:
    name = "ConsistencyCheck"

    def execute(
        self,
        extracted: List[ExtractedDocument],
        member_name: str,
    ) -> ConsistencyResult:
        names_by_file: Dict[str, str] = {}
        for doc in extracted:
            if doc.patient_name:
                names_by_file[doc.file_id] = doc.patient_name

        if not names_by_file:
            return ConsistencyResult(
                passed=True,
                patient_names_by_file={},
                message=None,
                degraded=True,
            )

        normalized_names = {fid: normalize_name(name) for fid, name in names_by_file.items()}
        unique_normalized = set(normalized_names.values())

        if len(unique_normalized) > 1:
            names_list = list(normalized_names.items())
            conflicts = self._find_conflicts(names_list)
            if conflicts:
                pairs = "; ".join(
                    f"'{raw}' on file '{fid}'"
                    for fid, raw in names_by_file.items()
                )
                msg = (
                    "The documents in this claim appear to belong to different patients. "
                    f"We found: {pairs}. "
                    "Please verify the documents and resubmit with documents belonging to the same patient."
                )
                return ConsistencyResult(
                    passed=False,
                    patient_names_by_file=names_by_file,
                    message=msg,
                )

        first_name = next(iter(names_by_file.values()))
        if not names_match(first_name, member_name):
            pairs = "; ".join(
                f"'{raw}' on file '{fid}'"
                for fid, raw in names_by_file.items()
            )
            msg = (
                f"The patient name on the documents ({first_name}) does not match "
                f"the insured member name ({member_name}). "
                f"Found: {pairs}. "
                "Please verify and resubmit."
            )
            return ConsistencyResult(
                passed=False,
                patient_names_by_file=names_by_file,
                message=msg,
            )

        return ConsistencyResult(
            passed=True,
            patient_names_by_file=names_by_file,
            message=None,
        )

    def _find_conflicts(self, names_list: list) -> bool:
        from app.utils.names import names_match
        for i in range(len(names_list)):
            for j in range(i + 1, len(names_list)):
                if not names_match(names_list[i][1], names_list[j][1]):
                    return True
        return False
