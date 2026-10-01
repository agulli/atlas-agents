"""
model_router.py — Production Fallback Router
==============================================
Chapter 7 Online Example: LiteLLM fallback chaining with health tracking.

Instead of hardcoding a single model, this router tries a priority list
of providers and automatically skips any that have failed recently.

Usage:
    from model_router import route
    response = route("Summarize this report: ...")
"""

import time
import logging
from dataclasses import dataclass, field
import sys
from pathlib import Path

from litellm import completion
import litellm

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import OPENAI_MODEL, ANTHROPIC_MODEL, GEMINI_MODEL, OLLAMA_MODEL  # also loads .env

litellm.set_verbose = False
logger = logging.getLogger(__name__)


# ── Provider Priority List ───────────────────────────────────────────
# Ordered by preference: best quality first, cheapest fallback last.
PROVIDER_CHAIN = [
    OPENAI_MODEL,
    f"anthropic/{ANTHROPIC_MODEL}",
    f"gemini/{GEMINI_MODEL}",
    f"ollama_chat/{OLLAMA_MODEL}",   # always available locally
]

# How long (seconds) to skip a provider after a failure
COOLDOWN_SECONDS = 120


# ── Circuit Breaker ──────────────────────────────────────────────────

@dataclass
class ProviderState:
    failures: int = 0
    last_failure: float = 0.0
    cooldown: float = COOLDOWN_SECONDS

    def is_available(self) -> bool:
        if self.failures == 0:
            return True
        return time.time() - self.last_failure > self.cooldown

    def record_failure(self):
        self.failures += 1
        self.last_failure = time.time()

    def record_success(self):
        self.failures = 0
        self.last_failure = 0.0


_states: dict[str, ProviderState] = {m: ProviderState() for m in PROVIDER_CHAIN}


# ── Router ───────────────────────────────────────────────────────────

def route(
    prompt: str,
    system: str = "You are a helpful assistant.",
    tools: list | None = None,
    **kwargs,
):
    """
    Try each provider in priority order. Skip any on cooldown.
    Raises RuntimeError only if every provider fails.
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    attempted = []
    for model in PROVIDER_CHAIN:
        state = _states[model]
        if not state.is_available():
            logger.info(f"Skipping {model} (on cooldown, {state.failures} failures)")
            continue

        attempted.append(model)
        try:
            logger.info(f"Trying {model}...")
            start = time.time()
            response = completion(
                model=model,
                messages=messages,
                tools=tools,
                timeout=20,
                **kwargs,
            )
            latency = round((time.time() - start) * 1000)
            state.record_success()
            logger.info(f"✅ {model} responded in {latency}ms")
            return response

        except Exception as e:
            logger.warning(f"❌ {model} failed: {e}")
            state.record_failure()
            continue

    raise RuntimeError(
        f"All providers exhausted. Tried: {attempted}. "
        "Check API keys and local Ollama server."
    )


# ── Health Report ─────────────────────────────────────────────────────

def health_report() -> dict:
    return {
        model: {
            "available": state.is_available(),
            "failures": state.failures,
            "cooldown_remaining": max(
                0, state.cooldown - (time.time() - state.last_failure)
            ) if state.failures else 0,
        }
        for model, state in _states.items()
    }


# ── Demo ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    response = route(
        prompt="In one sentence, what is LiteLLM?",
        system="Answer concisely.",
    )
    print("\nResponse:", response.choices[0].message.content)
    print("\nProvider health:", health_report())