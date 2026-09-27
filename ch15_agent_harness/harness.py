"""
Atlas v0.15 — Agent Execution Harness
======================================
Chapter 15 Project: A sandboxed execution harness with path validation,
command allowlisting, and automated verification loops (syntax + lint).

The harness sits between the model and the world. Every file write,
every shell command, every path reference passes through it before
anything touches the filesystem.

Usage:
    python harness.py

Requires: pip install ruff  (for linter verification)
"""

import json
import logging
import shlex
import subprocess
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("harness")


class AgentHarness:
    """
    A sandboxed execution environment for agent tool calls.

    Enforces:
      - Path sandboxing: no writes outside workspace_dir
      - Command allowlisting: only permitted executables run
      - Verification loops: every .py write is syntax-checked and linted
      - Trajectory logging: every action recorded for audit/replay
    """

    DEFAULT_ALLOWED = {"pytest", "ruff", "python", "git"}

    def __init__(self, workspace_dir: Path, allowed_commands: set[str] | None = None):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.allowed_commands = (
            self.DEFAULT_ALLOWED if allowed_commands is None else allowed_commands
        )
        self.trajectory: list[dict[str, Any]] = []

        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"Harness ready. Workspace: {self.workspace_dir}")

    # ── Public tool dispatch ──────────────────────────────────────────

    def execute_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        """Route a model tool call through validation and execution."""
        log.info(f"Tool call: {tool_name}({args})")
        self._record(action=tool_name, args=args)

        if tool_name == "write_file":
            return self._write_file(args.get("path", ""), args.get("content", ""))
        elif tool_name == "read_file":
            return self._read_file(args.get("path", ""))
        elif tool_name == "run_command":
            return self._run_command(args.get("command", ""))
        elif tool_name == "read_reference":
            return self._read_reference(args.get("name", ""))
        else:
            return f"Error: Unknown tool '{tool_name}'."

    # ── Path validation ───────────────────────────────────────────────

    def _validate_path(self, rel_path: str) -> Path:
        """
        Resolve the path and verify it stays inside the sandbox.

        Path.resolve() expands all '..' and symlinks before comparison,
        so there is no path the model can construct that sneaks past this.
        """
        target = (self.workspace_dir / rel_path).resolve()
        if not target.is_relative_to(self.workspace_dir):
            raise PermissionError(
                f"Security violation: '{rel_path}' escapes the sandbox."
            )
        return target

    # ── Tool implementations ──────────────────────────────────────────

    def _write_file(self, rel_path: str, content: str) -> str:
        """Write a file after path validation; run verification on .py files."""
        if not rel_path:
            return "Error: path is required."
        try:
            target = self._validate_path(rel_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            log.info(f"Wrote: {rel_path} ({len(content)} bytes)")
            self._record(event="write_file", path=rel_path, bytes=len(content))

            if rel_path.endswith(".py"):
                verdict = self._verify_python(rel_path)
                return f"Wrote {rel_path}. {verdict}"
            return f"Wrote {rel_path}."

        except PermissionError as e:
            self._record(event="blocked", reason=str(e))
            return str(e)
        except Exception as e:
            return f"Error: {e}"

    def _read_file(self, rel_path: str) -> str:
        """Read a file after path validation."""
        if not rel_path:
            return "Error: path is required."
        try:
            target = self._validate_path(rel_path)
            if not target.exists():
                return f"Error: File not found — '{rel_path}'"
            content = target.read_text(encoding="utf-8")
            self._record(event="read_file", path=rel_path)
            return content
        except PermissionError as e:
            return str(e)
        except Exception as e:
            return f"Error: {e}"

    def _run_command(self, command: str) -> str:
        """Run one executable directly after checking it against the allowlist."""
        if not command.strip():
            return "Error: command is empty."

        try:
            argv = shlex.split(command)
        except ValueError as e:
            self._record(event="blocked_command", command=command, reason=str(e))
            return f"Error: Invalid command syntax — {e}"

        if not argv:
            return "Error: command is empty."

        base_cmd = argv[0]
        if base_cmd not in self.allowed_commands:
            log.warning(f"Blocked: {command}")
            self._record(event="blocked_command", command=command)
            return f"Error: '{base_cmd}' is not on the command allowlist."

        try:
            result = subprocess.run(
                argv, shell=False, cwd=self.workspace_dir,
                capture_output=True, text=True, timeout=30,
            )
            output = (result.stdout + result.stderr).strip() or "(no output)"
            status = "ok" if result.returncode == 0 else f"exit {result.returncode}"
            self._record(event="run_command", command=command, status=status)
            return output
        except subprocess.TimeoutExpired:
            self._record(event="run_command", command=command, status="timeout")
            return "Error: Command timed out after 30 seconds."
        except Exception as e:
            return f"Error: {e}"

    def _read_reference(self, name: str) -> str:
        """Lazy-load a reference doc by name (progressive disclosure pattern)."""
        catalog = {
            "api_spec":   "docs/api_spec.md",
            "db_schema":  "docs/db_schema.sql",
            "style_guide": "docs/style_guide.md",
        }
        if name not in catalog:
            return f"Unknown reference '{name}'. Available: {sorted(catalog)}"
        return self._read_file(catalog[name])

    # ── Verification loop (internal — not a tool call) ────────────────

    def _verify_python(self, rel_path: str) -> str:
        """
        Syntax-check + lint a Python file.

        Runs internally after every .py write — the model does not control
        when this runs. Uses exit codes, not string matching, for pass/fail.
        Does NOT go through _run_command; linting is harness bookkeeping,
        not an agent action, and should not appear in the trajectory log.
        """
        full_path = self._validate_path(rel_path)

        # 1. Syntax check — instant, no subprocess needed
        try:
            compile(full_path.read_text(encoding="utf-8"), rel_path, "exec")
        except SyntaxError as e:
            return f"⚠️ Syntax error on line {e.lineno}: {e.msg}"

        # 2. Linter — exit code 0 = clean, 1 = issues found
        result = subprocess.run(
            ["ruff", "check", str(full_path)],
            capture_output=True, text=True,
            cwd=self.workspace_dir,
        )
        if result.returncode != 0:
            issues = (result.stdout or result.stderr).strip()
            return f"⚠️ Linter issues:\n{issues}"

        return "✅ Verification passed."

    # ── Trajectory log ────────────────────────────────────────────────

    def _record(self, **kwargs: Any):
        self.trajectory.append(kwargs)

    def dump_trajectory(self) -> str:
        return json.dumps(self.trajectory, indent=2)


# ── Demo ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    workspace = Path(__file__).parent / "workspace"
    harness = AgentHarness(
        workspace_dir=workspace,
        allowed_commands={"python", "ruff", "pytest"},
    )

    print("\n--- 1. Normal file write ---")
    print(harness.execute_tool("write_file", {
        "path": "math_utils.py",
        "content": "def add(a, b):\n    return a + b\n",
    }))

    print("\n--- 2. Path traversal attempt (should be blocked) ---")
    print(harness.execute_tool("write_file", {
        "path": "../../../hacked.txt",
        "content": "exposed",
    }))

    print("\n--- 3. Syntax error caught by verification loop ---")
    print(harness.execute_tool("write_file", {
        "path": "broken.py",
        "content": "def divide(a, b):\n    return a / b\n  bad_indent = True\n",
    }))

    print("\n--- 4. Forbidden shell command (should be blocked) ---")
    print(harness.execute_tool("run_command", {"command": "rm -rf /"}))

    print("\n--- 5. Allowed command ---")
    print(harness.execute_tool("run_command", {"command": "python --version"}))

    print("\n--- Trajectory log ---")
    print(harness.dump_trajectory())

    # Cleanup
    for f in ["math_utils.py", "broken.py"]:
        (workspace / f).unlink(missing_ok=True)
    try:
        workspace.rmdir()
    except OSError:
        pass
