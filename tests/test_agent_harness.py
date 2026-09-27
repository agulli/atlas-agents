import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ch15_agent_harness.harness import AgentHarness


class AgentHarnessCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_allowed_command_is_executed_without_a_shell(self):
        harness = AgentHarness(self.workspace, allowed_commands={"python"})

        with patch("ch15_agent_harness.harness.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "ok\n"
            run.return_value.stderr = ""

            result = harness._run_command('python -c "print(123)"')

        self.assertEqual(result, "ok")
        run.assert_called_once_with(
            ["python", "-c", "print(123)"],
            shell=False,
            cwd=harness.workspace_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_shell_operators_are_passed_as_arguments_not_executed(self):
        harness = AgentHarness(self.workspace, allowed_commands={"echo"})
        escaped_file = self.workspace / "escaped.txt"

        result = harness._run_command("echo safe > escaped.txt")

        self.assertIn("safe > escaped.txt", result)
        self.assertFalse(escaped_file.exists())

    def test_command_substitution_is_not_evaluated(self):
        harness = AgentHarness(self.workspace, allowed_commands={"echo"})
        escaped_file = self.workspace / "escaped.txt"

        result = harness._run_command("echo $(touch escaped.txt)")

        self.assertIn("$(touch escaped.txt)", result)
        self.assertFalse(escaped_file.exists())

    def test_disallowed_executable_is_blocked_before_subprocess(self):
        harness = AgentHarness(self.workspace, allowed_commands={"python"})

        with patch("ch15_agent_harness.harness.subprocess.run") as run:
            result = harness._run_command("sh -c 'echo unsafe'")

        self.assertIn("not on the command allowlist", result)
        run.assert_not_called()

    def test_malformed_quoting_returns_a_clear_error(self):
        harness = AgentHarness(self.workspace, allowed_commands={"python"})

        result = harness._run_command("python -c 'unterminated")

        self.assertIn("Invalid command syntax", result)
        self.assertEqual(harness.trajectory[-1]["event"], "blocked_command")

    def test_empty_allowlist_remains_empty(self):
        harness = AgentHarness(self.workspace, allowed_commands=set())

        result = harness._run_command("python --version")

        self.assertIn("not on the command allowlist", result)


if __name__ == "__main__":
    unittest.main()
