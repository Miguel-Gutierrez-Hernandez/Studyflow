"""
generator/content.py — Study material generation per topic and subtopic.

For each topic generates:
    - Per subtopic: explanation, key concepts table
    - Flashcards (term -> definition)
    - Multiple-choice questions with explanation
"""

import logging

from core.llm import LLM
from core.json_utils import parse_llm_json


_SYSTEM = (
    "You are an expert professor creating detailed study material. "
    "Always respond with valid JSON only — no extra text outside the JSON. "
    "CRITICAL: respond in the SAME language as the input content."
)


def _prompt_subtopic(subtopic_title: str, topic_title: str, full_text: str) -> str:
    excerpt = full_text[:8000]
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


def _prompt_questions(topic_title: str, full_text: str, n: int) -> str:
    excerpt = full_text[:8000]
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


def _prompt_flashcards(topic_title: str, full_text: str) -> str:
    excerpt = full_text[:8000]
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


def generate_topic(
    topic: dict, full_text: str, llm: LLM, n_questions: int,
    logger: logging.Logger | None = None, recorder=None,
) -> dict:
    topic_title = topic["title"]
    subtopics_raw = topic.get("subtopics", [])

    # Generate content per subtopic
    subtopics_generated = []
    for sub in subtopics_raw:
        sub_title = sub["title"] if isinstance(sub, dict) else sub
        sub_id = sub["id"] if isinstance(sub, dict) else f"sub_{len(subtopics_generated)}"
        print(f"      Subtopic: {sub_title}")
        data = parse_llm_json(
            llm, _prompt_subtopic(sub_title, topic_title, full_text), system=_SYSTEM,
            fallback={"explanation": "", "concepts": []},
            max_tokens=2500, temperature=0.3, logger=logger,
            recorder=recorder, task="subtopic",
        )
        subtopics_generated.append({
            "id": sub_id,
            "title": sub_title,
            "explanation": data.get("explanation", ""),
            "concepts": data.get("concepts", []),
        })

    # Test questions (still generated — the global exam in the HTML uses these,
    # even though there's no more per-topic quiz UI)
    print(f"    Generating {n_questions} questions for: {topic_title}")
    q_data = parse_llm_json(
        llm, _prompt_questions(topic_title, full_text, n_questions), system=_SYSTEM,
        fallback={"questions": []}, max_tokens=3000, temperature=0.5, logger=logger,
        recorder=recorder, task="questions",
    )

    # Flashcards
    print(f"    Generating flashcards for: {topic_title}")
    fc_data = parse_llm_json(
        llm, _prompt_flashcards(topic_title, full_text), system=_SYSTEM,
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


def generate_material(
    analysis: dict, llm: LLM, questions_per_topic: int = 8,
    logger: logging.Logger | None = None, recorder=None,
) -> dict:
    title = analysis["title"]
    topics = analysis["topics"]
    full_text = analysis["full_text"]
    sources = analysis.get("sources", [])

    print(f"\n  Generating material for '{title}' ({len(topics)} topics)...")

    generated = []
    for i, topic in enumerate(topics, 1):
        print(f"\n  [{i}/{len(topics)}] {topic['title']}")
        generated.append(
            generate_topic(
                topic, full_text, llm, n_questions=questions_per_topic,
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