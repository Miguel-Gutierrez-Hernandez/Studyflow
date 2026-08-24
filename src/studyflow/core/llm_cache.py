"""
core/llm_cache.py — Disk cache for LLM responses.

Caches LLM responses per project so re-running the pipeline on unchanged
content (e.g. reopening a project in update mode without new files) doesn't
repeat identical calls to Ollama.

Cache key = sha256(model + system + prompt + temperature). Cache lives at:
    projects/<name>/.cache/llm/<hash>.json
"""

import hashlib
import json
from pathlib import Path


class LLMCache:
    def __init__(self, project_path: Path):
        self.dir = Path(project_path) / ".cache" / "llm"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    def _key(self, model: str, system: str | None, prompt: str, temperature: float) -> str:
        raw = f"{model}||{system or ''}||{prompt}||{temperature}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, model: str, system: str | None, prompt: str, temperature: float) -> str | None:
        path = self.dir / f"{self._key(model, system, prompt, temperature)}.json"
        if not path.exists():
            self.misses += 1
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.hits += 1
            return data["response"]
        except (json.JSONDecodeError, KeyError):
            self.misses += 1
            return None

    def set(self, model: str, system: str | None, prompt: str, temperature: float, response: str) -> None:
        path = self.dir / f"{self._key(model, system, prompt, temperature)}.json"
        path.write_text(
            json.dumps({"response": response}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses}