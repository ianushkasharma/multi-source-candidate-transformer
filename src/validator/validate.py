"""
Validator — validates a projected output record against the default schema
or a runtime config's field spec.

Returns a list of error strings. Empty list = valid.
"""

from typing import Any, Dict, List, Optional


DEFAULT_SCHEMA = {
    "candidate_id": {"type": "string", "required": True},
    "full_name": {"type": "string", "required": False},
    "emails": {"type": "list", "required": False},
    "phones": {"type": "list", "required": False},
    "location": {"type": "dict", "required": False},
    "links": {"type": "dict", "required": False},
    "headline": {"type": "string_or_null", "required": False},
    "years_experience": {"type": "number_or_null", "required": False},
    "skills": {"type": "list", "required": False},
    "experience": {"type": "list", "required": False},
    "education": {"type": "list", "required": False},
    "provenance": {"type": "list", "required": False},
    "overall_confidence": {"type": "number", "required": False},
}


def _check_type(value: Any, type_hint: str) -> bool:
    if type_hint == "string":
        return isinstance(value, str)
    if type_hint == "string_or_null":
        return value is None or isinstance(value, str)
    if type_hint == "number":
        return isinstance(value, (int, float))
    if type_hint == "number_or_null":
        return value is None or isinstance(value, (int, float))
    if type_hint == "list":
        return isinstance(value, list)
    if type_hint == "dict":
        return isinstance(value, dict)
    return True  # unknown type — skip check


def validate_profile(output: Dict, config: Optional[Dict] = None) -> List[str]:
    """
    Validate output dict. Returns list of error strings.
    Uses config field specs if provided, else DEFAULT_SCHEMA.
    """
    errors: List[str] = []

    if config and "fields" in config:
        # Validate against config schema
        for field_spec in config["fields"]:
            path = field_spec.get("path")
            required = field_spec.get("required", False)
            type_hint = field_spec.get("type", "any")

            value = output.get(path)

            if value is None:
                if required:
                    errors.append(f"Required field '{path}' is missing or null.")
            else:
                # Basic type check
                if type_hint == "string" and not isinstance(value, str):
                    errors.append(f"Field '{path}' should be string, got {type(value).__name__}.")
                elif type_hint in ("string[]", "array") and not isinstance(value, list):
                    errors.append(f"Field '{path}' should be array, got {type(value).__name__}.")
                elif type_hint == "number" and not isinstance(value, (int, float)):
                    errors.append(f"Field '{path}' should be number, got {type(value).__name__}.")
    else:
        # Validate against default schema
        for field, spec in DEFAULT_SCHEMA.items():
            value = output.get(field)
            if spec["required"] and (value is None or value == ""):
                errors.append(f"Required field '{field}' is missing.")
                continue
            if value is not None:
                if not _check_type(value, spec["type"]):
                    errors.append(
                        f"Field '{field}' has wrong type: expected {spec['type']}, "
                        f"got {type(value).__name__}."
                    )

    # Check missing_required from projector
    if "_missing_required" in output and output["_missing_required"]:
        for f in output["_missing_required"]:
            errors.append(f"Required config field '{f}' resolved to null.")

    return errors
