"""
learn_command.py — Atlas v0.21: Teaching Atlas to /learn.

Bolts a `/learn` onto Atlas: it reads the current session's trajectory log
(the Chapter 15 harness already writes one), asks the model to abstract the
successful procedure — explicitly excluding session-specific data — and
emits a SKILL.md into a staging directory.

The review gate is the point; don't remove it. The Chapter 9 loader picks
skills up only after a human moves them from staging/ into the trusted
skills/ folder, because an agent-written SKILL.md is executable behavior
and gets the same review as a skill written by a colleague.

Usage:
    python learn_command.py --session logs/session_0713.jsonl

Trajectory log format (JSONL, one event per line):
    {"type": "task", "content": "..."}
    {"type": "tool_call", "tool": "...", "input": {...}}
    {"type": "tool_result", "content": "..."}
    {"type": "correction", "content": "..."}     # user steered the agent
    {"type": "outcome", "status": "success", "attempt": 2}

Requires: pip install anthropic
"""

import argparse
import json
import re
import sys
from pathlib import Path

import anthropic

client = anthropic.Anthropic()
MODEL = "claude-opus-4-8"

STAGING_DIR = Path("staging")

DISTILL_PROMPT = """You are extracting a reusable Agent Skill from a successful session.

Below is the session's trajectory log. Abstract the successful procedure into
a SKILL.md with YAML frontmatter (name, description) followed by the numbered
procedure and its constraints.

Rules — these matter:
- Distill the PROCEDURE, not the DATA. Exclude every session-specific value:
  this session's figures, dates, names, file contents, and outputs. A skill
  with September's revenue fossilized inside it will confidently report a
  quarter that already ended.
- Corrections in the log are gold: each one is a rule the user had to teach
  by hand. Encode them as explicit constraints so nobody teaches them twice.
- The `description` in the frontmatter must match how a user would naturally
  ask for this task, because that is what triggers the skill.
- The skill must not require tools the session never used.

Respond with ONLY the SKILL.md content."""


def load_trajectory(path: Path) -> list[dict]:
    events = []
    for line in path.read_text().splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def summarize_events(events: list[dict]) -> tuple[str, dict]:
    """Render the log for the model and pull out headline stats."""
    lines = []
    stats = {"tasks": 0, "corrections": 0, "outcome": None}
    for e in events:
        kind = e.get("type")
        if kind == "task":
            stats["tasks"] += 1
            lines.append(f"TASK: {e['content']}")
        elif kind == "tool_call":
            lines.append(f"TOOL {e['tool']}: {json.dumps(e.get('input', {}))[:200]}")
        elif kind == "tool_result":
            lines.append(f"RESULT: {str(e.get('content', ''))[:200]}")
        elif kind == "correction":
            stats["corrections"] += 1
            lines.append(f"USER CORRECTION: {e['content']}")
        elif kind == "outcome":
            stats["outcome"] = e
            lines.append(f"OUTCOME: {e.get('status')} (attempt {e.get('attempt', '?')})")
    return "\n".join(lines), stats


def draft_skill(trajectory_text: str) -> str:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=DISTILL_PROMPT,
        messages=[{"role": "user", "content": trajectory_text}],
    )
    return resp.content[0].text.strip()


def skill_name(skill_md: str) -> str:
    m = re.search(r"^name:\s*(.+)$", skill_md, re.MULTILINE)
    raw = m.group(1).strip() if m else "unnamed-skill"
    return re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")


def main():
    parser = argparse.ArgumentParser(description="Atlas /learn command")
    parser.add_argument("--session", required=True, help="Trajectory log (JSONL)")
    args = parser.parse_args()

    log_path = Path(args.session)
    if not log_path.exists():
        sys.exit(f"No trajectory log at {log_path}")

    events = load_trajectory(log_path)
    trajectory_text, stats = summarize_events(events)
    outcome = stats["outcome"] or {}
    print(f"📖 Analyzed {len(events)} trajectory events "
          f"({stats['tasks']} task, {outcome.get('status', 'unknown')} "
          f"on attempt {outcome.get('attempt', '?')})")

    if outcome.get("status") != "success":
        sys.exit("Refusing to distill: only successful trajectories become skills.")

    skill_md = draft_skill(trajectory_text)
    name = skill_name(skill_md)
    out_dir = STAGING_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "SKILL.md"
    out_path.write_text(skill_md)

    print(f"✍️  Drafted skill: {out_path}")
    print(f"⚠️  Review before promoting: mv {out_dir} skills/")


if __name__ == "__main__":
    main()
