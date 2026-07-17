"""
adversarial_pair.py — A builder/adversary harness from §21.2.

One agent produces, a second attacks, and only their disagreements are
surfaced to the human. The practical advice from the chapter: review the
disagreements, not the output. When builder and adversary agree, the work
is almost always fine; when they disagree, that disagreement is the most
information-dense artifact the system produces.

The adversary is not a politeness layer. Its prompt gives no credit for
agreeing: its only job is to find the input that breaks the artifact, the
requirement it silently dropped, the assumption that was wrong on day one.

Includes the stats tracker that tells you when your adversary has become a
rubber stamp — if it has never once blocked a builder, you don't have an
adversary, you have a second bill.

Usage:
    python adversarial_pair.py "Write a Python function that parses ISO-8601 durations"

Requires: pip install anthropic
"""

import json
import sys
import time
from pathlib import Path

import anthropic

client = anthropic.Anthropic()
MODEL = "claude-opus-4-8"

STATS_FILE = Path("adversary_stats.json")
RUBBER_STAMP_WINDOW = 20   # zero blocks in this many reviews → warn

BUILDER_SYSTEM = """You are the Builder. Produce the requested artifact completely and
correctly. Output the artifact itself, with a short usage note."""

ADVERSARY_SYSTEM = """You are the Adversary. You get NO credit for agreeing. Your only job
is to break the artifact: find the input that crashes it, the requirement it
silently dropped, the edge case it mishandles, the assumption that is wrong.
Do not suggest improvements. Do not praise. Hunt.

Respond with ONLY JSON:
{"verdict": "block" | "pass",
 "findings": [{"severity": "high|medium|low",
               "claim": "<what breaks>",
               "breaking_input": "<concrete input or scenario that triggers it>"}]}

Rules: a "pass" verdict requires that you genuinely attacked and found
nothing of substance — an empty findings list with no attack attempted is a
failure on your part. "block" whenever any high-severity finding exists."""


def build(task: str) -> str:
    resp = client.messages.create(
        model=MODEL, max_tokens=4000,
        system=BUILDER_SYSTEM,
        messages=[{"role": "user", "content": task}],
    )
    return resp.content[0].text


def attack(task: str, artifact: str) -> dict:
    resp = client.messages.create(
        model=MODEL, max_tokens=2000,
        system=ADVERSARY_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"ORIGINAL TASK:\n{task}\n\nBUILDER'S ARTIFACT:\n{artifact}",
        }],
    )
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return json.loads(text)


# ── The rubber-stamp detector ────────────────────────────────────────

def record_review(verdict: str) -> dict:
    stats = json.loads(STATS_FILE.read_text()) if STATS_FILE.exists() else {"history": []}
    stats["history"].append({"verdict": verdict, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
    STATS_FILE.write_text(json.dumps(stats, indent=2))
    return stats


def rubber_stamp_check(stats: dict):
    recent = [h["verdict"] for h in stats["history"][-RUBBER_STAMP_WINDOW:]]
    blocks = recent.count("block")
    rate = blocks / len(recent)
    print(f"\n📊 Adversary block rate: {blocks}/{len(recent)} recent reviews ({rate:.0%})")
    if len(recent) >= RUBBER_STAMP_WINDOW and blocks == 0:
        print("⚠️  RUBBER STAMP ALERT: the adversary has not blocked anything in "
              f"{RUBBER_STAMP_WINDOW} reviews. Either your builders are perfect "
              "(they aren't) or the adversary prompt has gone soft. Re-sharpen it.")


def main():
    task = sys.argv[1] if len(sys.argv) > 1 else (
        "Write a Python function parse_duration(s) that parses ISO-8601 "
        "duration strings like 'P1DT2H30M' into total seconds."
    )

    print(f"🔨 Builder working on: {task}\n")
    artifact = build(task)

    print("⚔️  Adversary attacking...\n")
    review = attack(task, artifact)
    stats = record_review(review["verdict"])

    if review["verdict"] == "pass":
        # Agreement: ship it. The human never needs to see this one.
        print("✅ Builder and adversary agree — auto-approved, no human review needed.")
    else:
        # Disagreement: THIS is what deserves human eyes.
        print("🚨 DISAGREEMENT — surfaced for human review:\n")
        print("ARTIFACT:\n" + artifact[:1500] + ("\n..." if len(artifact) > 1500 else ""))
        print("\nADVERSARY FINDINGS:")
        for f in review["findings"]:
            print(f"  [{f['severity'].upper()}] {f['claim']}")
            print(f"          breaks on: {f['breaking_input']}")

    rubber_stamp_check(stats)


if __name__ == "__main__":
    main()
