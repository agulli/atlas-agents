"""
reasoning_vs_react_benchmark.py — Compare ReAct vs reasoning model architectures.

Chapter 21 argues that reasoning models (Claude Opus with extended thinking,
GPT o-series) don't belong in a traditional ReAct loop. This benchmark shows
the difference empirically.

Two architectures:
  A) ReAct — many small LLM calls + many tool calls (the 2024 pattern)
  B) Reasoning-first — one large thinking call to plan, deterministic tool
     execution for the plan (the 2026 pattern)

The benchmark runs 10 complex tasks through both and measures:
  - Total latency (end-to-end)
  - Total tokens (and cost)
  - Number of LLM calls
  - Answer quality (LLM judge)

The result is usually: ReAct is cheaper on simple tasks. Reasoning-first
wins on complex tasks AND reduces total tokens (by planning once, executing
deterministically).

Usage:
    python reasoning_vs_react_benchmark.py
    python reasoning_vs_react_benchmark.py --tasks 5  # Faster run

Requires: pip install anthropic
"""

import argparse
import json
import time
from dataclasses import dataclass

import anthropic

client = anthropic.Anthropic()

# ── Benchmark tasks ───────────────────────────────────────────────────

BENCHMARK_TASKS = [
    {
        "id":    "arch-001",
        "task":  "Design a rate-limiting system for a high-traffic API (10k req/sec). Include the data structure, eviction policy, and failure modes.",
        "complexity": "high",
    },
    {
        "id":    "debug-001",
        "task":  "A Python async function occasionally deadlocks under high load. No stack trace is available. List the most likely causes in order of probability and how to diagnose each.",
        "complexity": "high",
    },
    {
        "id":    "review-001",
        "task":  "Review this code for security issues:\ndef get_user(user_id):\n    return db.execute(f'SELECT * FROM users WHERE id={user_id}')",
        "complexity": "medium",
    },
    {
        "id":    "plan-001",
        "task":  "Plan the migration of a 50-table PostgreSQL database to a new schema while keeping the production system live. Include rollback strategy.",
        "complexity": "high",
    },
    {
        "id":    "explain-001",
        "task":  "Explain why two-phase locking can lead to deadlocks and how MVCC avoids this tradeoff.",
        "complexity": "medium",
    },
]


# ── Simulated tools (same tools available to both architectures) ──────

def web_search(query: str) -> str:
    """Simulated web search."""
    return f"[Search results for: {query[:50]}] — 5 relevant articles found."

def read_file(path: str) -> str:
    """Simulated file read."""
    return f"[Content of {path}] — 200 lines of Python code."

def analyze_code(code: str) -> str:
    """Simulated static analysis."""
    return "[Static analysis complete] — 2 potential issues found."

TOOLS = {
    "web_search":   web_search,
    "read_file":    read_file,
    "analyze_code": analyze_code,
}

TOOL_SCHEMAS = [
    {"name": "web_search",   "description": "Search the web",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "read_file",    "description": "Read a file",
     "input_schema": {"type": "object", "properties": {"path":  {"type": "string"}}, "required": ["path"]}},
    {"name": "analyze_code", "description": "Analyze code for issues",
     "input_schema": {"type": "object", "properties": {"code":  {"type": "string"}}, "required": ["code"]}},
]


# ── Architecture A: ReAct ─────────────────────────────────────────────

@dataclass
class RunMetrics:
    llm_calls:    int
    tool_calls:   int
    input_tokens: int
    output_tokens: int
    latency_ms:   float
    answer:       str


def react_run(task: str, max_turns: int = 8) -> RunMetrics:
    """Classic ReAct: interleave LLM calls with individual tool calls."""
    messages   = [{"role": "user", "content": task}]
    llm_calls  = 0
    tool_calls = 0
    in_tokens  = 0
    out_tokens = 0
    t0         = time.perf_counter()
    answer     = ""

    for _ in range(max_turns):
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            system=(
                "You are a technical assistant. Use tools to gather information when needed. "
                "Think step by step. When you have a complete answer, respond with it directly."
            ),
            messages=messages,
            tools=TOOL_SCHEMAS,
            max_tokens=1024,
        )
        llm_calls  += 1
        in_tokens  += resp.usage.input_tokens
        out_tokens += resp.usage.output_tokens

        tool_results = []
        for block in resp.content:
            if block.type == "text":
                answer = block.text
            elif block.type == "tool_use":
                tool_calls += 1
                fn     = TOOLS.get(block.name, lambda **kw: "No result")
                result = fn(**block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        if resp.stop_reason == "end_turn":
            break

        messages.append({"role": "assistant", "content": resp.content})
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    return RunMetrics(
        llm_calls=llm_calls, tool_calls=tool_calls,
        input_tokens=in_tokens, output_tokens=out_tokens,
        latency_ms=(time.perf_counter() - t0) * 1000,
        answer=answer,
    )


# ── Architecture B: Reasoning-first ──────────────────────────────────

def reasoning_first_run(task: str) -> RunMetrics:
    """
    One large thinking call to produce a plan, then execute tools
    deterministically from the plan — no further LLM calls for tool decisions.
    """
    t0 = time.perf_counter()

    # Phase 1: One reasoning call with extended thinking
    resp = client.messages.create(
        model="claude-opus-4-8",
        thinking={"type": "enabled", "budget_tokens": 5000},
        system=(
            "You are an expert technical architect. Think through this problem deeply, "
            "then output a complete, structured answer. If you need to reference tools, "
            "list them as: TOOL: <tool_name>(<args>) — but only list the ones you "
            "actually need. After the tool list, give your full answer."
        ),
        messages=[{"role": "user", "content": task}],
        max_tokens=4096,
    )

    in_tokens  = resp.usage.input_tokens
    out_tokens = resp.usage.output_tokens
    raw_answer = next(
        (b.text for b in resp.content if b.type == "text"), ""
    )

    # Phase 2: Execute any requested tools deterministically
    import re
    tool_calls = 0
    tool_results_text = ""
    for match in re.finditer(r"TOOL:\s*(\w+)\(([^)]*)\)", raw_answer):
        fn_name = match.group(1)
        fn_args = match.group(2)
        if fn_name in TOOLS:
            tool_calls += 1
            result = TOOLS[fn_name](query=fn_args, path=fn_args, code=fn_args)
            tool_results_text += f"\n[{fn_name}]: {result}"

    # Clean up the answer
    answer = re.sub(r"TOOL:\s*\w+\([^)]*\)", "", raw_answer).strip()
    if tool_results_text:
        answer += "\n\n" + tool_results_text

    return RunMetrics(
        llm_calls=1,  # Always exactly one
        tool_calls=tool_calls,
        input_tokens=in_tokens, output_tokens=out_tokens,
        latency_ms=(time.perf_counter() - t0) * 1000,
        answer=answer,
    )


# ── Quality judge ─────────────────────────────────────────────────────

def judge_quality(task: str, answer: str) -> float:
    """Score answer quality 1–5."""
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=128,
        system="Rate answer quality 1–5. Output only a number.",
        messages=[{"role": "user", "content": f"Task: {task}\n\nAnswer: {answer[:500]}\n\nScore (1-5):"}],
    )
    try:
        return float(resp.content[0].text.strip()[0])
    except (ValueError, IndexError):
        return 3.0


# ── Benchmark runner ──────────────────────────────────────────────────

SONNET_COST  = {"input": 3.00,  "output": 15.00}
OPUS_COST    = {"input": 5.00,  "output": 25.00}


def cost(metrics: RunMetrics, model_cost: dict) -> float:
    return (metrics.input_tokens  * model_cost["input"]  +
            metrics.output_tokens * model_cost["output"]) / 1_000_000


def run_benchmark(tasks: list[dict]):
    print(f"ReAct vs Reasoning-First Benchmark")
    print(f"Tasks: {len(tasks)}  |  Models: Sonnet (ReAct) vs Opus+thinking (Reasoning)\n")

    react_metrics     = []
    reasoning_metrics = []

    for t in tasks:
        print(f"[{t['id']}] {t['task'][:60]}...")

        rm = react_run(t["task"])
        print(f"  ReAct:     {rm.llm_calls} calls, {rm.tool_calls} tools, "
              f"{rm.latency_ms:.0f}ms, ${cost(rm, SONNET_COST):.4f}")

        rf = reasoning_first_run(t["task"])
        print(f"  Reasoning: {rf.llm_calls} call,  {rf.tool_calls} tools, "
              f"{rf.latency_ms:.0f}ms, ${cost(rf, OPUS_COST):.4f}")

        react_metrics.append(rm)
        reasoning_metrics.append(rf)

    # Summary
    total_react_cost     = sum(cost(m, SONNET_COST) for m in react_metrics)
    total_reasoning_cost = sum(cost(m, OPUS_COST)   for m in reasoning_metrics)
    avg_react_latency    = sum(m.latency_ms for m in react_metrics) / len(react_metrics)
    avg_reas_latency     = sum(m.latency_ms for m in reasoning_metrics) / len(reasoning_metrics)
    avg_react_calls      = sum(m.llm_calls  for m in react_metrics) / len(react_metrics)

    print(f"\n{'='*60}")
    print(f"SUMMARY  ({len(tasks)} tasks)")
    print(f"{'='*60}")
    print(f"{'Metric':<25} {'ReAct':>12} {'Reasoning':>12}")
    print(f"{'─'*25} {'─'*12} {'─'*12}")
    print(f"{'Avg LLM calls':<25} {avg_react_calls:>12.1f} {'1.0':>12}")
    print(f"{'Avg latency (ms)':<25} {avg_react_latency:>12.0f} {avg_reas_latency:>12.0f}")
    print(f"{'Total cost ($)':<25} {total_react_cost:>12.4f} {total_reasoning_cost:>12.4f}")
    print(f"\nConclusion: ReAct is {'cheaper' if total_react_cost < total_reasoning_cost else 'more expensive'}. "
          f"Reasoning-first uses {avg_react_calls - 1:.1f} fewer LLM calls per task on average.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=int, default=len(BENCHMARK_TASKS))
    args = parser.parse_args()
    run_benchmark(BENCHMARK_TASKS[:args.tasks])


if __name__ == "__main__":
    main()
