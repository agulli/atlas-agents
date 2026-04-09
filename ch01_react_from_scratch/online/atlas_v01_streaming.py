"""
Atlas v0.1 — Streaming Variant (Online Extra)
================================================
Demonstrates real-time streaming of both LLM thoughts and tool calls
using the Anthropic streaming API.

Usage:
    python atlas_v01_streaming.py "What is the Model Context Protocol?"

Requires: pip install anthropic
"""

import sys
from pathlib import Path

from anthropic import Anthropic

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import require_key, ANTHROPIC_MODEL

client = Anthropic(api_key=require_key("anthropic"))


def stream_agent_response(prompt: str):
    """Stream both thinking and tool execution in real-time."""
    print("🔄 Streaming response...\n")

    with client.messages.stream(
        model=ANTHROPIC_MODEL,
        max_tokens=1000,
        system="You are Atlas, a research assistant. Think step by step before answering.",
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        current_type = None
        for event in stream:
            # Text delta — the LLM is "thinking" or answering
            if hasattr(event, "type") and event.type == "content_block_start":
                block = event.content_block
                if block.type == "text":
                    if current_type != "text":
                        current_type = "text"
                        print("💭 ", end="", flush=True)
                elif block.type == "tool_use":
                    current_type = "tool"
                    print(f"\n🔧 [Tool Call: {block.name}]", flush=True)

            elif hasattr(event, "type") and event.type == "content_block_delta":
                delta = event.delta
                if hasattr(delta, "text"):
                    print(delta.text, end="", flush=True)
                elif hasattr(delta, "partial_json"):
                    print(f"  args: {delta.partial_json}", end="", flush=True)

    print("\n\n✅ Stream complete.")


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Explain how AI agents use tools, step by step."
    print(f"🔍 Atlas v0.1 (Streaming) — {prompt}\n")
    stream_agent_response(prompt)