"""
pipeline.py — StudyFlow AI main orchestrator.

Runs the full pipeline:
    1. Create or load the project folder structure
    2. Copy input files into the project
    3. Extract text from all files
    4. Save extracted text to procesado/
    5. Detect topics with LLM
    6. Generate study material with LLM
    7. Build the HTML output
    8. Save HTML to output/index.html

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
from generator.content import generate_material
from generator.html_builder import build_html
from consumption.extractor import extract_all
from studyflow.process.analyzer import analyze
from studyflow.utils.project import Project

console = Console()


def run(
    project_name: str,
    files: list[str | Path],
    questions_per_topic: int = 8,
    overwrite: bool = False,
) -> Path:
    """
    Run the full StudyFlow AI pipeline.

    Args:
        project_name:       Project identifier (no spaces, e.g. "stats_t1")
        files:              Paths to input files (PDF, DOCX, PPTX, TXT, audio)
        questions_per_topic: Number of test questions generated per topic
        overwrite:          If True, recreate the project folder from scratch

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

    if not project_files:
        project_files = project.documents()
        console.print(f"  ℹ️  Using {len(project_files)} existing files")

    if not project_files:
        raise ValueError("No files to process. Add at least one file.")

    console.print("\n[bold]3/6 · Extracting text...[/bold]")
    texts = extract_all(project_files)
    for name, text in texts.items():
        if not text.startswith("[ERROR:"):
            out = project.path_extracted / (Path(name).stem + ".txt")
            out.write_text(text, encoding="utf-8")
    console.print(f"  ✅ Saved to: [dim]{project.path_extracted}[/dim]")

    console.print("\n[bold]4/6 · Detecting topics...[/bold]")
    llm = LLM()
    console.print(f"  🤖 {llm}")
    analysis = analyze(texts, llm=llm)
    n_topics = len(analysis["topics"])
    console.print(f"  ✅ {n_topics} topics: {', '.join(t['title'] for t in analysis['topics'])}")

    console.print(f"\n[bold]5/6 · Generating study material...[/bold]")
    material = generate_material(analysis, llm=llm, questions_per_topic=questions_per_topic)
    console.print(f"  ✅ {n_topics} topics · {material['stats']['n_questions']} questions")

    console.print("\n[bold]6/6 · Building HTML...[/bold]")
    html = build_html(material)
    html_path = project.save_html(html)

    console.print(Panel.fit(
        f"[bold green]Done![/bold green]\n\n"
        f"  Project:   [bold]{project_name}[/bold]\n"
        f"  Topics:    {n_topics}\n"
        f"  Questions: {material['stats']['n_questions']}\n"
        f"  Output:    [dim]{html_path}[/dim]",
        border_style="green",
    ))
    return html_path


if __name__ == "__main__":
    import sys
    console.print("[bold blue]StudyFlow AI[/bold blue]\n")

    name = input("Project name (no spaces): ").strip()
    if not name:
        console.print("[red]Error: name cannot be empty[/red]")
        sys.exit(1)

    console.print("Files to process (empty line to finish):")
    files = []
    while True:
        f = input("  Path: ").strip()
        if not f:
            break
        files.append(f)

    if not files:
        console.print("[red]Error: add at least one file[/red]")
        sys.exit(1)

    n = input("Questions per topic [8]: ").strip()
    questions_per_topic = int(n) if n.isdigit() else 8

    run(project_name=name, files=files, questions_per_topic=questions_per_topic)