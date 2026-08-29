"""
process/analyzer.py — Text cleaning + incremental index building.

Topic/subtopic detection used to happen here as a single batch call over all
merged text (detect_topics + detect_subtopics). That approach is what caused
over-fragmented topic lists on multi-document input, since the model was
asked to invent a flat "3-8 topics" grouping with no persistent structure to
anchor against.

That responsibility now lives in process/classifier.py, which classifies one
document at a time against a persistent, growing project index (Lector ->
Enrutador -> Redactor). This module keeps text cleaning, and exposes
build_index() as the thin orchestration loop the pipeline calls.
"""

import logging
import re

from core.llm import LLM
from process.classifier import classify_document, check_saturation, classified_sources
from process.chunker import split_document
from utils.project import Project


def clean_text(text: str) -> str:
    text = re.sub(r"[^\S\n\t ]+", " ", text)
    text = text.replace("\t", "  ")
    lines = [l.rstrip() for l in text.split("\n")]
    result, blanks = [], 0
    for line in lines:
        if line.strip() == "":
            blanks += 1
            if blanks <= 2:
                result.append("")
        else:
            blanks = 0
            result.append(line)
    return "\n".join(result).strip()


def build_index(
    texts: dict[str, str], project: Project, llm: LLM,
    logger: logging.Logger | None = None, recorder=None,
) -> tuple[dict, set[str]]:
    """Fold every (new) document in `texts` into the project's persistent
    index. Each document is first split into topic-sized pieces (see
    process.chunker.split_document) — a long multi-section document (e.g. a
    45-page unit PDF with its own "Tema 1", "Tema 2"... structure) would
    otherwise be classified as a SINGLE topic/subtopic no matter how much
    internal structure it actually has, and generator/content.py would only
    ever see the first ~8000 characters of it. Splitting first means each
    section is classified — and later generates content — independently.

    Each chunk is classified via process.classifier.classify_document, which
    first tries a fast, no-LLM match (filename or leading content/heading
    against existing topic titles) before falling back to the full
    Lector/Enrutador LLM flow — see classify_document's docstring.

    A document that doesn't need splitting (short, or no internal structure
    detected) comes back from split_document() as a single chunk, so its
    source id in the index stays the plain filename, exactly as before. Only
    documents that DO get split produce chunk-suffixed ids ("file.pdf#2",
    "file.pdf#3", ...) in each subtopic's `sources` list — inspect_index.py
    shows these as-is.

    The index is written to disk after EACH chunk, not just once at the end
    — classification is a multi-call LLM process per chunk, and interrupting
    a long document mid-way (Ollama drops, the process is killed) should not
    lose everything already folded in before that point.

    A failure on one chunk is logged and skipped rather than aborting the
    whole run — one bad section doesn't cost you the ones around it.

    Documents/chunks whose id is already present in the index's sources are
    skipped — they were folded in by a previous run of the pipeline.

    `texts` maps filename -> raw extracted text (as produced by
    consumption.extractor.extract_all / project.read_extracted). Extraction
    errors (values starting with "[ERROR:") are skipped.

    Returns (index, touched_topic_ids) — touched_topic_ids is every topic
    that received new/changed content in this call (via classification or
    saturation promotion), so the pipeline knows which topics' study
    material actually needs regenerating (see generator.content.generate_material's
    `topics_to_regenerate` parameter) instead of redoing everything.
    """
    index = project.read_index()
    already_classified = classified_sources(index)
    touched_topic_ids: set[str] = set()

    # Sorted by filename rather than dict insertion order (which follows
    # extraction order) so the resulting index is deterministic run to run.
    for name in sorted(texts.keys()):
        text = texts[name]
        if text.startswith("[ERROR:"):
            continue
        cleaned = clean_text(text)
        if not cleaned:
            continue

        chunks = split_document(cleaned)
        multi = len(chunks) > 1
        if multi:
            print(f"    {name}: dividido en {len(chunks)} secciones para clasificar")

        for i, chunk in enumerate(chunks, 1):
            chunk_id = f"{name}#{i}" if multi else name
            if chunk_id in already_classified:
                continue

            label = f' ("{chunk["title"]}")' if chunk.get("title") else ""
            print(f"    Clasificando: {chunk_id}{label}")
            try:
                index = classify_document(
                    chunk_id, chunk["text"], index, llm, logger=logger, recorder=recorder,
                    source_filename=name, chunk_title=chunk.get("title"),
                )
            except Exception as e:
                print(f"      ⚠️  Error clasificando {chunk_id}: {e}")
                if logger:
                    logger.error("classification_failed", extra={"file": chunk_id, "error": str(e)})
                continue
            finally:
                project.write_index(index)

            tid = _topic_id_for_source(index, chunk_id)
            if tid:
                touched_topic_ids.add(tid)

    # Saturation can also change which topic a subtopic's content lives
    # under — track that as "touched" too, both the newly-promoted topic
    # and any existing topic whose set of subtopics changed as a result.
    subtopic_ids_before = {t["id"]: {s["id"] for s in t["subtopics"]} for t in index["topics"]}
    index = check_saturation(index, logger=logger)
    project.write_index(index)
    for t in index["topics"]:
        subs_now = {s["id"] for s in t["subtopics"]}
        if t["id"] not in subtopic_ids_before or subtopic_ids_before[t["id"]] != subs_now:
            touched_topic_ids.add(t["id"])

    return index, touched_topic_ids


def _topic_id_for_source(index: dict, source_id: str) -> str | None:
    """Find which topic a given source id (filename or "filename#N" chunk
    id) currently lives under, by checking every subtopic's sources list."""
    for t in index.get("topics", []):
        for s in t.get("subtopics", []):
            if source_id in s.get("sources", []):
                return t["id"]
    return None