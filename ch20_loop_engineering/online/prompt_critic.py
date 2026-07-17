"""
prompt_critic.py — A scheduled critic pass over the agent's failure logs.

The first self-improvement mechanism from §20.3: prompts stop being sacred
text a human tunes by hand and become config the system maintains.

The pipeline, run on a schedule (cron it weekly):
  1. Read a week of failure logs (JSONL: one failed task per line)
  2. Cluster repeated failure patterns with Haiku — cheap, and pattern
     clustering doesn't need a frontier model
  3. Ask a stronger model to locate the ambiguous sentence in the system
     prompt and propose a sharper version, as a full replacement
  4. Gate the rewrite behind the eval suite: the new prompt is only
     merged if it passes at least as many eval cases as the old one

Nothing ships on the critic's word alone — the eval suite is the reviewer.

Usage:
    python prompt_critic.py [--logs failures.jsonl] [--prompt system_prompt.txt]

Requires: pip install anthropic
"""

import argparse
import difflib
import json
from pathlib import Path

import anthropic

client = anthropic.Anthropic()

CRITIC_MODEL = "claude-haiku-4-5"   # clusters failure patterns
REWRITE_MODEL = "claude-opus-4-8"   # proposes the prompt rewrite

# Demo data used when no real logs/prompt exist yet, so the script runs
# end-to-end out of the box.
DEMO_PROMPT = """You are Atlas, a billing assistant. Use the billing API to answer
questions. Send payloads to the API in the usual format. Be concise."""

DEMO_FAILURES = [
    {"task": "refund order 8812", "error": "API 400: payload field 'amount' must be integer cents, got float dollars"},
    {"task": "refund order 9034", "error": "API 400: payload field 'amount' must be integer cents, got float dollars"},
    {"task": "invoice for acct 22", "error": "API 400: missing required field 'currency'"},
    {"task": "refund order 7215", "error": "API 400: payload field 'amount' must be integer cents, got string"},
    {"task": "list charges", "error": "timeout: retried same malformed request 3 times"},
]

# A miniature stand-in for the Chapter 18 eval suite: each case is a
# question plus a predicate over the answer.
EVAL_CASES = [
    ("How do I express $12.50 in a refund payload?", lambda a: "1250" in a),
    ("What fields does a refund payload need?", lambda a: "amount" in a.lower() and "currency" in a.lower()),
    ("Refund $3 to order 100 — show the payload.", lambda a: '"amount": 300' in a.replace(" ", " ")),
]


def cluster_failures(failures: list[dict]) -> str:
    """Haiku groups a week of failures into named, counted patterns."""
    log_text = "\n".join(f"- {f['task']}: {f['error']}" for f in failures)
    resp = client.messages.create(
        model=CRITIC_MODEL,
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": (
                "Cluster these agent failures into repeated patterns. For each "
                "cluster output: a name, the count, and one representative "
                f"error.\n\n{log_text}"
            ),
        }],
    )
    return resp.content[0].text


def propose_rewrite(system_prompt: str, clusters: str) -> str:
    """The critic locates the ambiguity and proposes a sharper prompt."""
    resp = client.messages.create(
        model=REWRITE_MODEL,
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": (
                "This system prompt keeps producing the failure clusters "
                "below. Find the ambiguous or missing instructions that cause "
                "them and rewrite the prompt to prevent them. Change as "
                "little as possible.\n\n"
                f"CURRENT PROMPT:\n{system_prompt}\n\n"
                f"FAILURE CLUSTERS:\n{clusters}\n\n"
                "Respond with ONLY the full rewritten prompt."
            ),
        }],
    )
    return resp.content[0].text.strip()


def run_eval_suite(system_prompt: str) -> int:
    """Score a prompt against the eval cases. Returns the pass count."""
    passed = 0
    for question, check in EVAL_CASES:
        resp = client.messages.create(
            model=CRITIC_MODEL,
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": question}],
        )
        if check(resp.content[0].text):
            passed += 1
    return passed


def main():
    parser = argparse.ArgumentParser(description="Scheduled prompt critic")
    parser.add_argument("--logs", default="failures.jsonl")
    parser.add_argument("--prompt", default="system_prompt.txt")
    args = parser.parse_args()

    prompt_file = Path(args.prompt)
    if not prompt_file.exists():
        prompt_file.write_text(DEMO_PROMPT)
    log_file = Path(args.logs)
    if log_file.exists():
        failures = [json.loads(l) for l in log_file.read_text().splitlines() if l.strip()]
    else:
        print(f"(no {log_file} found — using built-in demo failures)")
        failures = DEMO_FAILURES

    old_prompt = prompt_file.read_text()

    print(f"🔍 Clustering {len(failures)} failures with {CRITIC_MODEL}...")
    clusters = cluster_failures(failures)
    print(clusters)

    print(f"\n✍️  Proposing rewrite with {REWRITE_MODEL}...")
    new_prompt = propose_rewrite(old_prompt, clusters)

    diff = "\n".join(difflib.unified_diff(
        old_prompt.splitlines(), new_prompt.splitlines(),
        fromfile="system_prompt (current)", tofile="system_prompt (proposed)",
        lineterm="",
    ))
    print(f"\nProposed diff:\n{diff}\n")

    # The gate: the eval suite decides, not the critic
    print("🧪 Gating behind the eval suite...")
    old_score = run_eval_suite(old_prompt)
    new_score = run_eval_suite(new_prompt)
    print(f"   current prompt: {old_score}/{len(EVAL_CASES)}   "
          f"proposed prompt: {new_score}/{len(EVAL_CASES)}")

    if new_score >= old_score and new_score == len(EVAL_CASES):
        backup = prompt_file.with_suffix(".txt.bak")
        backup.write_text(old_prompt)
        prompt_file.write_text(new_prompt)
        print(f"✅ Merged. Old prompt backed up to {backup}.")
    else:
        rejected = prompt_file.with_suffix(".txt.rejected")
        rejected.write_text(new_prompt)
        print(f"❌ Rejected — eval suite did not improve. Saved to {rejected} for review.")


if __name__ == "__main__":
    main()
