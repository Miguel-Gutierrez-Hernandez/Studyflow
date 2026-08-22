from pathlib import Path
from dotenv import load_dotenv, find_dotenv
import os

_dotenv_path = find_dotenv(usecwd=True)
load_dotenv(_dotenv_path if _dotenv_path else Path(__file__).parent / ".env")

# HuggingFace
HF_TOKEN: str = os.getenv("HF_TOKEN", "")
HF_MODEL: str = os.getenv("HF_MODEL", "meta-llama/Llama-3.2-3B-Instruct")
HF_WHISPER_MODEL: str = os.getenv("HF_WHISPER_MODEL", "openai/whisper-large-v3")

# Projects
PROJECTS_DIR: Path = Path(os.getenv("PROJECTS_DIR", "./projects")).resolve()