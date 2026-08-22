"""
ingesta/extractor.py — Text extraction from multiple file formats.

Supported:
    .pdf            → PyMuPDF
    .docx           → python-docx
    .pptx           → python-pptx
    .txt            → direct read
    .mp3/.wav/etc.  → HuggingFace Whisper API
"""

from pathlib import Path

DOCUMENT_FORMATS = {".pdf", ".docx", ".pptx", ".txt"}
AUDIO_FORMATS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".opus"}


def extract_text(path: Path) -> str:
    """Detect format and extract text. Raises ValueError for unsupported formats."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    ext = path.suffix.lower()
    if ext == ".pdf":
        return _pdf(path)
    elif ext == ".docx":
        return _docx(path)
    elif ext == ".pptx":
        return _pptx(path)
    elif ext == ".txt":
        return _txt(path)
    elif ext in AUDIO_FORMATS:
        return _audio(path)
    else:
        raise ValueError(f"Unsupported format '{ext}'. Supported: {DOCUMENT_FORMATS | AUDIO_FORMATS}")


def extract_all(paths: list[Path]) -> dict[str, str]:
    """Extract text from a list of files. Returns {filename: text}."""
    results = {}
    for path in paths:
        try:
            print(f"  Processing: {path.name}")
            results[path.name] = extract_text(path)
            print(f"     OK ({len(results[path.name])} chars)")
        except Exception as e:
            print(f"     ERROR: {e}")
            results[path.name] = f"[ERROR: {e}]"
    return results


def _pdf(path: Path) -> str:
    try:
        import fitz
    except ImportError:
        raise ImportError("Install PyMuPDF: pip install pymupdf")
    doc = fitz.open(str(path))
    pages = [f"[Page {i+1}]\n{page.get_text('text').strip()}" for i, page in enumerate(doc) if page.get_text("text").strip()]
    doc.close()
    return "\n\n".join(pages)


def _docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError:
        raise ImportError("Install python-docx: pip install python-docx")
    doc = Document(str(path))
    return "\n\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())


def _pptx(path: Path) -> str:
    try:
        from pptx import Presentation
    except ImportError:
        raise ImportError("Install python-pptx: pip install python-pptx")
    prs = Presentation(str(path))
    slides = []
    for i, slide in enumerate(prs.slides, 1):
        texts = [shape.text.strip() for shape in slide.shapes if hasattr(shape, "text") and shape.text.strip()]
        if texts:
            slides.append(f"[Slide {i}]\n" + "\n".join(texts))
    return "\n\n".join(slides)


def _txt(path: Path) -> str:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return path.read_text(encoding=enc).strip()
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not read {path} with any known encoding.")


def _audio(path: Path) -> str:
    """Transcribe audio via HuggingFace Whisper API. No local dependencies required."""
    import requests
    from config import HF_TOKEN, HF_WHISPER_MODEL

    if not HF_TOKEN:
        raise ValueError("HF_TOKEN is missing from .env.")

    url = f"https://api-inference.huggingface.co/models/{HF_WHISPER_MODEL}"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    params = {"language": "es", "task": "transcribe", "return_timestamps": False}

    print(f"  Transcribing '{path.name}' via HuggingFace API ({HF_WHISPER_MODEL})...")

    with open(path, "rb") as f:
        audio = f.read()

    response = requests.post(url, headers=headers, params=params, data=audio, timeout=300)

    if response.status_code == 503:
        raise RuntimeError("Whisper model is loading on HuggingFace (503). Wait 20-30s and retry.")

    response.raise_for_status()
    data = response.json()

    if isinstance(data, dict) and "text" in data:
        return data["text"].strip()
    if isinstance(data, list):
        return " ".join(c.get("text", "") for c in data if isinstance(c, dict)).strip()

    raise RuntimeError(f"Unexpected response from HuggingFace Whisper: {data}")