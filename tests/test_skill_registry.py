import unittest

from shared.skills import DuplicateToolNameError, Skill, SkillRegistry


class RecordingSkill(Skill):
    def __init__(self, name, tool_names):
        self._name = name
        self._tool_names = tool_names
        self.calls = []

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return "Test skill"

    def get_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"Run {name}",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
            for name in self._tool_names
        ]

    def execute(self, tool_name, args):
        self.calls.append((tool_name, args))
        return f"{self.name}:{tool_name}"


class SkillRegistryTests(unittest.TestCase):
    def test_unique_tools_remain_unqualified(self):
        registry = SkillRegistry()
        skill = RecordingSkill("files", ["read"])

        registry.register(skill)

        self.assertEqual(registry.get_all_tools()[0]["function"]["name"], "read")
        self.assertEqual(registry.execute_tool("read", {"path": "notes.md"}), "files:read")
        self.assertEqual(skill.calls, [("read", {"path": "notes.md"})])

    def test_duplicate_public_name_is_rejected_without_overwriting_route(self):
        registry = SkillRegistry()
        first = RecordingSkill("files", ["read"])
        second = RecordingSkill("database", ["read"])
        registry.register(first)

        with self.assertRaisesRegex(DuplicateToolNameError, "namespace"):
            registry.register(second)

        self.assertEqual(registry.list_skills(), ["files"])
        self.assertEqual(registry.execute_tool("read", {}), "files:read")

    def test_namespaces_disambiguate_tools_and_preserve_local_execution_name(self):
        registry = SkillRegistry()
        files = RecordingSkill("files", ["read"])
        database = RecordingSkill("database", ["read"])

        registry.register(files, namespace="file")
        registry.register(database, namespace="database")

        published_names = [
            tool["function"]["name"] for tool in registry.get_all_tools()
        ]
        self.assertEqual(published_names, ["file__read", "database__read"])
        self.assertEqual(registry.execute_tool("file__read", {}), "files:read")
        self.assertEqual(
            registry.execute_tool("database__read", {"id": 7}), "database:read"
        )
        self.assertEqual(files.calls, [("read", {})])
        self.assertEqual(database.calls, [("read", {"id": 7})])

    def test_registration_is_atomic_when_later_tool_collides(self):
        registry = SkillRegistry()
        registry.register(RecordingSkill("existing", ["duplicate"]))

        with self.assertRaises(DuplicateToolNameError):
            registry.register(RecordingSkill("candidate", ["unique", "duplicate"]))

        self.assertEqual(registry.list_skills(), ["existing"])
        self.assertEqual(
            [tool["function"]["name"] for tool in registry.get_all_tools()],
            ["duplicate"],
        )
        self.assertEqual(registry.execute_tool("unique", {}), "Error: Unknown tool 'unique'")

    def test_duplicate_skill_name_is_rejected(self):
        registry = SkillRegistry()
        registry.register(RecordingSkill("files", ["read"]))

        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register(RecordingSkill("files", ["write"]))

    def test_invalid_namespace_is_rejected(self):
        registry = SkillRegistry()

        with self.assertRaisesRegex(ValueError, "Namespace"):
            registry.register(RecordingSkill("files", ["read"]), namespace="file.tools")

    def test_returned_schemas_cannot_mutate_registry_state(self):
        registry = SkillRegistry()
        registry.register(RecordingSkill("files", ["read"]), namespace="file")

        tools = registry.get_all_tools()
        tools[0]["function"]["name"] = "changed"

        self.assertEqual(registry.get_all_tools()[0]["function"]["name"], "file__read")
        self.assertEqual(registry.execute_tool("file__read", {}), "files:read")


if __name__ == "__main__":
    unittest.main()
