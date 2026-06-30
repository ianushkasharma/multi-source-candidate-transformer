"""Phone normalizer → E.164 format."""

import re
from typing import Optional


def normalize_phone(raw: str) -> Optional[str]:
    """
    Normalize a phone number to E.164 format (+<country_code><number>).
    Returns None if the input is empty or cannot be parsed.
    """
    if not raw or not raw.strip():
        return None

    # Strip everything except digits and leading +
    digits_only = re.sub(r"[^\d+]", "", raw.strip())

    if not digits_only:
        return None

    # Already has + prefix
    if digits_only.startswith("+"):
        cleaned = "+" + re.sub(r"\D", "", digits_only[1:])
        if 8 <= len(cleaned) <= 16:
            return cleaned
        return None

    # Strip leading zeros
    digits = re.sub(r"\D", "", digits_only)

    if len(digits) < 7:
        return None

    # 11-digit starting with 1: US/Canada
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"

    # 12-digit starting with 91: India
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"

    # 13-digit numbers: likely a PDF icon glyph (e.g. FontAwesome phone/mobile
    # symbol decoded as 1-3 garbage digits) prepended to a real 10-digit Indian
    # mobile number. "1318795403469" = "131" (garbled icon) + "8795403469".
    # If the last 10 digits start with 6-9 (the valid Indian mobile prefixes),
    # discard the leading garbage and treat the rest as an Indian number.
    if len(digits) == 13 and digits[-10] in "6789":
        return f"+91{digits[-10:]}"

    # 10-digit Indian mobile number (no country code). Check BEFORE the
    # generic "assume US" rule below, or every 10-digit number gets
    # mis-tagged +1 regardless of whether it's actually Indian.
    if len(digits) == 10 and digits[0] in "6789":
        return f"+91{digits}"

    # 10-digit number, doesn't look Indian: assume US (+1)
    if len(digits) == 10:
        return f"+1{digits}"

    # Fallback: prepend + and return if reasonable length
    if 8 <= len(digits) <= 15:
        return f"+{digits}"

    return None
