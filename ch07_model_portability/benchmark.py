"""
Atlas v0.7 — Multi-Model Benchmark
====================================
Chapter 7 Project: Run the same agent task across 4 models and compare.

Usage:
    python benchmark.py

Requires: pip install litellm
"""

import time
import json
import sys
from pathlib import Path
from dataclasses import dataclass

import litellm

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.config import (
    OPENAI_API_KEY, GOOGLE_API_KEY, ANTHROPIC_API_KEY,
    OPENAI_MODEL, ANTHROPIC_MODEL, GEMINI_MODEL, OLLAMA_MODEL,
    OPENAI_BASE_URL, ANTHROPIC_BASE_URL,
)


# ── Models to Benchmark ─────────────────────────────────────────────

# Cloud rows are added only when their key is set AND the endpoint isn't
# redirected to a local server (a local .env points both SDKs at Ollama).
MODELS = []
if OPENAI_API_KEY and not OPENAI_BASE_URL:
    MODELS.append({"id": OPENAI_MODEL, "display": OPENAI_MODEL, "provider": "openai"})
if GOOGLE_API_KEY:
    MODELS.append({"id": f"gemini/{GEMINI_MODEL}", "display": GEMINI_MODEL, "provider": "google"})
if ANTHROPIC_API_KEY and not ANTHROPIC_BASE_URL:
    MODELS.append({"id": f"anthropic/{ANTHROPIC_MODEL}", "display": ANTHROPIC_MODEL, "provider": "anthropic"})
# Ollama (always attempted; fails fast if `ollama serve` isn't running).
# ollama_chat/ uses Ollama's chat endpoint, which supports native tool calls.
MODELS.append({"id": f"ollama_chat/{OLLAMA_MODEL}", "display": f"{OLLAMA_MODEL} (local)", "provider": "ollama"})


# ── Tool Schema ──────────────────────────────────────────────────────

TOOLS = [{
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "Search the web for information.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    }
}]


# ── Benchmark Cases ──────────────────────────────────────────────────

BENCHMARK_CASES = [
    {
        "name": "Simple factual",
        "messages": [
            {"role": "system", "content": "You are a research assistant. Use tools when needed."},
            {"role": "user", "content": "What is the Model Context Protocol?"}
        ],
        "expect_tool_call": False,
        "expected_keywords": ["protocol", "tool"],
    },
    {
        "name": "Tool calling",
        "messages": [
            {"role": "system", "content": "You are a research assistant. Always search before answering."},
            {"role": "user", "content": "Search for the latest LangGraph release notes."}
        ],
        "expect_tool_call": True,
        "expected_keywords": [],
    },
    {
        "name": "Structured reasoning",
        "messages": [
            {"role": "system", "content": "You are a research assistant. Think step by step."},
            {"role": "user", "content": "Compare LangGraph and CrewAI for a production agent system. Give pros and cons."}
        ],
        "expect_tool_call": False,
        "expected_keywords": ["langgraph", "crewai"],
    },
]


# ── Benchmark Runner ─────────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    model: str
    case_name: str
    success: bool
    latency_ms: int
    tool_call_made: bool
    tool_call_correct: bool
    has_keywords: bool
    tokens_in: int
    tokens_out: int
    cost_usd: float
    error: str | None = None


def run_single_benchmark(model_id: str, case: dict) -> BenchmarkResult:
    """Run a single benchmark case on a single model."""
    start = time.time()
    try:
        response = litellm.completion(
            model=model_id,
            messages=case["messages"],
            tools=TOOLS if case["expect_tool_call"] else None,
            timeout=30,
        )
        latency = int((time.time() - start) * 1000)

        msg = response.choices[0].message
        content = msg.content or ""
        tool_calls = msg.tool_calls or []

        # Check tool calling
        tool_call_made = len(tool_calls) > 0
        tool_call_correct = tool_call_made == case["expect_tool_call"]

        # Check keywords
        content_lower = content.lower()
        has_keywords = all(kw in content_lower for kw in case["expected_keywords"])

        # Cost estimation
        usage = response.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0
        try:
            cost = litellm.completion_cost(response)
        except Exception:
            cost = 0.0

        return BenchmarkResult(
            model=model_id, case_name=case["name"],
            success=True, latency_ms=latency,
            tool_call_made=tool_call_made,
            tool_call_correct=tool_call_correct,
            has_keywords=has_keywords,
            tokens_in=tokens_in, tokens_out=tokens_out,
            cost_usd=cost,
        )
    except Exception as e:
        return BenchmarkResult(
            model=model_id, case_name=case["name"],
            success=False, latency_ms=int((time.time() - start) * 1000),
            tool_call_made=False, tool_call_correct=False,
            has_keywords=False, tokens_in=0, tokens_out=0,
            cost_usd=0, error=str(e)[:100],
        )


def run_full_benchmark():
    """Run all cases across all models."""
    results: dict[str, list[BenchmarkResult]] = {}

    for model in MODELS:
        model_id = model["id"]
        display = model["display"]
        print(f"\n{'─'*50}")
        print(f"Benchmarking: {display} ({model_id})")
        print(f"{'─'*50}")

        model_results = []
        for case in BENCHMARK_CASES:
            print(f"  {case['name']}...", end=" ", flush=True)
            result = run_single_benchmark(model_id, case)
            status = "✅" if result.success else f"❌ {result.error}"
            print(f"{status} ({result.latency_ms}ms)")
            model_results.append(result)

        results[display] = model_results

    return results


def print_report(results: dict[str, list[BenchmarkResult]]):
    """Print a comparison table."""
    print(f"\n\n{'='*75}")
    print("MULTI-MODEL BENCHMARK RESULTS")
    print(f"{'='*75}\n")

    header = f"{'Model':<20} | {'Success':>8} | {'Avg Cost':>9} | {'Avg Latency':>12} | {'Tool OK':>8}"
    print(header)
    print("─" * len(header))

    for display, model_results in results.items():
        total = len(model_results)
        success_rate = sum(1 for r in model_results if r.success) / total * 100
        avg_cost = sum(r.cost_usd for r in model_results) / total
        avg_latency = sum(r.latency_ms for r in model_results) / total
        tool_cases = [r for r in model_results if r.tool_call_made or any(
            c["expect_tool_call"] for c in BENCHMARK_CASES
            if c["name"] == r.case_name
        )]
        tool_ok = sum(1 for r in model_results if r.tool_call_correct) / total * 100

        print(f"{display:<20} | {success_rate:>7.0f}% | ${avg_cost:>7.4f} | {avg_latency:>10.0f}ms | {tool_ok:>7.0f}%")

    print()


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("⚡ Atlas v0.7 — Multi-Model Benchmark")
    print(f"Models: {len(MODELS)} | Cases: {len(BENCHMARK_CASES)}\n")

    if not MODELS:
        print("❌ No API keys configured. Set at least one in .env")
        sys.exit(1)

    results = run_full_benchmark()
    print_report(results)
