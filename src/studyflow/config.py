from pathlib import Path
from dotenv import load_dotenv, find_dotenv
import os

_dotenv_path = find_dotenv(usecwd=True)
load_dotenv(_dotenv_path if _dotenv_path else Path(__file__).parent / ".env")

# Ollama
OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")

# Projects
PROJECTS_DIR: Path = Path(os.getenv("PROJECTS_DIR", "./projects")).resolve()