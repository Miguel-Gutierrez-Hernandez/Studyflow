"""
core/json_utils.py — Robust JSON parsing for LLM responses, with retries.

Local LLMs (like Llama 3.2 3B) sometimes wrap JSON in prose or produce
slightly malformed JSON. `parse_llm_json` tries a few extraction strategies,
and if all fail, re-prompts the model once (or more) asking it to return
only fixed JSON before finally giving up and returning a fallback value.
"""

import json
import logging
import re

from core.llm import LLM


def _extract_json(text: str) -> dict | None:
    """Try several strategies to pull a JSON object out of raw LLM text."""
    text = text.strip()

    # Strategy 1: plain parse.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: fenced code block (```json ... ``` or ``` ... ```).
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: first {...} block found anywhere in the text.
    m = re.search(r"\{[\s\S]+\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return None


def parse_llm_json(
    llm: LLM,
    prompt: str,
    system: str,
    fallback: dict,
    max_tokens: int = 2048,
    temperature: float = 0.3,
    retries: int = 2,
    logger: logging.Logger | None = None,
) -> dict:
    """
    Call the LLM and parse its response as JSON, retrying with a corrective
    prompt if the response can't be parsed.

    Returns `fallback` (unchanged) if every attempt fails.
    """
    response = llm.chat(prompt, system=system, max_tokens=max_tokens, temperature=temperature)
    data = _extract_json(response)
    if data is not None:
        return data

    if logger:
        logger.warning("json_parse_failed", extra={"attempt": 0, "raw_preview": response[:200]})

    for attempt in range(1, retries + 1):
        fix_prompt = (
            "Your previous response was not valid JSON. Return ONLY a valid JSON object, "
            "with no extra text, no markdown fences, no commentary. "
            f"Here was your previous response:\n\n{response}\n\n"
            "Fix it and return only the corrected JSON object."
        )
        response = llm.chat(fix_prompt, system=system, max_tokens=max_tokens, temperature=0.1)
        data = _extract_json(response)
        if data is not None:
            if logger:
                logger.info("json_parse_recovered", extra={"attempt": attempt})
            return data
        if logger:
            logger.warning(
                "json_parse_failed", extra={"attempt": attempt, "raw_preview": response[:200]}
            )

    if logger:
        logger.error("json_parse_gave_up", extra={"retries": retries})
    return fallback