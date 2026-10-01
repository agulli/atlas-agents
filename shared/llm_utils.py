"""
Small helpers for working with model output across providers.

Local models (Gemma, Llama, ...) often wrap JSON in ```json fences or add a
sentence before it, even when told "JSON only". parse_json() tolerates that,
so the same code works on Claude, GPT, and Gemma 4.
"""

import json
import re
from typing import Any

_MISSING = object()
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json(text: str, default: Any = _MISSING) -> Any:
    """
    Parse JSON from model output.

    If nothing parses, return `default`, or raise json.JSONDecodeError when no
    default is given (so existing `except json.JSONDecodeError` blocks still work).
    """
    if not text:
        if default is _MISSING:
            raise json.JSONDecodeError("Empty model output", text or "", 0)
        return default
    candidates = [text.strip()]
    candidates += [m.strip() for m in _FENCE.findall(text)]
    # Fall back to the outermost {...} or [...] block in the text.
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = text.find(open_ch), text.rfind(close_ch)
        if start != -1 and end > start:
            candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    if default is _MISSING:
        raise json.JSONDecodeError("No JSON found in model output", text, 0)
    return default
