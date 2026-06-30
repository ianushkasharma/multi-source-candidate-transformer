"""
Projector — applies runtime config to the canonical profile.

The projection layer is read-only: it reshapes output without mutating
the canonical record. Clean separation between internal model and API output.

Config schema:
{
  "fields": [
    { "path": "full_name", "type": "string", "required": true },
    { "path": "primary_email", "from": "emails[0]", "type": "string" },
    { "path": "phone", "from": "phones[0]", "normalize": "E164" },
    { "path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical" }
  ],
  "include_confidence": true,
  "include_provenance": false,
  "on_missing": "null"   // "null" | "omit" | "error"
}
"""

import re
from typing import Any, Dict, List, Optional

from normalizers.phone import normalize_phone
from normalizers.skills import canonicalize_skill


def _resolve_path(profile: Dict, path: str) -> Any:
    """
    Resolve a dot-path with optional array indexing.
    Supports: "emails[0]", "skills[].name", "location.country"
    """
    # Array-map shorthand: "skills[].name"
    arr_map = re.match(r"^(\w+)\[\]\.(.+)$", path)
    if arr_map:
        arr_key, sub_key = arr_map.group(1), arr_map.group(2)
        arr = profile.get(arr_key) or []
        return [_resolve_path(item, sub_key) for item in arr if isinstance(item, dict)]

    # Indexed: "emails[0]"
    idx_match = re.match(r"^(\w+)\[(\d+)\]$", path)
    if idx_match:
        key, idx = idx_match.group(1), int(idx_match.group(2))
        arr = profile.get(key) or []
        return arr[idx] if idx < len(arr) else None

    # Dot path: "location.country"
    parts = path.split(".")
    val = profile
    for part in parts:
        if not isinstance(val, dict):
            return None
        val = val.get(part)
    return val


def _apply_normalization(value: Any, normalize: Optional[str]) -> Any:
    if not normalize or value is None:
        return value
    norm = normalize.upper()
    if norm == "E164":
        if isinstance(value, list):
            return [normalize_phone(v) for v in value]
        return normalize_phone(str(value))
    elif norm == "CANONICAL":
        if isinstance(value, list):
            return [canonicalize_skill(v) for v in value]
        return canonicalize_skill(str(value))
    return value


def _cast_type(value: Any, type_hint: Optional[str]) -> Any:
    if value is None or not type_hint:
        return value
    t = type_hint.lower()
    if t == "string":
        return str(value) if value is not None else None
    if t in ("string[]", "array"):
        if isinstance(value, list):
            return [str(v) for v in value if v is not None]
        return [str(value)]
    if t == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return value


def project_output(profile: Dict, config: Optional[Dict] = None) -> Dict:
    """
    Apply config projection to canonical profile.
    If no config, return the canonical profile directly (minus internal keys).
    """
    # Strip internal keys
    clean = {k: v for k, v in profile.items() if not k.startswith("_")}

    if not config:
        return clean

    output: Dict[str, Any] = {}
    on_missing = config.get("on_missing", "null")
    include_confidence = config.get("include_confidence", False)
    include_provenance = config.get("include_provenance", False)

    fields: List[Dict] = config.get("fields", [])
    missing_required: List[str] = []

    for field_spec in fields:
        out_path = field_spec.get("path")
        from_path = field_spec.get("from", out_path)  # default: same as output path
        normalize = field_spec.get("normalize")
        type_hint = field_spec.get("type")
        required = field_spec.get("required", False)

        value = _resolve_path(profile, from_path)
        value = _apply_normalization(value, normalize)
        value = _cast_type(value, type_hint)

        if value is None or value == [] or value == "":
            if required:
                missing_required.append(out_path)
            if on_missing == "omit":
                continue
            elif on_missing == "error":
                output[out_path] = f"__MISSING__{out_path}"
                continue
            else:  # "null"
                output[out_path] = None
        else:
            output[out_path] = value

    if missing_required:
        output["_missing_required"] = missing_required

    if include_confidence:
        output["overall_confidence"] = profile.get("overall_confidence")
        output["_field_confidence"] = profile.get("_field_confidence")

    if include_provenance:
        output["provenance"] = profile.get("provenance", [])

    return output
