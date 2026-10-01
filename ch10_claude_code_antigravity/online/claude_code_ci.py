"""
claude_code_ci.py — Run Claude Code headlessly in GitHub Actions for automated PR review.

Claude Code supports a --print flag that runs a single prompt non-interactively
and exits. This makes it suitable for CI pipelines: no UI, no interactive
approval, just input → output → exit code.

This script wraps that pattern to provide:
  - Automated code review on every PR
  - Security scanning for common vulnerabilities
  - Test generation for uncovered changed functions
  - Results posted as a PR comment via the GitHub API

GitHub Actions setup:
    # .github/workflows/atlas-review.yml
    name: Atlas Code Review
    on: [pull_request]
    jobs:
      review:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: anthropics/setup-claude-code@v1
          - run: python .github/scripts/claude_code_ci.py
            env:
              ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
              GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
              PR_NUMBER: ${{ github.event.pull_request.number }}
              REPO: ${{ github.repository }}

Usage (local testing):
    ANTHROPIC_API_KEY=... GITHUB_TOKEN=... PR_NUMBER=42 REPO=org/repo \
        python claude_code_ci.py
"""

import os
import subprocess
import sys
import textwrap
import requests

from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import ANTHROPIC_MODEL  # also loads .env


ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
PR_NUMBER = os.environ.get("PR_NUMBER", "")
REPO = os.environ.get("REPO", "")

GITHUB_API = "https://api.github.com"


def get_pr_diff() -> str:
    """Get the diff for the current PR."""
    result = subprocess.run(
        ["git", "diff", "origin/main...HEAD"],
        capture_output=True, text=True, check=True
    )
    return result.stdout


def run_claude_headless(prompt: str, model: str = ANTHROPIC_MODEL) -> str:
    """
    Run Claude Code with --print for non-interactive, CI-safe execution.

    --print: output the response and exit (no interactive session)
    --model: specify which Claude model to use
    --output-format=text: plain text output for easier parsing
    """
    result = subprocess.run(
        [
            "claude",
            "--print",
            f"--model={model}",
            "--output-format=text",
            prompt,
        ],
        capture_output=True, text=True, timeout=120,
        env={**os.environ, "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY},
    )
    if result.returncode != 0:
        print(f"Claude Code exited {result.returncode}: {result.stderr}", file=sys.stderr)
    return result.stdout.strip()


def review_diff(diff: str) -> str:
    """Ask Claude Code to review the PR diff."""
    prompt = textwrap.dedent(f"""
    You are a senior code reviewer. Review this PR diff for:

    1. **Security issues** (injection, path traversal, hardcoded secrets, OWASP Top 10)
    2. **Correctness bugs** (off-by-one, null pointer, race conditions)
    3. **Missing tests** — list any changed functions not covered by tests
    4. **Breaking changes** — API changes without version bump

    Format your response as:

    ## Security
    - [CRITICAL/HIGH/MEDIUM/LOW] Description

    ## Bugs
    - Description

    ## Missing Tests
    - function_name() in file.py

    ## Breaking Changes
    - Description

    ## Summary
    One sentence overall assessment.

    If a section has no issues, write "None found."

    PR DIFF:
    ```
    {diff[:8000]}
    ```
    """).strip()

    return run_claude_headless(prompt)


def generate_tests(diff: str) -> str:
    """Generate pytest tests for uncovered changed code."""
    prompt = textwrap.dedent(f"""
    Given this PR diff, generate pytest test cases for any new or modified
    functions that don't already have tests in the diff.

    Rules:
    - Use pytest style (no unittest.TestCase)
    - Test the happy path and at least one error case per function
    - Use descriptive test names: test_function_name_when_condition
    - Do not import private functions (underscore-prefixed)
    - If no new tests are needed, respond with: "No new tests required."

    PR DIFF:
    ```
    {diff[:6000]}
    ```
    """).strip()

    return run_claude_headless(prompt)


def post_pr_comment(body: str):
    """Post a comment on the GitHub PR."""
    if not all([GITHUB_TOKEN, PR_NUMBER, REPO]):
        print("Skipping GitHub comment — GITHUB_TOKEN, PR_NUMBER, REPO not all set.")
        print("\n--- Review Output ---")
        print(body)
        return

    url = f"{GITHUB_API}/repos/{REPO}/issues/{PR_NUMBER}/comments"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json={"body": body},
        timeout=10,
    )
    if resp.status_code == 201:
        print(f"Posted review comment to PR #{PR_NUMBER}")
    else:
        print(f"Failed to post comment: {resp.status_code} {resp.text}", file=sys.stderr)


def main():
    print("Getting PR diff...")
    diff = get_pr_diff()
    if not diff.strip():
        print("No changes detected. Skipping review.")
        sys.exit(0)

    print(f"Diff size: {len(diff)} characters")

    print("Running security + correctness review...")
    review = review_diff(diff)

    print("Generating missing tests...")
    tests = generate_tests(diff)

    comment = textwrap.dedent(f"""
    ## 🤖 Atlas Automated Review

    {review}

    ---

    ## Suggested Tests

    {tests}

    ---

    *Generated by [Atlas](atlas-agents/ch10_claude_code_antigravity/) using Claude Code.*
    *Review these suggestions — do not merge automatically.*
    """).strip()

    post_pr_comment(comment)

    # Fail CI if critical security issues were found
    if "[CRITICAL]" in review:
        print("\n❌ Critical security issues detected. Failing CI.")
        sys.exit(1)

    print("✅ Review complete.")


if __name__ == "__main__":
    main()
