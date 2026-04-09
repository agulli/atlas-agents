"""
Shared configuration — loads API keys from .env and provides model constants.
Used by every chapter in the book.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

# ── API Keys ─────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Default Models ───────────────────────────────────────────────────
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b")

# ── LiteLLM universal model string ───────────────────────────────────
LITELLM_MODEL = os.getenv("LITELLM_MODEL", f"openai/{OPENAI_MODEL}")


def require_key(provider: str) -> str:
    """Return the API key for a provider or raise with a helpful message."""
    keys = {
        "openai": OPENAI_API_KEY,
        "google": GOOGLE_API_KEY,
        "anthropic": ANTHROPIC_API_KEY,
    }
    key = keys.get(provider.lower(), "")
    if not key:
        raise EnvironmentError(
            f"Missing {provider.upper()}_API_KEY. "
            f"Set it in your .env file or export it as an environment variable."
        )
    return key
