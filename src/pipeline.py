"""
Multi-Source Candidate Data Transformer — Eightfold Engineering Intern Assignment
Anushka Sharma – as2155@srmist.edu.in

Main pipeline: detect → extract → normalize → merge → confidence → project → validate
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Optional

from adapters.csv_adapter import CSVAdapter
from adapters.resume_adapter import ResumeAdapter
from merger.merge import merge_fragments
from projector.project import project_output
from validator.validate import validate_profile


def run_pipeline(
    csv_path: Optional[str] = None,
    resume_path: Optional[str] = None,
    config_path: Optional[str] = None,
    output_path: Optional[str] = None,
) -> dict:
    """
    Run the full pipeline.
    At least one structured (csv) and one unstructured (resume) source required.
    """
    fragments = []

    if csv_path:
        adapter = CSVAdapter(csv_path)
        fragments.extend(adapter.extract())

    if resume_path:
        adapter = ResumeAdapter(resume_path)
        fragments.append(adapter.extract())

    if not fragments:
        raise ValueError("No valid input sources provided.")

    # Merge all fragments into canonical profiles (keyed by candidate_id)
    profiles = merge_fragments(fragments)

    # Load runtime config if provided
    config = None
    if config_path:
        with open(config_path, "r") as f:
            config = json.load(f)

    results = []
    for profile in profiles.values():
        # Project + validate
        output = project_output(profile, config)
        errors = validate_profile(output, config)
        if errors:
            output["_validation_errors"] = errors
        results.append(output)

    final = results if len(results) > 1 else results[0] if results else {}

    if output_path:
        with open(output_path, "w") as f:
            json.dump(final, f, indent=2, default=str)
        print(f"Output written to {output_path}")
    else:
        print(json.dumps(final, indent=2, default=str))

    return final


def main():
    parser = argparse.ArgumentParser(
        description="Multi-Source Candidate Data Transformer"
    )
    parser.add_argument("--csv", help="Path to recruiter CSV file")
    parser.add_argument("--resume", help="Path to resume PDF or DOCX file")
    parser.add_argument("--config", help="Path to runtime config JSON file")
    parser.add_argument("--output", help="Path to write output JSON (default: stdout)")
    args = parser.parse_args()

    if not args.csv and not args.resume:
        parser.error("Provide at least --csv or --resume (ideally both).")

    run_pipeline(
        csv_path=args.csv,
        resume_path=args.resume,
        config_path=args.config,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
