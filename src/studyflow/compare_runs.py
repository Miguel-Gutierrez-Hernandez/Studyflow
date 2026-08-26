"""
compare_runs.py — Compare models/settings on the same input files.

Runs the full pipeline once per model (or per Ollama parameter set) against
the same input files, tagging each run in MLflow with the model name so
they show up side-by-side in the MLflow UI compare view.

Usage:
    python compare_runs.py --files notes.pdf lecture.mp3 --models llama3.2 llama3.1:8b

Then:
    mlflow ui --backend-store-uri sqlite:///mlflow.db
    -> open http://localhost:5000, select the "studyflow-pipeline-runs"
       experiment, select the runs, click "Compare".

Note: this creates one throwaway project per model (named
"<base_name>__<model>") so runs don't overwrite each other's extracted
text/output. Delete them afterwards with Project(name).delete() if you
don't need to keep the comparison projects around.
"""

import argparse
from pathlib import Path

from pipeline import run


def compare(base_name: str, files: list[str], models: list[str]) -> None:
    for model in models:
        project_name = f"{base_name}__{model.replace(':', '-').replace('.', '-')}"
        print(f"\n=== Running with model: {model} (project: {project_name}) ===")
        try:
            run(
                project_name=project_name,
                files=files,
                overwrite=True,
                export_pdf=False,
                track=True,
                model=model,
            )
        except Exception as e:
            print(f"  ❌ Run failed for model '{model}': {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-name", default="compare", help="Prefix for the throwaway project names")
    parser.add_argument("--files", nargs="+", required=True, help="Input files (shared across all runs)")
    parser.add_argument("--models", nargs="+", required=True, help="Ollama model names to compare")
    args = parser.parse_args()

    compare(args.base_name, args.files, args.models)

    print(
        "\nDone. Compare results with:\n"
        "  mlflow ui --backend-store-uri sqlite:///mlflow.db\n"
        "then open http://localhost:5000"
    )