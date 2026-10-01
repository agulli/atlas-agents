"""
Shared configuration — loads API keys from .env and provides model constants.
Used by every chapter in the book.

Every model name in the book's code comes from here, so you can switch the
whole repo to another provider (for example Gemma 4 on a local Ollama server)
by editing .env instead of the code. See "Run everything locally with Gemma 4
on Ollama" in the root README.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root. This also exports the values into os.environ,
# so the OpenAI and Anthropic SDKs pick up OPENAI_BASE_URL / ANTHROPIC_BASE_URL.
load_dotenv(Path(__file__).parent.parent / ".env")

# ── API Keys ─────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Endpoints (empty = the provider's cloud API) ─────────────────────
# Ollama: OPENAI_BASE_URL=http://localhost:11434/v1
#         ANTHROPIC_BASE_URL=http://localhost:11434
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "")

# ── Default Models ───────────────────────────────────────────────────
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_FAST_MODEL = os.getenv("OPENAI_FAST_MODEL", "gpt-4o-mini")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b")

# Three Anthropic tiers: fast/cheap, main, strongest.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
ANTHROPIC_FAST_MODEL = os.getenv("ANTHROPIC_FAST_MODEL", "claude-haiku-4-5")
ANTHROPIC_STRONG_MODEL = os.getenv("ANTHROPIC_STRONG_MODEL", "claude-opus-4-8")

# Embeddings (OpenAI-compatible /v1/embeddings). Ollama: embeddinggemma
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

# Extended thinking (Anthropic `thinking=` parameter). Set false for local models.
ENABLE_THINKING = os.getenv("ENABLE_THINKING", "true").lower() in ("1", "true", "yes")

# ── LiteLLM universal model string ───────────────────────────────────
LITELLM_MODEL = os.getenv("LITELLM_MODEL", f"openai/{OPENAI_MODEL}")


def is_local() -> bool:
    """True when the OpenAI or Anthropic endpoint points at a local server (e.g. Ollama)."""
    urls = (OPENAI_BASE_URL + ANTHROPIC_BASE_URL).lower()
    return "localhost" in urls or "127.0.0.1" in urls or "11434" in urls


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
            f"Set it in your .env file or export it as an environment variable. "
            f"(For a local Ollama server any placeholder works, e.g. 'ollama'.)"
        )
    return key
