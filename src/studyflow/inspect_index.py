"""
inspect_index.py — Inspect and manually fix a project's classification index.

Usage:
    python inspect_index.py <project_name>
    python inspect_index.py <project_name> --full
        Print the topic/subtopic tree, optionally with a content preview.

    python inspect_index.py <project_name> --move <filename> <target_topic_id> [--subtopic "Título"]
        Manually reassign a misclassified document: detaches it from wherever
        it currently lives in the index and (re-)merges its original
        extracted text into the given topic (and subtopic, if provided —
        reused if a close match already exists, created otherwise). Requires
        that <filename> has already been extracted (extracted/<name>.txt
        must exist) and that <target_topic_id> already exists in the index
        — run `python inspect_index.py <project_name>` first to see the ids.

        See process.classifier.move_document's docstring for the one real
        limitation: if the document shared a subtopic with others, its text
        can't be cleanly un-merged from what's already there.
"""

import sys

from rich.console import Console
from rich.tree import Tree

from core.llm import LLM
from process.classifier import move_document
from utils.project import Project

console = Console()


def _preview(text: str, n: int = 160) -> str:
    text = " ".join(text.split())
    return text[:n] + ("…" if len(text) > n else "")


def show_index(project_name: str, full: bool = False) -> None:
    project = Project(project_name)
    if not project.path.exists():
        console.print(f"[red]No existe el proyecto '{project_name}'.[/red]")
        sys.exit(1)

    index = project.read_index()
    topics = index.get("topics", [])

    if not topics:
        console.print(f"[yellow]El índice de '{project_name}' está vacío — todavía no se ha clasificado ningún documento.[/yellow]")
        return

    tree = Tree(f"[bold blue]{project_name}[/bold blue] — {len(topics)} tema(s)")
    total_subtopics = 0
    total_sources = set()

    for t in topics:
        subtopics = t.get("subtopics", [])
        total_subtopics += len(subtopics)
        topic_branch = tree.add(f'[bold]{t["title"]}[/bold]  [dim]({t["id"]} · {len(subtopics)} subtema(s))[/dim]')
        for s in subtopics:
            n_chars = len(s.get("content", ""))
            sources = s.get("sources", [])
            total_sources.update(sources)
            label = f'{s["title"]}  [dim]({s["id"]} · {n_chars} chars · {len(sources)} doc(s): {", ".join(sources)})[/dim]'
            sub_branch = topic_branch.add(label)
            if full:
                sub_branch.add(f'[italic]{_preview(s.get("content", ""), 300)}[/italic]')

    console.print(tree)
    console.print(
        f"\n[dim]Total: {len(topics)} temas · {total_subtopics} subtemas · "
        f"{len(total_sources)} documentos únicos clasificados.[/dim]"
    )


def move(project_name: str, filename: str, target_topic_id: str, target_subtopic_title: str | None) -> None:
    project = Project(project_name)
    if not project.path.exists():
        console.print(f"[red]No existe el proyecto '{project_name}'.[/red]")
        sys.exit(1)

    text = project.read_extracted(filename)
    if text is None:
        console.print(
            f"[red]No hay texto extraído para '{filename}' en este proyecto "
            f"(¿el nombre es exacto? ¿ya se corrió la extracción?).[/red]"
        )
        sys.exit(1)

    index = project.read_index()
    llm = LLM()
    console.print(f"  🤖 {llm}")

    try:
        index = move_document(filename, text, index, target_topic_id, target_subtopic_title, llm)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    project.write_index(index)
    console.print(f"[green]✅ '{filename}' reasignado a tema '{target_topic_id}'"
                  + (f", subtema '{target_subtopic_title}'." if target_subtopic_title else ".") + "[/green]")
    console.print("[dim]Recuerda regenerar el HTML (volver a correr el pipeline) para que el material de estudio refleje este cambio.[/dim]")
    show_index(project_name)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        console.print(__doc__)
        sys.exit(1)

    project_name = args[0]

    if "--move" in args:
        i = args.index("--move")
        try:
            filename = args[i + 1]
            target_topic_id = args[i + 2]
        except IndexError:
            console.print("Uso: python inspect_index.py <project_name> --move <archivo> <target_topic_id> [--subtopic \"Título\"]")
            sys.exit(1)
        target_subtopic_title = None
        if "--subtopic" in args:
            j = args.index("--subtopic")
            try:
                target_subtopic_title = args[j + 1]
            except IndexError:
                console.print("Falta el título tras --subtopic")
                sys.exit(1)
        move(project_name, filename, target_topic_id, target_subtopic_title)
    else:
        show_index(project_name, full="--full" in args)