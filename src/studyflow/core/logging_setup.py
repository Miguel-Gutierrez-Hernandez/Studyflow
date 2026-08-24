"""
core/logging_setup.py — Structured JSON-lines logging for the pipeline.

Each pipeline run writes one log file per project at:
    projects/<name>/logs/pipeline.log

Log lines are JSON objects, one per line (JSONL), so they're easy to grep,
parse, or feed into a log viewer. This is independent from the Rich console
output in pipeline.py, which stays for interactive UX.

Usage:
    from core.logging_setup import get_logger
    log = get_logger("pipeline", project_path)
    log.info("extraction_started", extra={"n_files": 3})
"""

import json
import logging
from pathlib import Path


class JsonlFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        # Any extra fields passed via `extra={...}` get merged in.
        for key, value in record.__dict__.items():
            if key in (
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            ):
                continue
            payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def get_logger(name: str, project_path: Path) -> logging.Logger:
    """Return a logger that writes JSONL entries to <project_path>/logs/pipeline.log."""
    logs_dir = Path(project_path) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(f"studyflow.{name}.{project_path}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Avoid duplicate handlers if get_logger is called multiple times for the same project.
    if not logger.handlers:
        handler = logging.FileHandler(logs_dir / "pipeline.log", encoding="utf-8")
        handler.setFormatter(JsonlFormatter())
        logger.addHandler(handler)

    return logger