"""
Handoff with Context Compression (Online Extra)
==================================================
When handing off between agents, the raw conversation history
can blow up the context window. This module compresses the
history into a concise summary before injecting it into the
target agent's system prompt.

Usage:
    python handoff_with_context.py

Requires: pip install openai
"""

import sys
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import require_key, OPENAI_MODEL

client = OpenAI(api_key=require_key("openai"))


def compress_history(source_agent: str, conversation: list[dict]) -> str:
    """Use a fast model to compress conversation history before handoff."""
    history_text = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}" for msg in conversation
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # Fast and cheap for compression
        messages=[{
            "role": "user",
            "content": f"""Summarize what {source_agent} accomplished in this conversation.
Include: key facts gathered, decisions made, and unresolved questions.
Keep it under 100 words.

Conversation:
{history_text}""",
        }],
        max_tokens=150,
        temperature=0,
    )
    return response.choices[0].message.content


def build_handoff_prompt(source_agent: str, target_agent: str,
                         conversation: list[dict]) -> str:
    """Build the system prompt for the target agent with compressed context."""
    compressed = compress_history(source_agent, conversation)

    return f"""HANDOFF FROM: {source_agent}
CONTEXT OF WORK COMPLETED:
{compressed}

YOUR ROLE: {target_agent}
Continue from where {source_agent} left off. Do NOT repeat already-completed work.
Focus on your specialization."""


# ── Demo ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Simulate a conversation from the Technical Support agent
    conversation = [
        {"role": "user", "content": "My API integration is failing with 401 errors"},
        {"role": "assistant", "content": "I see you're getting 401 Unauthorized errors. Let me check your API key status."},
        {"role": "assistant", "content": "I found that your API key expired on March 15th. You need to regenerate it from the dashboard."},
        {"role": "user", "content": "I regenerated it but now I'm getting 403 errors instead."},
        {"role": "assistant", "content": "A 403 means your new key doesn't have the right permissions. This is a billing-tier issue because your current plan doesn't include API access. I need to hand you off to billing."},
    ]

    prompt = build_handoff_prompt(
        source_agent="Technical Support",
        target_agent="Billing Specialist",
        conversation=conversation,
    )

    print("📋 Handoff Prompt for Target Agent:")
    print("=" * 50)
    print(prompt)