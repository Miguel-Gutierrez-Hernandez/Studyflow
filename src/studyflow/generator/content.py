"""
generador/contenido.py — Study material generation.

For each detected topic generates:
    - structured summary
    - key concepts with definitions
    - memory tricks
    - multiple-choice questions with answer and explanation
"""

import json
import re

from core.llm import LLM


_SYSTEM = (
    "You are an expert at creating effective study material. "
    "Convert academic notes into clear summaries, memory tricks and exam questions. "
    "Always respond with valid JSON only — no extra text outside the JSON."
)


def _parse_json(response: str, fallback: dict) -> dict:
    text = response.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if m:
            text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]+\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return fallback


def _prompt_summary(topic: dict, full_text: str) -> str:
    excerpt = full_text[:8000]
    return f"""Generate study material for the following topic.

TOPIC: {topic['title']}
SUBTOPICS: {', '.join(topic.get('subtopics', []))}
MATERIAL:
{excerpt}

Return ONLY this JSON (no ```json, no extra text):
{{
  "summary": "Full explanation of the topic in 3-6 paragraphs. Include key definitions, important concepts and relationships between ideas.",
  "key_points": ["point 1", "point 2", "point 3", "point 4", "point 5"],
  "keywords": [
    {{"term": "Term", "definition": "Brief precise definition"}}
  ],
  "memory_tricks": [
    {{"trick": "Description of the trick or mnemonic", "example": "Application example"}}
  ]
}}

- Summary must cover all subtopics
- Include 5-8 keywords with definitions
- Include 2-4 memory tricks or mnemonics"""


def _prompt_questions(topic: dict, full_text: str, n: int) -> str:
    excerpt = full_text[:8000]
    return f"""Generate {n} multiple-choice questions for the following topic.

TOPIC: {topic['title']}
SUBTOPICS: {', '.join(topic.get('subtopics', []))}
MATERIAL:
{excerpt}

Return ONLY this JSON (no ```json, no extra text):
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


def generate_topic(topic: dict, full_text: str, llm: LLM, n_questions: int) -> dict:
    print(f"    Generating summary for: {topic['title']}")
    r_summary = llm.chat(_prompt_summary(topic, full_text), system=_SYSTEM, max_tokens=2500, temperature=0.4)
    summary_data = _parse_json(r_summary, {"summary": "", "key_points": [], "keywords": [], "memory_tricks": []})

    print(f"    Generating questions for: {topic['title']}")
    r_questions = llm.chat(_prompt_questions(topic, full_text, n_questions), system=_SYSTEM, max_tokens=3000, temperature=0.5)
    questions_data = _parse_json(r_questions, {"questions": []})

    return {
        "id": topic["id"],
        "title": topic["title"],
        "subtopics": topic.get("subtopics", []),
        "summary": summary_data.get("summary", ""),
        "key_points": summary_data.get("key_points", []),
        "keywords": summary_data.get("keywords", []),
        "memory_tricks": summary_data.get("memory_tricks", []),
        "questions": questions_data.get("questions", []),
    }


def generate_material(analysis: dict, llm: LLM, questions_per_topic: int = 8) -> dict:
    """
    Generate full study material for all topics.

    Args:
        analysis:           Output from analyze()
        llm:                LLM instance
        questions_per_topic: Number of test questions per topic

    Returns:
        Dict ready to pass to build_html()
    """
    title = analysis["title"]
    topics = analysis["topics"]
    full_text = analysis["full_text"]
    sources = analysis.get("sources", [])

    print(f"\n  Generating material for '{title}' ({len(topics)} topics)...")

    generated = []
    for i, topic in enumerate(topics, 1):
        print(f"\n  [{i}/{len(topics)}] {topic['title']}")
        generated.append(generate_topic(topic, full_text, llm, n_questions=questions_per_topic))

    return {
        "title": title,
        "topics": generated,
        "sources": sources,
        "stats": {
            "n_topics": len(generated),
            "n_questions": sum(len(t["questions"]) for t in generated),
        },
    }