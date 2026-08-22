"""
procesado/analizador.py — Text cleaning and topic detection.

Steps:
    1. clean_text()   → normalizes raw extracted text
    2. detect_topics() → uses LLM to identify topics and subtopics
    3. analyze()      → full pipeline, returns a structured dict

Output dict shape:
    {
        "title": "Subject or document name",
        "topics": [
            {
                "id": "topic_1",
                "title": "Topic title",
                "subtopics": ["subtopic A", "subtopic B"],
                "summary": "Brief content description"
            }
        ],
        "full_text": "...",
        "sources": ["file1.pdf", ...]
    }
"""

import json
import re

from core.llm import LLM


_SYSTEM = (
    "You are an expert at organizing academic study material. "
    "Analyze the content and structure it clearly. "
    "Always respond with valid JSON only — no extra text outside the JSON."
)


def clean_text(text: str) -> str:
    """Normalize raw extracted text: collapse blank lines, strip control chars."""
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


def merge_texts(texts: dict[str, str]) -> str:
    """Clean and concatenate multiple source texts with source headers."""
    parts = []
    for name, text in texts.items():
        if text.startswith("[ERROR:"):
            continue
        cleaned = clean_text(text)
        if cleaned:
            parts.append(f"=== Source: {name} ===\n\n{cleaned}")
    return ("\n\n" + "─" * 60 + "\n\n").join(parts)


def detect_topics(text: str, llm: LLM) -> dict:
    """Call LLM to detect the topic structure of the text."""
    excerpt = text[:12000]
    prompt = f"""Analyze the following academic content and extract its topic structure.

CONTENT:
{excerpt}

Return ONLY a JSON object with this exact shape (no ```json, no extra text):
{{
  "title": "Descriptive title of the material (subject or general topic)",
  "topics": [
    {{
      "id": "topic_1",
      "title": "Topic title",
      "subtopics": ["subtopic 1", "subtopic 2"],
      "summary": "2-4 sentence description of the main content of this topic"
    }}
  ]
}}

Rules:
- Maximum 10 topics
- Topic ids must be topic_1, topic_2, topic_3...
- Topics must be coherent and well differentiated
- If the content covers a single topic, split it into logical sub-sections"""

    response = llm.chat(prompt, system=_SYSTEM, max_tokens=2000)

    # Strip code fences if model adds them
    clean = response.strip()
    if "```" in clean:
        m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", clean)
        if m:
            clean = m.group(1)

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return {
            "title": "Study material",
            "topics": [{"id": "topic_1", "title": "General content", "subtopics": [], "summary": text[:500]}],
        }


def analyze(texts: dict[str, str], llm: LLM) -> dict:
    """
    Full analysis pipeline.

    Args:
        texts: {filename: extracted_text} from extract_all()
        llm:   LLM instance

    Returns:
        Dict with title, topics, full_text and sources.
    """
    print("  Merging and cleaning texts...")
    full_text = merge_texts(texts)

    print("  Detecting topic structure...")
    structure = detect_topics(full_text, llm)

    return {
        "title": structure.get("title", "Study material"),
        "topics": structure.get("topics", []),
        "full_text": full_text,
        "sources": list(texts.keys()),
    }