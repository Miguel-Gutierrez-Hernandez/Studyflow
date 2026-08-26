"""
utils/project.py — Project folder structure manager.

Layout:
    projects/
    └── project_name/
        ├── project.json     <- metadata
        ├── index.json       <- persistent topic/subtopic classification index
        │                       (built incrementally by process.classifier
        │                       as documents are added — see build_index)
        ├── documents/       <- original uploaded files
        ├── extracted/       <- plain text extracted from each file
        └── output/
            └── index.html   <- generated study HTML
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
        self._index_file: Path = self.path / "index.json"

    # -- Lifecycle ------------------------------------------------------------

    def create(self, overwrite: bool = False) -> "Project":
        if self.path.exists() and not overwrite:
            raise FileExistsError(
                f"Project '{self.name}' already exists. Use overwrite=True to force."
            )
        for folder in (self.path_documents, self.path_extracted, self.path_output):
            folder.mkdir(parents=True, exist_ok=True)
        self._write_meta({"name": self.name, "created": datetime.now().isoformat(), "files": []})
        self.write_index({"topics": []})
        return self

    def delete(self) -> None:
        if self.path.exists():
            shutil.rmtree(self.path)

    # -- Files ------------------------------------------------------------------

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

    def extracted_stems(self) -> set[str]:
        """Stems (filename without extension) that already have extracted text on disk."""
        if not self.path_extracted.exists():
            return set()
        return {p.stem for p in self.path_extracted.iterdir() if p.is_file() and p.suffix == ".txt"}

    def pending_documents(self) -> list[Path]:
        """Documents that have not been extracted yet (new files added to an existing project)."""
        done = self.extracted_stems()
        return [d for d in self.documents() if d.stem not in done]

    def read_extracted(self, name: str) -> str | None:
        """Read previously extracted text for a document by its original filename, if it exists."""
        path = self.path_extracted / (Path(name).stem + ".txt")
        return path.read_text(encoding="utf-8") if path.exists() else None

    # -- Index (topic/subtopic classification) ---------------------------------

    def read_index(self) -> dict:
        """The persistent classification index: {"topics": [{"id","title",
        "subtopics": [{"id","title","content","sources"}]}]}. Built and
        updated incrementally by process.analyzer.build_index /
        process.classifier.classify_document as documents are added to this
        project — never recomputed from scratch, so re-running the pipeline
        on an existing project only classifies genuinely new files."""
        if not self._index_file.exists():
            return {"topics": []}
        return json.loads(self._index_file.read_text(encoding="utf-8"))

    def write_index(self, index: dict) -> None:
        self._index_file.write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._patch_meta({"last_index_update": datetime.now().isoformat()})

    # -- Output -------------------------------------------------------------------

    def save_html(self, html: str) -> Path:
        self.path_output.mkdir(parents=True, exist_ok=True)
        out = self.path_output / "index.html"
        out.write_text(html, encoding="utf-8")
        self._patch_meta({"last_html": datetime.now().isoformat()})
        return out

    def save_pdf(self) -> Path:
        """Export the current output/index.html to output/index.pdf."""
        from generator.pdf_export import export_pdf
        html_path = self.path_output / "index.html"
        if not html_path.exists():
            raise FileNotFoundError(
                "No index.html found for this project yet. Run the pipeline first."
            )
        pdf_path = export_pdf(html_path, self.path_output / "index.pdf")
        self._patch_meta({"last_pdf": datetime.now().isoformat()})
        return pdf_path

    # -- Metadata -------------------------------------------------------------

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

    # -- History / management --------------------------------------------------

    @classmethod
    def list_all(cls) -> list[dict]:
        """
        Scan PROJECTS_DIR and return metadata for every existing project,
        sorted by most recently created first.
        """
        if not PROJECTS_DIR.exists():
            return []

        results = []
        for entry in PROJECTS_DIR.iterdir():
            if not entry.is_dir():
                continue
            meta_file = entry / "project.json"
            if not meta_file.exists():
                continue
            try:
                meta = json.loads(meta_file.read_text())
            except json.JSONDecodeError:
                meta = {}

            html_path = entry / "output" / "index.html"
            pdf_path = entry / "output" / "index.pdf"
            results.append({
                "name": meta.get("name", entry.name),
                "path": entry,
                "created": meta.get("created"),
                "n_files": len(meta.get("files", [])),
                "files": meta.get("files", []),
                "last_html": meta.get("last_html"),
                "has_html": html_path.exists(),
                "has_pdf": pdf_path.exists(),
            })

        results.sort(key=lambda r: r["created"] or "", reverse=True)
        return results

    @classmethod
    def exists(cls, name: str) -> bool:
        return (PROJECTS_DIR / name / "project.json").exists()

    def info(self) -> dict:
        """Summary of this project's current state."""
        meta = self._read_meta()
        html_path = self.path_output / "index.html"
        return {
            "name": self.name,
            "path": self.path,
            "created": meta.get("created"),
            "files": meta.get("files", []),
            "n_files": len(meta.get("files", [])),
            "last_html": meta.get("last_html"),
            "has_html": html_path.exists(),
            "html_path": html_path if html_path.exists() else None,
        }