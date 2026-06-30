"""
CSV Adapter — Structured Source
Reads recruiter CSV export and produces canonical partial fragments.
Expected columns (flexible, extra columns tolerated):
  name/full_name, email, phone, current_company, title, linkedin, github
"""

import csv
import hashlib
from pathlib import Path
from typing import List, Dict, Any

from normalizers.phone import normalize_phone
from normalizers.email import normalize_email
from normalizers.name import normalize_name


SOURCE_NAME = "recruiter_csv"

# Column name aliases → canonical field
COLUMN_MAP = {
    # name
    "name": "full_name",
    "full_name": "full_name",
    "candidate_name": "full_name",
    # email
    "email": "email",
    "email_address": "email",
    # phone
    "phone": "phone",
    "phone_number": "phone",
    "mobile": "phone",
    # company
    "current_company": "current_company",
    "company": "current_company",
    "employer": "current_company",
    # title
    "title": "title",
    "job_title": "title",
    "position": "title",
    # links
    "linkedin": "linkedin",
    "linkedin_url": "linkedin",
    "github": "github",
    "github_url": "github",
    "portfolio": "portfolio",
    # location
    "location": "location",
    "city": "city",
    "country": "country",
    # headline
    "headline": "headline",
    "summary": "headline",
    # years_experience
    "years_experience": "years_experience",
    "experience_years": "years_experience",
    "yoe": "years_experience",
}


def _make_provenance(field: str, method: str = "direct_mapping") -> Dict:
    return {"field": field, "source": SOURCE_NAME, "method": method}


def _candidate_id(email: str = "", name: str = "") -> str:
    """
    Per design doc: candidate_id = SHA-1(normalized_email).
    Must match resume_adapter._candidate_id exactly, since this is the key
    the merge step uses to recognize the same person across sources.
    """
    if email:
        normalized = email.strip().lower()
        return hashlib.sha1(normalized.encode()).hexdigest()
    normalized = "noemail:" + name.strip().lower()
    return "noemail-" + hashlib.sha1(normalized.encode()).hexdigest()


class CSVAdapter:
    def __init__(self, path: str):
        self.path = Path(path)

    def extract(self) -> List[Dict[str, Any]]:
        """Return one fragment dict per CSV row."""
        fragments = []
        with open(self.path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                fragment = self._row_to_fragment(row)
                if fragment:
                    fragments.append(fragment)
        return fragments

    def _row_to_fragment(self, row: Dict[str, str]) -> Dict[str, Any]:
        # Normalize column keys
        normalized_row: Dict[str, str] = {}
        for raw_col, value in row.items():
            key = raw_col.strip().lower().replace(" ", "_")
            canonical = COLUMN_MAP.get(key)
            if canonical:
                normalized_row[canonical] = value.strip() if value else ""

        frag: Dict[str, Any] = {
            "_source": SOURCE_NAME,
            "provenance": [],
        }

        # full_name
        raw_name = normalized_row.get("full_name", "")
        if raw_name:
            frag["full_name"] = normalize_name(raw_name)
            frag["provenance"].append(_make_provenance("full_name"))

        # emails
        raw_email = normalized_row.get("email", "")
        norm_email = normalize_email(raw_email)
        frag["emails"] = [norm_email] if norm_email else []
        if norm_email:
            frag["provenance"].append(_make_provenance("emails"))

        # phones
        raw_phone = normalized_row.get("phone", "")
        norm_phone = normalize_phone(raw_phone)
        frag["phones"] = [norm_phone] if norm_phone else []
        if norm_phone:
            frag["provenance"].append(_make_provenance("phones"))

        # candidate_id
        frag["candidate_id"] = _candidate_id(norm_email, frag.get("full_name", ""))

        # links
        links: Dict[str, Any] = {"other": []}
        for link_field in ("linkedin", "github", "portfolio"):
            val = normalized_row.get(link_field, "")
            if val:
                links[link_field] = val
                frag["provenance"].append(_make_provenance(f"links.{link_field}"))
        frag["links"] = links

        # location
        loc: Dict[str, Any] = {}
        if normalized_row.get("city"):
            loc["name"] = normalized_row["city"]
        if normalized_row.get("country"):
            loc["country"] = normalized_row["country"].upper()[:2]
        if normalized_row.get("location"):
            parts = [p.strip() for p in normalized_row["location"].split(",")]
            loc["name"] = parts[0]
            if len(parts) >= 2:
                loc["region"] = parts[1]
            if len(parts) >= 3:
                loc["country"] = parts[2].upper()[:2]
        if loc:
            frag["location"] = loc
            frag["provenance"].append(_make_provenance("location"))

        # headline (from title + company)
        title = normalized_row.get("title", "")
        company = normalized_row.get("current_company", "")
        if title or company:
            headline_parts = [x for x in [title, company] if x]
            frag["headline"] = " at ".join(headline_parts)
            frag["provenance"].append(_make_provenance("headline", "derived"))

        # experience entry from CSV
        if title or company:
            frag["experience"] = [
                {
                    "company": company or None,
                    "title": title or None,
                    "start": None,
                    "end": None,
                    "summary": None,
                }
            ]
            frag["provenance"].append(_make_provenance("experience"))

        # years_experience
        raw_yoe = normalized_row.get("years_experience", "")
        if raw_yoe:
            try:
                frag["years_experience"] = float(raw_yoe)
                frag["provenance"].append(_make_provenance("years_experience"))
            except ValueError:
                pass

        # skills (if CSV has a skills column)
        # Not standard but handle gracefully
        frag["skills"] = []
        frag["education"] = []

        # confidence: CSV is authoritative for contact info
        frag["_confidence"] = 0.90

        return frag
