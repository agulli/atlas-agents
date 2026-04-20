"""
Atlas v0.1 — A Raw ReAct Agent from Scratch
============================================
Chapter 1 Project: No frameworks, just Python and an LLM.

This agent:
  1. Takes a research question as input
  2. Searches the web using DuckDuckGo
  3. Reads web pages
  4. Synthesizes a structured answer

Usage:
    python atlas_v01.py "What are the key differences between LangGraph and CrewAI?"
"""

import json
import re
import sys
from urllib.request import urlopen, Request
from urllib.parse import quote_plus
from html.parser import HTMLParser

from openai import OpenAI

# ── Configuration ────────────────────────────────────────────────────
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.config import require_key, OPENAI_MODEL

client = OpenAI(api_key=require_key("openai"))
MAX_ITERATIONS = 6


# ── Tool Implementations ────────────────────────────────────────────

class _HTMLTextExtractor(HTMLParser):
    """Simple HTML-to-text converter."""
    def __init__(self):
        super().__init__()
        self._text = []
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


def search_web(query: str) -> str:
    """Search DuckDuckGo and return top results as text."""
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Atlas Agent)"})
        with urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Extract result snippets
        results = []
        for match in re.finditer(
            r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'<a class="result__snippet"[^>]*>(.*?)</a>',
            html, re.DOTALL
        ):
            href, title, snippet = match.groups()
            title = re.sub(r"<[^>]+>", "", title).strip()
            snippet = re.sub(r"<[^>]+>", "", snippet).strip()
            if title:
                results.append(f"- [{title}]({href})\n  {snippet}")
            if len(results) >= 5:
                break

        if not results:
            return "No results found."
        return f"Search results for '{query}':\n\n" + "\n\n".join(results)
    except Exception as e:
        return f"Search failed: {e}"


def read_url(url: str) -> str:
    """Read a web page and return its text content (truncated to 3000 chars)."""
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Atlas Agent)"})
        with urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        extractor = _HTMLTextExtractor()
        extractor.feed(html)
        text = extractor.get_text()

        # Truncate to avoid context window overflow
        if len(text) > 3000:
            text = text[:3000] + "\n\n[...truncated]"
        return text if text else "Could not extract text from this page."
    except Exception as e:
        return f"Failed to read URL: {e}"


# ── Tool Registry ────────────────────────────────────────────────────

TOOLS = {
    "search_web": search_web,
    "read_url": read_url,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web using DuckDuckGo. Returns top 5 results with titles and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_url",
            "description": "Read the text content of a web page. Returns up to 3000 characters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to read"
                    }
                },
                "required": ["url"]
            }
        }
    },
]


# ── System Prompt ────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Atlas, a research assistant.

You answer questions by searching the web and reading pages.
For each step, think carefully about what information you need next.

RULES:
- Always search before answering — don't rely on your training data alone.
- Read at least one source to verify your answer.
- Use at most 5 tool calls.
- If you can't find a reliable answer, say so honestly.
- Provide your final answer in a clear, structured format.
- Cite your sources with URLs.
"""


# ── The ReAct Loop ───────────────────────────────────────────────────

def run_atlas(question: str) -> str:
    """Run the Atlas ReAct agent on a question and return the final answer."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    for iteration in range(MAX_ITERATIONS):
        print(f"\n── Iteration {iteration + 1} ──")

        # Call the LLM
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
        )

        msg = response.choices[0].message
        messages.append(msg)

        # If no tool calls, we have a final answer
        if not msg.tool_calls:
            print(f"✅ Final answer received.")
            return msg.content

        # Execute each tool call
        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)

            print(f"🔧 Calling: {fn_name}({fn_args})")

            # Execute the tool
            if fn_name in TOOLS:
                result = TOOLS[fn_name](**fn_args)
            else:
                result = f"Error: Unknown tool '{fn_name}'"

            # Show a preview of the result
            preview = result[:200] + "..." if len(result) > 200 else result
            print(f"📋 Result: {preview}")

            # Feed the result back to the LLM
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    return "Agent reached maximum iterations without a final answer."


# ── CLI Entrypoint ───────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python atlas_v01.py \"Your research question here\"")
        print("Example: python atlas_v01.py \"What is the Model Context Protocol?\"")
        sys.exit(1)

    question = " ".join(sys.argv[1:])
    print(f"🔍 Atlas v0.1 — Research Question: {question}\n")

    answer = run_atlas(question)
    print(f"\n{'='*60}")
    print(f"FINAL ANSWER:\n{'='*60}")
    print(answer)
