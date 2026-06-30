"""
Merger — combines fragments from multiple sources into canonical profiles.

Matching key: normalized email (primary). If no email overlap, fragments
are kept separate (safe merge policy — no false merges).

Field priority:
  CSV is preferred for: emails, phones, current company, title
  Resume is preferred for: experience, education, headline, skills
  For other fields: more complete value wins
"""

from typing import Dict, List, Any, Optional


PREFERRED_SOURCE: Dict[str, str] = {
    "emails":   "recruiter_csv",
    "phones":   "recruiter_csv",
    "experience": "resume",
    "education":  "resume",
    "skills":     "resume",
    "headline":   "resume",
}


def _emails_set(frag: Dict) -> set:
    return set(frag.get("emails") or [])


def _merge_lists_dedupe(a: List, b: List, key: str = "name") -> List:
    """Merge two lists, deduping by key field (for dicts) or value (for strings)."""
    seen = set()
    result = []
    for item in a + b:
        if isinstance(item, dict):
            k = str(item.get(key, "")).lower()
        else:
            k = str(item).lower()
        if k and k not in seen:
            seen.add(k)
            result.append(item)
    return result


def _pick_field(field: str, csv_val: Any, resume_val: Any) -> Any:
    """Pick winner for a scalar field based on source preference and completeness."""
    preferred = PREFERRED_SOURCE.get(field)

    if preferred == "recruiter_csv":
        return csv_val if csv_val else resume_val
    elif preferred == "resume":
        return resume_val if resume_val else csv_val
    else:
        # prefer more complete value
        if csv_val and resume_val:
            return csv_val if len(str(csv_val)) >= len(str(resume_val)) else resume_val
        return csv_val or resume_val


def _confidence_score(
    field: str,
    from_csv: bool,
    from_resume: bool,
    conflict: bool,
    base: float,
) -> float:
    """Assign confidence based on source coverage and corroboration."""
    if from_csv and from_resume:
        score = 0.99 if not conflict else 0.75
    elif from_csv:
        preferred = PREFERRED_SOURCE.get(field)
        score = 0.90 if preferred == "recruiter_csv" else 0.80
    elif from_resume:
        preferred = PREFERRED_SOURCE.get(field)
        score = 0.90 if preferred == "resume" else 0.75
    else:
        score = 0.50

    if conflict:
        score = max(score - 0.20, 0.30)

    return round(score, 2)


def _merge_two(csv_frag: Optional[Dict], resume_frag: Optional[Dict]) -> Dict:
    """Merge a CSV fragment and a resume fragment into one canonical profile."""
    c = csv_frag or {}
    r = resume_frag or {}

    provenance = (c.get("provenance") or []) + (r.get("provenance") or [])
    field_confidence: Dict[str, float] = {}

    profile: Dict[str, Any] = {}

    # candidate_id: prefer CSV
    profile["candidate_id"] = c.get("candidate_id") or r.get("candidate_id") or "unknown"

    # full_name
    cn, rn = c.get("full_name"), r.get("full_name")
    profile["full_name"] = _pick_field("full_name", cn, rn)
    conflict = bool(cn and rn and cn.lower() != rn.lower())
    field_confidence["full_name"] = _confidence_score(
        "full_name", bool(cn), bool(rn), conflict, 0.9
    )

    # emails — union, CSV first
    c_emails = list(c.get("emails") or [])
    r_emails = list(r.get("emails") or [])
    combined_emails = _merge_lists_dedupe(c_emails, r_emails)
    profile["emails"] = combined_emails
    field_confidence["emails"] = _confidence_score(
        "emails", bool(c_emails), bool(r_emails), False, 0.9
    )

    # phones — union, CSV first
    c_phones = list(c.get("phones") or [])
    r_phones = list(r.get("phones") or [])
    profile["phones"] = _merge_lists_dedupe(c_phones, r_phones)
    field_confidence["phones"] = _confidence_score(
        "phones", bool(c_phones), bool(r_phones), False, 0.9
    )

    # location — CSV preferred
    c_loc, r_loc = c.get("location"), r.get("location")
    profile["location"] = _pick_field("location", c_loc, r_loc)
    field_confidence["location"] = _confidence_score(
        "location", bool(c_loc), bool(r_loc), False, 0.8
    )

    # links — merge dicts
    c_links = dict(c.get("links") or {})
    r_links = dict(r.get("links") or {})
    merged_links: Dict[str, Any] = {"other": []}
    for k in set(list(c_links.keys()) + list(r_links.keys())):
        if k == "other":
            continue
        merged_links[k] = c_links.get(k) or r_links.get(k)
    merged_links["other"] = list(
        set((c_links.get("other") or []) + (r_links.get("other") or []))
    )
    profile["links"] = merged_links

    # headline — resume preferred
    c_hl, r_hl = c.get("headline"), r.get("headline")
    profile["headline"] = _pick_field("headline", c_hl, r_hl)
    field_confidence["headline"] = _confidence_score(
        "headline", bool(c_hl), bool(r_hl), False, 0.7
    )

    # years_experience — max value wins (more info)
    c_yoe = c.get("years_experience")
    r_yoe = r.get("years_experience")
    if c_yoe is not None and r_yoe is not None:
        profile["years_experience"] = max(c_yoe, r_yoe)
        field_confidence["years_experience"] = _confidence_score(
            "years_experience", True, True, abs(c_yoe - r_yoe) > 2, 0.8
        )
    else:
        profile["years_experience"] = c_yoe if c_yoe is not None else r_yoe
        field_confidence["years_experience"] = _confidence_score(
            "years_experience", c_yoe is not None, r_yoe is not None, False, 0.7
        )

    # skills — union from resume (primary) + csv
    c_skills = list(c.get("skills") or [])
    r_skills = list(r.get("skills") or [])
    profile["skills"] = _merge_lists_dedupe(r_skills + c_skills, [], key="name")
    field_confidence["skills"] = _confidence_score(
        "skills", bool(c_skills), bool(r_skills), False, 0.8
    )

    # experience — resume preferred, CSV adds current role
    c_exp = list(c.get("experience") or [])
    r_exp = list(r.get("experience") or [])
    # merge: resume entries first, then CSV entries not already present
    seen_titles = {(e.get("title") or "").lower() for e in r_exp}
    for entry in c_exp:
        t = (entry.get("title") or "").lower()
        if t and t not in seen_titles:
            r_exp.append(entry)
    profile["experience"] = r_exp or c_exp
    field_confidence["experience"] = _confidence_score(
        "experience", bool(c_exp), bool(r_exp), False, 0.85
    )

    # education — resume only
    profile["education"] = list(r.get("education") or []) or list(c.get("education") or [])
    field_confidence["education"] = _confidence_score(
        "education", False, bool(r.get("education")), False, 0.8
    )

    # provenance
    profile["provenance"] = provenance

    # overall_confidence
    scores = [v for v in field_confidence.values() if v is not None]
    profile["overall_confidence"] = round(sum(scores) / len(scores), 3) if scores else 0.5

    # Attach per-field confidence as a sub-object for transparency
    profile["_field_confidence"] = field_confidence

    return profile


def merge_fragments(fragments: List[Dict]) -> Dict[str, Dict]:
    """
    Group fragments by normalized email, merge each group.
    Returns dict: candidate_id → canonical profile.
    """
    # Separate by source
    csv_frags: Dict[str, Dict] = {}   # email → fragment
    resume_frags: Dict[str, Dict] = {}

    orphan_csv: List[Dict] = []
    orphan_resumes: List[Dict] = []

    for frag in fragments:
        source = frag.get("_source", "unknown")
        emails = frag.get("emails") or []
        if emails:
            key = emails[0]
            if source == "recruiter_csv":
                csv_frags[key] = frag
            else:
                resume_frags[key] = frag
        else:
            if source == "recruiter_csv":
                orphan_csv.append(frag)
            else:
                orphan_resumes.append(frag)

    profiles: Dict[str, Dict] = {}

    # Merge matching pairs (by email).
    # Use an order-preserving sequence instead of a set so output order is
    # deterministic: CSV rows appear in the order they were read, followed
    # by any resume-only emails not already covered by a CSV row.
    seen_emails = {}  # acts as an ordered set (dict insertion order is stable in Python 3.7+)
    for email in csv_frags:
        seen_emails[email] = None
    for email in resume_frags:
        if email not in seen_emails:
            seen_emails[email] = None

    for email in seen_emails:
        c = csv_frags.get(email)
        r = resume_frags.get(email)
        merged = _merge_two(c, r)
        profiles[merged["candidate_id"]] = merged

    # Orphans without email — merge pairs if possible, else keep separate
    for i, c in enumerate(orphan_csv):
        r = orphan_resumes[i] if i < len(orphan_resumes) else None
        merged = _merge_two(c, r)
        profiles[merged["candidate_id"]] = merged

    for i in range(len(orphan_csv), len(orphan_resumes)):
        merged = _merge_two(None, orphan_resumes[i])
        profiles[merged["candidate_id"]] = merged

    return profiles
