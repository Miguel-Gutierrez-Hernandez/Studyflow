"""
core/llm.py — HuggingFace Inference API client using InferenceClient.

Usage:
    from core.llm import LLM
    llm = LLM()
    response = llm.chat("Summarize this text: ...")
"""

from huggingface_hub import InferenceClient
import config


class LLM:
    """HuggingFace Inference API client using the official InferenceClient."""

    def __init__(self):
        if not config.HF_TOKEN:
            raise ValueError(
                "HF_TOKEN is missing from .env. "
            )
        self.model = config.HF_MODEL
        self.client = InferenceClient(
            model=self.model,
            api_key=config.HF_TOKEN,
            timeout=120,
        )

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

        try:
            response = self.client.chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError(f"Error calling HuggingFace API for model '{self.model}': {e}") from e

    def __repr__(self) -> str:
        return f"<LLM model={self.model}>"