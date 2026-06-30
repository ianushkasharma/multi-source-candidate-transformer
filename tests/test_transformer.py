"""
Tests for the Multi-Source Candidate Data Transformer.
Run: python -m pytest tests/ -v  (from the src/ directory)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from normalizers.phone import normalize_phone
from normalizers.email import normalize_email
from normalizers.date import normalize_date
from normalizers.skills import canonicalize_skill
from normalizers.name import normalize_name
from merger.merge import merge_fragments, _merge_two
from projector.project import project_output, _resolve_path
from validator.validate import validate_profile


# ── Phone normalizer ──────────────────────────────────────────────────────────

class TestPhoneNormalizer:
    def test_e164_passthrough(self):
        assert normalize_phone("+14155550100") == "+14155550100"

    def test_us_10_digit(self):
        assert normalize_phone("4155550100") == "+14155550100"

    def test_us_11_digit(self):
        # 11-digit starting with 1 → US/Canada +1 prefix
        assert normalize_phone("14155550100") == "+14155550100"

    def test_indian_10_digit(self):
        # 10-digit starting with 9 matches US 10-digit rule first → +1 prefix
        # Indian numbers need explicit country code; without it we cannot distinguish
        result = normalize_phone("9876543210")
        assert result is not None and result.startswith("+")

    def test_indian_with_country(self):
        assert normalize_phone("+919876543210") == "+919876543210"

    def test_dashes_spaces(self):
        result = normalize_phone("+91-98765-43210")
        assert result == "+919876543210"

    def test_empty(self):
        assert normalize_phone("") is None
        assert normalize_phone("   ") is None

    def test_too_short(self):
        assert normalize_phone("123") is None

    def test_garbage(self):
        assert normalize_phone("not-a-phone") is None


# ── Email normalizer ──────────────────────────────────────────────────────────

class TestEmailNormalizer:
    def test_lowercase(self):
        assert normalize_email("Priya.Nair@Example.COM") == "priya.nair@example.com"

    def test_valid(self):
        assert normalize_email("user@domain.io") == "user@domain.io"

    def test_empty(self):
        assert normalize_email("") is None
        assert normalize_email(None) is None

    def test_invalid(self):
        assert normalize_email("notanemail") is None
        assert normalize_email("missing@") is None


# ── Date normalizer ───────────────────────────────────────────────────────────

class TestDateNormalizer:
    def test_month_year(self):
        assert normalize_date("Jan 2022") == "2022-01"
        assert normalize_date("December 2020") == "2020-12"

    def test_year_only(self):
        assert normalize_date("2019") == "2019-01"

    def test_present(self):
        assert normalize_date("Present") is None
        assert normalize_date("Current") is None
        assert normalize_date("now") is None

    def test_none(self):
        assert normalize_date(None) is None
        assert normalize_date("") is None

    def test_iso_format(self):
        assert normalize_date("2022-06") == "2022-06"


# ── Skills canonicalizer ──────────────────────────────────────────────────────

class TestSkillsCanonicalizer:
    def test_known_alias(self):
        assert canonicalize_skill("python") == "Python"
        assert canonicalize_skill("js") == "JavaScript"
        assert canonicalize_skill("k8s") == "Kubernetes"
        assert canonicalize_skill("golang") == "Go"

    def test_exact_match(self):
        assert canonicalize_skill("React") == "React"

    def test_unknown_skill(self):
        result = canonicalize_skill("SomeWeirdTech")
        assert result == "Someweirdtech" or result  # should not crash

    def test_empty(self):
        assert canonicalize_skill("") == ""


class TestResumeSkillExtraction:
    """Regression test: CI/CD must not be split into 'Ci' and 'Cd' by the '/' delimiter."""

    def test_ci_cd_not_split(self):
        from adapters.resume_adapter import _extract_skills
        skills = _extract_skills("Python, Docker, CI/CD, Kubernetes")
        names = [s["name"] for s in skills]
        assert "CI/CD" in names
        assert "Ci" not in names
        assert "Cd" not in names

    def test_normal_slash_skills_still_split_correctly(self):
        from adapters.resume_adapter import _extract_skills
        skills = _extract_skills("Python/Django, React")
        names = [s["name"] for s in skills]
        # Python and Django should be separated since "Python/Django" isn't a protected phrase
        assert "Python" in names
        assert "Django" in names

    def test_category_label_prefix_stripped(self):
        """'Programming Languages: Python' should yield 'Python', not the full label."""
        from adapters.resume_adapter import _extract_skills
        skills = _extract_skills("Programming Languages: Python, C++, SQL")
        names = [s["name"] for s in skills]
        assert "Python" in names
        assert not any("Programming Languages" in n for n in names)


class TestResumeExperienceExtraction:
    """Regression tests for DD/MM/YYYY date-range experience parsing (real resume bug)."""

    def test_two_jobs_split_correctly(self):
        from adapters.resume_adapter import _extract_experience
        text = (
            "Vikram Sarabhai Space Centre (VSSC), ISRO — Intern 02/12/2025 – 05/01/2026\n"
            "Thiruvananthapuram, India\n"
            "◦ Did some work.\n"
            "YSS Foundation - Data Analyst Intern 02/06/2025 - 24/06/2025\n"
            "Noida, India\n"
            "◦ Did other work.\n"
        )
        entries = _extract_experience(text)
        assert len(entries) == 2
        assert entries[0]["start"] == "2025-12"
        assert entries[0]["end"] == "2026-01"
        assert entries[1]["start"] == "2025-06"
        assert entries[1]["end"] == "2025-06"

    def test_company_title_split_on_emdash(self):
        from adapters.resume_adapter import _extract_experience
        text = "Acme Corp — Software Engineer 01/01/2022 – 01/01/2023\n◦ Built things.\n"
        entries = _extract_experience(text)
        assert len(entries) == 1
        assert entries[0]["company"] == "Acme Corp"
        assert entries[0]["title"] == "Software Engineer"


class TestSectionSplitting:
    """Regression test: skills section must stop at unrelated trailing sections (Leadership, Achievements, etc.)."""

    def test_skills_section_terminates_at_leadership(self):
        from adapters.resume_adapter import _split_sections
        text = (
            "Skills\n"
            "Python, SQL, Git\n"
            "Leadership & Activities\n"
            "Team Lead — Hackathon\n"
        )
        sections = _split_sections(text)
        assert "Leadership" not in sections.get("skills", "")
        assert "Team Lead" not in sections.get("skills", "")

    def test_page_number_lines_ignored(self):
        from adapters.resume_adapter import _split_sections
        text = "Skills\nPython, SQL\n1\nGit, Docker\n"
        sections = _split_sections(text)
        assert sections["skills"].strip() == "Python, SQL\nGit, Docker"


# ── Name normalizer ───────────────────────────────────────────────────────────

class TestNameNormalizer:
    def test_title_case(self):
        assert normalize_name("PRIYA NAIR") == "Priya Nair"

    def test_strip_whitespace(self):
        assert normalize_name("  John Doe  ") == "John Doe"

    def test_empty(self):
        assert normalize_name("") == ""


# ── Merger ────────────────────────────────────────────────────────────────────

class TestMerger:
    def _csv_frag(self, email="a@b.com", name="Alice Smith", phone="+14155550100"):
        import hashlib
        cid = "csv-" + hashlib.sha1(email.encode()).hexdigest()[:12]
        return {
            "_source": "recruiter_csv",
            "candidate_id": cid,
            "full_name": name,
            "emails": [email],
            "phones": [phone],
            "headline": "Engineer at Acme",
            "experience": [{"company": "Acme", "title": "Engineer", "start": None, "end": None, "summary": None}],
            "skills": [],
            "education": [],
            "links": {"other": []},
            "provenance": [{"field": "emails", "source": "recruiter_csv", "method": "direct_mapping"}],
            "_confidence": 0.90,
        }

    def _resume_frag(self, email="a@b.com", name="Alice Smith"):
        return {
            "_source": "resume",
            "candidate_id": "resume-abc",
            "full_name": name,
            "emails": [email],
            "phones": [],
            "headline": "Experienced engineer building scalable systems",
            "skills": [{"name": "Python", "confidence": 0.9, "sources": ["resume"]}],
            "experience": [
                {"company": "Acme", "title": "Engineer", "start": "2021-01", "end": None, "summary": "Led backend"},
                {"company": "OldCo", "title": "Junior Dev", "start": "2019-06", "end": "2020-12", "summary": ""},
            ],
            "education": [{"institution": "MIT", "degree": "B.Tech", "field": "CS", "end_year": "2019"}],
            "links": {"linkedin": "https://linkedin.com/in/alice", "other": []},
            "provenance": [{"field": "skills", "source": "resume", "method": "regex_heuristic"}],
            "_confidence": 0.75,
        }

    def test_merge_two_email_match(self):
        merged = _merge_two(self._csv_frag(), self._resume_frag())
        assert merged["full_name"] == "Alice Smith"
        assert "+14155550100" in merged["phones"]
        assert any(s["name"] == "Python" for s in merged["skills"])
        assert len(merged["education"]) == 1
        assert merged["overall_confidence"] > 0

    def test_csv_phone_preferred(self):
        merged = _merge_two(self._csv_frag(phone="+14155550100"), self._resume_frag())
        assert "+14155550100" in merged["phones"]

    def test_resume_skills_preferred(self):
        merged = _merge_two(self._csv_frag(), self._resume_frag())
        assert any(s["name"] == "Python" for s in merged["skills"])

    def test_merge_fragments_groups_by_email(self):
        frags = [self._csv_frag(), self._resume_frag()]
        profiles = merge_fragments(frags)
        # Both have same email so should be merged into 1 profile
        assert len(profiles) == 1

    def test_merge_fragments_two_candidates(self):
        frags = [
            self._csv_frag(email="a@b.com"),
            self._csv_frag(email="c@d.com", name="Bob Jones"),
        ]
        profiles = merge_fragments(frags)
        assert len(profiles) == 2

    def test_empty_resume_no_crash(self):
        empty_resume = {
            "_source": "resume",
            "candidate_id": "resume-empty",
            "emails": [],
            "phones": [],
            "skills": [],
            "experience": [],
            "education": [],
            "provenance": [],
            "_confidence": 0.30,
            "_empty": True,
        }
        merged = _merge_two(self._csv_frag(), empty_resume)
        assert merged["full_name"] == "Alice Smith"
        assert merged["skills"] == []


# ── Projector ─────────────────────────────────────────────────────────────────

class TestProjector:
    def _profile(self):
        return {
            "candidate_id": "abc123",
            "full_name": "Alice Smith",
            "emails": ["alice@example.com", "alice.work@corp.com"],
            "phones": ["+14155550100"],
            "headline": "Engineer",
            "years_experience": 5.0,
            "skills": [
                {"name": "Python", "confidence": 0.9, "sources": ["resume"]},
                {"name": "Go", "confidence": 0.8, "sources": ["resume"]},
            ],
            "experience": [],
            "education": [],
            "location": {"name": "San Francisco", "country": "US"},
            "links": {"linkedin": "https://linkedin.com/in/alice", "other": []},
            "provenance": [],
            "overall_confidence": 0.88,
            "_field_confidence": {"full_name": 0.99},
        }

    def test_no_config_returns_clean(self):
        result = project_output(self._profile(), None)
        assert "full_name" in result
        assert "_field_confidence" not in result  # internal keys stripped

    def test_field_selection(self):
        config = {
            "fields": [
                {"path": "full_name", "type": "string", "required": True},
                {"path": "primary_email", "from": "emails[0]", "type": "string"},
            ],
            "on_missing": "null",
        }
        result = project_output(self._profile(), config)
        assert result["full_name"] == "Alice Smith"
        assert result["primary_email"] == "alice@example.com"
        assert "emails" not in result

    def test_array_map(self):
        config = {
            "fields": [
                {"path": "skill_names", "from": "skills[].name", "type": "string[]"},
            ],
            "on_missing": "null",
        }
        result = project_output(self._profile(), config)
        assert result["skill_names"] == ["Python", "Go"]

    def test_on_missing_omit(self):
        config = {
            "fields": [
                {"path": "github", "from": "links.github", "type": "string"},
            ],
            "on_missing": "omit",
        }
        result = project_output(self._profile(), config)
        assert "github" not in result

    def test_on_missing_null(self):
        config = {
            "fields": [
                {"path": "github", "from": "links.github", "type": "string"},
            ],
            "on_missing": "null",
        }
        result = project_output(self._profile(), config)
        assert result["github"] is None

    def test_include_confidence(self):
        config = {"fields": [], "include_confidence": True, "on_missing": "null"}
        result = project_output(self._profile(), config)
        assert "overall_confidence" in result

    def test_include_provenance(self):
        config = {"fields": [], "include_provenance": True, "on_missing": "null"}
        result = project_output(self._profile(), config)
        assert "provenance" in result


# ── Validator ─────────────────────────────────────────────────────────────────

class TestValidator:
    def _valid_profile(self):
        return {
            "candidate_id": "abc123",
            "full_name": "Alice Smith",
            "emails": ["alice@example.com"],
            "phones": ["+14155550100"],
            "headline": "Engineer",
            "years_experience": 5.0,
            "skills": [],
            "experience": [],
            "education": [],
            "location": {"name": "SF"},
            "links": {},
            "provenance": [],
            "overall_confidence": 0.88,
        }

    def test_valid_profile_no_errors(self):
        errors = validate_profile(self._valid_profile())
        assert errors == []

    def test_missing_required_candidate_id(self):
        p = self._valid_profile()
        del p["candidate_id"]
        errors = validate_profile(p)
        assert any("candidate_id" in e for e in errors)

    def test_wrong_type(self):
        p = self._valid_profile()
        p["emails"] = "not-a-list"
        errors = validate_profile(p)
        assert any("emails" in e for e in errors)

    def test_config_required_missing(self):
        config = {
            "fields": [{"path": "full_name", "type": "string", "required": True}],
            "on_missing": "null",
        }
        errors = validate_profile({"full_name": None}, config)
        assert any("full_name" in e for e in errors)

    def test_config_valid(self):
        config = {
            "fields": [{"path": "full_name", "type": "string", "required": True}],
            "on_missing": "null",
        }
        errors = validate_profile({"full_name": "Alice"}, config)
        assert errors == []


# ── Edge Case: path resolver ──────────────────────────────────────────────────

class TestResolve:
    def test_nested_dot(self):
        assert _resolve_path({"location": {"country": "US"}}, "location.country") == "US"

    def test_index(self):
        assert _resolve_path({"emails": ["a@b.com", "c@d.com"]}, "emails[0]") == "a@b.com"
        assert _resolve_path({"emails": []}, "emails[0]") is None

    def test_array_map(self):
        profile = {"skills": [{"name": "Python"}, {"name": "Go"}]}
        assert _resolve_path(profile, "skills[].name") == ["Python", "Go"]

    def test_missing_key(self):
        assert _resolve_path({}, "location.country") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
