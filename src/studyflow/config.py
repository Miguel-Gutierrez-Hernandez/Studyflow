"""
config.py — Configuración central de StudyFlow AI
Lee variables de entorno desde .env y expone valores con defaults.
"""
from pathlib import Path
from dotenv import load_dotenv
import os

# Busca el .env en la raíz del proyecto
_ROOT = Path(__file__).parent
load_dotenv(_ROOT / ".env")


# ── LLM ──────────────────────────────────────────────────────────────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "huggingface")

# HuggingFace
HF_TOKEN: str = os.getenv("HF_TOKEN", "")
HF_MODEL: str = os.getenv("HF_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
HF_API_URL: str = os.getenv("HF_API_URL", "https://api-inference.huggingface.co/models")
HF_WHISPER_MODEL: str = os.getenv("HF_WHISPER_MODEL", "openai/whisper-large-v3")

# OpenAI
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Anthropic
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# Ollama
OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1")

# ── Whisper ───────────────────────────────────────────────────────────────────
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "small")

# ── Proyectos ─────────────────────────────────────────────────────────────────
PROYECTOS_DIR: Path = Path(os.getenv("PROYECTOS_DIR", "./proyectos")).resolve()