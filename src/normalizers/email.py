"""Email normalizer — lowercase + strip."""

import re
from typing import Optional

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def normalize_email(raw: str) -> Optional[str]:
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip().lower()
    if EMAIL_RE.match(cleaned):
        return cleaned
    return None
