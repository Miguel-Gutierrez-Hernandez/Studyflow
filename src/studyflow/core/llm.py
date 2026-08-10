"""
core/llm.py — Módulo LLM agnóstico.

Uso:
    from core.llm import get_llm

    llm = get_llm()               # usa el provider del .env
    respuesta = llm.chat("Hola")  # string limpio

Cambiar de provider:
    llm = get_llm(provider="openai")
    llm = get_llm(provider="anthropic")
    llm = get_llm(provider="ollama")

Todos los providers implementan la misma interfaz BaseLLM:
    .chat(prompt, system=None, max_tokens=2048) -> str
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

import requests

import config


# ── Interfaz común ────────────────────────────────────────────────────────────

class BaseLLM(ABC):
    """Interfaz que deben implementar todos los providers."""

    @abstractmethod
    def chat(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        """Envía un mensaje y devuelve la respuesta como string."""
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"


# ── HuggingFace Inference API ─────────────────────────────────────────────────

class HuggingFaceLLM(BaseLLM):
    """
    HuggingFace Inference API (serverless).
    Soporta modelos con endpoint /v1/chat/completions (compatible OpenAI).
    """

    def __init__(self, model: str | None = None, token: str | None = None):
        self.model = model or config.HF_MODEL
        self.token = token or config.HF_TOKEN
        if not self.token:
            raise ValueError(
                "Falta HF_TOKEN en el .env. "
                "Obtén uno en https://huggingface.co/settings/tokens"
            )
        # HuggingFace ofrece endpoint compatible con OpenAI para modelos de chat
        self.url = f"https://api-inference.huggingface.co/v1/chat/completions"

    def chat(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        response = requests.post(self.url, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
        data = response.json()

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Respuesta inesperada de HuggingFace: {data}") from e


# ── OpenAI ────────────────────────────────────────────────────────────────────

class OpenAILLM(BaseLLM):
    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or config.OPENAI_MODEL
        self.api_key = api_key or config.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("Falta OPENAI_API_KEY en el .env.")

    def chat(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()


# ── Anthropic ─────────────────────────────────────────────────────────────────

class AnthropicLLM(BaseLLM):
    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or config.ANTHROPIC_MODEL
        self.api_key = api_key or config.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Falta ANTHROPIC_API_KEY en el .env.")

    def chat(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        payload: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"].strip()


# ── Ollama (local) ────────────────────────────────────────────────────────────

class OllamaLLM(BaseLLM):
    def __init__(self, model: str | None = None, url: str | None = None):
        self.model = model or config.OLLAMA_MODEL
        self.url = (url or config.OLLAMA_URL).rstrip("/") + "/api/chat"

    def chat(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        response = requests.post(self.url, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"].strip()


# ── Factory ───────────────────────────────────────────────────────────────────

_PROVIDERS: dict[str, type[BaseLLM]] = {
    "huggingface": HuggingFaceLLM,
    "openai": OpenAILLM,
    "anthropic": AnthropicLLM,
    "ollama": OllamaLLM,
}


def get_llm(provider: str | None = None, **kwargs) -> BaseLLM:
    """
    Devuelve una instancia del LLM configurado.

    Args:
        provider: 'huggingface' | 'openai' | 'anthropic' | 'ollama'
                  Si None, usa LLM_PROVIDER del .env.
        **kwargs: parámetros extra para el provider (model, api_key, etc.)

    Returns:
        Instancia de BaseLLM lista para usar.
    """
    provider = (provider or config.LLM_PROVIDER).lower()
    if provider not in _PROVIDERS:
        raise ValueError(
            f"Provider '{provider}' no soportado. "
            f"Opciones: {list(_PROVIDERS.keys())}"
        )
    return _PROVIDERS[provider](**kwargs)
