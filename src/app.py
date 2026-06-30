"""
Minimal web UI for the Multi-Source Candidate Data Transformer.

Wraps the real `run_pipeline()` from pipeline.py — no reimplementation,
no mock data. Upload a CSV and/or a resume (PDF/DOCX/TXT), optionally pick
or upload a runtime config, and this calls your actual pipeline and shows
the JSON it produces.

Run from the same directory as pipeline.py:

    pip install fastapi uvicorn python-multipart
    uvicorn app:app --reload --port 8000

Then open http://localhost:8000
"""

import json
import shutil
import tempfile
import traceback
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse

from pipeline import run_pipeline

app = FastAPI(title="Candidate Data Transformer UI")

BASE_DIR = Path(__file__).parent
SAMPLE_DIR = BASE_DIR.parent / "sample_inputs"  # adjust if your layout differs

# Built-in config presets, used only if the user doesn't upload their own config file.
PRESET_CONFIGS = {
    "none": None,
    "default": SAMPLE_DIR / "config_default.json",
    "custom": SAMPLE_DIR / "config_custom.json",
}


PAGE_HEAD = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Candidate Data Transformer</title>
<style>
  :root {
    --bg: #0f1115;
    --panel: #161922;
    --border: #262b36;
    --text: #e7e9ee;
    --muted: #8b91a0;
    --accent: #4fd1c5;
    --danger: #e5534b;
    --warning: #e8a33d;
  }
  * { box-sizing: border-box; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Arial, sans-serif;
    margin: 0;
    padding: 2.5rem 1.5rem 4rem;
  }
  .wrap { max-width: 880px; margin: 0 auto; }
  h1 { font-size: 1.4rem; font-weight: 600; margin: 0 0 0.25rem; }
  .sub { color: var(--muted); font-size: 0.85rem; margin: 0 0 2rem; }
  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.5rem;
  }
  label { display: block; font-size: 0.8rem; color: var(--muted); margin-bottom: 6px; }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }
  input[type="file"], select {
    width: 100%;
    background: #0d0f14;
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 0.85rem;
  }
  button {
    background: var(--accent);
    color: #06231f;
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
  }
  button:hover { opacity: 0.9; }
  .field-hint { font-size: 0.75rem; color: var(--muted); margin-top: 4px; }
  pre {
    background: #0d0f14;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem;
    overflow: auto;
    font-size: 0.8rem;
    line-height: 1.5;
    max-height: 600px;
  }
  .error { color: var(--danger); white-space: pre-wrap; font-size: 0.85rem; }
  .toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
  .toolbar h2 { font-size: 1rem; margin: 0; font-weight: 600; }
  .small-btn {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 12px;
    font-size: 0.75rem;
  }
  a { color: var(--accent); }
</style>
</head>
<body>
<div class="wrap">
  <h1>Candidate Data Transformer</h1>
  <p class="sub">Calls the real <code>run_pipeline()</code> from pipeline.py. Nothing here is mocked.</p>
"""

PAGE_TAIL = """
</div>
</body>
</html>
"""

FORM_HTML = """
  <div class="panel">
    <form action="/run" method="post" enctype="multipart/form-data">
      <div class="row">
        <div>
          <label for="csv_file">Recruiter CSV</label>
          <input type="file" id="csv_file" name="csv_file" accept=".csv" />
          <div class="field-hint">Structured source — name, email, phone, headline, etc.</div>
        </div>
        <div>
          <label for="resume_file">Resume</label>
          <input type="file" id="resume_file" name="resume_file" accept=".pdf,.docx,.txt" />
          <div class="field-hint">Unstructured source — PDF, DOCX, or TXT.</div>
        </div>
      </div>
      <div class="row">
        <div>
          <label for="config_preset">Config</label>
          <select id="config_preset" name="config_preset">
            <option value="none">No config (raw canonical schema)</option>
            <option value="default">Default config (config_default.json)</option>
            <option value="custom">Custom config (config_custom.json)</option>
            <option value="upload">Upload my own config file</option>
          </select>
        </div>
        <div>
          <label for="config_file">Custom config file (if "Upload my own" selected)</label>
          <input type="file" id="config_file" name="config_file" accept=".json" />
        </div>
      </div>
      <button type="submit">Run pipeline</button>
    </form>
  </div>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE_HEAD + FORM_HTML + PAGE_TAIL


@app.post("/run", response_class=HTMLResponse)
async def run(
    csv_file: UploadFile | None = File(None),
    resume_file: UploadFile | None = File(None),
    config_preset: str = Form("none"),
    config_file: UploadFile | None = File(None),
):
    if (csv_file is None or csv_file.filename == "") and (
        resume_file is None or resume_file.filename == ""
    ):
        body = '<div class="panel"><p class="error">Provide at least a CSV or a resume file.</p></div>'
        return PAGE_HEAD + FORM_HTML + body + PAGE_TAIL

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        csv_path = None
        resume_path = None
        config_path = None

        if csv_file is not None and csv_file.filename:
            csv_path = tmp_path / csv_file.filename
            with open(csv_path, "wb") as f:
                shutil.copyfileobj(csv_file.file, f)

        if resume_file is not None and resume_file.filename:
            resume_path = tmp_path / resume_file.filename
            with open(resume_path, "wb") as f:
                shutil.copyfileobj(resume_file.file, f)

        if config_file is not None and config_file.filename:
            config_path = tmp_path / config_file.filename
            with open(config_path, "wb") as f:
                shutil.copyfileobj(config_file.file, f)
        elif config_preset in PRESET_CONFIGS and PRESET_CONFIGS[config_preset]:
            preset_path = PRESET_CONFIGS[config_preset]
            if preset_path.exists():
                config_path = preset_path
            else:
                body = (
                    '<div class="panel"><p class="error">'
                    f"Preset config not found at {preset_path}. "
                    "Adjust SAMPLE_DIR in app.py to match your repo layout, "
                    "or upload a config file instead.</p></div>"
                )
                return PAGE_HEAD + FORM_HTML + body + PAGE_TAIL

        try:
            result = run_pipeline(
                csv_path=str(csv_path) if csv_path else None,
                resume_path=str(resume_path) if resume_path else None,
                config_path=str(config_path) if config_path else None,
                output_path=None,
            )
        except Exception as exc:
            tb = traceback.format_exc()
            body = (
                '<div class="panel"><p class="error">Pipeline raised an exception:\n'
                f"{tb}</p></div>"
            )
            return PAGE_HEAD + FORM_HTML + body + PAGE_TAIL

    pretty = json.dumps(result, indent=2, default=str)
    result_body = f"""
  <div class="panel">
    <div class="toolbar">
      <h2>Output</h2>
      <button class="small-btn" onclick="downloadJson()">Download JSON</button>
    </div>
    <pre id="json-output">{escape_html(pretty)}</pre>
  </div>
  <script>
    function downloadJson() {{
      const text = document.getElementById('json-output').textContent;
      const blob = new Blob([text], {{ type: 'application/json' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'pipeline_output.json';
      a.click();
      URL.revokeObjectURL(url);
    }}
  </script>
"""
    return PAGE_HEAD + FORM_HTML + result_body + PAGE_TAIL


@app.post("/run.json")
async def run_json(
    csv_file: UploadFile | None = File(None),
    resume_file: UploadFile | None = File(None),
    config_file: UploadFile | None = File(None),
):
    """JSON-only endpoint, useful for curl / programmatic calls."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        csv_path = None
        resume_path = None
        config_path = None

        if csv_file is not None and csv_file.filename:
            csv_path = tmp_path / csv_file.filename
            with open(csv_path, "wb") as f:
                shutil.copyfileobj(csv_file.file, f)

        if resume_file is not None and resume_file.filename:
            resume_path = tmp_path / resume_file.filename
            with open(resume_path, "wb") as f:
                shutil.copyfileobj(resume_file.file, f)

        if config_file is not None and config_file.filename:
            config_path = tmp_path / config_file.filename
            with open(config_path, "wb") as f:
                shutil.copyfileobj(config_file.file, f)

        try:
            result = run_pipeline(
                csv_path=str(csv_path) if csv_path else None,
                resume_path=str(resume_path) if resume_path else None,
                config_path=str(config_path) if config_path else None,
                output_path=None,
            )
        except Exception as exc:
            return JSONResponse(status_code=500, content={"error": str(exc)})

    return JSONResponse(content=result)


def escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
