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
) -> dict:
    """Fold every (new) document in `texts` into the project's persistent
    index, one at a time — writing the index to disk after EACH document,
    not just once at the end.

    This matters because classification is a multi-call LLM process per
    document (Lector -> Enrutador -> Redactor): if it's interrupted midway
    through a batch (Ollama drops, the process is killed, a document causes
    an error), any document already folded in before the interruption stays
    saved instead of being silently lost and re-billed on the next run.

    A failure on one document (extraction error already skipped upstream, or
    an unexpected exception during classification) is logged and skipped
    rather than aborting the whole batch — so one bad file doesn't cost you
    the documents around it.

    Documents whose filename is already present in the index's sources are
    skipped — they were folded in by a previous run of the pipeline.

    `texts` maps filename -> raw extracted text (as produced by
    consumption.extractor.extract_all / project.read_extracted). Extraction
    errors (values starting with "[ERROR:") are skipped.
    """
    index = project.read_index()
    already_classified = classified_sources(index)

    # Sorted by filename rather than dict insertion order (which follows
    # extraction order) so the resulting index is deterministic run to run —
    # otherwise which document "arrives first" at an ambiguous topic could
    # change depending on extraction timing/order and nudge classification.
    for name in sorted(texts.keys()):
        text = texts[name]
        if text.startswith("[ERROR:"):
            continue
        if name in already_classified:
            continue
        cleaned = clean_text(text)
        if not cleaned:
            continue

        print(f"    Clasificando: {name}")
        try:
            index = classify_document(name, cleaned, index, llm, logger=logger, recorder=recorder)
        except Exception as e:
            print(f"      ⚠️  Error clasificando {name}: {e}")
            if logger:
                logger.error("classification_failed", extra={"file": name, "error": str(e)})
            continue
        finally:
            project.write_index(index)

    index = check_saturation(index, logger=logger)
    project.write_index(index)
    return index