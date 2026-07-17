"""
loop_harness.py — The full engineered loop as a reusable class.

Everything from §20.2 packaged so you can wrap it around any task:
  - Pluggable verifier: any callable returning (done: bool, evidence: str)
  - Pluggable generator: any callable that takes (goal, lessons) and acts
  - Failure fingerprinting: detects the loop that is "redecorating"
  - Lesson compaction: attempt 6 is smarter than attempt 1, not just longer
  - Budget caps: max attempts AND max dollars, whichever hits first
  - Escalation hook: writes a resumable state file for the human who
    picks it up, then calls your alerting function

The demo at the bottom wraps the loop around a toy task (make a JSON file
that satisfies a schema) so you can run it without a broken repo handy.

Usage:
    python loop_harness.py

Requires: pip install anthropic
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import anthropic

# Rough blended $/1M tokens used for the budget cap (input+output averaged).
COST_PER_MTOK = {"claude-opus-4-8": 15.0, "claude-haiku-4-5": 3.0}


@dataclass
class LoopResult:
    status: str                  # "success" | "escalated"
    attempts: int
    cost_usd: float
    lessons: list[str] = field(default_factory=list)
    reason: str = ""


class EngineeredLoop:
    """Verify → generate → verify again, with a memory and a tripwire."""

    def __init__(
        self,
        verifier: Callable[[], tuple[bool, str]],
        generator: Callable[[str, list[str]], anthropic.types.Message],
        summarizer: Callable[[int, str], str],
        max_attempts: int = 6,
        budget_usd: float = 5.0,
        stall_limit: int = 2,
        state_file: Path = Path("loop_state.json"),
        on_escalate: Callable[[dict], None] = lambda state: None,
    ):
        self.verifier = verifier
        self.generator = generator
        self.summarizer = summarizer
        self.max_attempts = max_attempts
        self.budget_usd = budget_usd
        self.stall_limit = stall_limit
        self.state_file = state_file
        self.on_escalate = on_escalate

    @staticmethod
    def fingerprint(evidence: str) -> str:
        failures = [l for l in evidence.splitlines() if "FAIL" in l or "Error" in l]
        key = "\n".join(sorted(failures)) or evidence[-500:]
        return hashlib.sha256(key.encode()).hexdigest()[:12]

    def _track_cost(self, response: anthropic.types.Message) -> float:
        rate = COST_PER_MTOK.get(response.model, 15.0)
        tokens = response.usage.input_tokens + response.usage.output_tokens
        return tokens * rate / 1_000_000

    def _escalate(self, goal: str, lessons: list[str], attempts: int,
                  cost: float, reason: str) -> LoopResult:
        state = {
            "status": "escalated",
            "goal": goal,
            "reason": reason,
            "attempts": attempts,
            "cost_usd": round(cost, 4),
            "lessons": lessons,
            "resumable": True,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self.state_file.write_text(json.dumps(state, indent=2))
        self.on_escalate(state)
        print(f"🚨 Escalated ({reason}). State → {self.state_file}")
        return LoopResult("escalated", attempts, cost, lessons, reason)

    def run(self, goal: str) -> LoopResult:
        lessons: list[str] = []
        cost, last_fp, stall_count = 0.0, None, 0

        for attempt in range(1, self.max_attempts + 1):
            # 1. Verify FIRST — maybe the goal is already met
            done, evidence = self.verifier()
            if done:
                print(f"── Attempt {attempt} ── ✅ verified: {goal}")
                return LoopResult("success", attempt, cost, lessons)

            fp = self.fingerprint(evidence)
            print(f"── Attempt {attempt} ── not done  [fp: {fp}]  "
                  f"(${cost:.3f} spent)")

            # 2. Tripwires BEFORE burning more tokens
            stall_count = stall_count + 1 if fp == last_fp else 0
            last_fp = fp
            if stall_count >= self.stall_limit:
                return self._escalate(goal, lessons, attempt, cost,
                                      f"same failure {stall_count + 1}x ({fp})")
            if cost >= self.budget_usd:
                return self._escalate(goal, lessons, attempt, cost,
                                      f"budget ${self.budget_usd} exhausted")

            # 3. Generate — the agent sees goal + lessons, not raw history
            response = self.generator(f"{goal}\n\nCurrent state:\n{evidence}", lessons)
            cost += self._track_cost(response)

            # 4. Compact — feed forward a lesson, not a transcript
            lessons.append(self.summarizer(attempt, evidence))

        done, _ = self.verifier()
        if done:
            return LoopResult("success", self.max_attempts, cost, lessons)
        return self._escalate(goal, lessons, self.max_attempts, cost,
                              "max attempts exhausted")


# ── Demo: wrap the loop around a toy task ────────────────────────────

if __name__ == "__main__":
    client = anthropic.Anthropic()
    OUTPUT = Path("demo_config.json")
    REQUIRED_KEYS = {"service", "port", "retries", "timeout_s"}

    def verifier() -> tuple[bool, str]:
        """A shell-script-grade check: valid JSON with the required keys."""
        if not OUTPUT.exists():
            return False, "FAIL: demo_config.json does not exist"
        try:
            data = json.loads(OUTPUT.read_text())
        except json.JSONDecodeError as e:
            return False, f"FAIL: invalid JSON — {e}"
        missing = REQUIRED_KEYS - set(data)
        if missing:
            return False, f"FAIL: missing keys {sorted(missing)}"
        return True, "all checks passed"

    def generator(goal: str, lessons: list[str]) -> anthropic.types.Message:
        context = "\n".join(lessons) if lessons else "(first attempt)"
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    f"{goal}\n\nLessons from failed attempts:\n{context}\n\n"
                    "Respond with ONLY the JSON content for demo_config.json."
                ),
            }],
        )
        OUTPUT.write_text(response.content[0].text.strip().strip("`"))
        return response

    def summarizer(attempt: int, evidence: str) -> str:
        return f"Attempt {attempt}: {evidence.splitlines()[0]}"

    loop = EngineeredLoop(
        verifier=verifier,
        generator=generator,
        summarizer=summarizer,
        max_attempts=4,
        budget_usd=0.50,
        on_escalate=lambda state: print(f"  (would page on-call with: {state['reason']})"),
    )
    result = loop.run(f"Create demo_config.json containing keys {sorted(REQUIRED_KEYS)}")
    print(f"\nResult: {result.status} after {result.attempts} attempt(s), "
          f"${result.cost_usd:.3f}")
