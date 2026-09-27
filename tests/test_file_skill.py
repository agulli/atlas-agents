import tempfile
import unittest
from pathlib import Path

from shared.skills import FileSkill


class FileSkillSandboxTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory()
        self.outside = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.sandbox.name)
        self.outside_dir = Path(self.outside.name)
        self.skill = FileSkill(str(self.base_dir))

    def tearDown(self):
        self.sandbox.cleanup()
        self.outside.cleanup()

    def test_read_write_and_list_inside_sandbox(self):
        result = self.skill.execute(
            "file_write", {"path": "notes/topic.txt", "content": "hello"}
        )

        self.assertEqual(result, "Written 5 chars to notes/topic.txt")
        self.assertEqual(
            self.skill.execute("file_read", {"path": "notes/topic.txt"}), "hello"
        )
        self.assertEqual(
            self.skill.execute("file_list", {"directory": "notes"}), "📄 topic.txt"
        )

    def test_parent_traversal_is_blocked_for_every_file_operation(self):
        escaped_name = f"{self.base_dir.name}-created.txt"
        self.assertEqual(
            self.skill.execute("file_read", {"path": "../secret.txt"}),
            "Error: Path escapes sandbox.",
        )
        self.assertEqual(
            self.skill.execute(
                "file_write", {"path": f"../{escaped_name}", "content": "unsafe"}
            ),
            "Error: Path escapes sandbox.",
        )
        self.assertEqual(
            self.skill.execute("file_list", {"directory": ".."}),
            "Error: Path escapes sandbox.",
        )
        self.assertFalse((self.base_dir.parent / escaped_name).exists())

    def test_symlink_escape_is_blocked_for_every_file_operation(self):
        (self.outside_dir / "secret.txt").write_text("secret", encoding="utf-8")
        (self.base_dir / "outside").symlink_to(self.outside_dir, target_is_directory=True)

        self.assertEqual(
            self.skill.execute("file_read", {"path": "outside/secret.txt"}),
            "Error: Path escapes sandbox.",
        )
        self.assertEqual(
            self.skill.execute(
                "file_write", {"path": "outside/created.txt", "content": "unsafe"}
            ),
            "Error: Path escapes sandbox.",
        )
        self.assertEqual(
            self.skill.execute("file_list", {"directory": "outside"}),
            "Error: Path escapes sandbox.",
        )
        self.assertFalse((self.outside_dir / "created.txt").exists())


if __name__ == "__main__":
    unittest.main()
