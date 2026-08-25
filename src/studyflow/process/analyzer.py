"""
process/analyzer.py — Text cleaning and topic detection.
"""

import logging
import re

from core.llm import LLM
from core.json_utils import parse_llm_json


_SYSTEM = (
    "You are an expert at organizing academic study material. "
    "Analyze the content and structure it clearly. "
    "Always respond with valid JSON only — no extra text outside the JSON. "
    "CRITICAL: respond in the SAME language as the input content."
)


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


def merge_texts(texts: dict[str, str]) -> str:
    parts = []
    for name, text in texts.items():
        if text.startswith("[ERROR:"):
            continue
        cleaned = clean_text(text)
        if cleaned:
            parts.append(f"=== Source: {name} ===\n\n{cleaned}")
    return ("\n\n" + "─" * 60 + "\n\n").join(parts)


def detect_topics(text: str, llm: LLM, logger: logging.Logger | None = None, recorder=None) -> dict:
    excerpt = text[:12000]
    prompt = f"""Analyze the following academic content and extract its topic structure.

CONTENT:
{excerpt}

Return ONLY a JSON object with this exact shape (no ```json, no extra text):
{{
  "title": "Descriptive title of the material in the SAME language as the content",
  "topics": [
    {{
      "id": "topic_1",
      "title": "Topic title in the SAME language as the content",
      "subtopics": [
        {{
          "id": "topic_1_sub_1",
          "title": "Subtopic title"
        }}
      ]
    }}
  ]
}}

Rules:
- Maximum 8 topics, maximum 6 subtopics per topic
- Topic and subtopic ids: topic_1, topic_1_sub_1, topic_1_sub_2, topic_2, topic_2_sub_1...
- Topics and titles must be in the SAME language as the input content
- Subtopics must be specific and well differentiated sections within the topic"""

    fallback = {
        "title": "Study material",
        "topics": [{"id": "topic_1", "title": "General content", "subtopics": []}],
    }
    return parse_llm_json(
        llm, prompt, system=_SYSTEM, fallback=fallback,
        max_tokens=2000, temperature=0.3, logger=logger,
        recorder=recorder, task="topic_detection",
    )


def analyze(
    texts: dict[str, str], llm: LLM, logger: logging.Logger | None = None, recorder=None,
) -> dict:
    print("  Merging and cleaning texts...")
    full_text = merge_texts(texts)
    print("  Detecting topic structure...")
    structure = detect_topics(full_text, llm, logger=logger, recorder=recorder)
    return {
        "title": structure.get("title", "Study material"),
        "topics": structure.get("topics", []),
        "full_text": full_text,
        "sources": list(texts.keys()),
    }