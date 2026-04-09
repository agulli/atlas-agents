"""
Atlas v0.1 — Plan-and-Execute Variant (Online Extra)
======================================================
Separates planning from execution to reduce context window bloat.
The planner LLM creates a step-by-step plan, then the executor
runs each step independently.

Usage:
    python atlas_v01_plan_and_execute.py "Research the top 3 AI agent frameworks"

Requires: pip install openai
"""

import json
import sys
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import require_key, OPENAI_MODEL

client = OpenAI(api_key=require_key("openai"))


# ── Phase 1: Planning ───────────────────────────────────────────────

def create_plan(task: str) -> list[str]:
    """Use the LLM to break a task into discrete steps."""
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": """You are a planning agent.
            Break the user's task into 3-5 concrete, sequential steps.
            Output ONLY a numbered list. Each step should be independently executable.
            Example:
            1. Search for X
            2. Read the top result about Y
            3. Summarize findings"""},
            {"role": "user", "content": task},
        ],
        temperature=0,
    )
    plan_text = response.choices[0].message.content or ""
    steps = [line.strip() for line in plan_text.split("\n")
             if line.strip() and line.strip()[0].isdigit()]
    return steps


# ── Phase 2: Execution ──────────────────────────────────────────────

def execute_step(step: str, context: str) -> str:
    """Execute a single step with the accumulated context."""
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": """You are an execution agent.
            Complete the assigned step using your knowledge.
            Be concise and factual. If the step asks you to search,
            provide what you know about the topic."""},
            {"role": "user", "content": f"Previous context:\n{context}\n\nStep to execute:\n{step}"},
        ],
        max_tokens=500,
    )
    return response.choices[0].message.content or ""


# ── Phase 3: Synthesis ──────────────────────────────────────────────

def synthesize(task: str, results: list[str]) -> str:
    """Combine all step results into a final answer."""
    combined = "\n\n".join(f"Step {i+1} result:\n{r}" for i, r in enumerate(results))
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "Synthesize these research results into a clear, structured answer."},
            {"role": "user", "content": f"Original task: {task}\n\nResults:\n{combined}"},
        ],
    )
    return response.choices[0].message.content or ""


# ── Orchestrator ────────────────────────────────────────────────────

def plan_and_execute(task: str) -> str:
    """Run the full Plan-and-Execute pipeline."""
    # Phase 1
    print("📋 Phase 1: Planning...")
    steps = create_plan(task)
    for i, step in enumerate(steps, 1):
        print(f"  {step}")

    # Phase 2
    print("\n⚡ Phase 2: Executing...")
    results = []
    context = ""
    for i, step in enumerate(steps, 1):
        print(f"  [{i}/{len(steps)}] {step[:60]}...", end=" ")
        result = execute_step(step, context)
        results.append(result)
        context += f"\n{result}"  # Accumulate context
        print("✅")

    # Phase 3
    print("\n🧩 Phase 3: Synthesizing...")
    return synthesize(task, results)


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Research the top 3 AI agent frameworks in 2025"
    print(f"🔍 Atlas v0.1 (Plan-and-Execute) — {task}\n")
    answer = plan_and_execute(task)
    print(f"\n{'='*60}\nFINAL ANSWER:\n{'='*60}\n{answer}")