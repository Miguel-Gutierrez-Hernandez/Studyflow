"""
pipeline.py — Orquestador principal de StudyFlow AI.

Ejecuta el flujo completo:
    1. Crea o carga el proyecto
    2. Añade los documentos al proyecto
    3. Extrae texto de todos los archivos
    4. Guarda los textos procesados en procesado/
    5. Analiza y detecta temas
    6. Genera material de estudio
    7. Genera el HTML final
    8. Guarda el HTML en output/index.html

Uso desde terminal:
    python pipeline.py

Uso desde código:
    from pipeline import ejecutar
    ejecutar(
        nombre_proyecto="estadistica_T1",
        archivos=["apuntes.pdf", "clase.mp3"],
    )
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import track

from config import PROYECTOS_DIR
from core.llm import get_llm
from generador.contenido import generar_material
from generador.html_builder import generar_html
from ingesta.extractor import extraer_todos
from procesado.analizador import analizar
from utils.proyecto import Proyecto, cargar_proyecto

console = Console()


def ejecutar(
    nombre_proyecto: str,
    archivos: list[str | Path],
    n_preguntas_por_tema: int = 8,
    sobrescribir_proyecto: bool = False,
    llm_provider: str | None = None,
) -> Path:
    """
    Pipeline completo de StudyFlow AI.

    Args:
        nombre_proyecto: Nombre identificador del proyecto (sin espacios, p.ej. "estadistica_T1")
        archivos: Lista de rutas a los archivos a procesar (PDF, DOCX, PPTX, TXT, audio)
        n_preguntas_por_tema: Número de preguntas test por tema (default: 8)
        sobrescribir_proyecto: Si True, sobreescribe proyecto existente. Si False, añade documentos.
        llm_provider: Provider del LLM ('huggingface', 'openai', etc.). None = usa el del .env.

    Returns:
        Path al HTML generado (output/index.html)
    """
    console.print(Panel.fit(
        f"[bold blue]StudyFlow AI[/bold blue] — Procesando proyecto: [bold]{nombre_proyecto}[/bold]",
        border_style="blue"
    ))

    # ── 1. Proyecto ───────────────────────────────────────────────────────────
    console.print("\n[bold]1/6 · Preparando proyecto...[/bold]")
    proyecto = Proyecto(nombre_proyecto)

    if not proyecto.ruta.exists():
        proyecto.crear()
        console.print(f"  ✅ Proyecto creado en: [dim]{proyecto.ruta}[/dim]")
    elif sobrescribir_proyecto:
        proyecto.crear(sobrescribir=True)
        console.print(f"  🔄 Proyecto sobreescrito en: [dim]{proyecto.ruta}[/dim]")
    else:
        console.print(f"  📂 Proyecto existente. Añadiendo documentos nuevos.")

    # ── 2. Añadir documentos ──────────────────────────────────────────────────
    console.print("\n[bold]2/6 · Añadiendo documentos al proyecto...[/bold]")
    rutas_en_proyecto = []
    for archivo in archivos:
        ruta = Path(archivo)
        try:
            destino = proyecto.añadir_documento(ruta)
            rutas_en_proyecto.append(destino)
            console.print(f"  ✅ [dim]{ruta.name}[/dim] → documentos/")
        except FileNotFoundError as e:
            console.print(f"  ❌ [red]{e}[/red]")

    if not rutas_en_proyecto:
        # Si no hay archivos nuevos, usar los que ya están en el proyecto
        rutas_en_proyecto = proyecto.documentos()
        console.print(f"  ℹ️  Usando {len(rutas_en_proyecto)} documentos existentes")

    if not rutas_en_proyecto:
        raise ValueError("No hay documentos para procesar. Añade al menos un archivo.")

    # ── 3. Extracción de texto ────────────────────────────────────────────────
    console.print("\n[bold]3/6 · Extrayendo texto de los documentos...[/bold]")
    textos = extraer_todos(rutas_en_proyecto)

    # Guardar textos extraídos en procesado/
    for nombre, texto in textos.items():
        if not texto.startswith("[ERROR:"):
            ruta_txt = proyecto.ruta_procesado / (Path(nombre).stem + ".txt")
            ruta_txt.write_text(texto, encoding="utf-8")
    console.print(f"  ✅ Textos guardados en: [dim]{proyecto.ruta_procesado}[/dim]")

    # ── 4. Análisis y detección de temas ─────────────────────────────────────
    console.print("\n[bold]4/6 · Analizando estructura temática con LLM...[/bold]")
    llm = get_llm(provider=llm_provider)
    console.print(f"  🤖 Usando LLM: [dim]{llm}[/dim]")

    analisis = analizar(textos, llm=llm)
    n_temas = len(analisis["temas"])
    console.print(f"  ✅ Detectados [bold]{n_temas}[/bold] temas: {', '.join(t['titulo'] for t in analisis['temas'])}")

    # ── 5. Generación de material ─────────────────────────────────────────────
    console.print(f"\n[bold]5/6 · Generando material de estudio ({n_preguntas_por_tema} preguntas/tema)...[/bold]")
    material = generar_material(
        analisis,
        llm=llm,
        n_preguntas_por_tema=n_preguntas_por_tema,
    )
    total_preguntas = material["stats"]["n_preguntas"]
    console.print(f"  ✅ Material generado: {n_temas} temas, {total_preguntas} preguntas test")

    # ── 6. Generación y guardado del HTML ─────────────────────────────────────
    console.print("\n[bold]6/6 · Generando HTML de repaso...[/bold]")
    html = generar_html(material)
    ruta_html = proyecto.guardar_html(html)

    # ── Resumen final ─────────────────────────────────────────────────────────
    console.print(Panel.fit(
        f"[bold green]✅ ¡Listo![/bold green]\n\n"
        f"  Proyecto:   [bold]{nombre_proyecto}[/bold]\n"
        f"  Temas:      {n_temas}\n"
        f"  Preguntas:  {total_preguntas}\n"
        f"  HTML:       [dim]{ruta_html}[/dim]",
        border_style="green"
    ))

    return ruta_html


# ── CLI básico ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    console.print("[bold blue]StudyFlow AI[/bold blue] — Modo interactivo\n")

    nombre = input("Nombre del proyecto (sin espacios): ").strip()
    if not nombre:
        console.print("[red]Error: el nombre no puede estar vacío[/red]")
        sys.exit(1)

    console.print("Archivos a procesar (intro en vacío para terminar):")
    archivos = []
    while True:
        ruta = input("  Ruta: ").strip()
        if not ruta:
            break
        archivos.append(ruta)

    if not archivos:
        console.print("[red]Error: añade al menos un archivo[/red]")
        sys.exit(1)

    n_preguntas = input("Preguntas por tema [8]: ").strip()
    n_preguntas = int(n_preguntas) if n_preguntas.isdigit() else 8

    ejecutar(
        nombre_proyecto=nombre,
        archivos=archivos,
        n_preguntas_por_tema=n_preguntas,
    )
