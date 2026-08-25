"""
core/tracking.py — MLflow tracking for pipeline runs.

Wraps each pipeline execution in an MLflow run so you can compare:
    - Runtime per step (extraction, topic detection, material generation)
    - Model / temperature / questions_per_topic params
    - Output "quality" proxies (n_topics, n_questions, n_flashcards)
    - LLM cache hit rate
    - JSON parse failure/retry counts (a rough malformed-output signal)
    - The generated HTML/PDF as artifacts, for manual inspection

By default MLflow logs to a local SQLite database `./mlflow.db` (the
current MLflow-recommended local backend — no server required). View
results with:
    mlflow ui --backend-store-uri sqlite:///mlflow.db
then open http://localhost:5000

Usage:
    from core.tracking import PipelineTracker

    with PipelineTracker(project_name, model=llm.model) as tracker:
        tracker.log_param("questions_per_topic", 8)
        with tracker.step("extraction"):
            ...
        tracker.log_metric("n_topics", 5)
        tracker.log_artifact(html_path)
"""

import time
from contextlib import contextmanager
from pathlib import Path

import mlflow

_EXPERIMENT_NAME = "studyflow-pipeline-runs"
_TRACKING_URI = "sqlite:///mlflow.db"


class PipelineTracker:
    """Context manager wrapping one MLflow run for one pipeline execution."""

    def __init__(self, project_name: str, model: str, enabled: bool = True):
        self.project_name = project_name
        self.model = model
        self.enabled = enabled
        self._run = None
        self._step_start: float | None = None

    def __enter__(self) -> "PipelineTracker":
        if not self.enabled:
            return self
        mlflow.set_tracking_uri(_TRACKING_URI)
        mlflow.set_experiment(_EXPERIMENT_NAME)
        self._run = mlflow.start_run(run_name=f"{self.project_name}-{int(time.time())}")
        mlflow.set_tag("project", self.project_name)
        mlflow.log_param("model", self.model)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if not self.enabled:
            return
        if exc_type is not None:
            mlflow.set_tag("status", "error")
            mlflow.log_param("error", str(exc_val)[:250])
        else:
            mlflow.set_tag("status", "success")
        mlflow.end_run()

    # -- Logging helpers -------------------------------------------------------

    def log_param(self, key: str, value) -> None:
        if self.enabled:
            mlflow.log_param(key, value)

    def log_params(self, params: dict) -> None:
        if self.enabled:
            mlflow.log_params(params)

    def log_metric(self, key: str, value: float) -> None:
        if self.enabled:
            mlflow.log_metric(key, value)

    def log_metrics(self, metrics: dict) -> None:
        if self.enabled:
            mlflow.log_metrics(metrics)

    def log_artifact(self, path: Path) -> None:
        if self.enabled and Path(path).exists():
            mlflow.log_artifact(str(path))

    @contextmanager
    def step(self, name: str):
        """Time a pipeline step and log it as `<name>_seconds`."""
        start = time.time()
        try:
            yield
        finally:
            elapsed = time.time() - start
            self.log_metric(f"{name}_seconds", elapsed)