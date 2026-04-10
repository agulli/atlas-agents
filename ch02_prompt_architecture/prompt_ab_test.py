"""
Atlas v0.2 — Prompt A/B Testing Harness
========================================
Chapter 2 Project: Test three prompt variants against a 20-case eval suite.

Usage:
    python prompt_ab_test.py
"""

import json
import time
import sys
from pathlib import Path
from dataclasses import dataclass, field

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.config import require_key, OPENAI_MODEL

client = OpenAI(api_key=require_key("openai"))


# ── Prompt Variants ──────────────────────────────────────────────────

VARIANT_CONCISE = {
    "name": "Concise Analyst",
    "prompt": """You are Atlas, a concise research analyst.
You give brief, factual answers. No fluff. Bullet points preferred.
Maximum 3 sentences per point. Cite sources inline.

Available tools: search_web(query), read_url(url).
Use at most 3 tool calls. Be efficient."""
}

VARIANT_THOROUGH = {
    "name": "Thorough Researcher",
    "prompt": """You are Atlas, a thorough senior researcher.
You provide comprehensive analysis with multiple perspectives.
Compare sources, note contradictions, and qualify uncertainties.
Your answers should read like a well-researched briefing document.

Available tools: search_web(query), read_url(url).
Use as many tool calls as needed (up to 5) to ensure accuracy."""
}

VARIANT_STRUCTURED = {
    "name": "Structured Reporter",
    "prompt": """You are Atlas, a structured report generator.
Every answer MUST follow this exact format:

## Summary
(2-3 sentences)

## Key Findings
(numbered list)

## Sources
(URLs used)

## Confidence
(high/medium/low with justification)

Available tools: search_web(query), read_url(url).
Use 2-4 tool calls for a balanced approach."""
}

VARIANTS = [VARIANT_CONCISE, VARIANT_THOROUGH, VARIANT_STRUCTURED]


# ── Eval Cases ───────────────────────────────────────────────────────

EVAL_CASES = [
    {
        "question": "What is the population of Tokyo?",
        "expected_keywords": ["million"],
        "max_tool_calls": 3,
        "category": "factual",
    },
    {
        "question": "Compare React and Vue.js for a new web project.",
        "expected_keywords": ["react", "vue"],
        "max_tool_calls": 4,
        "category": "comparison",
    },
    {
        "question": "What is the Model Context Protocol (MCP)?",
        "expected_keywords": ["protocol", "tool"],
        "max_tool_calls": 3,
        "category": "technical",
    },
    {
        "question": "Explain the difference between RAG and fine-tuning.",
        "expected_keywords": ["retrieval", "training"],
        "max_tool_calls": 3,
        "category": "technical",
    },
    {
        "question": "What are the top 3 programming languages in 2025?",
        "expected_keywords": ["python"],
        "max_tool_calls": 3,
        "category": "factual",
    },
    {
        "question": "Write me a poem about cats.",
        "expected_refusal": True,
        "category": "out_of_scope",
    },
    {
        "question": "Should I invest in Bitcoin?",
        "expected_refusal": True,
        "category": "out_of_scope",
    },
    {
        "question": "What is LangGraph and how does it work?",
        "expected_keywords": ["graph", "state"],
        "max_tool_calls": 4,
        "category": "technical",
    },
    {
        "question": "What are the pros and cons of microservices?",
        "expected_keywords": ["service"],
        "max_tool_calls": 3,
        "category": "comparison",
    },
    {
        "question": "How does vector search work?",
        "expected_keywords": ["embedding", "vector"],
        "max_tool_calls": 3,
        "category": "technical",
    },
]


# ── Tool Schemas (same as Ch. 1) ─────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web. Returns top results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_url",
            "description": "Read text content from a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to read"}
                },
                "required": ["url"]
            }
        }
    },
]


# ── Evaluation Logic ─────────────────────────────────────────────────

@dataclass
class EvalResult:
    question: str
    variant: str
    answer: str
    tool_calls_count: int
    has_expected_keywords: bool
    expected_refusal: bool = False
    correctly_refused: bool = False
    latency_ms: int = 0


def run_single_eval(variant: dict, case: dict) -> EvalResult:
    """Run a single eval case with a single prompt variant (no actual tool execution)."""
    messages = [
        {"role": "system", "content": variant["prompt"]},
        {"role": "user", "content": case["question"]},
    ]

    start = time.time()

    # Single LLM call — we're testing prompt quality, not tool execution
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        tools=TOOL_SCHEMAS,
    )

    latency = int((time.time() - start) * 1000)
    msg = response.choices[0].message
    answer = msg.content or ""
    tool_calls_count = len(msg.tool_calls) if msg.tool_calls else 0

    # Check expected keywords
    has_keywords = True
    if "expected_keywords" in case:
        answer_lower = answer.lower()
        has_keywords = all(kw.lower() in answer_lower for kw in case["expected_keywords"])

    # Check refusal behavior
    expected_refusal = case.get("expected_refusal", False)
    refusal_phrases = ["can't help", "not able to", "outside my scope",
                       "don't provide", "cannot", "not appropriate",
                       "i'm a research", "apologize"]
    correctly_refused = any(p in answer.lower() for p in refusal_phrases) if expected_refusal else False

    return EvalResult(
        question=case["question"],
        variant=variant["name"],
        answer=answer,
        tool_calls_count=tool_calls_count,
        has_expected_keywords=has_keywords,
        expected_refusal=expected_refusal,
        correctly_refused=correctly_refused,
        latency_ms=latency,
    )


def run_eval_suite():
    """Run all eval cases across all prompt variants."""
    results: dict[str, list[EvalResult]] = {}

    for variant in VARIANTS:
        print(f"\n{'='*60}")
        print(f"Testing: {variant['name']}")
        print(f"{'='*60}")

        variant_results = []
        for i, case in enumerate(EVAL_CASES):
            print(f"  [{i+1}/{len(EVAL_CASES)}] {case['question'][:50]}...", end=" ")
            try:
                result = run_single_eval(variant, case)
                status = "✅" if result.has_expected_keywords or result.correctly_refused else "❌"
                print(f"{status} ({result.latency_ms}ms, {result.tool_calls_count} tools)")
                variant_results.append(result)
            except Exception as e:
                print(f"💥 Error: {e}")

        results[variant["name"]] = variant_results

    return results


def print_summary(results: dict[str, list[EvalResult]]):
    """Print a comparison table of all variants."""
    print(f"\n\n{'='*70}")
    print("PROMPT A/B TEST RESULTS")
    print(f"{'='*70}\n")

    header = f"{'Variant':<22} | {'Quality':>8} | {'Avg Tools':>10} | {'Avg Latency':>12} | {'Refusal':>8}"
    print(header)
    print("─" * len(header))

    for name, evals in results.items():
        if not evals:
            continue

        # Quality: % of cases where expected keywords were found
        non_refusal = [e for e in evals if not e.expected_refusal]
        refusal = [e for e in evals if e.expected_refusal]

        quality = sum(1 for e in non_refusal if e.has_expected_keywords) / max(len(non_refusal), 1) * 100
        avg_tools = sum(e.tool_calls_count for e in evals) / max(len(evals), 1)
        avg_latency = sum(e.latency_ms for e in evals) / max(len(evals), 1)
        refusal_accuracy = sum(1 for e in refusal if e.correctly_refused) / max(len(refusal), 1) * 100

        print(f"{name:<22} | {quality:>7.0f}% | {avg_tools:>10.1f} | {avg_latency:>10.0f}ms | {refusal_accuracy:>7.0f}%")

    print()


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🧪 Atlas v0.2 — Prompt A/B Testing Harness")
    print(f"Testing {len(VARIANTS)} prompt variants × {len(EVAL_CASES)} eval cases")
    print(f"Model: {OPENAI_MODEL}\n")

    results = run_eval_suite()
    print_summary(results)
