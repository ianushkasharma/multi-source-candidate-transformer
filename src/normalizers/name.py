"""Name normalizer — title-case, strip noise."""

import re


def normalize_name(raw: str) -> str:
    if not raw:
        return ""
    # Remove extra whitespace and non-name chars
    cleaned = re.sub(r"[^a-zA-Z\s'\-.]", "", raw.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title()
