"""
Multi-Persona Router (Online Extra)
=====================================
A router prompt that classifies user intent into predefined categories
before dispatching to the appropriate specialist agent.

Usage:
    python multi_persona_router.py "I need help with my API integration"
"""

import json
import sys
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import require_key, OPENAI_MODEL

client = OpenAI(api_key=require_key("openai"))


# ── Routing Options ─────────────────────────────────────────────────

ROUTING_OPTIONS = {
    "technical": "Bug reports, API issues, integration help, error troubleshooting",
    "billing": "Payment questions, refunds, subscription changes, invoices",
    "sales": "Pricing inquiries, demos, enterprise plans, feature requests",
    "general": "General questions, company policies, account management",
}

# ── Persona Prompts ─────────────────────────────────────────────────

PERSONA_PROMPTS = {
    "technical": "You are a senior technical support engineer. Be precise, ask for error logs.",
    "billing": "You are a billing specialist. Be empathetic, reference specific account details.",
    "sales": "You are a solutions consultant. Be enthusiastic, focus on value propositions.",
    "general": "You are a friendly support agent. Be helpful and direct.",
}


def build_router_prompt(query: str) -> str:
    """Build a classification prompt for intent routing."""
    options_str = "\n".join([f"- {k}: {v}" for k, v in ROUTING_OPTIONS.items()])
    return f"""You are a classification router.
Read the user's query and categorize it into EXACTLY ONE of the following buckets:

OPTIONS:
{options_str}

QUERY: {query}

Output strictly the category name, nothing else."""


def route_and_respond(query: str) -> tuple[str, str]:
    """Route a query to the right persona and generate a response."""
    # Step 1: Classify intent
    router_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": build_router_prompt(query)}],
        temperature=0,
    )
    category = router_response.choices[0].message.content.strip().lower()

    if category not in PERSONA_PROMPTS:
        category = "general"

    # Step 2: Respond with the right persona
    persona = PERSONA_PROMPTS[category]
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": persona},
            {"role": "user", "content": query},
        ],
        max_tokens=500,
    )
    return category, response.choices[0].message.content


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "My API key stopped working after the update"
    print(f"📨 Query: {query}\n")

    category, answer = route_and_respond(query)
    print(f"🏷️ Routed to: {category}")
    print(f"🤖 Response:\n{answer}")