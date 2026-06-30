# Multi-Source Candidate Data Transformer
**Eightfold Engineering Intern Assignment — Anushka Sharma (as2155@srmist.edu.in)**

Transforms structured and unstructured candidate data into deterministic, canonical JSON profiles with provenance tracking, confidence scoring, and configurable output projection.

---

## Features

- Multi-source profile aggregation (CSV + PDF/DOCX/TXT resumes)
- Deterministic candidate merging using email identity resolution
- Resume parsing with heuristic extraction
- Field-level provenance tracking
- Confidence scoring and conflict handling
- Config-driven output projection
- Gold-profile testing against hand-labeled ground truth
- Web UI and CLI support

---

## Architecture

```
Structured Sources (CSV)          Unstructured Sources (PDF/DOCX/TXT)
         │                                       │
         └──────────────┬────────────────────────┘
                        ▼
               [ Detect & Extract ]    ← CSVAdapter, ResumeAdapter
                        │
                        ▼
                  [ Normalize ]        ← E.164 phones, YYYY-MM dates, canonical skills, ISO-3166 country
                        │
                        ▼
                   [ Merge ]           ← match by email, field-level source preference, conflict detection
                        │
                        ▼
                [ Confidence ]         ← per-field scores, overall_confidence
                        │
                        ▼
                 [ Project ]           ← runtime config: field selection, rename, normalize, on_missing
                        │
                        ▼
                 [ Validate ]          ← schema check, required fields, type check
                        │
                        ▼
              Canonical JSON Profile
```

---

## Project Structure

```
multi-source-candidate-transformer/
├── src/
│   ├── adapters/          ← CSVAdapter, ResumeAdapter
│   ├── merger/            ← email-based merge, conflict resolution
│   ├── normalizers/       ← phones (E.164), dates, skills, email, name
│   ├── projector/         ← config-driven field selection and renaming
│   ├── validator/         ← schema and required-field validation
│   ├── pipeline.py        ← main entry point (CLI)
│   └── app.py             ← minimal FastAPI web UI
├── tests/
│   ├── gold/              ← hand-labeled ground-truth fixtures
│   ├── test_transformer.py
│   └── test_gold_profile.py
├── sample_inputs/         ← candidates.csv, resumes, config files
├── output/                ← produced JSON outputs (checked in)
└── README.md
```

---

## Requirements

```bash
pip install pdfplumber pypdf python-docx pytest fastapi uvicorn[standard] python-multipart
```

Python 3.10+ recommended.

---

## Run Steps (CLI)

### 1. Clone / navigate to repo

```bash
git clone https://github.com/<your-username>/multi-source-candidate-transformer.git
cd multi-source-candidate-transformer
```

### 2. Run pipeline (default output — no config)
```bash
cd src
python pipeline.py \
  --csv ../sample_inputs/candidates.csv \
  --resume ../sample_inputs/priya_resume.txt \
  --output ../output/default_output.json
```

### 3. Run with default config (field selection + confidence)
```bash
python pipeline.py \
  --csv ../sample_inputs/candidates.csv \
  --resume ../sample_inputs/priya_resume.txt \
  --config ../sample_inputs/config_default.json \
  --output ../output/config_default_output.json
```

### 4. Run with custom config (minimal fields + provenance, omit missing)
```bash
python pipeline.py \
  --csv ../sample_inputs/candidates.csv \
  --resume ../sample_inputs/priya_resume.txt \
  --config ../sample_inputs/config_custom.json \
  --output ../output/config_custom_output.json
```

### 5. Run with a real PDF resume
```bash
python pipeline.py \
  --csv ../sample_inputs/candidates.csv \
  --resume ../sample_inputs/anushka_resume.pdf \
  --output ../output/anushka_real_resume_output.json
```
This is included as a real-world correctness test, separate from the synthetic `.txt` sample — it exercises actual PDF parsing quirks (page-break artifacts, `DD/MM/YYYY` date formats, multi-section skill blocks) rather than a clean hand-written fixture.

### 6. Run tests
```bash
cd ..
python -m pytest tests/ -v
```
All 78 tests should pass — including a parametrized gold-profile comparison suite (`tests/test_gold_profile.py`) that checks extracted fields against hand-labeled ground truth for two real/realistic resumes with different layouts (`tests/gold/*.json`).

---

## Web UI

A minimal browser-based UI is included (`src/app.py`) — upload a CSV and/or resume PDF/TXT, pick a config, and view the merged JSON output directly. This calls the real `run_pipeline()` with no reimplementation.

### Run locally
```bash
cd src
uvicorn app:app --reload --port 8000
```
Open [http://localhost:8000](http://localhost:8000).

### JSON-only endpoint (curl / scripting)
```bash
curl -X POST http://localhost:8000/run.json \
  -F "csv_file=@../sample_inputs/candidates.csv" \
  -F "resume_file=@../sample_inputs/priya_resume.txt"
```

---
<img width="1918" height="858" alt="image" src="https://github.com/user-attachments/assets/2b46b878-7a6e-43d2-9b8b-1f401b951fba" />
<img width="1897" height="857" alt="image" src="https://github.com/user-attachments/assets/aa5ee329-ab64-40a6-90f5-66eae45e04ec" />
<img width="1895" height="858" alt="image" src="https://github.com/user-attachments/assets/f818de26-7404-438d-ab67-83fec41baf06" />
<img width="1891" height="853" alt="image" src="https://github.com/user-attachments/assets/99c05509-4f69-43a9-909d-126a3f79d674" />
<img width="1892" height="867" alt="image" src="https://github.com/user-attachments/assets/e3a6c81c-922a-4a22-820f-0320fc1297e4" />
<img width="1902" height="862" alt="image" src="https://github.com/user-attachments/assets/43ec2f24-5c91-436e-82a2-6b2c93d38840" />
<img width="1892" height="863" alt="image" src="https://github.com/user-attachments/assets/b76f12b1-6fc6-4469-9c2e-98f2c89d88a5" />
<img width="1890" height="862" alt="image" src="https://github.com/user-attachments/assets/eeac62c0-e0e8-42d5-a4dd-75d5ac49a6ea" />

## Gold-Profile Testing

Beyond standard unit tests, `tests/test_gold_profile.py` runs the resume adapter end-to-end against real documents and compares the extracted profile against hand-labeled ground truth, validating extraction correctness rather than merely ensuring that parsing does not fail.

Two fixtures are used specifically to stress different layouts:

| Fixture | Layout quirks exercised |
|---|---|
| `anushka_resume.pdf` | Real PDF, em-dash job separators, `DD/MM/YYYY` dates, page-break artifacts |
| `stress_test_resume_2.txt` | Comma-separated job/education lines (no em-dash), abbreviated degrees (`M.Tech`), parenthesized date ranges, different section header wording |

Gold-profile testing uncovered several extraction bugs that were subsequently fixed and protected by regression tests.

---

## Sources Covered

| Source | Type | Adapter |
|---|---|---|
| Recruiter CSV | Structured | `adapters/csv_adapter.py` |
| Resume (PDF/DOCX/TXT) | Unstructured | `adapters/resume_adapter.py` |

---

## Output Schema (default)

```json
{
  "candidate_id": "string (SHA-1 of normalized email)",
  "full_name": "string",
  "emails": ["string"],
  "phones": ["string (E.164)"],
  "location": { "name": "city", "region": "state", "country": "ISO-3166-alpha-2" },
  "links": { "linkedin": "...", "github": "...", "other": [] },
  "headline": "string | null",
  "years_experience": "number | null",
  "skills": [{ "name": "canonical", "confidence": 0.8, "sources": ["resume"] }],
  "experience": [{ "company": "...", "title": "...", "start": "YYYY-MM", "end": "YYYY-MM | null", "summary": "..." }],
  "education": [{ "institution": "...", "degree": "...", "field": "...", "end_year": "YYYY" }],
  "provenance": [{ "field": "...", "source": "...", "method": "..." }],
  "overall_confidence": 0.88
}
```

---

## Runtime Config

Pass `--config path/to/config.json`. Config can:
- **Select** a subset of output fields
- **Rename** fields (`"path": "primary_email", "from": "emails[0]"`)
- **Normalize** per-field (`"normalize": "E164"` or `"canonical"`)
- **Include/exclude** provenance and confidence
- **Handle missing values**: `"on_missing": "null" | "omit" | "error"`

The projection layer is read-only — it never mutates the canonical record.

---

## Edge Cases Handled

| Case | Behavior |
|---|---|
| Empty/unreadable resume | Returns empty fragment, no crash |
| No email in any source | Profile created with name-based ID, flagged as low-confidence |
| Duplicate CSV rows | Both retained in provenance; last value wins for fields |
| Unknown skill name | Preserved with corrected casing, 0.8 confidence |
| Conflicting values across sources | Winner picked by source preference; confidence penalized −0.20 |
| Missing config field | Handled by `on_missing` policy |
| Garbage source / malformed input | Degrades gracefully, fields set to null |
| `DD/MM/YYYY` style dates in experience | Normalized to `YYYY-MM` |
| Hyphenated PDF line-wraps in skills | Rejoined before tokenizing (`"Feature En-\ngineering"` → `"Feature Engineering"`) |
| Trailing resume sections (Leadership, Achievements, Certifications) | Correctly terminate the Skills section instead of being absorbed into it |
| PDF page-break artifacts (stray page-number lines) | Filtered out during section splitting |
| PDF icon glyphs decoded as digits (e.g. phone icon → `"131"`) | Phone normalizer strips leading garbage digits when last 10 form a valid number |
| Date ranges in Education section matched as phone numbers | Phone extraction scoped to header/contact block only |
| Output order non-deterministic across runs | Merge step preserves CSV row order; resume-only profiles appended after |
| Resume with no matching CSV email | Kept as a standalone profile rather than force-merged (safe-merge policy) |
| `years_experience` missing from resume text | Derived from earliest experience start → latest end date as a documented fallback |

---

## Known Limitations (heuristic extraction)

Section/field extraction from free-text resumes is regex-based, not ML-based, so it works well on standard layouts but has known rough edges on unusual formats:
- Location lines directly under a job title are sometimes folded into the summary text instead of being extracted as a separate field.
- `years_experience` derived from date spans uses today's date for open-ended ("Present") roles, meaning the value shifts slightly on re-runs over time — a documented tradeoff against returning `null` for every currently-employed candidate.
- "Projects" sections are currently bucketed separately and not merged into `experience` — out of scope per the design doc's exclusion of resume-section inference beyond the four canonical buckets.
- Two distinct resume layouts have been verified against hand-labeled ground truth; a sufficiently different third layout could still surface new edge cases.

These are flagged here deliberately rather than hidden, in line with the assignment's emphasis on honest scope and edge-case communication.

---

## Design Decisions

- **Email as merge key**: exact match only — no fuzzy matching to avoid false merges.
- **candidate_id**: `SHA-1(normalized_email)` — full 40-char hex digest, identical across sources for the same person, enabling deterministic merge keying.
- **CSV preferred** for contact info (emails, phones); **resume preferred** for skills, experience, education.
- **Confidence** is rule-based rather than probabilistic:
  - `0.99` → value corroborated by multiple sources
  - `0.90` → authoritative source only
  - `0.50` → single unverified source
  - `−0.20` penalty → conflicting source values
- **Output order**: CSV row order preserved, resume-only candidates appended after — deterministic across runs.
- **Deterministic**: same inputs always produce the same output.

---

## Performance

Assuming profiles are indexed by email using a hash map:

- Resume parsing: O(L), where L = resume text length
- CSV parsing: O(n), where n = number of rows
- Merge: O(n) expected time (hash-map lookup by email)
- Projection: O(f) per profile, where f = number of configured fields
- Memory: O(n) — profiles held in memory; no streaming required at the intended assignment scale

---

## Assumptions

- Email is the primary identity key.
- Recruiter CSV is the source of truth for contact data.
- GitHub/LinkedIn adapters are out of scope (noted in design doc).
- OCR for image-only PDFs is out of scope.

---

## Demo Video

[Watch the walkthrough](https://drive.google.com/file/d/1B9KsYSylwVt2rKhraCEqrE0sr1NZLysM/view?usp=sharing)

---

## Produced Output

All outputs are checked into the `output/` directory and were produced by running the commands in **Run Steps** above on the provided sample inputs:

| File | Inputs used | Config |
|---|---|---|
| `output/default_output.json` | `candidates.csv` + `priya_resume.txt` | None — raw canonical schema |
| `output/config_default_output.json` | `candidates.csv` + `priya_resume.txt` | `config_default.json` — field selection + confidence |
| `output/config_custom_output.json` | `candidates.csv` + `priya_resume.txt` | `config_custom.json` — minimal fields + provenance, omit missing |
| `output/anushka_real_resume_output.json` | `candidates.csv` + `anushka_resume.pdf` | None — real PDF correctness test |
