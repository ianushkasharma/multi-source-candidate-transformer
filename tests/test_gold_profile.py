"""
Gold-profile comparison test.

Runs the resume adapter against real/realistic resume files and compares the
extracted fields against hand-labeled ground-truth JSON files in tests/gold/.

This is distinct from the unit tests in test_transformer.py: those test
individual functions in isolation with synthetic inputs. This test checks
end-to-end extraction accuracy against full documents with known-correct
answers, which is what actually catches parsing bugs that synthetic unit
fixtures miss — e.g. the degree-truncation, wrong-end-year, and
section-bleed bugs originally found by running this exact comparison.

Two fixtures are used to confirm fixes generalize rather than being
overfit to one resume's specific layout:
  - anushka_resume.pdf      : real PDF, em-dash job separators, DD/MM/YYYY dates
  - stress_test_resume_2.txt: different layout — comma-separated job/education
                               lines, abbreviated degrees, parenthesized dates
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from adapters.resume_adapter import ResumeAdapter

GOLD_DIR = os.path.join(os.path.dirname(__file__), "gold")
SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "sample_inputs")

FIXTURES = [
    ("anushka_resume.pdf", "anushka_resume_gold.json"),
    ("stress_test_resume_2.txt", "rahul_resume_gold.json"),
]


def _load_gold(gold_filename):
    with open(os.path.join(GOLD_DIR, gold_filename)) as f:
        return json.load(f)


def _extract(resume_filename):
    return ResumeAdapter(os.path.join(SAMPLE_DIR, resume_filename)).extract()


@pytest.mark.parametrize("resume_filename,gold_filename", FIXTURES, ids=[f[0] for f in FIXTURES])
class TestGoldProfile:
    """Compares actual pipeline output against hand-verified ground truth, across multiple resume layouts."""

    def test_full_name(self, resume_filename, gold_filename):
        gold = _load_gold(gold_filename)
        actual = _extract(resume_filename)
        assert actual.get("full_name") == gold["full_name"]

    def test_emails(self, resume_filename, gold_filename):
        gold = _load_gold(gold_filename)
        actual = _extract(resume_filename)
        assert actual.get("emails") == gold["emails"]

    def test_phones(self, resume_filename, gold_filename):
        gold = _load_gold(gold_filename)
        actual = _extract(resume_filename)
        assert actual.get("phones") == gold["phones"]

    def test_education_count(self, resume_filename, gold_filename):
        gold = _load_gold(gold_filename)
        actual = _extract(resume_filename)
        assert len(actual.get("education", [])) == len(gold["education"])

    def test_education_institutions(self, resume_filename, gold_filename):
        gold = _load_gold(gold_filename)
        actual = _extract(resume_filename)
        actual_edu = actual.get("education", [])
        for i, gold_entry in enumerate(gold["education"]):
            assert actual_edu[i]["institution"] == gold_entry["institution"]

    def test_education_degree(self, resume_filename, gold_filename):
        """Regression test: degree was previously truncated to a single word
        (e.g. 'Bachelor') instead of the full degree phrase."""
        gold = _load_gold(gold_filename)
        actual = _extract(resume_filename)
        actual_edu = actual.get("education", [])
        for i, gold_entry in enumerate(gold["education"]):
            assert actual_edu[i]["degree"] == gold_entry["degree"]

    def test_education_end_year(self, resume_filename, gold_filename):
        """Regression test: end_year previously captured the FIRST year on the
        line (start year) instead of the LAST (graduation year)."""
        gold = _load_gold(gold_filename)
        actual = _extract(resume_filename)
        actual_edu = actual.get("education", [])
        for i, gold_entry in enumerate(gold["education"]):
            assert actual_edu[i]["end_year"] == gold_entry["end_year"]

    def test_experience_count(self, resume_filename, gold_filename):
        gold = _load_gold(gold_filename)
        actual = _extract(resume_filename)
        assert len(actual.get("experience", [])) == len(gold["experience"])

    def test_experience_companies_and_titles(self, resume_filename, gold_filename):
        """Regression test: comma-separated 'Title, Company, Location (dates)'
        format previously left company=null and a stray '(' in the title."""
        gold = _load_gold(gold_filename)
        actual = _extract(resume_filename)
        actual_exp = actual.get("experience", [])
        for i, gold_entry in enumerate(gold["experience"]):
            assert actual_exp[i]["company"] == gold_entry["company"]
            assert actual_exp[i]["title"] == gold_entry["title"]

    def test_experience_dates(self, resume_filename, gold_filename):
        gold = _load_gold(gold_filename)
        actual = _extract(resume_filename)
        actual_exp = actual.get("experience", [])
        for i, gold_entry in enumerate(gold["experience"]):
            assert actual_exp[i]["start"] == gold_entry["start"]
            assert actual_exp[i]["end"] == gold_entry["end"]

    def test_required_skills_present(self, resume_filename, gold_filename):
        gold = _load_gold(gold_filename)
        actual = _extract(resume_filename)
        actual_names = {s["name"] for s in actual.get("skills", [])}
        missing = [s for s in gold["skills_must_include"] if s not in actual_names]
        assert not missing, f"Expected skills missing from extraction: {missing}"

    def test_no_section_bleed_into_skills(self, resume_filename, gold_filename):
        """Regression test: Skills section was previously absorbing trailing
        sections (Leadership/Achievements/Certifications/category labels like
        'Languages: Go, Java' being mistaken for a section header)."""
        gold = _load_gold(gold_filename)
        actual = _extract(resume_filename)
        actual_names = {s["name"] for s in actual.get("skills", [])}
        leaked = [s for s in gold["skills_must_not_include"] if s in actual_names]
        assert not leaked, f"Unwanted content leaked into skills: {leaked}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
