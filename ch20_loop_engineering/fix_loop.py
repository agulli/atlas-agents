"""
fix_loop.py — Atlas v0.20: The Self-Correcting Fix Loop.

Point it at a repo with failing tests and it runs the engineered loop from
Chapter 20: verify → generate a patch → apply → re-verify, until the goal is
met or the loop decides a human needs to see this.

The loop owns every role a tired engineer usually plays at 2 a.m.:
  - Trigger:      you run it once; it iterates on its own
  - Verifier:     pytest + ruff decide "done", not the model
  - Memory:       failed attempts are compacted into one-line lessons
  - Escalation:   fingerprint-based stall detection pages a human
  - Distillation: winning trajectories are saved to experience/ and
                  retrieved into context on future runs

Usage:
    python fix_loop.py --repo ./orders-service --goal "pytest green, ruff clean"

Requires: pip install anthropic
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import anthropic

client = anthropic.Anthropic()

MODEL = "claude-opus-4-8"        # generates the patches
COMPACT_MODEL = "claude-haiku-4-5"  # compacts failures into lessons
MAX_ATTEMPTS = 4
STALL_LIMIT = 2                  # same fingerprint N+1 times → escalate

EXPERIENCE_DIR = Path("experience")
ESCALATION_FILE = Path("escalation_state.json")

SYSTEM_PROMPT = """You are Atlas, an autonomous code-fixing agent inside an engineered loop.
You will receive a goal, test/lint output, relevant source files, and lessons
from previous failed attempts. Produce the minimal fix.

Respond with ONLY a JSON array of file replacements:
[{"path": "relative/path.py", "content": "<full new file content>"}]
No commentary, no markdown fences."""


# ── The verifier: the loop grades the work, not the model ────────────

def verify(repo: Path) -> tuple[bool, str]:
    """Machine-checkable termination condition: pytest green + ruff clean."""
    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "-q"],
        cwd=repo, capture_output=True, text=True, timeout=300,
    )
    lint = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        cwd=repo, capture_output=True, text=True, timeout=120,
    )
    ok = tests.returncode == 0 and lint.returncode == 0
    evidence = (tests.stdout + tests.stderr)[-3000:] + "\n" + lint.stdout[-1000:]
    return ok, evidence


def failure_fingerprint(evidence: str) -> str:
    """Hash the failing assertions so we can detect a no-progress loop."""
    failures = [l for l in evidence.splitlines() if "FAILED" in l or "Error" in l]
    return hashlib.sha256("\n".join(sorted(failures)).encode()).hexdigest()[:12]


# ── Compaction: feed forward lessons, not transcripts ────────────────

def summarize_failure(attempt: int, evidence: str, patch_summary: str) -> str:
    """Compress a failed attempt into one line the next attempt can learn from."""
    resp = client.messages.create(
        model=COMPACT_MODEL,
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                f"Attempt {attempt} applied this change: {patch_summary}\n"
                f"It failed with:\n{evidence[-1500:]}\n\n"
                "Write ONE line: what was tried and why it failed. "
                "Format: 'Attempt N: tried X — failed because Y.'"
            ),
        }],
    )
    return resp.content[0].text.strip()


# ── Experience: pay for the lesson once, keep it forever ─────────────

def retrieve_experience(goal: str) -> str:
    """Pull previously distilled worked examples that match this goal."""
    if not EXPERIENCE_DIR.exists():
        return ""
    goal_words = set(re.findall(r"\w+", goal.lower()))
    matches = []
    for f in EXPERIENCE_DIR.glob("*.md"):
        text = f.read_text()
        title_words = set(re.findall(r"\w+", text.splitlines()[0].lower()))
        if goal_words & title_words:
            matches.append(text)
    return "\n\n---\n\n".join(matches[:2])


def distill_trajectory(goal: str, lessons: list[str], final_patch: str) -> Path:
    """Compress the winning trajectory into a retrievable worked example."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": (
                f"Goal: {goal}\nFailed-attempt lessons:\n"
                + "\n".join(lessons)
                + f"\nWinning change summary:\n{final_patch[:2000]}\n\n"
                "Write a compact worked example for a future agent facing a "
                "similar task: '# <short title>' on line 1, then the key "
                "decisions and the verified outcome. Exclude file contents."
            ),
        }],
    )
    EXPERIENCE_DIR.mkdir(exist_ok=True)
    text = resp.content[0].text.strip()
    slug = re.sub(r"\W+", "_", text.splitlines()[0].strip("# ").lower())[:48]
    path = EXPERIENCE_DIR / f"{slug}.md"
    path.write_text(text)
    return path


# ── Generation: one attempt ──────────────────────────────────────────

def gather_sources(repo: Path, evidence: str) -> str:
    """Include only files mentioned in the failure output — not the whole repo."""
    mentioned = set(re.findall(r"([\w/\.\-]+\.py)", evidence))
    chunks = []
    for name in sorted(mentioned):
        p = repo / name
        if p.exists() and p.is_file():
            chunks.append(f"### {name}\n{p.read_text()[:8000]}")
    return "\n\n".join(chunks[:6])


def generate_and_apply(repo: Path, goal: str, evidence: str,
                       lessons: list[str], experience: str) -> str:
    """Ask the model for a fix, apply it, return a summary of what changed."""
    context = f"GOAL: {goal}\n\nFAILURE OUTPUT:\n{evidence}\n\n"
    if lessons:
        context += "LESSONS FROM FAILED ATTEMPTS (do not repeat these):\n"
        context += "\n".join(lessons) + "\n\n"
    if experience:
        context += f"WORKED EXAMPLES FROM PAST WINS:\n{experience}\n\n"
    context += f"RELEVANT SOURCES:\n{gather_sources(repo, evidence)}"

    resp = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}],
    )
    replacements = json.loads(resp.content[0].text)
    changed = []
    for item in replacements:
        target = (repo / item["path"]).resolve()
        if repo.resolve() not in target.parents and target != repo.resolve():
            raise ValueError(f"Patch escapes repo: {item['path']}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item["content"])
        changed.append(item["path"])
    return f"rewrote {', '.join(changed)}"


# ── Escalation: the loop must be able to lose ────────────────────────

def escalate(goal: str, lessons: list[str], reason: str) -> dict:
    state = {
        "status": "escalated",
        "goal": goal,
        "reason": reason,
        "lessons": lessons,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    ESCALATION_FILE.write_text(json.dumps(state, indent=2))
    print(f"🚨 Escalated: {reason}. Resumable state → {ESCALATION_FILE}")
    return state


# ── The loop ─────────────────────────────────────────────────────────

def run_loop(repo: Path, goal: str) -> dict:
    lessons: list[str] = []
    experience = retrieve_experience(goal)
    if experience:
        print("📚 Retrieved prior experience for this task class.")
    last_fp, stall_count, patch_summary = None, 0, ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        done, evidence = verify(repo)
        if done:
            print(f"── Attempt {attempt} ── ✅ goal met: {goal}")
            if lessons:  # only distill if the win took real work
                path = distill_trajectory(goal, lessons, patch_summary)
                print(f"📚 Trajectory distilled → {path}")
            return {"status": "success", "attempts": attempt}

        fp = failure_fingerprint(evidence)
        n_failures = evidence.count("FAILED")
        print(f"── Attempt {attempt} ── {n_failures} failures  [fp: {fp}]", end="")

        stall_count = stall_count + 1 if fp == last_fp else 0
        last_fp = fp
        if stall_count >= STALL_LIMIT:
            print()
            return escalate(goal, lessons, f"same failure {stall_count + 1}x ({fp})")

        patch_summary = generate_and_apply(repo, goal, evidence, lessons, experience)
        lessons.append(summarize_failure(attempt, evidence, patch_summary))
        print("  lesson recorded")

    done, _ = verify(repo)
    if done:
        return {"status": "success", "attempts": MAX_ATTEMPTS}
    return escalate(goal, lessons, "max attempts exhausted")


def main():
    parser = argparse.ArgumentParser(description="Atlas v0.20 self-correcting fix loop")
    parser.add_argument("--repo", required=True, help="Path to the repo to fix")
    parser.add_argument("--goal", default="pytest green, ruff clean")
    args = parser.parse_args()

    result = run_loop(Path(args.repo), args.goal)
    sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
