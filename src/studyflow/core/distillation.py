"""
core/distillation.py — Record teacher (large model) completions as
training data for distilling a smaller, specialized student model.

When enabled, every successfully-parsed JSON completion from the LLM
(topic detection, subtopic explanations, questions, flashcards, etc.) is
appended to a JSONL dataset. Over time, running the pipeline with a strong
teacher model (e.g. llama3.1:8b) on your real study material builds a
dataset of exactly the kind of task StudyFlow needs — no synthetic data
required.

See DISTILLATION.md for the full fine-tuning + deployment workflow.
"""

import json
from datetime import datetime
from pathlib import Path


class DistillationRecorder:
    """Appends (task, system, prompt, response) records to a shared JSONL dataset."""

    def __init__(self, dataset_dir: Path | str = "distillation_data", enabled: bool = True):
        self.enabled = enabled
        self.dir = Path(dataset_dir)
        if self.enabled:
            self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "records.jsonl"
        self.n_recorded = 0

    def record(self, task: str, system: str, prompt: str, response: dict, model: str) -> None:
        """Save one successful teacher completion. `response` must already be
        a parsed dict (i.e. only record completions that passed JSON validation —
        garbage in, garbage out)."""
        if not self.enabled:
            return
        entry = {
            "task": task,
            "system": system,
            "prompt": prompt,
            "response": response,
            "model": model,
            "recorded_at": datetime.now().isoformat(),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.n_recorded += 1

    def stats(self) -> dict:
        return {"n_recorded": self.n_recorded, "path": str(self.path)}