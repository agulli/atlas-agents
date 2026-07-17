"""
learned_router.py — A routing table that updates itself from outcomes.

Routing optimization from §20.3: the harness tracks success rates per model
per task type, and the data starts making decisions. If Haiku clears 99% on
log parsing, there is no reason to send those jobs to Opus at ten times the
price. The routing table from Chapter 7 stops being a static config file and
becomes a scoreboard that updates itself.

The guard that makes this safe in production:
  - MIN_SAMPLES: a model must be tried enough times before its rate counts,
    so one lucky Haiku run doesn't get your architecture reviews downgraded
  - EXPLORE_RATE: a small fraction of traffic keeps testing the cheap model
    even after the router has settled on the expensive one, so the table
    can discover when a new cheap model becomes good enough
  - DOWNGRADE_THRESHOLD: the cheap model must actually clear the bar
    (default 95%) before it takes over a task type

Usage:
    python learned_router.py            # simulate 300 routed tasks
    python learned_router.py --live     # route one real request per task type

Requires: pip install anthropic
"""

import argparse
import json
import random
from pathlib import Path

import anthropic

CHEAP_MODEL = "claude-haiku-4-5"      # ~10x cheaper
STRONG_MODEL = "claude-opus-4-8"      # the safe default

MIN_SAMPLES = 20          # rates below this sample size are ignored
DOWNGRADE_THRESHOLD = 0.95
EXPLORE_RATE = 0.10       # keep 10% of traffic testing the non-chosen model
AUDITION_RATE = 0.30      # until MIN_SAMPLES, route this much to the cheap model
STATS_FILE = Path("router_stats.json")


class LearnedRouter:
    def __init__(self, stats_file: Path = STATS_FILE):
        self.stats_file = stats_file
        # stats[task_type][model] = {"tries": int, "wins": int}
        self.stats: dict[str, dict[str, dict[str, int]]] = (
            json.loads(stats_file.read_text()) if stats_file.exists() else {}
        )

    def _rate(self, task_type: str, model: str) -> tuple[float, int]:
        s = self.stats.get(task_type, {}).get(model, {"tries": 0, "wins": 0})
        rate = s["wins"] / s["tries"] if s["tries"] else 0.0
        return rate, s["tries"]

    def route(self, task_type: str) -> str:
        """Pick a model for this task type based on the scoreboard."""
        cheap_rate, cheap_n = self._rate(task_type, CHEAP_MODEL)

        # The minimum-sample guard: until the cheap model has a track
        # record, the strong model keeps the job while the cheap one
        # auditions on a bounded slice of traffic.
        if cheap_n < MIN_SAMPLES:
            chosen = CHEAP_MODEL if random.random() < AUDITION_RATE else STRONG_MODEL
        elif cheap_rate >= DOWNGRADE_THRESHOLD:
            # Cheap model has earned the task type — but keep sampling the
            # strong model occasionally as a quality baseline.
            chosen = STRONG_MODEL if random.random() < EXPLORE_RATE else CHEAP_MODEL
        else:
            chosen = CHEAP_MODEL if random.random() < EXPLORE_RATE else STRONG_MODEL
        return chosen

    def record(self, task_type: str, model: str, success: bool):
        entry = self.stats.setdefault(task_type, {}).setdefault(
            model, {"tries": 0, "wins": 0}
        )
        entry["tries"] += 1
        entry["wins"] += int(success)
        self.stats_file.write_text(json.dumps(self.stats, indent=2))

    def scoreboard(self) -> str:
        lines = [f"{'task type':<22}{'model':<22}{'rate':>7}{'n':>6}  routing to"]
        for task_type, models in sorted(self.stats.items()):
            for model, s in sorted(models.items()):
                rate = s["wins"] / s["tries"] if s["tries"] else 0.0
                flag = "  ← below MIN_SAMPLES" if s["tries"] < MIN_SAMPLES else ""
                lines.append(f"{task_type:<22}{model:<22}{rate:>6.0%}{s['tries']:>6}{flag}")
            lines.append(f"{'':<22}{'→ ' + self.route(task_type)}")
        return "\n".join(lines)


# ── Simulation: watch the table learn ────────────────────────────────

# Ground-truth success probabilities the router does NOT know. Log parsing
# is easy (Haiku ~99%); architecture review is not (Haiku ~70%).
TRUE_RATES = {
    "log_parsing":         {CHEAP_MODEL: 0.99, STRONG_MODEL: 0.99},
    "architecture_review": {CHEAP_MODEL: 0.70, STRONG_MODEL: 0.97},
    "sql_generation":      {CHEAP_MODEL: 0.96, STRONG_MODEL: 0.98},
}


def simulate(router: LearnedRouter, n_tasks: int = 300):
    random.seed(7)
    for i in range(n_tasks):
        task_type = random.choice(list(TRUE_RATES))
        model = router.route(task_type)
        success = random.random() < TRUE_RATES[task_type][model]
        router.record(task_type, model, success)
        if (i + 1) % 100 == 0:
            print(f"\nAfter {i + 1} tasks:\n{router.scoreboard()}")


def live_route(router: LearnedRouter):
    """Route one real request per task type through the chosen model."""
    client = anthropic.Anthropic()
    prompts = {
        "log_parsing": "Extract the error class from: 'ERR 2026-07-17 TimeoutError in worker-3'. One word.",
        "architecture_review": "In two sentences: main risk of moving a monolith's billing module to a queue-based microservice?",
        "sql_generation": "SQL: total order value per customer, orders table (customer_id, amount). Just the query.",
    }
    for task_type, prompt in prompts.items():
        model = router.route(task_type)
        resp = client.messages.create(
            model=model, max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        print(f"[{task_type}] routed to {model}:\n  {resp.content[0].text.strip()[:120]}\n")
        # In production, success comes from your verifier — here we just
        # record the call as successful to feed the scoreboard.
        router.record(task_type, model, success=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Self-updating model router")
    parser.add_argument("--live", action="store_true", help="Route real API calls")
    args = parser.parse_args()

    router = LearnedRouter()
    if args.live:
        live_route(router)
    else:
        simulate(router)
        print("\nNote: architecture_review stays on the strong model — Haiku's "
              "70% never clears the 95% bar, no matter how many samples.")
