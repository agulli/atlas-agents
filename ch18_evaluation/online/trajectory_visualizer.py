"""
trajectory_visualizer.py — Render agent trajectories as readable terminal output.

When an eval fails, the raw trajectory log is a wall of JSON. This visualizer
turns it into a human-readable timeline: each tool call, its latency, its cost,
and a short preview of the result. At the bottom: total cost, total latency,
and a verdict.

Works with any trajectory log that follows the format:
  [{"type": "tool_call"|"tool_result"|"text", "name": ..., "input": ...,
    "output": ..., "latency_ms": ..., "tokens": ...}]

Usage:
    python trajectory_visualizer.py trajectory.json
    python trajectory_visualizer.py --from-eval tc-001   # Visualize a specific case

Requires: pip install anthropic
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic


sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import ANTHROPIC_MODEL  # also loads .env


client = anthropic.Anthropic()

# Cost rates ($/1M tokens) as of Q2 2026
COST_RATES = {
    "claude-opus-4-8":           {"input": 5.00,  "output": 25.00},
    "claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80,  "output": 4.00},
}


# ── Trajectory data model ─────────────────────────────────────────────

@dataclass
class TrajectoryStep:
    step:       int
    type:       str          # "tool_call", "tool_result", "text", "thinking"
    name:       str = ""
    input:      Any = None
    output:     Any = None
    latency_ms: float = 0.0
    tokens:     int = 0
    model:      str = ANTHROPIC_MODEL
    error:      str | None = None


@dataclass
class Trajectory:
    case_id:  str
    question: str
    answer:   str
    steps:    list[TrajectoryStep] = field(default_factory=list)
    total_latency_ms: float = 0.0
    total_input_tokens:  int = 0
    total_output_tokens: int = 0
    passed:   bool = False


# ── Terminal colors ───────────────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    GREEN  = "\033[92m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    GRAY   = "\033[90m"


def colored(text: str, color: str) -> str:
    return f"{color}{text}{C.RESET}"


# ── Rendering ─────────────────────────────────────────────────────────

def render_trajectory(traj: Trajectory):
    """Print a trajectory as a human-readable timeline."""
    verdict = colored("✅ PASS", C.GREEN) if traj.passed else colored("❌ FAIL", C.RED)

    print(f"\n{C.BOLD}{'─'*60}{C.RESET}")
    print(f"{C.BOLD}Trajectory: {traj.case_id}{C.RESET}  {verdict}")
    print(f"{C.DIM}Q: {traj.question[:80]}{'...' if len(traj.question) > 80 else ''}{C.RESET}")
    print()

    tool_count   = 0
    total_cost   = 0.0

    for step in traj.steps:
        rates   = COST_RATES.get(step.model, COST_RATES["claude-sonnet-4-6"])
        cost    = step.tokens * rates.get("output", 0) / 1_000_000
        total_cost += cost

        if step.type == "thinking":
            print(f"  {colored('◆ thinking', C.GRAY)}  "
                  f"{colored(f'{step.latency_ms:.0f}ms', C.DIM)}")

        elif step.type == "tool_call":
            tool_count += 1
            input_str = json.dumps(step.input)[:80] if step.input else ""
            print(f"  {colored(f'[{tool_count}] {step.name}', C.CYAN)}  "
                  f"{colored(f'{step.latency_ms:.0f}ms', C.DIM)}  "
                  f"{colored(input_str, C.GRAY)}")

        elif step.type == "tool_result":
            if step.error:
                output_str = colored(f"ERROR: {step.error[:60]}", C.RED)
            else:
                output_str = str(step.output)[:80] if step.output else ""
                output_str = colored(output_str, C.DIM)
            print(f"      {colored('→', C.GRAY)} {output_str}")

        elif step.type == "text":
            text_preview = str(step.output)[:100] if step.output else ""
            print(f"  {colored('◎ text', C.BLUE)}  "
                  f"{colored(f'{step.latency_ms:.0f}ms', C.DIM)}  "
                  f"{colored(text_preview + ('...' if len(str(step.output or '')) > 100 else ''), C.GRAY)}")

    # Cost and latency summary
    rate = COST_RATES.get(traj.steps[0].model if traj.steps else "claude-sonnet-4-6",
                          COST_RATES["claude-sonnet-4-6"])
    input_cost  = traj.total_input_tokens  * rate["input"]  / 1_000_000
    output_cost = traj.total_output_tokens * rate["output"] / 1_000_000
    total_cost  = input_cost + output_cost

    print()
    print(f"  {colored('Answer:', C.BOLD)} {traj.answer[:120]}{'...' if len(traj.answer) > 120 else ''}")
    print()
    print(f"  {colored('Summary:', C.BOLD)}")
    print(f"    Tool calls:    {tool_count}")
    print(f"    Total latency: {traj.total_latency_ms/1000:.2f}s")
    print(f"    Input tokens:  {traj.total_input_tokens:,}")
    print(f"    Output tokens: {traj.total_output_tokens:,}")
    print(f"    Est. cost:     ${total_cost:.4f}")
    print(f"{'─'*60}")


# ── Live trajectory capture ───────────────────────────────────────────

def capture_and_visualize(question: str, model: str = ANTHROPIC_MODEL) -> Trajectory:
    """
    Run a real Claude call with tool use, capture the trajectory, and render it.
    Shows exactly what the eval harness would see.
    """
    tools = [
        {
            "name":        "web_search",
            "description": "Search the web for information.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }
    ]

    steps: list[TrajectoryStep] = []
    step_num   = 0
    messages   = [{"role": "user", "content": question}]
    total_in   = 0
    total_out  = 0

    while True:
        t0 = time.time()
        resp = client.messages.create(
            model=model,
            system="You are Atlas, a research assistant. Use web_search when needed.",
            messages=messages,
            tools=tools,
            max_tokens=1024,
        )
        latency = (time.time() - t0) * 1000
        total_in  += resp.usage.input_tokens
        total_out += resp.usage.output_tokens

        for block in resp.content:
            step_num += 1
            if block.type == "text":
                steps.append(TrajectoryStep(
                    step=step_num, type="text", output=block.text,
                    latency_ms=latency, tokens=resp.usage.output_tokens, model=model,
                ))
            elif block.type == "tool_use":
                steps.append(TrajectoryStep(
                    step=step_num, type="tool_call", name=block.name,
                    input=block.input, latency_ms=latency, model=model,
                ))
                # Simulate tool result
                tool_result = f"[simulated result for: {json.dumps(block.input)[:60]}]"
                step_num += 1
                steps.append(TrajectoryStep(
                    step=step_num, type="tool_result", name=block.name,
                    output=tool_result, model=model,
                ))

        if resp.stop_reason == "end_turn":
            break

        # Continue conversation
        messages.append({"role": "assistant", "content": resp.content})
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": b.id, "content": "Simulated result"}
            for b in resp.content if b.type == "tool_use"
        ]})

    answer = next((s.output for s in reversed(steps) if s.type == "text"), "")
    traj = Trajectory(
        case_id="live", question=question, answer=answer, steps=steps,
        total_latency_ms=sum(s.latency_ms for s in steps),
        total_input_tokens=total_in, total_output_tokens=total_out,
        passed=True,
    )
    return traj


# ── Load from file ────────────────────────────────────────────────────

def load_trajectory_file(path: str) -> Trajectory:
    with open(path) as f:
        data = json.load(f)
    steps = [TrajectoryStep(**s) for s in data.get("steps", [])]
    return Trajectory(
        case_id=data.get("case_id", "unknown"),
        question=data.get("question", ""),
        answer=data.get("answer", ""),
        steps=steps,
        total_latency_ms=data.get("total_latency_ms", 0),
        total_input_tokens=data.get("total_input_tokens", 0),
        total_output_tokens=data.get("total_output_tokens", 0),
        passed=data.get("passed", False),
    )


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Atlas Trajectory Visualizer")
    parser.add_argument("file",      nargs="?",  help="Trajectory JSON file to visualize")
    parser.add_argument("--live",    default=None, help="Capture live trajectory for a question")
    parser.add_argument("--model",   default=ANTHROPIC_MODEL)
    args = parser.parse_args()

    if args.live:
        traj = capture_and_visualize(args.live, model=args.model)
        render_trajectory(traj)
    elif args.file:
        traj = load_trajectory_file(args.file)
        render_trajectory(traj)
    else:
        # Demo: run a quick live capture
        print("No file specified. Running live demo...")
        traj = capture_and_visualize(
            "What is the difference between RAG and fine-tuning?",
            model=args.model,
        )
        render_trajectory(traj)


if __name__ == "__main__":
    main()
