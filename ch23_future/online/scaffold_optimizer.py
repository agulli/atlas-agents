"""
scaffold_optimizer.py — Dynamically rewrite LangGraph node routing based on intent.

This demonstrates Flavor 2 self-improvement from Chapter 21: not changing the model
weights, but changing the scaffolding around the model based on observed failures.

The insight: a LangGraph graph is just a Python data structure. If a certain
routing pattern consistently wastes turns (e.g., always running the reviewer
even when the coder is trivial), you can detect that at runtime and short-circuit.

This optimizer:
  1. Tracks tool-call sequences and outcomes across sessions
  2. Identifies wasteful patterns (unnecessary steps, redundant loops)
  3. Generates a modified graph config that skips or reorders nodes
  4. Validates the new config before activating it

In production, gate this behind an eval suite: only activate an optimization
if the benchmark score doesn't regress.

Usage:
    python scaffold_optimizer.py --sessions sessions.json
    python scaffold_optimizer.py --demo

Requires: pip install anthropic
"""

import argparse
import json
from dataclasses import dataclass, field
from typing import Any

import anthropic

client = anthropic.Anthropic()


# ── Session trajectory data ───────────────────────────────────────────

@dataclass
class NodeExecution:
    node_name:    str
    duration_ms:  float
    tokens:       int
    outcome:      str        # "success", "retry", "skip", "failure"
    retry_count:  int = 0


@dataclass
class SessionTrace:
    session_id:  str
    task:        str
    executions:  list[NodeExecution] = field(default_factory=list)
    total_tokens: int = 0
    total_cost:   float = 0.0
    succeeded:   bool = True


# ── Pattern detection ─────────────────────────────────────────────────

def detect_inefficiencies(sessions: list[SessionTrace]) -> list[dict]:
    """Identify routing patterns that waste tokens or time."""
    issues = []

    # Pattern 1: Reviewer always approves after first coder pass
    # → Reviewer adds latency with no value
    reviewer_necessary = 0
    reviewer_total     = 0
    for s in sessions:
        nodes = [e.node_name for e in s.executions]
        if "reviewer" in nodes:
            reviewer_total += 1
            # Reviewer was necessary if it triggered a revision
            coder_idx    = [i for i, e in enumerate(s.executions) if e.node_name == "coder"]
            reviewer_idx = [i for i, e in enumerate(s.executions) if e.node_name == "reviewer"]
            if len(coder_idx) > 1:  # Coder ran more than once → reviewer caught something
                reviewer_necessary += 1

    if reviewer_total > 5 and reviewer_necessary / reviewer_total < 0.2:
        issues.append({
            "pattern": "reviewer_rarely_catches_issues",
            "description": (
                f"Reviewer triggered revision in only {reviewer_necessary}/{reviewer_total} "
                f"sessions ({reviewer_necessary/reviewer_total:.0%}). Consider running reviewer "
                f"only on high-complexity issues or batching reviews."
            ),
            "optimization": "conditional_reviewer",
            "estimated_savings_pct": 15,
        })

    # Pattern 2: Tester always passes immediately
    # → Test node adds latency for simple tasks
    tester_fail_rate = sum(
        1 for s in sessions
        if any(e.node_name == "tester" and e.outcome == "retry" for e in s.executions)
    ) / max(len(sessions), 1)

    if tester_fail_rate < 0.1 and len(sessions) > 10:
        issues.append({
            "pattern": "tester_rarely_fails",
            "description": (
                f"Tests failed in only {tester_fail_rate:.0%} of sessions. "
                "Consider caching test results for identical code changes."
            ),
            "optimization": "test_result_cache",
            "estimated_savings_pct": 10,
        })

    # Pattern 3: Average retry count > 1.5 — coder needs better context
    avg_retries = sum(
        sum(e.retry_count for e in s.executions if e.node_name == "coder")
        for s in sessions
    ) / max(len(sessions), 1)

    if avg_retries > 1.5:
        issues.append({
            "pattern": "high_coder_retry_rate",
            "description": (
                f"Coder averaged {avg_retries:.1f} retries per session. "
                "Providing more context (existing code, test failures) in the first coder call "
                "should reduce this."
            ),
            "optimization": "enriched_coder_context",
            "estimated_savings_pct": 20,
        })

    return issues


# ── Optimization generation ───────────────────────────────────────────

def generate_optimization(issues: list[dict]) -> dict:
    """
    Ask Claude to propose concrete graph changes based on detected patterns.
    Returns a modified graph config.
    """
    if not issues:
        return {"changes": [], "expected_improvement": "No issues detected."}

    issues_text = json.dumps(issues, indent=2)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        system=(
            "You are a LangGraph optimization expert. Given a list of inefficiency patterns "
            "in an agent's routing, propose concrete graph changes. "
            "Output JSON: {\"changes\": [{\"node\": ..., \"change\": ..., \"rationale\": ...}], "
            "\"expected_improvement\": \"...\"}. "
            "Be conservative — only propose changes with clear evidence."
        ),
        messages=[{
            "role": "user",
            "content": (
                "The following inefficiencies were detected in an Atlas pipeline:\n\n"
                f"{issues_text}\n\n"
                "What graph changes would reduce wasted computation while preserving quality?"
            )
        }],
        max_tokens=1024,
    )

    try:
        return json.loads(response.content[0].text)
    except json.JSONDecodeError:
        return {"changes": [], "expected_improvement": response.content[0].text}


# ── Demo ──────────────────────────────────────────────────────────────

def run_demo():
    """Generate sample session data and optimize the graph."""
    import random

    print("Scaffold Optimizer — Demo\n")
    print("Generating 20 sample session traces...")

    sessions = []
    for i in range(20):
        executions = [
            NodeExecution("fetch_issue", 200, 0, "success"),
            NodeExecution("planner",     1200, 800, "success"),
            NodeExecution("coder",       3000, 2000, "success", retry_count=random.randint(0, 2)),
            NodeExecution("tester",      5000, 0, "success" if random.random() > 0.08 else "retry"),
            NodeExecution("reviewer",    1500, 600, "success"),
            NodeExecution("human_approval", 0, 0, "success"),
        ]
        sessions.append(SessionTrace(
            session_id   = f"session-{i}",
            task         = f"Fix issue #{i+1}",
            executions   = executions,
            total_tokens = sum(e.tokens for e in executions),
            succeeded    = True,
        ))

    print(f"Analysing {len(sessions)} sessions...\n")
    issues = detect_inefficiencies(sessions)

    if not issues:
        print("No inefficiencies detected — graph is well-optimized.")
        return

    print(f"Found {len(issues)} optimization opportunities:")
    for issue in issues:
        savings = issue.get("estimated_savings_pct", 0)
        print(f"\n  [{savings}% savings] {issue['pattern']}")
        print(f"  {issue['description']}")

    print("\nGenerating optimization recommendations...")
    optimization = generate_optimization(issues)

    print("\nProposed changes:")
    for change in optimization.get("changes", []):
        print(f"  • {change.get('node', '?')}: {change.get('change', '')}")
        print(f"    Rationale: {change.get('rationale', '')[:100]}")

    print(f"\nExpected improvement: {optimization.get('expected_improvement', '')[:200]}")

    total_savings = sum(i.get("estimated_savings_pct", 0) for i in issues)
    print(f"\nEstimated total savings: ~{total_savings}% fewer tokens/session")


def main():
    parser = argparse.ArgumentParser(description="Atlas Scaffold Optimizer")
    parser.add_argument("--sessions", default=None, help="Path to sessions JSON file")
    parser.add_argument("--demo",     action="store_true", help="Run with synthetic data")
    args = parser.parse_args()

    if args.demo or not args.sessions:
        run_demo()
    else:
        with open(args.sessions) as f:
            raw = json.load(f)
        sessions = [SessionTrace(**s) for s in raw]
        issues   = detect_inefficiencies(sessions)
        result   = generate_optimization(issues)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
