"""
Resume Adapter — Unstructured Source
Handles PDF and DOCX resumes via text extraction + regex heuristics.
"""

import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from normalizers.phone import normalize_phone
from normalizers.email import normalize_email
from normalizers.name import normalize_name
from normalizers.date import normalize_date
from normalizers.skills import canonicalize_skill

SOURCE_NAME = "resume"


def _make_provenance(field: str, method: str = "regex_heuristic") -> Dict:
    return {"field": field, "source": SOURCE_NAME, "method": method}


def _candidate_id(email: str = "", name: str = "") -> str:
    """
    Per design doc: candidate_id = SHA-1(normalized_email).
    Falls back to a name-keyed id (flagged with a prefix) only when no email
    is available at all, since SHA-1(email) is the documented merge key and
    must be identical across sources for the same person.
    """
    if email:
        normalized = email.strip().lower()
        return hashlib.sha1(normalized.encode()).hexdigest()
    normalized = "noemail:" + name.strip().lower()
    return "noemail-" + hashlib.sha1(normalized.encode()).hexdigest()


def _extract_text_pdf(path: Path) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)
    except Exception:
        pass
    try:
        import pypdf
        reader = pypdf.PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _extract_text_docx(path: Path) -> str:
    try:
        from docx import Document
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception:
        return ""


def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_text_pdf(path)
    elif suffix in (".docx", ".doc"):
        return _extract_text_docx(path)
    # plain text fallback
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


# --- Heuristic extractors ---

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+?[\d\s\-().]{7,20})"
)
LINKEDIN_RE = re.compile(r"linkedin\.com/in/[\w\-]+", re.IGNORECASE)
GITHUB_RE = re.compile(r"github\.com/[\w\-]+", re.IGNORECASE)

YOE_RE = re.compile(
    r"(\d+)\+?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:experience|exp)",
    re.IGNORECASE,
)

SECTION_HEADERS = {
    "experience": re.compile(
        r"^(work\s+)?experience|employment|career\s+history", re.IGNORECASE
    ),
    "education": re.compile(
        r"^education|academic|qualification", re.IGNORECASE
    ),
    "skills": re.compile(
        r"^(technical\s+)?skills?|technologies|competenc", re.IGNORECASE
    ),
    "summary": re.compile(
        r"^(professional\s+)?summary|objective|profile|about", re.IGNORECASE
    ),
    "projects": re.compile(
        r"^projects?$", re.IGNORECASE
    ),
    "other": re.compile(
        r"^(leadership|activities|achievements?|certifications?|awards?|"
        r"additional\s+information|languages?\s*$|hobbies|interests|publications|"
        r"volunteer)", re.IGNORECASE
    ),
}

DATE_RANGE_RE = re.compile(
    r"("
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}"   # Month YYYY
    r"|\d{1,2}/\d{1,2}/\d{4}"                                                  # DD/MM/YYYY
    r"|\d{4}"                                                                  # bare year
    r")"
    r"\s*[-–—]\s*"
    r"("
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{4}"
    r"|\d{4}"
    r"|Present|Current|Now"
    r")",
    re.IGNORECASE,
)

# Matches a whole line containing a date range, used to find entry boundaries
DATE_RANGE_LINE_RE = re.compile(
    r"^(.*?)\s+(" + DATE_RANGE_RE.pattern + r")\s*$",
    re.IGNORECASE,
)


def _extract_emails(text: str) -> List[str]:
    found = EMAIL_RE.findall(text)
    seen, result = set(), []
    for e in found:
        n = normalize_email(e)
        if n and n not in seen:
            seen.add(n)
            result.append(n)
    return result


def _extract_phones(text: str) -> List[str]:
    found = PHONE_RE.findall(text)
    seen, result = set(), []
    for p in found:
        digits_only = re.sub(r"\D", "", p)
        # Real phone numbers run 10-15 digits (E.164 max). The loose regex
        # above also matches things like "2023 - 2027" (education date
        # ranges) and "2022 - 2023", which are 8 digits once you strip
        # spaces/hyphens — filtering on digit count throws those out
        # without needing to special-case "looks like a year range".
        if len(digits_only) < 10 or len(digits_only) > 15:
            continue
        n = normalize_phone(p.strip())
        if n and n not in seen:
            seen.add(n)
            result.append(n)
    return result


def _extract_name(lines: List[str]) -> Optional[str]:
    """Heuristic: first non-empty line that looks like a name."""
    for line in lines[:6]:
        line = line.strip()
        if not line:
            continue
        # skip lines that look like emails/phones/urls
        if "@" in line or re.search(r"\d{5,}", line) or "http" in line.lower():
            continue
        words = line.split()
        if 1 < len(words) <= 5 and all(w[0].isupper() for w in words if w):
            return normalize_name(line)
    return None


def _split_sections(text: str) -> Dict[str, str]:
    """Split resume text into named sections."""
    lines = text.splitlines()
    sections: Dict[str, List[str]] = {"header": []}
    current = "header"

    for line in lines:
        stripped = line.strip()

        # Skip standalone page-number artifacts from PDF extraction (e.g. "1", "2")
        if re.match(r"^\d{1,2}$", stripped):
            continue

        matched = False
        for sec_name, pattern in SECTION_HEADERS.items():
            if pattern.match(stripped) and len(stripped) < 60:
                current = sec_name
                matched = True
                break
        if not matched:
            sections.setdefault(current, []).append(line)

    return {k: "\n".join(v) for k, v in sections.items()}


# Known multi-token skill phrases that must not be broken by the "/" delimiter,
# checked against the raw text (case-insensitive) before generic splitting.
_SLASH_PROTECTED_SKILLS = ["CI/CD", "TCP/IP", "A/B Testing"]


def _extract_skills(skills_text: str) -> List[Dict]:
    """Extract skills from skills section."""
    result = []
    seen = set()

    # PDF text extraction sometimes preserves a hyphenated line-wrap
    # (e.g. "Feature En-\ngineering"). Rejoin those before splitting on
    # delimiters, or the trailing-hyphen strip below leaves "Feature En"
    # and "Gineering" as two separate (wrong) skill tokens. Scoped to the
    # skills text only so it doesn't affect date ranges or bullets elsewhere.
    skills_text = re.sub(r"-\s*\n\s*", "", skills_text)

    # First, pull out protected multi-token phrases so the generic splitter
    # (which treats "/" as a delimiter) doesn't fragment them.
    remaining = skills_text
    for phrase in _SLASH_PROTECTED_SKILLS:
        if re.search(re.escape(phrase), remaining, re.IGNORECASE):
            canonical = canonicalize_skill(phrase)
            if canonical.lower() not in seen:
                seen.add(canonical.lower())
                result.append({
                    "name": canonical,
                    "confidence": 0.80,
                    "sources": [SOURCE_NAME],
                })
            remaining = re.sub(re.escape(phrase), ",", remaining, flags=re.IGNORECASE)

    # Split the rest on common delimiters
    raw = re.split(r"[,|•·\n\t/]+", remaining)
    for token in raw:
        token = token.strip().strip("–-•*·")
        # Strip a leading "Category Label:" prefix (e.g. "Programming Languages: Python" -> "Python")
        if ":" in token:
            prefix, _, rest = token.partition(":")
            # Only strip if prefix looks like a category label (short, title-ish) not a real skill
            if len(prefix.split()) <= 5 and rest.strip():
                token = rest.strip()
        if not token or len(token) > 50 or len(token) < 2:
            continue
        canonical = canonicalize_skill(token)
        if canonical.lower() not in seen:
            seen.add(canonical.lower())
            result.append({
                "name": canonical,
                "confidence": 0.80,
                "sources": [SOURCE_NAME],
            })
    return result


def _extract_experience(exp_text: str) -> List[Dict]:
    """
    Extract experience entries from experience section text.

    Strategy: a line containing a date range marks the start of a new entry
    (title/company line). The text before the date range on that line is the
    title/company; the date range itself is start/end; everything after that
    line up to the next date-bearing line is location + bullet summary.
    """
    lines = [l for l in exp_text.splitlines()]
    entries: List[Dict] = []
    current: Optional[Dict] = None
    summary_lines: List[str] = []

    def flush():
        if current is not None:
            current["summary"] = " ".join(summary_lines).strip()[:500] or None
            entries.append(current)

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        date_match = DATE_RANGE_RE.search(stripped)
        if date_match:
            # New entry boundary
            flush()
            summary_lines = []

            before_date = stripped[:date_match.start()].strip()
            # Strip a trailing opening paren left over from "Title (Jul 2024 - Present)" style
            before_date = re.sub(r"\(\s*$", "", before_date).strip()
            start_raw, end_raw = date_match.group(1), date_match.group(2)

            # before_date is typically one of:
            #   "Title — Company"           (em-dash / en-dash / hyphen separated)
            #   "Title, Company, Location"  (comma separated, no dash)
            title, company = None, None
            for sep in ["—", "–", " - "]:
                if sep in before_date:
                    parts = [p.strip() for p in before_date.split(sep, 1)]
                    if len(parts) == 2:
                        company, title = parts[0], parts[1]
                        break

            if title is None and "," in before_date:
                # "Software Engineer II, Razorpay, Bangalore" -> title=first, company=second
                parts = [p.strip() for p in before_date.split(",")]
                if len(parts) >= 2:
                    title, company = parts[0], parts[1]

            if title is None:
                title = before_date or None

            current = {
                "company": company,
                "title": title,
                "start": normalize_date(start_raw),
                "end": normalize_date(end_raw),
                "summary": None,
            }
        elif current is not None:
            # Location or bullet line belonging to current entry
            # Skip a bare location-only line (no bullet marker, short, has comma) as company hint
            if current["company"] is None and "," in stripped and len(stripped) < 60 and not stripped.startswith("◦"):
                current["company"] = stripped
            else:
                summary_lines.append(stripped.lstrip("◦").strip())

    flush()
    return entries


def _extract_education(edu_text: str) -> List[Dict]:
    """Extract education entries."""
    entries = []
    lines = [l.strip() for l in edu_text.splitlines() if l.strip()]

    DEGREE_RE = re.compile(
        r"\b(B\.?Tech|B\.?E|M\.?Tech|M\.?S|M\.?Sc|B\.?Sc|MBA|Ph\.?D|Bachelor[a-z]*|Master[a-z]*|Diploma)\b",
        re.IGNORECASE,
    )
    YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

    i = 0
    while i < len(lines):
        line = lines[i]
        degree_match = DEGREE_RE.search(line)
        years_on_line = YEAR_RE.findall(line)
        # findall with a capturing group returns the group, not the full match;
        # re-extract full 4-digit years explicitly
        years_on_line = re.findall(r"\b(?:19|20)\d{2}\b", line)

        if degree_match or (i == 0):
            next_line = lines[i + 1] if i + 1 < len(lines) else None

            # Single-line format: "M.Tech, Computer Science, IIT Bombay, 2024"
            # (degree found, line has multiple comma parts, and the year is on this same line)
            if degree_match and "," in line and years_on_line:
                parts = [p.strip() for p in line.split(",")]
                # Last part is usually the year (already captured); drop it from parts
                parts_no_year = [p for p in parts if not re.fullmatch(r"(?:19|20)\d{2}", p)]
                institution = parts_no_year[-1] if len(parts_no_year) >= 2 else (next_line or line)
                degree_text = parts_no_year[0] if parts_no_year else degree_match.group()
                end_year = years_on_line[-1]

                entries.append({
                    "institution": institution,
                    "degree": degree_text,
                    "field": parts_no_year[1] if len(parts_no_year) >= 3 else None,
                    "end_year": end_year,
                })
                i += 1
                continue

            institution = next_line if next_line and not DEGREE_RE.search(next_line) else None

            # Degree text: everything from the match start up to where a year/date begins
            # (so "Bachelors Of Technology in CSE Aug 2023 – May 2027" -> "Bachelors Of Technology in CSE")
            degree_text = None
            if degree_match:
                date_start = re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4})\b", line[degree_match.start():], re.IGNORECASE)
                if date_start:
                    degree_text = line[:degree_match.start() + date_start.start()].strip()
                else:
                    degree_text = line.strip()

            # end_year: prefer the LAST year mentioned on the line (graduation year),
            # not the first (which is typically the start year)
            end_year = years_on_line[-1] if years_on_line else None
            if not end_year and i + 1 < len(lines):
                next_years = re.findall(r"\b(?:19|20)\d{2}\b", lines[i + 1])
                if next_years:
                    end_year = next_years[-1]

            entries.append({
                "institution": institution or line,
                "degree": degree_text or (degree_match.group() if degree_match else None),
                "field": None,
                "end_year": end_year,
            })
            i += 2
        else:
            i += 1

    return entries[:5]  # cap at 5


def _derive_years_experience(experience: List[Dict]) -> Optional[float]:
    """
    Fallback for when no explicit 'X years of experience' phrase is found
    in the resume text: derive it from the experience entries' date ranges
    instead of leaving years_experience null.

    Spans from the EARLIEST start date across all entries to the LATEST
    end date (an entry with end=None, i.e. "Present", uses today's date).
    This intentionally measures total career span, not summed tenure, so
    overlapping or back-to-back roles aren't double-counted.

    Caveat (documented, not hidden): using "today" for an open-ended
    "Present" role means this value technically drifts over time for the
    same input resume, in mild tension with the pipeline's determinism
    goal. We accept that tradeoff here because the alternative — leaving
    years_experience null whenever the most recent role is ongoing, which
    is the common case — would make this fallback nearly useless. If
    strict determinism is required, treat this field as "as of run time"
    rather than a frozen fact about the resume.
    """
    starts: List[tuple] = []
    ends: List[tuple] = []

    for entry in experience:
        start_raw = entry.get("start")
        if start_raw:
            ym = _parse_year_month(start_raw)
            if ym:
                starts.append(ym)

        end_raw = entry.get("end")
        if end_raw:
            ym = _parse_year_month(end_raw)
            if ym:
                ends.append(ym)
        else:
            # None means "Present" in our normalized experience entries
            today = datetime.now()
            ends.append((today.year, today.month))

    if not starts:
        return None

    earliest_start = min(starts)
    latest_end = max(ends) if ends else max(starts)

    months = (latest_end[0] - earliest_start[0]) * 12 + (latest_end[1] - earliest_start[1])
    if months < 0:
        return None

    years = round(months / 12, 1)
    return years


def _parse_year_month(date_str: str) -> Optional[tuple]:
    """Parse a normalized 'YYYY-MM' date string into (year, month) ints."""
    m = re.match(r"^(\d{4})-(\d{2})$", date_str.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


class ResumeAdapter:
    def __init__(self, path: str):
        self.path = Path(path)

    def extract(self) -> Dict[str, Any]:
        text = _extract_text(self.path)
        if not text.strip():
            # graceful degradation: empty fragment
            return {
                "_source": SOURCE_NAME,
                "candidate_id": "resume-empty",
                "provenance": [{"field": "_all", "source": SOURCE_NAME, "method": "failed_extraction"}],
                "emails": [],
                "phones": [],
                "skills": [],
                "experience": [],
                "education": [],
                "_confidence": 0.30,
                "_empty": True,
            }

        lines = text.splitlines()
        sections = _split_sections(text)

        frag: Dict[str, Any] = {
            "_source": SOURCE_NAME,
            "provenance": [],
            "skills": [],
            "experience": [],
            "education": [],
        }

        # emails
        emails = _extract_emails(text)
        frag["emails"] = emails
        if emails:
            frag["provenance"].append(_make_provenance("emails"))

        # phones — scoped to the header/contact block first. Phone numbers
        # live there in practice, and scanning the whole document risks
        # false positives like "School - 78  2022 - 2023" (which strips to
        # 10 digits and would otherwise pass the digit-count filter as a
        # plausible phone number). Falls back to the full text only if the
        # header section is empty or yields nothing, so unusual layouts
        # without a clear header still get a chance at extraction.
        header_text = sections.get("header", "")
        phones = _extract_phones(header_text) if header_text.strip() else []
        if not phones:
            phones = _extract_phones(text)
        frag["phones"] = phones
        if phones:
            frag["provenance"].append(_make_provenance("phones"))

        # candidate_id
        frag["candidate_id"] = _candidate_id(
            emails[0] if emails else "", ""
        )

        # name
        name = _extract_name(lines)
        if name:
            frag["full_name"] = name
            frag["provenance"].append(_make_provenance("full_name"))

        # links
        links: Dict[str, Any] = {"other": []}
        li = LINKEDIN_RE.search(text)
        if li:
            links["linkedin"] = "https://" + li.group()
            frag["provenance"].append(_make_provenance("links.linkedin"))
        gh = GITHUB_RE.search(text)
        if gh:
            links["github"] = "https://" + gh.group()
            frag["provenance"].append(_make_provenance("links.github"))
        frag["links"] = links

        # summary / headline
        summary_text = sections.get("summary", "").strip()
        if summary_text:
            headline = " ".join(summary_text.split()[:20])
            frag["headline"] = headline
            frag["provenance"].append(_make_provenance("headline", "section_extraction"))

        # years of experience
        yoe_match = YOE_RE.search(text)
        if yoe_match:
            frag["years_experience"] = float(yoe_match.group(1))
            frag["provenance"].append(_make_provenance("years_experience"))

        # skills
        skills_text = sections.get("skills", "")
        if skills_text:
            frag["skills"] = _extract_skills(skills_text)
            if frag["skills"]:
                frag["provenance"].append(_make_provenance("skills"))

        # experience
        exp_text = sections.get("experience", "")
        if exp_text:
            frag["experience"] = _extract_experience(exp_text)
            if frag["experience"]:
                frag["provenance"].append(_make_provenance("experience"))

        # years of experience — fallback to deriving from experience date
        # ranges only if no explicit "X years of experience" phrase matched
        if "years_experience" not in frag:
            derived_yoe = _derive_years_experience(frag["experience"])
            if derived_yoe is not None:
                frag["years_experience"] = derived_yoe
                frag["provenance"].append(
                    _make_provenance("years_experience", "derived_from_dates")
                )

        # education
        edu_text = sections.get("education", "")
        if edu_text:
            frag["education"] = _extract_education(edu_text)
            if frag["education"]:
                frag["provenance"].append(_make_provenance("education"))

        # confidence: resume is authoritative for experience/education
        frag["_confidence"] = 0.75

        return frag
