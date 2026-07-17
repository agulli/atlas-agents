"""
skill_reviewer.py — A guardrail for /learn output.

An agent-written SKILL.md is executable behavior, so it gets reviewed like a
pull request (§21.3, §21.5). This script automates the Chapter 9 audit for
the three failure modes specific to skills that agents write about their own
sessions:

  1. Embedded session data — this quarter's figures, dates, emails, and IDs
     fossilized into the procedure ("every future run confidently reported
     a quarter that had already ended")
  2. Unpinned package invocations — `pip install foo` with no version is a
     supply-chain door left open in an instruction file that runs forever
  3. Tool scope creep — the skill requires tools the recorded task never
     needed, which is how injected instructions widen an agent's blast
     radius one merge at a time

Exit code 0 = clean, 1 = findings (wire it into CI on the staging/ dir).

Usage:
    python skill_reviewer.py staging/quarterly-summary/SKILL.md
    python skill_reviewer.py staging/            # review every staged skill
    python skill_reviewer.py staging/ --allowed-tools read,bash

Requires: nothing beyond the standard library.
"""

import argparse
import re
import sys
from pathlib import Path

# ── 1. Embedded session data ─────────────────────────────────────────
SESSION_DATA_PATTERNS = [
    (r"\$[\d,]+(?:\.\d+)?[MKBmkb]?\b", "dollar amount"),
    (r"\b\d{4}-\d{2}-\d{2}\b", "specific date"),
    (r"\b(?:Q[1-4])\s*(?:FY)?\s*20\d{2}\b", "specific quarter"),
    (r"\b[\w.+-]+@[\w-]+\.[\w.]+\b", "email address"),
    (r"\b\d{1,3}(?:,\d{3}){2,}\b", "large literal number"),
    (r"\b(?:acct|account|order|invoice|ticket)[_\s#-]*\d{3,}\b", "record ID"),
    (r"(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S+", "credential-like value"),
]

# ── 2. Unpinned package invocations ──────────────────────────────────
UNPINNED_PATTERNS = [
    (r"pip3?\s+install\s+(?![^\n]*==)[a-zA-Z]", "pip install without =="),
    (r"npm\s+install\s+(?![^\n]*@\d)[a-zA-Z]", "npm install without @version"),
    (r"npx\s+(?!-)[a-zA-Z](?![^\n]*@\d)", "npx without pinned version"),
    (r"curl[^\n]*\|\s*(?:ba)?sh", "curl piped to shell"),
]

# ── 3. Tool scope creep ──────────────────────────────────────────────
TOOL_MENTION_RE = re.compile(
    r"\b(?:use|run|call|invoke|execute)\s+(?:the\s+)?"
    r"(bash|shell|browser|web[_ ]?search|web[_ ]?fetch|write|edit|read|"
    r"delete|email|curl|git|docker|sudo)\b",
    re.IGNORECASE,
)


def review(path: Path, allowed_tools: set[str]) -> list[str]:
    text = path.read_text()
    findings = []

    for pattern, label in SESSION_DATA_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            findings.append(f"[session-data] {label}: '{m.group(0)[:40]}'")

    for pattern, label in UNPINNED_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            line = text[:m.start()].count("\n") + 1
            findings.append(f"[unpinned] {label} (line {line})")

    if allowed_tools:
        for m in TOOL_MENTION_RE.finditer(text):
            tool = m.group(1).lower().replace(" ", "_")
            if tool not in allowed_tools:
                findings.append(
                    f"[scope-creep] skill requires '{tool}' — "
                    "the recorded task never used it"
                )

    return findings


def main():
    parser = argparse.ArgumentParser(description="Audit agent-written skills")
    parser.add_argument("target", help="A SKILL.md file or a directory of skills")
    parser.add_argument(
        "--allowed-tools", default="",
        help="Comma-separated tools the original session actually used; "
             "anything else is flagged as scope creep",
    )
    args = parser.parse_args()

    target = Path(args.target)
    files = [target] if target.is_file() else sorted(target.rglob("SKILL.md"))
    if not files:
        sys.exit(f"No SKILL.md found under {target}")
    allowed = {t.strip().lower() for t in args.allowed_tools.split(",") if t.strip()}

    total = 0
    for f in files:
        findings = review(f, allowed)
        status = "❌" if findings else "✅"
        print(f"{status} {f}")
        for finding in findings:
            print(f"     {finding}")
        total += len(findings)

    if total:
        print(f"\n{total} finding(s). Do not promote to skills/ until resolved —")
        print("a merged skill is unreviewed behavior injected into every future session.")
        sys.exit(1)
    print("\nAll staged skills clean. Human review still applies before promoting.")


if __name__ == "__main__":
    main()
