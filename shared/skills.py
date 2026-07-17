"""
Shared Skill Definitions — Used across all chapters.
=====================================================
These skill classes are the reusable building blocks of Atlas.
Each skill provides a set of related tools that can be registered
with the SkillRegistry and used by any agent framework.
"""

from abc import ABC, abstractmethod
from typing import Any, Literal
from pathlib import Path
import subprocess
import tempfile
from html.parser import HTMLParser
from tavily import TavilyClient

# ── Base Class ───────────────────────────────────────────────────────

class Skill(ABC):
    """Base class for all Atlas skills."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable skill name."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """What this skill does — shown to the LLM."""
        ...

    @abstractmethod
    def get_tools(self) -> list[dict]:
        """Return OpenAI-compatible tool schemas."""
        ...

    @abstractmethod
    def execute(self, tool_name: str, args: dict) -> Any:
        """Execute a tool by name with the given arguments."""
        ...


# ── Skill Registry ───────────────────────────────────────────────────

class SkillRegistry:
    """Registry that manages skills and dispatches tool calls."""

    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._tool_to_skill: dict[str, str] = {}

    def register(self, skill: Skill):
        """Register a skill and index its tools."""
        self._skills[skill.name] = skill
        for tool in skill.get_tools():
            tool_name = tool["function"]["name"]
            self._tool_to_skill[tool_name] = skill.name

    def get_all_tools(self) -> list[dict]:
        """Return all tool schemas from all registered skills."""
        tools = []
        for skill in self._skills.values():
            tools.extend(skill.get_tools())
        return tools

    def execute_tool(self, tool_name: str, args: dict) -> str:
        """Route a tool call to the correct skill."""
        skill_name = self._tool_to_skill.get(tool_name)
        if not skill_name:
            return f"Error: Unknown tool '{tool_name}'"
        return self._skills[skill_name].execute(tool_name, args)

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())

    def __repr__(self) -> str:
        skills = ", ".join(self._skills.keys())
        tools = ", ".join(self._tool_to_skill.keys())
        return f"SkillRegistry(skills=[{skills}], tools=[{tools}])"


# ── HTML Text Extractor ──────────────────────────────────────────────

class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._text: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._text.append(data.strip())

    def get_text(self) -> str:
        return "\n".join(line for line in self._text if line)


# ── FileSkill ────────────────────────────────────────────────────────

class FileSkill(Skill):
    """Local file operations — read, write, list."""

    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir).resolve()

    @property
    def name(self) -> str:
        return "FileSkill"

    @property
    def description(self) -> str:
        return "Read, write, and list local files within a sandboxed directory."

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "file_read",
                    "description": "Read the contents of a text file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative file path"}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "file_write",
                    "description": "Write content to a file (creates parent directories if needed).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative file path"},
                            "content": {"type": "string", "description": "Content to write"}
                        },
                        "required": ["path", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "file_list",
                    "description": "List files and directories.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "directory": {"type": "string", "description": "Relative directory path", "default": "."}
                            }
                    }
                }
            },
        ]

    def execute(self, tool_name: str, args: dict) -> str:
        if tool_name == "file_read":
            return self._read(args["path"])
        elif tool_name == "file_write":
            return self._write(args["path"], args["content"])
        elif tool_name == "file_list":
            return self._list(args.get("directory", "."))
        raise ValueError(f"Unknown tool: {tool_name}")

    def _read(self, path: str) -> str:
        full = self.base_dir / path
        if not full.resolve().is_relative_to(self.base_dir):
            return "Error: Path escapes sandbox."
        if not full.exists():
            return f"Error: File not found: {path}"
        return full.read_text(encoding="utf-8")

    def _write(self, path: str, content: str) -> str:
        full = self.base_dir / path
        if not full.resolve().is_relative_to(self.base_dir):
            return "Error: Path escapes sandbox."
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        return f"Written {len(content)} chars to {path}"

    def _list(self, directory: str = ".") -> str:
        dir_path = self.base_dir / directory
        if not dir_path.exists():
            return f"Error: Not found: {directory}"
        entries = sorted(dir_path.iterdir())
        lines = [
            f"{'📁' if e.is_dir() else '📄'} {e.name}" for e in entries
            if not e.name.startswith(".")
        ]
        return "\n".join(lines) if lines else "(empty directory)"


# ── CodeSkill ────────────────────────────────────────────────────────

class CodeSkill(Skill):
    """Execute Python code in a local subprocess (sandboxed by timeout)."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "CodeSkill"

    @property
    def description(self) -> str:
        return "Write and execute Python code in an isolated subprocess."

    def get_tools(self) -> list[dict]:
        return [{
                "type": "function",
                "function": {
                    "name": "code_execute",
                    "description": (
                        "Execute Python code and return stdout/stderr. "
                        f"Runs in a subprocess with a {self.timeout}s timeout."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                        "code": {"type": "string", "description": "Python code to execute"}
                        },
                    "required": ["code"]
                }
            }
        }]

    def execute(self, tool_name: str, args: dict) -> str:
        if tool_name != "code_execute":
            raise ValueError(f"Unknown tool: {tool_name}")
        return self._run(args["code"])

    def _run(self, code: str) -> str:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                result = subprocess.run(
                    ["python", f.name],
                    capture_output=True, text=True, timeout=self.timeout
                )
                out = result.stdout
                if result.stderr:
                    out += f"\nSTDERR:\n{result.stderr}"
                return out.strip() or "(no output)"
            except subprocess.TimeoutExpired:
                return f"Error: Timed out after {self.timeout}s."
            finally:
                Path(f.name).unlink(missing_ok=True)


# ── WebSearchSkill ──────────────────────────────────────────────────────

class WebSearchSkill(Skill):
    """Web research skill — deep search via the Tavily API."""

    def __init__(
        self,
        api_key: str | None = None,
        max_results: int = 5,
        search_depth: Literal["basic", "advanced"] = "advanced",
    ):
        self.client = TavilyClient(api_key)
        self.max_results = max_results
        self.search_depth = search_depth

    @property
    def name(self) -> str:
        return "WebSearchSkill"

    @property
    def description(self) -> str:
        return (
            "Search the web using Tavily for deep research with extracted page content."
        )

    def get_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": (
                        "Search the web using Tavily. Returns top results with "
                        "titles, URLs, and extracted page content."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"}
                        },
                        "required": ["query"],
                    },
                },
            }
        ]

    def execute(self, tool_name: str, args: dict) -> str:
        if tool_name == "web_search":
            return self._search(args["query"])
        raise ValueError(f"Unknown tool: {tool_name}")

    def _search(self, query: str) -> str:
        try:
            response = self.client.search(
                query=query,
                search_depth=self.search_depth,
                max_results=self.max_results,
            )
            return self._format_results(response.get("results", []))
        except Exception as e:
            return f"Error: Tavily search failed — {e}"

    def _format_results(self, results: list[dict]) -> str:
        if not results:
            return "No results found."
        sep = "-" * 100
        lines = []
        for result in results:
            lines.append(sep)
            lines.append(f"# TITLE: {result.get('title', '')}")
            lines.append(f"# URL: {result.get('url', '')}")
            lines.append(f"# CONTENT: {result.get('content', '')}")
            lines.append(sep)
        return "\n".join(lines)
