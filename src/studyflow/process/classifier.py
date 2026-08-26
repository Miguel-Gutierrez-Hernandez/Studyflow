"""
process/classifier.py — Incremental document classification into a
persistent, growing project index.

Implements the three-prompt pipeline that folds a *new* document into the
project's knowledge index, one document at a time:

    1. El Lector      (_read_document)  — extract explicit topic guidance
                                           (if the document literally states
                                           "Tema 1: X"), a topic/subtopic
                                           guess, and key concepts.
    2. El Enrutador    (_route_document) — given the current index, decide
                                           where the document belongs: an
                                           existing topic/subtopic, a new
                                           subtopic under an existing topic,
                                           or a brand new topic.
    3. El Redactor     (_merge_content)  — merge the new text into whatever
                                           content already lives at that
                                           path, without duplicating ideas.

classify_document() runs all three for one file and returns the updated
index. check_saturation() is called once after all files in a run have been
classified and promotes any subtopic that has grown too large into its own
top-level topic.

No fixed catalogue of topics is baked in anywhere here — every topic/subtopic
title comes from the documents themselves (explicit guidance) or from the
model's best-effort classification against whatever the index already
contains. This intentionally supports notes on *any* subject.
"""

import difflib
import logging
import re
import unicodedata

import config
from core.llm import LLM
from core.json_utils import parse_llm_json

# A subtopic gets promoted to its own top-level topic once it has absorbed
# this much merged text, or this many source documents — whichever comes
# first. Overridable from config.py (falls back to these defaults if not set
# there, so this works even without touching config.py).
#
# NOTE on tuning SATURATION_CHAR_THRESHOLD: generator/content.py truncates a
# subtopic's merged content to its first 8000 characters when generating the
# explanation/questions/flashcards for it (excerpt = text[:8000]). If a
# subtopic is allowed to grow well past 8000 chars before saturation kicks
# in, the tail of its content is silently ignored during generation even
# though it's sitting right there in the index. Keeping
# SATURATION_CHAR_THRESHOLD close to (or at/under) that 8000 figure — rather
# than letting it drift much higher — avoids that silent truncation. 9000 is
# already a bit past it; lowering it to ~7500-8000 is a reasonable tweak.
# SATURATION_DOC_THRESHOLD is more about topical breadth than size: a
# subtopic that has absorbed content from 5+ separate source documents is
# usually broad enough to deserve being its own topic. That one's more a
# matter of taste — raise it if your projects tend to have many short,
# closely related documents that genuinely belong together.
SATURATION_CHAR_THRESHOLD = getattr(config, "SATURATION_CHAR_THRESHOLD", 9000)
SATURATION_DOC_THRESHOLD = getattr(config, "SATURATION_DOC_THRESHOLD", 4)

# Cap on how many subtopics are listed per topic when the current index is
# shown to the Enrutador. Without this, a project with many documents in one
# topic makes that single prompt grow unbounded. Past the cap we just show a
# count of the rest — the router still knows the topic exists and roughly
# how big it already is, which is enough context for routing decisions.
INDEX_SUMMARY_MAX_SUBTOPICS = getattr(config, "INDEX_SUMMARY_MAX_SUBTOPICS", 10)

_SYSTEM = (
    "Eres un asistente experto en organizar y clasificar material académico. "
    "Responde siempre con JSON válido, nada de texto fuera del JSON. "
    "IMPORTANTE: responde en el MISMO idioma que el contenido de entrada."
)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:40] or "tema"


def _normalize(text: str) -> str:
    """Lowercase, strip accents, and collapse whitespace/punctuation — used
    to compare titles independently of casing/accent variation (e.g.
    "Estadística" vs "estadistica" vs "ESTADÍSTICA")."""
    nfkd = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", without_accents.lower()).strip()


# Similarity ratio (0-1, via difflib) above which two titles are treated as
# the same thing rather than genuinely different topics/subtopics. This is a
# safety net on top of the router's own judgement — the LLM is asked not to
# create near-duplicates, but casing/accent/wording drift can still slip
# through, especially on a small local model.
DUPLICATE_TITLE_SIMILARITY = getattr(config, "DUPLICATE_TITLE_SIMILARITY", 0.87)


def _find_similar(title: str, candidates: list[dict]) -> dict | None:
    """Return the candidate dict (topic or subtopic) whose title best matches
    `title` after normalization, if the match is close enough — else None.
    `candidates` is a list of dicts each with a "title" key."""
    if not candidates:
        return None
    norm_title = _normalize(title)
    best, best_ratio = None, 0.0
    for c in candidates:
        norm_c = _normalize(c["title"])
        if norm_title == norm_c:
            return c  # exact match after normalization — no need to look further
        ratio = difflib.SequenceMatcher(None, norm_title, norm_c).ratio()
        if ratio > best_ratio:
            best, best_ratio = c, ratio
    return best if best_ratio >= DUPLICATE_TITLE_SIMILARITY else None


def _new_id(existing_ids: set[str], base: str) -> str:
    slug = _slugify(base)
    candidate = slug
    n = 2
    while candidate in existing_ids:
        candidate = f"{slug}_{n}"
        n += 1
    return candidate


# ── Prompt 1: El Lector ──────────────────────────────────────────────────

def _read_document(doc_name: str, text: str, llm: LLM, logger=None, recorder=None) -> dict:
    excerpt = text[:10000]
    prompt = f"""Analiza el siguiente documento y extrae su estructura temática.

ARCHIVO: {doc_name}
CONTENIDO:
{excerpt}

Devuelve SOLO este JSON (sin ```json, sin texto extra), en el MISMO idioma del contenido:
{{
  "explicit_topic": "Si el documento indica EXPLÍCITAMENTE un título/tema (ej. 'Tema 1: X', un encabezado o título de sección claro), cópialo tal cual. Si no hay ninguna indicación explícita, usa null.",
  "explicit_subtopic": "Igual que arriba pero para un subtema explícito, o null si no hay.",
  "topic_guess": "Si NO hay guía explícita, tu mejor estimación de a qué tema/disciplina pertenece este contenido (título corto y descriptivo, en el idioma del contenido).",
  "subtopic_guess": "Tu mejor estimación de subtema dentro de ese tema (título corto).",
  "key_concepts": ["lista de 3-8 conceptos clave que aparecen en el documento"]
}}

Reglas:
- explicit_topic / explicit_subtopic SOLO si el propio documento lo declara literalmente (no los inventes ni los deduzcas).
- Ante ambigüedad de disciplina (p. ej. contenido de negocio con jerga técnica), prioriza la disciplina/asignatura sobre el sujeto superficial."""

    fallback = {
        "explicit_topic": None,
        "explicit_subtopic": None,
        "topic_guess": "Contenido general",
        "subtopic_guess": None,
        "key_concepts": [],
    }
    return parse_llm_json(
        llm, prompt, system=_SYSTEM, fallback=fallback, max_tokens=700,
        temperature=0.2, logger=logger, recorder=recorder, task="lector",
    )


# ── Prompt 2: El Enrutador ───────────────────────────────────────────────

def _format_index(index: dict) -> str:
    if not index.get("topics"):
        return "(índice vacío, no hay temas todavía — este será el primer documento)"
    lines = []
    for t in index["topics"]:
        subtopics = t.get("subtopics", [])
        lines.append(f'- topic_id="{t["id"]}" · "{t["title"]}" ({len(subtopics)} subtema(s))')
        shown = subtopics[:INDEX_SUMMARY_MAX_SUBTOPICS]
        for s in shown:
            n_docs = len(s.get("sources", []))
            lines.append(f'    - subtopic_id="{s["id"]}" · "{s["title"]}" ({n_docs} doc(s) ya integrados)')
        remaining = len(subtopics) - len(shown)
        if remaining > 0:
            lines.append(f"    - ... y {remaining} subtema(s) más en este tema")
    return "\n".join(lines)


def _route_document(doc_summary: dict, index: dict, llm: LLM, logger=None, recorder=None) -> dict:
    index_str = _format_index(index)
    prompt = f"""Eres el enrutador de una base de conocimiento incremental. Decide dónde encaja
el documento nuevo dentro del ÍNDICE actual.

ÍNDICE ACTUAL:
{index_str}

DOCUMENTO A CLASIFICAR:
- Tema explícito indicado por el documento: {doc_summary.get("explicit_topic") or "(ninguno)"}
- Subtema explícito indicado: {doc_summary.get("explicit_subtopic") or "(ninguno)"}
- Tema estimado (si no hay guía explícita): {doc_summary.get("topic_guess")}
- Subtema estimado: {doc_summary.get("subtopic_guess")}
- Conceptos clave: {", ".join(doc_summary.get("key_concepts", [])) or "(ninguno)"}

Devuelve SOLO este JSON (sin texto extra):
{{
  "action": "existing_subtopic" | "new_subtopic" | "new_topic",
  "topic_id": "id del tema existente elegido (null si action == new_topic)",
  "topic_title": "título del tema (solo se usa si action == new_topic)",
  "subtopic_id": "id del subtema existente elegido (solo si action == existing_subtopic, si no null)",
  "subtopic_title": "título del subtema — el existente si reutilizas uno, o el nuevo título si creas uno"
}}

Reglas de decisión, en este orden de prioridad:
1. Guía explícita: si el documento declara un tema/subtema explícito y ya existe algo equivalente en el
   índice (aunque el título no sea idéntico palabra por palabra), reutiliza ese topic_id/subtopic_id.
2. Pertenencia lógica: si el contenido es un subconjunto claro de un tema ya existente en el índice,
   clasifícalo como subtema de ese tema — existing_subtopic si el subtema ya existe y encaja bien,
   new_subtopic si el tema existe pero esto es un subtema nuevo dentro de él.
3. Tema nuevo: SOLO si el contenido no encaja razonablemente en ningún tema existente del índice.
   No crees un tema nuevo solo porque el título no coincide exactamente con uno existente.
4. Ante ambigüedad de disciplina, prioriza la disciplina/asignatura sobre el sujeto superficial
   (ej. "el mercado de la IA" va con Economía, no con Tecnología, si el índice ya tiene un tema de Economía).
5. No crees temas ni subtemas casi duplicados de uno ya existente — reutiliza el que ya englobe la idea.
   El objetivo es un índice compacto, no uno con un tema por documento."""

    fallback = {
        "action": "new_topic",
        "topic_id": None,
        "topic_title": doc_summary.get("explicit_topic") or doc_summary.get("topic_guess") or "Contenido general",
        "subtopic_id": None,
        "subtopic_title": doc_summary.get("explicit_subtopic") or doc_summary.get("subtopic_guess") or "General",
    }
    return parse_llm_json(
        llm, prompt, system=_SYSTEM, fallback=fallback, max_tokens=400,
        temperature=0.1, logger=logger, recorder=recorder, task="enrutador",
    )


# ── Prompt 3: El Redactor ────────────────────────────────────────────────

def _merge_content(new_text: str, existing_text: str, llm: LLM, logger=None, recorder=None) -> str:
    if not existing_text.strip():
        # Nothing to merge with yet — first document landing at this path.
        return new_text.strip()

    prompt = f"""Fusiona el TEXTO NUEVO dentro del TEXTO HISTÓRICO, produciendo un único documento
unificado, sin perder información y sin duplicar conceptos ya cubiertos.

TEXTO HISTÓRICO:
{existing_text[:9000]}

TEXTO NUEVO:
{new_text[:9000]}

Devuelve SOLO el texto fusionado en plano (sin JSON, sin comentarios ni encabezados tipo
"Texto fusionado:"), en el MISMO idioma del contenido, con un formato jerárquico limpio
(párrafos y listas si procede). No repitas explicaciones ya presentes en el texto histórico;
añade solo lo que sea nuevo o lo complemente."""

    try:
        response = llm.chat(prompt, system=_SYSTEM, max_tokens=4000, temperature=0.2)
        if recorder:
            # DistillationRecorder.record() expects a parsed dict as the
            # response, not raw text — the Redactor's output isn't JSON like
            # the other tasks, so it's wrapped here just for recording.
            recorder.record("redactor", _SYSTEM, prompt, {"merged_text": response}, model=llm.model)
        merged = (response or "").strip()
        return merged if merged else (existing_text + "\n\n" + new_text).strip()
    except Exception as e:
        if logger:
            logger.warning("merge_failed", extra={"error": str(e)})
        # Fail safe: never lose content — just concatenate.
        return (existing_text + "\n\n" + new_text).strip()


# ── Orchestration ─────────────────────────────────────────────────────────

def classify_document(
    doc_name: str, text: str, index: dict, llm: LLM,
    logger: logging.Logger | None = None, recorder=None,
) -> dict:
    """Run Lector -> Enrutador -> Redactor for one document and return the
    updated index (topics/subtopics mutated in place, dict returned for
    convenience/chaining)."""
    topics = index.setdefault("topics", [])
    existing_topic_ids = {t["id"] for t in topics}

    summary = _read_document(doc_name, text, llm, logger=logger, recorder=recorder)
    route = _route_document(summary, index, llm, logger=logger, recorder=recorder)

    action = route.get("action", "new_topic")

    topic = None
    if action in ("existing_subtopic", "new_subtopic") and route.get("topic_id"):
        topic = next((t for t in topics if t["id"] == route["topic_id"]), None)

    if topic is None:
        # action == new_topic, or the model referenced a topic_id that
        # doesn't actually exist — fall back to creating a fresh topic,
        # unless a near-duplicate of it already exists in the index (safety
        # net for casing/accent/wording drift the router itself missed).
        title = (
            route.get("topic_title")
            or summary.get("explicit_topic")
            or summary.get("topic_guess")
            or "Contenido general"
        )
        duplicate = _find_similar(title, topics)
        if duplicate is not None:
            if logger:
                logger.info("duplicate_topic_avoided", extra={
                    "proposed_title": title, "reused_topic": duplicate["title"],
                })
            topic = duplicate
            action = "existing_subtopic" if topic["subtopics"] else "new_subtopic"
        else:
            topic = {"id": _new_id(existing_topic_ids, title), "title": title, "subtopics": []}
            topics.append(topic)
            action = "new_subtopic"  # this topic has no subtopics yet — must create one

    existing_sub_ids = {s["id"] for s in topic["subtopics"]}
    subtopic = None
    if action == "existing_subtopic" and route.get("subtopic_id"):
        subtopic = next((s for s in topic["subtopics"] if s["id"] == route["subtopic_id"]), None)

    if subtopic is None:
        sub_title = (
            route.get("subtopic_title")
            or summary.get("explicit_subtopic")
            or summary.get("subtopic_guess")
            or topic["title"]
        )
        duplicate_sub = _find_similar(sub_title, topic["subtopics"])
        if duplicate_sub is not None:
            if logger:
                logger.info("duplicate_subtopic_avoided", extra={
                    "topic": topic["title"], "proposed_title": sub_title,
                    "reused_subtopic": duplicate_sub["title"],
                })
            subtopic = duplicate_sub
        else:
            subtopic = {
                "id": _new_id(existing_sub_ids, sub_title),
                "title": sub_title,
                "content": "",
                "sources": [],
            }
            topic["subtopics"].append(subtopic)

    merged = _merge_content(text, subtopic.get("content", ""), llm, logger=logger, recorder=recorder)
    subtopic["content"] = merged
    if doc_name not in subtopic["sources"]:
        subtopic["sources"].append(doc_name)

    if logger:
        logger.info("document_classified", extra={
            "file": doc_name, "topic": topic["title"], "subtopic": subtopic["title"], "action": action,
        })

    return index


def move_document(
    filename: str, text: str, index: dict, target_topic_id: str,
    target_subtopic_title: str | None, llm: LLM,
    logger: logging.Logger | None = None, recorder=None,
) -> dict:
    """Manually reassign a document that the router put in the wrong place —
    the escape hatch for when classify_document's automatic decision was
    wrong and needs a human override, without having to hand-edit index.json.

    Detaches `filename` from wherever it currently lives in the index, then
    (re-)merges its original extracted text into the chosen target
    topic/subtopic (created if it doesn't exist yet, or reused via the same
    fuzzy-title matching used during normal classification).

    IMPORTANT LIMITATION: if the document being moved shared a subtopic with
    other documents, its contribution can't be cleanly un-merged from that
    subtopic's already-fused text (the Redactor doesn't track which sentence
    came from which source). In that case the source is removed from the
    subtopic's `sources` list (so it's no longer counted or re-classified as
    belonging there) but the old subtopic's *content* is left untouched —
    you may want to regenerate that subtopic's content by re-running the
    documents that still belong there, if the leftover text bothers you. If
    the moved document was the ONLY source for its old subtopic, that
    subtopic (and its parent topic, if now empty) is removed entirely
    instead, since in that case all of its content really did belong to the
    document being moved.
    """
    topics = index.setdefault("topics", [])

    # 1. Detach from wherever it currently lives.
    for t in list(topics):
        for s in list(t.get("subtopics", [])):
            if filename in s.get("sources", []):
                s["sources"].remove(filename)
                if not s["sources"]:
                    t["subtopics"].remove(s)
                    if logger:
                        logger.info("subtopic_removed_after_move", extra={
                            "topic": t["title"], "subtopic": s["title"], "file": filename,
                        })
                elif logger:
                    logger.warning("move_leaves_merged_content_behind", extra={
                        "topic": t["title"], "subtopic": s["title"], "file": filename,
                    })
        if not t.get("subtopics"):
            topics.remove(t)

    # 2. Find the target topic — must already exist (use classify_document /
    #    a normal pipeline run to create genuinely new topics; this is for
    #    correcting a misroute, not for hand-building an index from scratch).
    target_topic = next((t for t in topics if t["id"] == target_topic_id), None)
    if target_topic is None:
        available = ", ".join(f'{t["id"]} ("{t["title"]}")' for t in topics) or "(ninguno)"
        raise ValueError(
            f"No existe ningún tema con id '{target_topic_id}' en el índice. "
            f"Temas disponibles: {available}"
        )

    # 3. Find or create the target subtopic.
    existing_sub_ids = {s["id"] for s in target_topic["subtopics"]}
    target_sub = _find_similar(target_subtopic_title, target_topic["subtopics"]) if target_subtopic_title else None
    if target_sub is None:
        title = target_subtopic_title or target_topic["title"]
        target_sub = {"id": _new_id(existing_sub_ids, title), "title": title, "content": "", "sources": []}
        target_topic["subtopics"].append(target_sub)

    # 4. Merge the document's original text into the target subtopic.
    merged = _merge_content(text, target_sub.get("content", ""), llm, logger=logger, recorder=recorder)
    target_sub["content"] = merged
    if filename not in target_sub["sources"]:
        target_sub["sources"].append(filename)

    if logger:
        logger.info("document_moved", extra={
            "file": filename, "target_topic": target_topic["title"], "target_subtopic": target_sub["title"],
        })

    return index


def check_saturation(index: dict, logger: logging.Logger | None = None) -> dict:
    """Promote any subtopic that has grown past the size/doc-count threshold
    into its own top-level topic (Regla de Saturación). Its own future
    growth is then classified independently by the router, instead of
    continuing to swell the topic it was born in."""
    topics = index.get("topics", [])
    existing_topic_ids = {t["id"] for t in topics}
    promoted = []

    for topic in topics:
        keep = []
        for sub in topic.get("subtopics", []):
            oversized = (
                len(sub.get("content", "")) > SATURATION_CHAR_THRESHOLD
                or len(sub.get("sources", [])) > SATURATION_DOC_THRESHOLD
            )
            # Never fully drain a topic to zero subtopics via promotion —
            # a topic with a single (big) subtopic just stays as-is.
            if oversized and len(topic["subtopics"]) > 1:
                new_topic = {
                    "id": _new_id(existing_topic_ids, sub["title"]),
                    "title": sub["title"],
                    "subtopics": [{
                        "id": _new_id(set(), sub["title"] + "_general"),
                        "title": sub["title"],
                        "content": sub["content"],
                        "sources": sub["sources"],
                    }],
                }
                existing_topic_ids.add(new_topic["id"])
                promoted.append(new_topic)
                if logger:
                    logger.info("subtopic_promoted", extra={
                        "from_topic": topic["title"], "subtopic": sub["title"],
                    })
            else:
                keep.append(sub)
        topic["subtopics"] = keep

    index["topics"] = [t for t in topics if t["subtopics"]] + promoted
    return index


def classified_sources(index: dict) -> set[str]:
    """All filenames already folded into the index, across every
    topic/subtopic — used by the pipeline to skip re-classifying files from
    a previous run."""
    seen = set()
    for t in index.get("topics", []):
        for s in t.get("subtopics", []):
            seen.update(s.get("sources", []))
    return seen