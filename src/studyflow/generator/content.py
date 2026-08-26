"""
generator/content.py — Study material generation per topic and subtopic.

For each topic (as already structured by process/classifier.py's persistent
index — see process/analyzer.build_index) generates:
    - Per subtopic: explanation, key concepts table
    - Flashcards (term -> definition)
    - Multiple-choice questions with explanation

Subtopics are no longer detected here via a separate LLM call: they come
pre-defined (id, title, merged content, sources) from the index, since the
classifier already decided the structure incrementally as documents were
added. This module's job is purely to turn that structure into study
material.
"""

import logging

from core.llm import LLM
from core.json_utils import parse_llm_json


_SYSTEM = (
    "You are an expert professor creating detailed study material. "
    "Always respond with valid JSON only — no extra text outside the JSON. "
    "CRITICAL: respond in the SAME language as the input content."
)

_SYSTEM_TITLE = (
    "You are an expert at naming academic study material concisely. "
    "Always respond with valid JSON only. "
    "CRITICAL: respond in the SAME language as the input content."
)


def _prompt_subtopic(subtopic_title: str, topic_title: str, subtopic_text: str) -> str:
    excerpt = subtopic_text[:8000]
    return f"""Generate detailed study content for this subtopic.

TOPIC: {topic_title}
SUBTOPIC: {subtopic_title}
MATERIAL:
{excerpt}

Return ONLY this JSON (no ```json, no extra text). Respond in the SAME language as the material:
{{
  "explanation": "Detailed explanation of this subtopic in 3-5 paragraphs. Be thorough and pedagogical.",
  "concepts": [
    {{"concept": "Term or concept", "definition": "Clear and precise definition"}}
  ]
}}

Rules:
- explanation must be detailed and cover the subtopic fully (minimum 3 paragraphs)
- concepts: 4-8 key terms with precise definitions"""


def _prompt_questions(topic_title: str, topic_text: str, n: int) -> str:
    excerpt = topic_text[:8000]
    return f"""Generate {n} multiple-choice questions for this topic.

TOPIC: {topic_title}
MATERIAL:
{excerpt}

Return ONLY this JSON (no ```json, no extra text). Respond in the SAME language as the material:
{{
  "questions": [
    {{
      "question": "Clear question text",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct": 0,
      "explanation": "Why this answer is correct and why the others are not (2-3 sentences)."
    }}
  ]
}}

Rules:
- correct is the index (0-3) of the correct option
- Wrong options must be plausible, not obviously false
- Vary difficulty: conceptual, application and analysis
- No repeated or similar questions"""


def _prompt_flashcards(topic_title: str, topic_text: str) -> str:
    excerpt = topic_text[:8000]
    return f"""Generate flashcards for this topic.

TOPIC: {topic_title}
MATERIAL:
{excerpt}

Return ONLY this JSON (no ```json, no extra text). Respond in the SAME language as the material:
{{
  "flashcards": [
    {{"front": "Term or concept", "back": "Definition or key explanation"}}
  ]
}}

Rules:
- Generate 8-15 flashcards
- front: a single term, concept or question
- back: concise but complete answer (1-3 sentences max)"""


def _prompt_subtopic_repair(subtopic_title: str, topic_title: str, subtopic_text: str) -> str:
    """A deliberately simpler prompt/schema used only as a second attempt when
    the full subtopic prompt failed to produce valid JSON. Smaller ask, smaller
    JSON shape — more likely to succeed on a weak/small model."""
    excerpt = subtopic_text[:5000]
    return f"""Write a short study explanation for this subtopic.

TOPIC: {topic_title}
SUBTOPIC: {subtopic_title}
MATERIAL:
{excerpt}

Return ONLY this JSON, nothing else. Respond in the SAME language as the material:
{{"explanation": "2-3 short paragraphs explaining this subtopic clearly."}}"""


def _prompt_title(topic_titles: list[str]) -> str:
    listed = "\n".join(f"- {t}" for t in topic_titles)
    return f"""These are the topics covered in a set of study material:
{listed}

Return ONLY this JSON (no extra text), in the SAME language as the topic titles above:
{{"title": "A short, descriptive title (max ~8 words) for the whole set of material"}}"""


def repair_empty_subtopics(
    topic_title: str, subtopics: list[dict], llm: LLM,
    logger: logging.Logger | None = None, recorder=None,
) -> list[dict]:
    """Post-check pass, run after the normal generation loop: any subtopic that
    came back with no explanation and no concepts (the model failed to return
    usable JSON for it, even after parse_llm_json's own retries) gets one more,
    simpler attempt. If that also comes back empty, the subtopic is dropped
    from the topic entirely — better than shipping a blank or apologetic
    section in the final HTML."""
    repaired = []
    for sub in subtopics:
        has_content = bool((sub.get("explanation") or "").strip()) or bool(sub.get("concepts"))
        if has_content:
            repaired.append(sub)
            continue

        print(f"      🔧 Repairing empty subtopic: {sub['title']}")
        data = parse_llm_json(
            llm, _prompt_subtopic_repair(sub["title"], topic_title, sub.get("_source_text", "")),
            system=_SYSTEM, fallback={}, max_tokens=1000, temperature=0.2, retries=1,
            logger=logger, recorder=recorder, task="subtopic_repair",
        )
        explanation = (data.get("explanation") or "").strip()
        if explanation:
            sub["explanation"] = explanation
            repaired.append(sub)
            if logger:
                logger.info("subtopic_repaired", extra={"topic": topic_title, "subtopic": sub["title"]})
        else:
            print(f"      🗑️  Dropped subtopic (no content after repair attempt): {sub['title']}")
            if logger:
                logger.warning(
                    "subtopic_dropped_empty", extra={"topic": topic_title, "subtopic": sub["title"]}
                )
    return repaired


def generate_topic(
    topic: dict, llm: LLM, n_questions: int,
    logger: logging.Logger | None = None, recorder=None,
) -> dict:
    """`topic` comes straight from the project index:
    {"id": ..., "title": ..., "subtopics": [{"id", "title", "content", "sources"}, ...]}
    Subtopics are already decided — no detection call happens here.
    """
    topic_title = topic["title"]
    subtopics_raw = topic.get("subtopics", [])
    if not subtopics_raw:
        # Shouldn't normally happen (the index never keeps empty topics), but
        # guard anyway so generation never blows up on a stray topic.
        subtopics_raw = [{"id": "sub_1", "title": topic_title, "content": ""}]

    topic_text = "\n\n".join(s.get("content", "") for s in subtopics_raw)

    subtopics_generated = []
    for sub in subtopics_raw:
        sub_title = sub["title"]
        sub_id = sub["id"]
        sub_text = sub.get("content", "")
        print(f"      Subtopic: {sub_title}")
        data = parse_llm_json(
            llm, _prompt_subtopic(sub_title, topic_title, sub_text), system=_SYSTEM,
            fallback={"explanation": "", "concepts": []},
            max_tokens=2500, temperature=0.3, logger=logger,
            recorder=recorder, task="subtopic",
        )
        subtopics_generated.append({
            "id": sub_id,
            "title": sub_title,
            "explanation": data.get("explanation", ""),
            "concepts": data.get("concepts", []),
            "_source_text": sub_text,  # kept only for the repair pass below
        })

    subtopics_generated = repair_empty_subtopics(
        topic_title, subtopics_generated, llm, logger=logger, recorder=recorder,
    )
    for sub in subtopics_generated:
        sub.pop("_source_text", None)

    print(f"    Generating {n_questions} questions for: {topic_title}")
    q_data = parse_llm_json(
        llm, _prompt_questions(topic_title, topic_text, n_questions), system=_SYSTEM,
        fallback={"questions": []}, max_tokens=3000, temperature=0.5, logger=logger,
        recorder=recorder, task="questions",
    )

    print(f"    Generating flashcards for: {topic_title}")
    fc_data = parse_llm_json(
        llm, _prompt_flashcards(topic_title, topic_text), system=_SYSTEM,
        fallback={"flashcards": []}, max_tokens=1500, temperature=0.3, logger=logger,
        recorder=recorder, task="flashcards",
    )

    return {
        "id": topic["id"],
        "title": topic_title,
        "subtopics": subtopics_generated,
        "questions": q_data.get("questions", []),
        "flashcards": fc_data.get("flashcards", []),
    }


def generate_title(index: dict, llm: LLM, logger: logging.Logger | None = None, recorder=None) -> str:
    topic_titles = [t["title"] for t in index.get("topics", [])]
    if not topic_titles:
        return "Material de estudio"
    if len(topic_titles) == 1:
        return topic_titles[0]
    data = parse_llm_json(
        llm, _prompt_title(topic_titles), system=_SYSTEM_TITLE,
        fallback={"title": topic_titles[0]}, max_tokens=100, temperature=0.3,
        logger=logger, recorder=recorder, task="title",
    )
    return (data.get("title") or topic_titles[0]).strip()


def generate_material(
    index: dict, llm: LLM, questions_per_topic: int = 8,
    logger: logging.Logger | None = None, recorder=None,
) -> dict:
    topics = index.get("topics", [])
    sources = sorted({s for t in topics for sub in t.get("subtopics", []) for s in sub.get("sources", [])})

    print(f"\n  Generando título del material...")
    title = generate_title(index, llm, logger=logger, recorder=recorder)

    print(f"  Generating material for '{title}' ({len(topics)} topics)...")

    generated = []
    for i, topic in enumerate(topics, 1):
        print(f"\n  [{i}/{len(topics)}] {topic['title']}")
        generated.append(
            generate_topic(
                topic, llm, n_questions=questions_per_topic,
                logger=logger, recorder=recorder,
            )
        )

    return {
        "title": title,
        "topics": generated,
        "sources": sources,
        "stats": {
            "n_topics": len(generated),
            "n_questions": sum(len(t["questions"]) for t in generated),
        },
    }