"""
process/chunker.py — Split a long document into topic-sized pieces before
classification.

Why this exists: process.classifier.classify_document treats its entire
input as ONE classification unit — one Lector call, one topic/subtopic
decision. That's fine for a short document that covers a single subtopic,
but it silently collapses a multi-topic document (a full unit/chapter PDF
with its own "Tema 1", "Tema 2"... structure) into a single topic and a
single subtopic, no matter how long it is. Two compounding problems follow:
the index ends up with one giant subtopic instead of the document's real
structure, and generator/content.py truncates each subtopic's content to its
first 8000 characters when generating study material — so everything past
roughly the first 10% of a long, unsegmented document never reaches
generation at all.

split_document() fixes this by cutting the document into pieces BEFORE it
reaches the classifier, so each piece is classified (and later generates
content) independently:

    1. Heading-based split (preferred): looks for the document's own
       section markers — numbered headings ("3. Tema 1: X", "6.1. Y"),
       ALL-CAPS "TEMA N:" / "CAPÍTULO N:" markers, or markdown "#" headings
       — and cuts on those. This preserves the author's own structure,
       which is exactly what should become topics/subtopics.
    2. Size-based fallback: if no reliable heading structure is found (too
       few matches, or one "heading" ends up covering almost the whole
       document — a sign the pattern matched noise, not real structure),
       falls back to splitting on paragraph boundaries into chunks of a
       bounded size. Each chunk still goes through the normal Lector ->
       Enrutador classification, so the LLM decides how these untitled
       chunks group together — this is the "fall back to the LLM" path.
"""

import re

# Patterns for section headings, checked together (union) so a document that
# mixes styles (e.g. numbered top-level "Tema N" plus numbered "N.N"
# subsections, as in a typical unit/chapter PDF) gets cut at every level.
_HEADING_PATTERNS: list[tuple[int, re.Pattern]] = [
    (1, re.compile(r"^\s*\d+\.\s+(?:TEMA|Tema)\s+\d+\s*:\s*.{2,100}$", re.MULTILINE)),
    (2, re.compile(r"^\s*\d+\.\d+\.?\s+[A-ZÁÉÍÓÚÑ][^\n]{2,100}$", re.MULTILINE)),
    (1, re.compile(r"^\s*(?:TEMA|CAP[IÍ]TULO|UNIDAD)\s+\d+\s*[:\-]\s*.{2,100}$", re.MULTILINE)),
    (1, re.compile(r"^#\s+.{2,100}$", re.MULTILINE)),        # "# Título" — level 1
    (2, re.compile(r"^#{2,3}\s+.{2,100}$", re.MULTILINE)),   # "## / ###" — level 2
]

MIN_HEADINGS = 2                # need at least this many matches to trust heading-based splitting
MAX_SINGLE_CHUNK_SHARE = 0.7    # if one heading-chunk covers more than this share of the doc, distrust the split
MIN_CHUNK_CHARS = 400           # heading-based chunks smaller than this get merged into a neighbor
FALLBACK_CHUNK_CHARS = 6000     # target size for the size-based fallback


def _find_headings(text: str) -> list[tuple[int, str]]:
    """Return (start_offset, heading_line) pairs for every heading-like line
    found by any pattern, sorted by position and de-duplicated by offset."""
    found: dict[int, str] = {}
    for level, pattern in _HEADING_PATTERNS: 
        for m in pattern.finditer(text):
            found[m.start()] = m.group(0).strip()
    return sorted(found.items())


def _split_by_headings(text: str) -> list[dict] | None:
    headings = _find_headings(text)
    if len(headings) < MIN_HEADINGS:
        return None

    chunks = []
    for i, (start, title) in enumerate(headings):
        end = headings[i + 1][0] if i + 1 < len(headings) else len(text)
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({"title": title, "text": chunk_text})

    if not chunks:
        return None

    total_len = sum(len(c["text"]) for c in chunks)
    largest = max(len(c["text"]) for c in chunks)
    if total_len == 0 or (largest / total_len) > MAX_SINGLE_CHUNK_SHARE:
        return None

    merged: list[dict] = []
    for chunk in chunks:
        if merged and len(chunk["text"]) < MIN_CHUNK_CHARS:
            merged[-1]["text"] += "\n\n" + chunk["text"]
        else:
            merged.append(chunk)

    return merged


def _split_by_size(text: str) -> list[dict]:
    paragraphs = re.split(r"\n\s*\n", text)
    pieces: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) <= FALLBACK_CHUNK_CHARS:
            pieces.append(para)
        else:
            for start in range(0, len(para), FALLBACK_CHUNK_CHARS):
                pieces.append(para[start:start + FALLBACK_CHUNK_CHARS])

    chunks: list[dict] = []
    current: list[str] = []
    current_len = 0
    for piece in pieces:
        if current and current_len + len(piece) > FALLBACK_CHUNK_CHARS:
            chunks.append({"title": None, "text": "\n\n".join(current)})
            current, current_len = [], 0
        current.append(piece)
        current_len += len(piece)

    if current:
        chunks.append({"title": None, "text": "\n\n".join(current)})

    return chunks or [{"title": None, "text": text}]


def split_document(text: str) -> list[dict]:
    if not text.strip():
        return []

    chunks = _split_by_headings(text)
    if chunks is not None:
        return chunks
    return _split_by_size(text)