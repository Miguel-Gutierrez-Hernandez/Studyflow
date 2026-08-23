"""
core/llm.py — Ollama local LLM client.

Usage:
    from core.llm import LLM
    llm = LLM()
    response = llm.chat("Summarize this text: ...")
"""

import requests
import config


class LLM:
    """Ollama local inference client."""

    def __init__(self):
        self.model = config.OLLAMA_MODEL
        self.url = config.OLLAMA_URL.rstrip("/") + "/api/chat"

    def chat(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        """Send a prompt and return the response as a plain string."""
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
            return data["message"]["content"].strip()
        except (KeyError, TypeError) as e:
            raise RuntimeError(f"Unexpected response from Ollama: {data}") from e

    def __repr__(self) -> str:
        return f"<LLM model={self.model} url={self.url}>"