"""
tests/test_classifier.py — Unit tests for process/classifier.py using a
fake LLM instead of real Ollama calls.

These test the Python logic around the three prompts (index bookkeeping,
fallback behavior when the model returns something unusable or references
an id that doesn't exist, saturation promotion) — not whether the prompts
themselves produce good classifications. That still has to be checked by
running the real pipeline against real notes.

Run with:
    pytest tests/test_classifier.py -v
"""

import json

import pytest

from process.classifier import classify_document, check_saturation, classified_sources


class FakeLLM:
    """Drop-in replacement for core.llm.LLM. Returns pre-scripted responses
    in order, one per call to .chat(), instead of hitting Ollama."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[str] = []

    def chat(self, prompt, system=None, max_tokens=2048, temperature=0.3):
        self.calls.append(prompt)
        if not self._responses:
            raise AssertionError(
                f"FakeLLM ran out of scripted responses (call #{len(self.calls)})"
            )
        return self._responses.pop(0)


def _lector(explicit_topic=None, explicit_subtopic=None, topic_guess="Tema genérico",
            subtopic_guess="Subtema genérico", key_concepts=None) -> str:
    return json.dumps({
        "explicit_topic": explicit_topic,
        "explicit_subtopic": explicit_subtopic,
        "topic_guess": topic_guess,
        "subtopic_guess": subtopic_guess,
        "key_concepts": key_concepts or [],
    })


def _router(action, topic_id=None, topic_title=None, subtopic_id=None, subtopic_title=None) -> str:
    return json.dumps({
        "action": action,
        "topic_id": topic_id,
        "topic_title": topic_title,
        "subtopic_id": subtopic_id,
        "subtopic_title": subtopic_title,
    })


# ── Empty index ──────────────────────────────────────────────────────────

def test_first_document_creates_topic_and_subtopic():
    index = {"topics": []}
    fake = FakeLLM([
        _lector(explicit_topic="Estadística Descriptiva", topic_guess="Estadística"),
        _router(action="new_topic", topic_title="Estadística Descriptiva",
                subtopic_title="Medidas de tendencia central"),
        "Texto fusionado.",
    ])

    result = classify_document("notas1.txt", "contenido de prueba", index, fake)

    assert len(result["topics"]) == 1
    topic = result["topics"][0]
    assert topic["title"] == "Estadística Descriptiva"
    assert len(topic["subtopics"]) == 1
    sub = topic["subtopics"][0]
    assert sub["title"] == "Medidas de tendencia central"
    assert sub["sources"] == ["notas1.txt"]
    assert sub["content"] == "contenido de prueba"  # nothing to merge with yet, kept as-is


# ── Hallucinated topic_id ────────────────────────────────────────────────

def test_router_hallucinated_topic_id_falls_back_to_new_topic():
    """If the router names a topic_id that isn't actually in the index (the
    model invented it), classify_document must not crash — it should fall
    back to creating a real new topic instead."""
    index = {"topics": [{"id": "estadistica", "title": "Estadística", "subtopics": []}]}
    fake = FakeLLM([
        _lector(topic_guess="Probabilidad", subtopic_guess="Teorema de Bayes"),
        _router(action="existing_subtopic", topic_id="topic_que_no_existe",
                subtopic_id="sub_que_no_existe", subtopic_title="Bayes"),
        "Texto fusionado.",
    ])

    result = classify_document("notas2.txt", "contenido", index, fake)

    # Original topic untouched, plus a new one created instead of crashing.
    assert len(result["topics"]) == 2
    assert result["topics"][0]["id"] == "estadistica"
    assert result["topics"][0]["subtopics"] == []
    new_topic = result["topics"][1]
    assert len(new_topic["subtopics"]) == 1


# ── Reuse of an existing subtopic (merge path) ───────────────────────────

def test_existing_subtopic_merges_content_and_appends_source():
    index = {
        "topics": [{
            "id": "estadistica",
            "title": "Estadística",
            "subtopics": [{
                "id": "medidas_centrales",
                "title": "Medidas de tendencia central",
                "content": "La media es la suma dividida entre n.",
                "sources": ["notas1.txt"],
            }],
        }]
    }
    fake = FakeLLM([
        _lector(topic_guess="Estadística", subtopic_guess="Medidas de tendencia central"),
        _router(action="existing_subtopic", topic_id="estadistica",
                subtopic_id="medidas_centrales", subtopic_title="Medidas de tendencia central"),
        "La media es la suma dividida entre n. La mediana es el valor central.",
    ])

    result = classify_document("notas2.txt", "La mediana es el valor central.", index, fake)

    sub = result["topics"][0]["subtopics"][0]
    assert "mediana" in sub["content"]
    assert sub["sources"] == ["notas1.txt", "notas2.txt"]  # appended, not replaced


def test_same_source_not_duplicated_if_classified_twice():
    index = {
        "topics": [{
            "id": "t1", "title": "Tema", "subtopics": [{
                "id": "s1", "title": "Sub", "content": "algo", "sources": ["a.txt"],
            }],
        }]
    }
    fake = FakeLLM([
        _lector(),
        _router(action="existing_subtopic", topic_id="t1", subtopic_id="s1", subtopic_title="Sub"),
        "algo fusionado",
    ])
    result = classify_document("a.txt", "algo nuevo", index, fake)
    assert result["topics"][0]["subtopics"][0]["sources"] == ["a.txt"]


# ── Redactor failure doesn't lose content ────────────────────────────────

def test_merge_failure_falls_back_to_concatenation(monkeypatch):
    """If the Redactor call raises (e.g. Ollama drops mid-merge), the
    existing content must not be lost — it should fall back to a plain
    concatenation rather than propagating the exception."""
    index = {
        "topics": [{
            "id": "t1", "title": "Tema", "subtopics": [{
                "id": "s1", "title": "Sub", "content": "contenido viejo", "sources": ["a.txt"],
            }],
        }]
    }

    class RaisingLLM(FakeLLM):
        def chat(self, prompt, system=None, max_tokens=2048, temperature=0.3):
            self.calls.append(prompt)
            if len(self.calls) <= 2:
                return self._responses.pop(0)
            raise RuntimeError("Ollama connection dropped")

    fake = RaisingLLM([
        _lector(),
        _router(action="existing_subtopic", topic_id="t1", subtopic_id="s1", subtopic_title="Sub"),
    ])

    result = classify_document("b.txt", "contenido nuevo", index, fake)
    sub = result["topics"][0]["subtopics"][0]
    assert "contenido viejo" in sub["content"]
    assert "contenido nuevo" in sub["content"]


# ── Saturation ────────────────────────────────────────────────────────────

def test_saturation_promotes_oversized_subtopic_to_new_topic():
    index = {
        "topics": [{
            "id": "t1",
            "title": "Tema grande",
            "subtopics": [
                {"id": "s1", "title": "Sub pequeño", "content": "poco texto", "sources": ["a.txt"]},
                {"id": "s2", "title": "Sub enorme", "content": "x" * 10000, "sources": ["b.txt", "c.txt"]},
            ],
        }]
    }
    result = check_saturation(index)

    titles = [t["title"] for t in result["topics"]]
    assert "Tema grande" in titles
    assert "Sub enorme" in titles  # promoted to its own top-level topic

    grande = next(t for t in result["topics"] if t["title"] == "Tema grande")
    assert len(grande["subtopics"]) == 1
    assert grande["subtopics"][0]["title"] == "Sub pequeño"

    promoted = next(t for t in result["topics"] if t["title"] == "Sub enorme")
    assert len(promoted["subtopics"]) == 1
    assert promoted["subtopics"][0]["content"] == "x" * 10000


def test_saturation_never_leaves_topic_with_zero_subtopics():
    """A topic with a single oversized subtopic and nothing else stays as-is
    — promoting it would just be renaming the same topic."""
    index = {
        "topics": [{
            "id": "t1", "title": "Tema único",
            "subtopics": [{"id": "s1", "title": "Único sub", "content": "x" * 20000, "sources": ["a.txt"] * 10}],
        }]
    }
    result = check_saturation(index)
    assert len(result["topics"]) == 1
    assert len(result["topics"][0]["subtopics"]) == 1


def test_saturation_promotes_by_doc_count_even_if_short():
    index = {
        "topics": [{
            "id": "t1", "title": "Tema",
            "subtopics": [
                {"id": "s1", "title": "Sub A", "content": "corto", "sources": ["a.txt"]},
                {"id": "s2", "title": "Sub B", "content": "corto", "sources": ["b.txt", "c.txt", "d.txt", "e.txt", "f.txt"]},
            ],
        }]
    }
    result = check_saturation(index)
    titles = [t["title"] for t in result["topics"]]
    assert "Sub B" in titles


# ── classified_sources ───────────────────────────────────────────────────

def test_classified_sources_collects_across_all_topics():
    index = {
        "topics": [
            {"id": "t1", "title": "T1", "subtopics": [
                {"id": "s1", "title": "S1", "content": "", "sources": ["a.txt", "b.txt"]},
            ]},
            {"id": "t2", "title": "T2", "subtopics": [
                {"id": "s2", "title": "S2", "content": "", "sources": ["c.txt"]},
            ]},
        ]
    }
    assert classified_sources(index) == {"a.txt", "b.txt", "c.txt"}


def test_classified_sources_empty_index():
    assert classified_sources({"topics": []}) == set()


# ── Duplicate-title safety net (accents/casing) ──────────────────────────

def test_near_duplicate_topic_reused_instead_of_created():
    """Router says 'new_topic' with a title that only differs from an
    existing one by accents/casing — should be caught and reused instead of
    creating a duplicate."""
    index = {"topics": [{"id": "estadistica", "title": "Estadística", "subtopics": [
        {"id": "s1", "title": "Media", "content": "algo", "sources": ["a.txt"]},
    ]}]}
    fake = FakeLLM([
        _lector(topic_guess="ESTADISTICA", subtopic_guess="Mediana"),
        _router(action="new_topic", topic_title="estadistica", subtopic_title="Mediana"),
        "texto fusionado",
    ])

    result = classify_document("b.txt", "contenido", index, fake)

    assert len(result["topics"]) == 1  # no se creó un segundo tema duplicado
    assert result["topics"][0]["id"] == "estadistica"


def test_near_duplicate_subtopic_reused_instead_of_created():
    index = {"topics": [{"id": "t1", "title": "Tema", "subtopics": [
        {"id": "medidas_centrales", "title": "Medidas de Tendencia Central", "content": "algo", "sources": ["a.txt"]},
    ]}]}
    fake = FakeLLM([
        _lector(),
        _router(action="new_subtopic", topic_id="t1",
                subtopic_title="medidas de tendencia central"),  # sin tildes/mayúsculas
        "texto fusionado",
    ])

    result = classify_document("b.txt", "contenido nuevo", index, fake)

    assert len(result["topics"][0]["subtopics"]) == 1  # reutilizado, no duplicado
    assert result["topics"][0]["subtopics"][0]["sources"] == ["a.txt", "b.txt"]


def test_genuinely_different_titles_not_merged():
    """Two clearly different topics must NOT be merged just because the
    similarity check exists — only near-duplicates should trigger it."""
    index = {"topics": [{"id": "estadistica", "title": "Estadística Descriptiva", "subtopics": []}]}
    fake = FakeLLM([
        _lector(topic_guess="Redes Neuronales"),
        _router(action="new_topic", topic_title="Redes Neuronales", subtopic_title="Perceptrón"),
        "texto fusionado",
    ])

    result = classify_document("b.txt", "contenido", index, fake)

    assert len(result["topics"]) == 2  # tema genuinamente distinto, no se fusiona