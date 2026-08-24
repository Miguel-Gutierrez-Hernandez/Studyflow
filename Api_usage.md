# StudyFlow AI — REST API

Run the server:
```bash
pip install fastapi "uvicorn[standard]" python-multipart --break-system-packages
uvicorn api:app --reload
```

Interactive docs: http://localhost:8000/docs

## Typical flow

1. **Create a project** (uploads files, kicks off the pipeline in the background):
```bash
curl -X POST "http://localhost:8000/projects?name=stats_t1&questions_per_topic=8" \
  -F "files=@notes.pdf" -F "files=@lecture.mp3"
```
Returns a `job_id`.

2. **Poll job status**:
```bash
curl http://localhost:8000/jobs/<job_id>
```
`status` moves through `queued` -> `running` -> `done` (or `error`).

3. **Get the result**:
```bash
curl http://localhost:8000/projects/stats_t1/html -o stats_t1.html
curl http://localhost:8000/projects/stats_t1/pdf  -o stats_t1.pdf
```

## Update mode

Add new files to an existing project and regenerate (already-extracted
files are reused, not reprocessed):
```bash
curl -X PATCH "http://localhost:8000/projects/stats_t1" -F "files=@extra_notes.pdf"
```

## Other endpoints

- `GET /projects` — list all projects
- `GET /projects/{name}` — project details
- `DELETE /projects/{name}` — delete a project
- `GET /health` — health check