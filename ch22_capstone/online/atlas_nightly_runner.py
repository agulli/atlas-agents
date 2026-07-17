"""
atlas_nightly_runner.py — Scheduled sweep of open GitHub issues.

Runs Atlas on every unassigned, open issue tagged "atlas-ready" in a
repository, working through them in priority order. Designed to run as
a nightly cron job.

The pattern:
  1. Fetch all open issues labeled "atlas-ready"
  2. Sort by priority (P0 first, then oldest)
  3. For each issue: run the full Atlas pipeline in dry-run mode
  4. Post a comment with the plan (human approves separately)
  5. Skip issues already processed today

Schedule with cron:
  0 2 * * * cd /path/to/atlas && python atlas_nightly_runner.py

Or with Antigravity /schedule:
  /schedule "run atlas nightly scan every day at 02:00 UTC"

Usage:
    python atlas_nightly_runner.py --repo myorg/myrepo
    python atlas_nightly_runner.py --repo myorg/myrepo --max-issues 5

Requires: pip install anthropic
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
from atlas_capstone import AtlasState, build_graph, fetch_issue_node, planner_node

client = anthropic.Anthropic()

PROCESSED_LOG = Path(".atlas_nightly.json")
ATLAS_LABEL   = "atlas-ready"


# ── Issue discovery ───────────────────────────────────────────────────

def fetch_open_issues(repo: str, label: str = ATLAS_LABEL) -> list[dict]:
    """Fetch open issues with the atlas-ready label via gh CLI."""
    result = subprocess.run(
        [
            "gh", "issue", "list",
            "--repo",  repo,
            "--label", label,
            "--state", "open",
            "--json",  "number,title,body,labels,createdAt,assignees",
            "--limit", "50",
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Warning: gh CLI returned error: {result.stderr}", file=sys.stderr)
        return []
    return json.loads(result.stdout or "[]")


def priority_score(issue: dict) -> tuple[int, str]:
    """Sort key: P0 labels first, then oldest issues."""
    labels = {l.get("name", "") for l in issue.get("labels", [])}
    if "P0" in labels:
        priority = 0
    elif "P1" in labels:
        priority = 1
    elif "P2" in labels:
        priority = 2
    else:
        priority = 3
    return (priority, issue.get("createdAt", ""))


# ── Processed log ─────────────────────────────────────────────────────

def load_processed() -> set[int]:
    """Return set of issue numbers processed today."""
    today = datetime.now(timezone.utc).date().isoformat()
    if not PROCESSED_LOG.exists():
        return set()
    log = json.loads(PROCESSED_LOG.read_text())
    return {entry["number"] for entry in log.get(today, [])}


def mark_processed(issue_number: int, result: str):
    """Record that we processed this issue today."""
    today = datetime.now(timezone.utc).date().isoformat()
    log   = json.loads(PROCESSED_LOG.read_text()) if PROCESSED_LOG.exists() else {}
    log.setdefault(today, []).append({
        "number":    issue_number,
        "result":    result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    PROCESSED_LOG.write_text(json.dumps(log, indent=2))


# ── Plan comment ──────────────────────────────────────────────────────

def post_plan_comment(repo: str, issue_number: int, plan: list[str]):
    """Post Atlas's implementation plan as a GitHub issue comment."""
    plan_text = "\n".join(f"{i+1}. {task}" for i, task in enumerate(plan))
    body = (
        "## Atlas Implementation Plan\n\n"
        f"Atlas v0.20 analyzed this issue and proposes:\n\n"
        f"{plan_text}\n\n"
        "---\n"
        "*Reply with `/atlas approve` to run the full implementation.*"
    )
    subprocess.run(
        ["gh", "issue", "comment", str(issue_number),
         "--repo", repo, "--body", body],
        capture_output=True,
    )


# ── Main sweep ────────────────────────────────────────────────────────

def nightly_sweep(repo: str, max_issues: int = 10, dry_run: bool = False):
    """Process up to max_issues open issues tagged atlas-ready."""
    print(f"Atlas v0.20 — Nightly Sweep")
    print(f"Repository: {repo}")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}\n")

    issues    = fetch_open_issues(repo)
    processed = load_processed()

    # Filter already-processed and sort by priority
    pending = [i for i in issues if i["number"] not in processed]
    pending.sort(key=priority_score)

    print(f"Found {len(issues)} labeled issues, {len(pending)} pending today.\n")

    processed_count = 0
    for issue in pending[:max_issues]:
        number = issue["number"]
        title  = issue["title"]
        print(f"{'─'*50}")
        print(f"Issue #{number}: {title}")
        print(f"Labels: {[l['name'] for l in issue.get('labels', [])]}")

        try:
            # Run planning phase only (dry-run by design for nightly sweep)
            state: AtlasState = {
                "messages":     [],
                "repo":         repo,
                "issue_number": number,
                "issue":        {
                    "title": issue["title"],
                    "body":  issue.get("body", ""),
                },
                "plan":         [],
                "current_step": 0,
                "code_changes": {},
                "test_results": {},
                "review":       {},
                "approved":     False,
                "retry_count":  0,
                "dry_run":      True,
            }

            updated = planner_node(state)
            plan    = updated.get("plan", [])

            if plan and not dry_run:
                post_plan_comment(repo, number, plan)
                print(f"✅ Plan posted ({len(plan)} tasks)")
            elif plan:
                print(f"[dry-run] Would post {len(plan)}-task plan")

            mark_processed(number, "planned")
            processed_count += 1

        except Exception as e:
            print(f"❌ Error processing issue #{number}: {e}")
            mark_processed(number, f"error: {e}")

        time.sleep(2)  # Be a polite API citizen

    print(f"\n{'─'*50}")
    print(f"Sweep complete: {processed_count} issues processed.")
    print(f"Log: {PROCESSED_LOG.absolute()}")


def main():
    parser = argparse.ArgumentParser(description="Atlas Nightly Issue Sweep")
    parser.add_argument("--repo",       required=True)
    parser.add_argument("--max-issues", type=int, default=10)
    parser.add_argument("--dry-run",    action="store_true",
                        help="Plan only, do not post comments")
    args = parser.parse_args()
    nightly_sweep(args.repo, args.max_issues, args.dry_run)


if __name__ == "__main__":
    main()
