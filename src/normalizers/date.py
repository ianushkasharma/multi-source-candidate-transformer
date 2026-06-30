"""Date normalizer → YYYY-MM format."""

import re
from typing import Optional

MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

# Present/Current/Now → None (still employed)
PRESENT_RE = re.compile(r"^(present|current|now|ongoing)$", re.IGNORECASE)

# e.g. "Jan 2022", "January 2022", "Jan. 2022"
MONTH_YEAR_RE = re.compile(
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*(\d{4})",
    re.IGNORECASE,
)

# e.g. "2022", "2022-01", "01/2022", "2022/01"
YEAR_ONLY_RE = re.compile(r"^(\d{4})$")
YEAR_MONTH_RE = re.compile(r"^(\d{4})[/-](\d{1,2})$")
MONTH_YEAR_SLASH_RE = re.compile(r"^(\d{1,2})[/-](\d{4})$")
# e.g. "02/12/2025" interpreted as DD/MM/YYYY
DAY_MONTH_YEAR_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def normalize_date(raw: Optional[str]) -> Optional[str]:
    """Return YYYY-MM string, None for present/missing, or best effort."""
    if not raw:
        return None
    s = raw.strip()
    if PRESENT_RE.match(s):
        return None  # "present" → null end date

    # "Jan 2022" style
    m = MONTH_YEAR_RE.search(s)
    if m:
        month = MONTH_MAP[m.group(1).lower()[:3]]
        return f"{m.group(2)}-{month}"

    # "2022"
    m = YEAR_ONLY_RE.match(s)
    if m:
        return f"{m.group(1)}-01"

    # "2022-06" or "2022/06"
    m = YEAR_MONTH_RE.match(s)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}"

    # "02/12/2025" → DD/MM/YYYY (checked before MM/YYYY since both use "/")
    m = DAY_MONTH_YEAR_RE.match(s)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        return f"{year}-{month.zfill(2)}"

    # "06/2022"
    m = MONTH_YEAR_SLASH_RE.match(s)
    if m:
        return f"{m.group(2)}-{m.group(1).zfill(2)}"

    return None
