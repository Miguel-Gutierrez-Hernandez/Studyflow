"""
api.py — StudyFlow AI REST API.

Wraps the existing pipeline (pipeline.run) and Project management behind
HTTP endpoints, so StudyFlow can be driven from a frontend, a script, or
curl instead of only the interactive CLI.

Because pipeline runs (LLM calls) take minutes, project creation and
updates run as background jobs: the request returns immediately with a
job_id, and the client polls GET /jobs/{job_id} for status.

Run with:
    pip install fastapi "uvicorn[standard]" python-multipart --break-system-packages
    uvicorn api:app --reload

Docs (interactive): http://localhost:8000/docs
"""

import shutil
import uuid
from datetime import datetime
from pathlib import Path
from tempfile import mkdtemp
from threading import Lock

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pipeline import run as run_pipeline
from utils.project import Project

app = FastAPI(
    title="StudyFlow AI API",
    description="Turn academic documents into structured study material and study material into HTML/PDF.",
    version="1.0.0",
)

# -- In-memory job tracking ---------------------------------------------------
# A simple dict is enough for a single-process local deployment. Swap for a
# real queue (Redis/RQ, Celery) if this ever needs to run distributed.

_jobs: dict[str, dict] = {}
_jobs_lock = Lock()


def _set_job(job_id: str, **fields) -> None:
    with _jobs_lock:
        _jobs[job_id].update(fields)


class JobStatus(BaseModel):
    job_id: str
    status: str  # "queued" | "running" | "done" | "error"
    project_name: str
    created_at: str
    finished_at: str | None = None
    error: str | None = None
    html_path: str | None = None
    pdf_path: str | None = None


class ProjectSummary(BaseModel):
    name: str
    created: str | None
    n_files: int
    files: list[str]
    has_html: bool
    has_pdf: bool
    last_html: str | None


# -- Background job runner -----------------------------------------------------

def _run_job(job_id: str, project_name: str, file_paths: list[Path], questions_per_topic: int,
             overwrite: bool, export_pdf: bool) -> None:
    _set_job(job_id, status="running")
    try:
        html_path = run_pipeline(
            project_name=project_name,
            files=file_paths,
            questions_per_topic=questions_per_topic,
            overwrite=overwrite,
            export_pdf=export_pdf,
        )
        project = Project(project_name)
        pdf_path = project.path_output / "index.pdf"
        _set_job(
            job_id,
            status="done",
            finished_at=datetime.now().isoformat(),
            html_path=str(html_path),
            pdf_path=str(pdf_path) if pdf_path.exists() else None,
        )
    except Exception as e:
        _set_job(job_id, status="error", finished_at=datetime.now().isoformat(), error=str(e))
    finally:
        # Clean up the temp upload dir used to stage this request's files.
        if file_paths:
            tmp_dir = file_paths[0].parent
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _save_uploads(uploads: list[UploadFile]) -> list[Path]:
    tmp_dir = Path(mkdtemp(prefix="studyflow_upload_"))
    saved = []
    for upload in uploads:
        dest = tmp_dir / upload.filename
        with dest.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        saved.append(dest)
    return saved


# -- Endpoints ------------------------------------------------------------------

@app.get("/projects", response_model=list[ProjectSummary])
def list_projects():
    """List all existing projects, most recently created first."""
    return [
        ProjectSummary(
            name=p["name"], created=p["created"], n_files=p["n_files"],
            files=p["files"], has_html=p["has_html"], has_pdf=p.get("has_pdf", False),
            last_html=p["last_html"],
        )
        for p in Project.list_all()
    ]


@app.get("/projects/{name}", response_model=ProjectSummary)
def get_project(name: str):
    """Get details for a single project."""
    if not Project.exists(name):
        raise HTTPException(404, f"Project '{name}' not found")
    info = Project(name).info()
    return ProjectSummary(
        name=info["name"], created=info["created"], n_files=info["n_files"],
        files=info["files"], has_html=info["has_html"],
        has_pdf=(info["html_path"] is not None and (Path(info["html_path"]).parent / "index.pdf").exists()),
        last_html=info["last_html"],
    )


@app.delete("/projects/{name}")
def delete_project(name: str):
    """Delete a project and all its files."""
    if not Project.exists(name):
        raise HTTPException(404, f"Project '{name}' not found")
    Project(name).delete()
    return {"deleted": name}


@app.post("/projects", response_model=JobStatus, status_code=202)
def create_project(
    background_tasks: BackgroundTasks,
    name: str,
    files: list[UploadFile] = File(...),
    questions_per_topic: int = 8,
    export_pdf: bool = False,
):
    """
    Create a new project from uploaded files and run the full pipeline.
    Returns immediately with a job_id; poll GET /jobs/{job_id} for progress.
    """
    if Project.exists(name):
        raise HTTPException(409, f"Project '{name}' already exists. Use PATCH to add files instead.")
    if not files:
        raise HTTPException(400, "At least one file is required")

    file_paths = _save_uploads(files)
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id, "status": "queued", "project_name": name,
            "created_at": datetime.now().isoformat(), "finished_at": None,
            "error": None, "html_path": None, "pdf_path": None,
        }
    background_tasks.add_task(
        _run_job, job_id, name, file_paths, questions_per_topic, False, export_pdf,
    )
    return JobStatus(**_jobs[job_id])


@app.patch("/projects/{name}", response_model=JobStatus, status_code=202)
def update_project(
    name: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(default=[]),
    questions_per_topic: int = 8,
    export_pdf: bool = False,
):
    """
    Add new files (optional) to an existing project and regenerate its HTML.
    Already-extracted files are reused, not re-processed (update mode).
    """
    if not Project.exists(name):
        raise HTTPException(404, f"Project '{name}' not found")

    file_paths = _save_uploads(files) if files else []
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id, "status": "queued", "project_name": name,
            "created_at": datetime.now().isoformat(), "finished_at": None,
            "error": None, "html_path": None, "pdf_path": None,
        }
    background_tasks.add_task(
        _run_job, job_id, name, file_paths, questions_per_topic, False, export_pdf,
    )
    return JobStatus(**_jobs[job_id])


@app.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str):
    """Poll the status of a background pipeline run."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"Job '{job_id}' not found")
    return JobStatus(**job)


@app.get("/projects/{name}/html")
def get_project_html(name: str):
    """Serve the generated study HTML for a project."""
    if not Project.exists(name):
        raise HTTPException(404, f"Project '{name}' not found")
    html_path = Project(name).path_output / "index.html"
    if not html_path.exists():
        raise HTTPException(404, "No HTML generated yet for this project")
    return FileResponse(html_path, media_type="text/html")


@app.get("/projects/{name}/pdf")
def get_project_pdf(name: str, generate_if_missing: bool = True):
    """Serve the generated study PDF for a project, generating it on demand if missing."""
    if not Project.exists(name):
        raise HTTPException(404, f"Project '{name}' not found")
    project = Project(name)
    pdf_path = project.path_output / "index.pdf"
    if not pdf_path.exists():
        if not generate_if_missing:
            raise HTTPException(404, "No PDF generated yet for this project")
        try:
            pdf_path = project.save_pdf()
        except (FileNotFoundError, ImportError) as e:
            raise HTTPException(400, str(e))
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"{name}.pdf")


@app.get("/health")
def health():
    return {"status": "ok"}