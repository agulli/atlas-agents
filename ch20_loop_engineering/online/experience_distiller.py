"""
experience_distiller.py — Turn an expensive victory into a permanent asset.

Experience distillation from §20.3: when the agent finally cracks a gnarly
task on attempt nine, a static system throws the session away — the token
spend bought one pull request. This script compresses the winning trajectory
into a compact worked example, stores it in Chroma, and demonstrates the
payoff: the same task class converging in one attempt instead of nine.

Flow:
  1. Load a trajectory log (JSONL of attempts, or the built-in demo one)
  2. Distill it: task, key decisions, verified outcome — no session data
  3. Embed and store the example in a Chroma collection
  4. Simulate a new, similar task: retrieve the example, inject it into
     context, and show the first attempt starting where attempt 9 left off

Usage:
    python experience_distiller.py [--trajectory session.jsonl]

Requires: pip install anthropic chromadb
"""

import argparse
import json
from pathlib import Path

import anthropic
import chromadb

client = anthropic.Anthropic()
MODEL = "claude-opus-4-8"

# A nine-attempt saga, compressed here for the demo. In production this is
# the loop's attempt log (fix_loop.py writes one lesson per attempt).
DEMO_TRAJECTORY = [
    {"attempt": 1, "action": "renamed column user_id → customer_id in migration", "result": "FAILED: FK constraint from orders table"},
    {"attempt": 2, "action": "dropped FK, renamed, recreated FK", "result": "FAILED: orders_archive has a second FK nobody documented"},
    {"attempt": 3, "action": "same, including orders_archive", "result": "FAILED: view v_customer_ltv references old column name"},
    {"attempt": 4, "action": "recreated view after rename", "result": "FAILED: view recreated before rename committed — wrong order"},
    {"attempt": 9, "action": "single transaction: drop views, drop FKs, rename, recreate FKs, recreate views — in dependency order", "result": "SUCCESS: 214 tests pass"},
]


def distill(trajectory: list[dict]) -> str:
    """Compress a winning trajectory into a worked example — procedure, not data."""
    log = "\n".join(
        f"Attempt {t['attempt']}: {t['action']} → {t['result']}" for t in trajectory
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": (
                "Distill this multi-attempt agent trajectory into a compact "
                "worked example for future retrieval. Include: the task class "
                "(one line), the key decisions that made the final attempt "
                "work, and the pitfalls the failed attempts revealed. EXCLUDE "
                "session-specific data (table names are fine as examples, "
                f"but generalize the lesson).\n\n{log}"
            ),
        }],
    )
    return resp.content[0].text.strip()


def store(example: str, collection: chromadb.Collection) -> str:
    doc_id = f"exp_{collection.count() + 1}"
    collection.add(documents=[example], ids=[doc_id])
    return doc_id


def attempt_task(task: str, retrieved: str | None) -> str:
    """One attempt at a new task, with or without retrieved experience."""
    context = ""
    if retrieved:
        context = f"WORKED EXAMPLE FROM A PAST WIN:\n{retrieved}\n\n"
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": (
                f"{context}TASK: {task}\n\n"
                "Write your migration plan as a numbered list. Be specific "
                "about ordering and transaction boundaries."
            ),
        }],
    )
    return resp.content[0].text


def main():
    parser = argparse.ArgumentParser(description="Distill winning trajectories")
    parser.add_argument("--trajectory", help="JSONL file of attempts")
    args = parser.parse_args()

    if args.trajectory and Path(args.trajectory).exists():
        trajectory = [json.loads(l) for l in Path(args.trajectory).read_text().splitlines() if l.strip()]
    else:
        print("(no trajectory file — using the built-in 9-attempt demo)")
        trajectory = DEMO_TRAJECTORY

    print(f"📖 Distilling {len(trajectory)}-attempt trajectory...")
    example = distill(trajectory)
    print(f"\n{example}\n")

    chroma = chromadb.PersistentClient(path="./experience_db")
    collection = chroma.get_or_create_collection("distilled_experience")
    doc_id = store(example, collection)
    print(f"💾 Stored as {doc_id} in ./experience_db\n")

    # The payoff: a new task from the same class
    new_task = ("Rename column account_id to org_id in the payments table. "
                "Several FKs and reporting views depend on it.")

    print("=" * 60)
    print("NEW TASK, WITHOUT EXPERIENCE (how attempt 1 used to look):")
    print("=" * 60)
    print(attempt_task(new_task, retrieved=None)[:800], "...\n")

    hits = collection.query(query_texts=[new_task], n_results=1)
    retrieved = hits["documents"][0][0]
    print("=" * 60)
    print("NEW TASK, WITH RETRIEVED EXPERIENCE (attempt 1 = old attempt 9):")
    print("=" * 60)
    print(attempt_task(new_task, retrieved=retrieved)[:800], "...")
    print("\n✅ Compare the two plans: the second one already knows about "
          "dependency ordering, hidden FKs, and view recreation — lessons "
          "that previously cost eight failed attempts.")


if __name__ == "__main__":
    main()
