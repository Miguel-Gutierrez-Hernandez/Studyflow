"""
utils/proyecto.py — Project folder structure manager.

Layout:
    projects/
    └── project_name/
        ├── project.json     ← metadata
        ├── documents/       ← original uploaded files
        ├── extracted/       ← plain text extracted from each file
        └── output/
            └── index.html   ← generated study HTML
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

from config import PROJECTS_DIR


class Project:

    def __init__(self, name: str):
        self.name = name
        self.path: Path = PROJECTS_DIR / name
        self.path_documents: Path = self.path / "documents"
        self.path_extracted: Path = self.path / "extracted"
        self.path_output: Path = self.path / "output"
        self._meta_file: Path = self.path / "project.json"

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def create(self, overwrite: bool = False) -> "Project":
        if self.path.exists() and not overwrite:
            raise FileExistsError(
                f"Project '{self.name}' already exists. Use overwrite=True to force."
            )
        for folder in (self.path_documents, self.path_extracted, self.path_output):
            folder.mkdir(parents=True, exist_ok=True)
        self._write_meta({"name": self.name, "created": datetime.now().isoformat(), "files": []})
        return self

    def delete(self) -> None:
        if self.path.exists():
            shutil.rmtree(self.path)

    # ── Files ─────────────────────────────────────────────────────────────────

    def add_file(self, source: Path) -> Path:
        source = Path(source)
        if not source.exists():
            raise FileNotFoundError(f"File not found: {source}")
        dest = self.path_documents / source.name
        shutil.copy2(source, dest)
        self._register_file(source.name)
        return dest

    def documents(self) -> list[Path]:
        return [p for p in self.path_documents.iterdir() if p.is_file()] if self.path_documents.exists() else []

    # ── Output ────────────────────────────────────────────────────────────────

    def save_html(self, html: str) -> Path:
        self.path_output.mkdir(parents=True, exist_ok=True)
        out = self.path_output / "index.html"
        out.write_text(html, encoding="utf-8")
        self._patch_meta({"last_html": datetime.now().isoformat()})
        return out

    # ── Metadata ──────────────────────────────────────────────────────────────

    def _write_meta(self, data: dict) -> None:
        self._meta_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _read_meta(self) -> dict:
        return json.loads(self._meta_file.read_text()) if self._meta_file.exists() else {}

    def _patch_meta(self, changes: dict) -> None:
        meta = self._read_meta()
        meta.update(changes)
        self._write_meta(meta)

    def _register_file(self, name: str) -> None:
        meta = self._read_meta()
        if name not in meta.get("files", []):
            meta.setdefault("files", []).append(name)
        self._write_meta(meta)

    def __repr__(self) -> str:
        return f"<Project '{self.name}'>"