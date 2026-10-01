"""
ollama_tool_calling.py — Offline Tool Calling with Ollama
==========================================================
Chapter 7 Online Example: Structured tool calls completely locally.

Llama 3.1 and newer support native tool-call JSON output. This example
shows how to invoke a tool loop with zero external API dependencies —
useful for air-gapped environments or when data privacy prevents
sending payloads to a cloud provider.

Requires:
    brew install ollama && ollama pull gemma4   # set OLLAMA_MODEL in .env
    pip install requests
"""

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import OLLAMA_MODEL  # also loads .env

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = OLLAMA_MODEL  # Must support tool calling (gemma4, llama3.1+, mistral-nemo, ...)


# ── Tool Registry ────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name, e.g. 'London'"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": "Search the internal knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 3},
                },
                "required": ["query"],
            },
        },
    },
]


def _tool_dispatch(name: str, args: dict) -> str:
    """Fake tool implementations — replace with real logic."""
    if name == "get_weather":
        city = args.get("city", "unknown")
        unit = args.get("unit", "celsius")
        return json.dumps({"city": city, "temp": 18, "unit": unit, "condition": "Partly cloudy"})
    if name == "search_kb":
        return json.dumps({"results": [f"Result for '{args['query']}'"] * args.get("top_k", 3)})
    return json.dumps({"error": f"Unknown tool: {name}"})


def _chat(messages: list, use_tools: bool = True) -> dict:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
    }
    if use_tools:
        payload["tools"] = TOOLS

    response = requests.post(OLLAMA_URL, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


# ── Agentic Tool Loop ────────────────────────────────────────────────

def run_agent(user_prompt: str, max_rounds: int = 5) -> str:
    """
    Run a local tool-calling agent loop against Ollama.
    Returns the final text response after all tool calls are resolved.
    """
    messages = [{"role": "user", "content": user_prompt}]

    for round_num in range(max_rounds):
        result = _chat(messages)
        msg = result.get("message", {})
        tool_calls = msg.get("tool_calls", [])

        if not tool_calls:
            # No more tools to call — return final answer
            return msg.get("content", "(no response)")

        # Append the assistant's tool-call message
        messages.append({"role": "assistant", **msg})

        # Execute each tool and feed results back
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args)

            tool_result = _tool_dispatch(name, args)
            print(f"  🔧 [{round_num+1}] {name}({args}) → {tool_result}")

            messages.append({
                "role": "tool",
                "content": tool_result,
            })

    return "(max rounds reached without final answer)"


# ── Demo ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Running offline tool-calling agent (Ollama)...\n")

    answer = run_agent("What's the weather in Milan? Also search for 'LangGraph checkpointing'.")
    print(f"\nFinal answer: {answer}")