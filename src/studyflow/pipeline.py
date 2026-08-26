"""
pipeline.py — StudyFlow AI main orchestrator.

Runs the full pipeline:
    1. Create or load the project folder structure
    2. Copy input files into the project
    3. Extract text (skips files already extracted in a previous run)
    4. Classify each new document into the project's persistent topic/subtopic
       index (Lector -> Enrutador -> Redactor, see process/classifier.py),
       then run the saturation check
    5. Generate study material with LLM from the resulting index
    6. Build the HTML output
    7. Save HTML to output/index.html

Usage (interactive):
    python pipeline.py

Usage (from code):
    from pipeline import run
    run(project_name="stats_t1", files=["notes.pdf", "lecture.mp3"])
"""

from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from core.llm import LLM
from core.llm_cache import LLMCache
from core.logging_setup import get_logger
from core.tracking import PipelineTracker
from core.distillation import DistillationRecorder
from generator.content import generate_material
from generator.html_builder import build_html
from consumption.extractor import extract_all
from process.analyzer import build_index
from utils.project import Project

console = Console()


def run(
    project_name: str,
    files: list[str | Path],
    questions_per_topic: int = 8,
    overwrite: bool = False,
    export_pdf: bool = False,
    track: bool = True,
    model: str | None = None,
    distill: bool = False,
) -> Path:
    """
    Run the full StudyFlow AI pipeline.

    Args:
        project_name:        Project identifier (no spaces, e.g. "stats_t1")
        files:                Paths to input files (PDF, DOCX, PPTX, TXT, audio)
        questions_per_topic:  Number of test questions generated per topic
        overwrite:            If True, recreate the project folder from scratch
        export_pdf:           If True, also export output/index.html to output/index.pdf
        track:                If True, log this run to MLflow (see core/tracking.py)
        model:                Ollama model name to use for this run. Defaults to
                              config.OLLAMA_MODEL if not given. Useful for
                              comparing models without editing .env (see compare_runs.py).
        distill:              If True, record every successful LLM completion as
                              training data for distillation (see DISTILLATION.md).
                              Typically enabled only when running with a strong
                              teacher model (e.g. llama3.1:8b), not the default small one.

    Returns:
        Path to the generated index.html
    """
    console.print(Panel.fit(
        f"[bold blue]StudyFlow AI[/bold blue] — project: [bold]{project_name}[/bold]",
        border_style="blue",
    ))

    console.print("\n[bold]1/6 · Setting up project...[/bold]")
    project = Project(project_name)
    if not project.path.exists():
        project.create()
        console.print(f"  ✅ Created at: [dim]{project.path}[/dim]")
    elif overwrite:
        project.create(overwrite=True)
        console.print(f"  🔄 Overwritten at: [dim]{project.path}[/dim]")
    else:
        console.print(f"  📂 Existing project — adding new files.")

    log = get_logger("pipeline", project.path)
    log.info("run_started", extra={"project": project_name, "n_input_files": len(files)})

    llm_model = model or LLM().model  # peek at effective model before opening the tracker
    tracker = PipelineTracker(project_name, model=llm_model, enabled=track)
    with tracker:
        tracker.log_params({
            "questions_per_topic": questions_per_topic,
            "overwrite": overwrite,
            "n_input_files": len(files),
        })
        html_path = _run_steps(
            project, files, questions_per_topic, export_pdf, log, tracker, model, distill,
        )
    return html_path


def _run_steps(
    project: Project,
    files: list[str | Path],
    questions_per_topic: int,
    export_pdf: bool,
    log,
    tracker: PipelineTracker,
    model: str | None = None,
    distill: bool = False,
) -> Path:
    console.print("\n[bold]2/6 · Adding files to project...[/bold]")
    project_files = []
    for f in files:
        path = Path(f)
        try:
            dest = project.add_file(path)
            project_files.append(dest)
            console.print(f"  ✅ [dim]{path.name}[/dim] → documents/")
        except FileNotFoundError as e:
            console.print(f"  ❌ [red]{e}[/red]")
            log.warning("file_not_found", extra={"path": str(path)})

    if not project_files:
        project_files = project.documents()
        console.print(f"  ℹ️  Using {len(project_files)} existing files")

    if not project_files:
        log.error("no_files_to_process")
        raise ValueError("No files to process. Add at least one file.")

    console.print("\n[bold]3/6 · Extracting text...[/bold]")
    texts: dict[str, str] = {}
    reused, to_extract = [], []
    with tracker.step("extraction"):
        for f in project_files:
            cached = project.read_extracted(f.name)
            if cached is not None:
                texts[f.name] = cached
                reused.append(f.name)
            else:
                to_extract.append(f)

        if reused:
            console.print(f"  ⏭️  Reused {len(reused)} previously extracted file(s)")
        log.info("extraction_reused", extra={"n_files": len(reused), "files": reused})

        if to_extract:
            new_texts = extract_all(to_extract)
            for name, text in new_texts.items():
                if not text.startswith("[ERROR:"):
                    out = project.path_extracted / (Path(name).stem + ".txt")
                    out.write_text(text, encoding="utf-8")
                else:
                    log.error("extraction_failed", extra={"file": name, "error": text})
                texts[name] = text
            console.print(f"  ✅ Extracted {len(to_extract)} new file(s)")
        log.info("extraction_done", extra={"n_new_files": len(to_extract)})

    tracker.log_metrics({
        "n_files_reused": len(reused),
        "n_files_extracted": len(to_extract),
    })
    console.print(f"  ✅ Saved to: [dim]{project.path_extracted}[/dim]")

    console.print("\n[bold]4/6 · Classifying documents into the project index...[/bold]")
    cache = LLMCache(project.path)
    llm = LLM(cache=cache, model=model)
    console.print(f"  🤖 {llm}")
    recorder = DistillationRecorder(enabled=distill) if distill else None
    if distill:
        console.print(f"  🎓 Recording training data to: [dim]{recorder.dir}[/dim]")

    with tracker.step("classification"):
        n_topics_before = len(project.read_index().get("topics", []))
        index = build_index(texts, project, llm, logger=log, recorder=recorder)
    n_topics = len(index["topics"])
    n_new_topics = max(0, n_topics - n_topics_before)
    console.print(
        f"  ✅ {n_topics} topics in index"
        + (f" (+{n_new_topics} new)" if n_new_topics else "")
        + ": " + ", ".join(t["title"] for t in index["topics"])
    )
    log.info("index_updated", extra={"n_topics": n_topics})

    console.print(f"\n[bold]5/6 · Generating study material...[/bold]")
    with tracker.step("material_generation"):
        material = generate_material(
            index, llm=llm, questions_per_topic=questions_per_topic, logger=log,
            recorder=recorder,
        )
    console.print(f"  ✅ {n_topics} topics · {material['stats']['n_questions']} questions")
    cache_stats = cache.stats()
    console.print(
        f"  💾 LLM cache: {cache_stats['hits']} hits, {cache_stats['misses']} misses"
    )
    if distill:
        console.print(f"  🎓 Recorded {recorder.n_recorded} training examples")
    log.info("material_generated", extra={**material["stats"], "llm_cache": cache_stats})

    n_flashcards = sum(len(t["flashcards"]) for t in material["topics"])
    tracker.log_metrics({
        "n_topics": n_topics,
        "n_questions": material["stats"]["n_questions"],
        "n_flashcards": n_flashcards,
        "llm_cache_hits": cache_stats["hits"],
        "llm_cache_misses": cache_stats["misses"],
    })

    console.print("\n[bold]6/6 · Building HTML...[/bold]")
    with tracker.step("html_build"):
        html = build_html(material)
        html_path = project.save_html(html)
    tracker.log_artifact(html_path)

    pdf_path = None
    if export_pdf:
        console.print("\n[bold]Exporting PDF...[/bold]")
        try:
            with tracker.step("pdf_export"):
                pdf_path = project.save_pdf()
            tracker.log_artifact(pdf_path)
            console.print(f"  ✅ Saved to: [dim]{pdf_path}[/dim]")
        except ImportError as e:
            console.print(f"  ⚠️  [yellow]{e}[/yellow]")

    console.print(Panel.fit(
        f"[bold green]Done![/bold green]\n\n"
        f"  Project:   [bold]{project.name}[/bold]\n"
        f"  Topics:    {n_topics}\n"
        f"  Questions: {material['stats']['n_questions']}\n"
        f"  Output:    [dim]{html_path}[/dim]"
        + (f"\n  PDF:       [dim]{pdf_path}[/dim]" if pdf_path else ""),
        border_style="green",
    ))
    log.info("run_finished", extra={"html_path": str(html_path), "pdf_path": str(pdf_path) if pdf_path else None})
    return html_path


def _print_history(projects: list[dict]) -> None:
    if not projects:
        console.print("[dim]  (no projects yet)[/dim]\n")
        return
    for i, p in enumerate(projects, 1):
        html_flag = "✅ HTML" if p["has_html"] else "⏳ no HTML yet"
        pdf_flag = " · 📄 PDF" if p.get("has_pdf") else ""
        created = (p["created"] or "")[:10]
        console.print(
            f"  [bold]{i}.[/bold] {p['name']}  "
            f"[dim]({p['n_files']} files · {created} · {html_flag}{pdf_flag})[/dim]"
        )
    console.print()


def _prompt_files() -> list[str]:
    console.print("Files to process (empty line to finish):")
    files = []
    while True:
        f = input("  Path: ").strip()
        if not f:
            break
        files.append(f)
    return files


if __name__ == "__main__":
    import sys
    console.print("[bold blue]StudyFlow AI[/bold blue]\n")

    projects = Project.list_all()
    console.print("[bold]Existing projects:[/bold]")
    _print_history(projects)

    console.print("[bold]What do you want to do?[/bold]")
    console.print("  [bold]n[/bold] — New project")
    if projects:
        console.print("  [bold]1-{}[/bold] — Open an existing project (regenerate HTML)".format(len(projects)))
    choice = input("> ").strip().lower()

    if choice.isdigit() and projects and 1 <= int(choice) <= len(projects):
        selected = projects[int(choice) - 1]
        name = selected["name"]
        console.print(f"\n[bold]Project:[/bold] {name}")
        console.print("[dim]Already-classified files will be reused; only new files are re-processed.[/dim]")
        add_more = input("Add new files too? (path, empty to skip): ").strip()
        files = []
        if add_more:
            files.append(add_more)
            files.extend(_prompt_files())
    else:
        name = input("Project name (no spaces): ").strip()
        if not name:
            console.print("[red]Error: name cannot be empty[/red]")
            sys.exit(1)
        if Project.exists(name):
            console.print(f"[yellow]A project named '{name}' already exists.[/yellow]")
            sys.exit(1)
        files = _prompt_files()
        if not files:
            console.print("[red]Error: add at least one file[/red]")
            sys.exit(1)

    n = input("Questions per topic [8]: ").strip()
    questions_per_topic = int(n) if n.isdigit() else 8

    export_pdf = input("Also export to PDF? (y/N): ").strip().lower() == "y"

    run(
        project_name=name,
        files=files,
        questions_per_topic=questions_per_topic,
        export_pdf=export_pdf,
    )