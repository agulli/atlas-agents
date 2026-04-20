"""
Atlas v0.3 — A CLI Research Agent with Pluggable Skills
=========================================================
Chapter 3 Project: A modular agent using the SkillRegistry.

Usage:
    python atlas_v03.py "Summarize the latest changes in the LangGraph library"

Requires: pip install openai
"""

import json
import sys
from pathlib import Path
from openai import OpenAI

# ── Configuration ────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.config import require_key, OPENAI_MODEL
from shared.skills import SkillRegistry, WebSkill, FileSkill, CodeSkill

client = OpenAI(api_key=require_key("openai"))
MAX_ITERATIONS = 6

# ── Skill Setup ─────────────────────────────────────────────────────

registry = SkillRegistry()
registry.register(WebSkill())
registry.register(FileSkill(base_dir="./workspace"))
registry.register(CodeSkill())

# ── System Prompt ────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Atlas, a modular research assistant.

You solve tasks by using your skills. For each step, think about which tool is most appropriate.
If the user wants you to save something, use the FileSkill.

RULES:
- Always think before acting.
- Use at most 6 tool calls.
- Cite your sources.
- If you save a file, tell the user the path.
"""

# ── ReAct Loop ───────────────────────────────────────────────────────

def run_atlas(question: str):
    """Run the Atlas v0.3 agent loop."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    print(f"🔍 Atlas v0.3 — Researching: {question}\n")

    for iteration in range(MAX_ITERATIONS):
        # 1. Get completion from LLM
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=registry.get_all_tools(),
        )

        msg = response.choices[0].message
        messages.append(msg)

        # 2. Check for final answer
        if not msg.tool_calls:
            print("✅ Final answer received.")
            return msg.content

        # 3. Execute tools
        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)

            print(f"🔧 Calling: {fn_name}({fn_args})")
            
            # Execute through the registry
            result = registry.execute_tool(fn_name, fn_args)

            # Show preview
            preview = result[:200] + "..." if len(result) > 200 else result
            print(f"📋 Result: {preview}")

            # Feed back to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    return "Error: Agent reached maximum iterations."

# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        question = "What are the latest features of LangGraph v0.3? Summarize them and save to langgraph_news.md"
    else:
        question = " ".join(sys.argv[1:])

    answer = run_atlas(question)
    print(f"\n{'='*60}\nFINAL ANSWER:\n{'='*60}")
    print(answer)
