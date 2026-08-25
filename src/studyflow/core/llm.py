"""
core/llm.py — Ollama local LLM client.

Usage:
    from core.llm import LLM
    llm = LLM()
    response = llm.chat("Summarize this text: ...")

Optional response caching (used by the pipeline in update mode to avoid
repeating identical calls):
    from core.llm_cache import LLMCache
    llm = LLM(cache=LLMCache(project.path))
"""

import requests
import config
from core.llm_cache import LLMCache


class LLM:
    """Ollama local inference client."""

    def __init__(self, cache: LLMCache | None = None, model: str | None = None):
        self.model = model or config.OLLAMA_MODEL
        self.url = config.OLLAMA_URL.rstrip("/") + "/api/chat"
        self.cache = cache

    def chat(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        """Send a prompt and return the response as a plain string. Uses the
        cache (if configured) to skip identical calls."""
        if self.cache is not None:
            cached = self.cache.get(self.model, system, prompt, temperature)
            if cached is not None:
                return cached

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            response = requests.post(self.url, json=payload, timeout=300)
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                "Cannot connect to Ollama. Make sure it's running: ollama serve"
            )

        data = response.json()

        try:
            result = data["message"]["content"].strip()
        except (KeyError, TypeError) as e:
            raise RuntimeError(f"Unexpected response from Ollama: {data}") from e

        if self.cache is not None:
            self.cache.set(self.model, system, prompt, temperature, result)

        return result

    def __repr__(self) -> str:
        return f"<LLM model={self.model} url={self.url}>"