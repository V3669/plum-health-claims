from datetime import date
from typing import Optional

from dateutil import parser as dateutil_parser


def parse_date(value: str) -> Optional[date]:
    if not value:
        return None
    try:
        return dateutil_parser.parse(value, dayfirst=True).date()
    except (ValueError, OverflowError):
        return None
