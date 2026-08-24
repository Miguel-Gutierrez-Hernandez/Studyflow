"""
generator/pdf_export.py — Export the generated study HTML to PDF.

Uses WeasyPrint to render the saved index.html into a print-friendly PDF.
The HTML's existing `@media print` rules (hide nav, hide exam toolbar, etc.)
are respected automatically since WeasyPrint renders in print mode.

Install with:
    pip install weasyprint --break-system-packages

WeasyPrint depends on Pango/Cairo system libraries. On macOS:
    brew install pango
"""

from pathlib import Path


def export_pdf(html_path: Path, output_path: Path | None = None) -> Path:
    """
    Render an HTML file (e.g. a project's output/index.html) to PDF.

    Args:
        html_path:   Path to the source HTML file.
        output_path: Destination .pdf path. Defaults to the same name/folder
                     as html_path with a .pdf extension.

    Returns:
        Path to the generated PDF.
    """
    try:
        from weasyprint import HTML
    except ImportError:
        raise ImportError(
            "Install WeasyPrint for PDF export: pip install weasyprint --break-system-packages\n"
            "(macOS also needs the Pango system library: brew install pango)"
        )

    html_path = Path(html_path)
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    output_path = Path(output_path) if output_path else html_path.with_suffix(".pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    HTML(filename=str(html_path), base_url=str(html_path.parent)).write_pdf(str(output_path))
    return output_path