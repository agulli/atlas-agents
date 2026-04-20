"""
Atlas v0.1 — Anthropic Variant (Online Extra)
================================================
Same ReAct pattern from Chapter 1, rewritten for Claude's tool-calling API.
Demonstrates how Anthropic uses `input_schema` instead of `parameters`.

Usage:
    python atlas_v01_anthropic.py "What is the Model Context Protocol?"

Requires: pip install anthropic
"""

import ast
import json
import sys
from pathlib import Path

from anthropic import Anthropic

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import require_key, ANTHROPIC_MODEL
from shared.skills import WebSkill

_web = WebSkill()

client = Anthropic(api_key=require_key("anthropic"))

# ── Tool Definitions (Anthropic format) ──────────────────────────────

TOOLS = [
    {
        "name": "search_web",
        "description": "Search the web using DuckDuckGo. Returns top results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "calculator",
        "description": "Evaluate a mathematical expression.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Math expression to evaluate, e.g. '2 + 3 * 4'"}
            },
            "required": ["expression"],
        },
    },
]


# ── Tool Implementations ────────────────────────────────────────────

def execute_tool(name: str, args: dict) -> str:
    if name == "search_web":
        return _web._search(args["query"])
    elif name == "calculator":
        try:
            # ast.literal_eval is safe — it only parses Python literals,
            # not arbitrary expressions. For real math eval, use a proper
            # parser like sympy. Never use eval() on LLM-generated input.
            result = ast.literal_eval(args["expression"])
            return str(result)
        except (ValueError, SyntaxError) as e:
            return f"Error: {e}"
    return f"Unknown tool: {name}"


# ── ReAct Loop (Anthropic API) ──────────────────────────────────────

def run_anthropic_react(prompt: str, max_iterations: int = 5) -> str:
    """A ReAct loop using the Anthropic tool-calling API."""
    messages = [{"role": "user", "content": prompt}]

    for iteration in range(max_iterations):
        print(f"\n── Iteration {iteration + 1} ──")

        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1000,
            system="You are Atlas, a research assistant. Use tools to find answers.",
            tools=TOOLS,
            messages=messages,
        )

        # Collect assistant content blocks
        assistant_content = response.content
        messages.append({"role": "assistant", "content": assistant_content})

        # Check for tool use blocks
        tool_use_blocks = [b for b in assistant_content if b.type == "tool_use"]

        if not tool_use_blocks:
            # No tools called — extract final text answer
            text_blocks = [b.text for b in assistant_content if b.type == "text"]
            print("✅ Final answer received.")
            return "\n".join(text_blocks)

        # Execute each tool and feed results back
        tool_results = []
        for block in tool_use_blocks:
            print(f"🔧 Calling: {block.name}({block.input})")
            result = execute_tool(block.name, block.input)
            print(f"📋 Result: {result[:150]}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    return "Agent reached maximum iterations."


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What is 42 * 17?"
    print(f"🔍 Atlas v0.1 (Anthropic) — {question}\n")
    answer = run_anthropic_react(question)
    print(f"\n{'='*50}\nFINAL ANSWER:\n{'='*50}\n{answer}")