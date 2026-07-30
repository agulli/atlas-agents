"""
Atlas v0.8 — MCP Knowledge Server + A2A Federation
=====================================================
Chapter 8 Project: MCP server exposing a SQLite knowledge base,
plus A2A Agent Card for cross-agent collaboration.

Usage:
    # Start the MCP server:
    python mcp_knowledge_server.py

    # Test the client:
    python mcp_client.py

Requires: pip install mcp
"""

import sqlite3
import asyncio
import json
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, Resource

# ── Database Setup ───────────────────────────────────────────────────

DB_PATH = Path(__file__).parent / "knowledge.db"


def init_db():
    """Initialize the knowledge database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source_url TEXT DEFAULT ''
        )
    """)
    # Seed with sample data
    conn.execute("""
        INSERT OR IGNORE INTO knowledge (id, title, content, tags, source_url)
        VALUES
        (1, 'Model Context Protocol', 'MCP is an open standard created by Anthropic that standardizes how AI agents connect to tools and data sources. It defines a client-server architecture where MCP servers expose tools and resources.', 'protocol,mcp,tools', 'https://modelcontextprotocol.io'),
        (2, 'Agent-to-Agent Protocol', 'A2A is Googles protocol for agent interoperability. Agents publish Agent Cards describing their capabilities, and other agents can discover and delegate tasks to them.', 'protocol,a2a,google', 'https://google.github.io/a2a'),
        (3, 'LangGraph', 'LangGraph is a framework for building stateful agent graphs. Agents are modeled as directed graphs with nodes (actions), edges (transitions), and shared state.', 'framework,langgraph,graphs', 'https://langchain-ai.github.io/langgraph'),
        (4, 'CrewAI', 'CrewAI is a multi-agent framework using role-playing. Agents have roles, goals, and backstories. They collaborate in sequential, hierarchical, or parallel processes.', 'framework,crewai,multi-agent', 'https://crewai.com'),
        (5, 'E2B Sandboxes', 'E2B provides disposable cloud microVMs for safe code execution. Each sandbox is isolated with its own filesystem and network. Cold start is ~300ms.', 'sandbox,e2b,code-execution', 'https://e2b.dev')
    """)
    conn.commit()
    conn.close()


# ── MCP Server ───────────────────────────────────────────────────────

server = Server("atlas-knowledge")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="query_knowledge",
            description="Query the knowledge base using SQL. Only SELECT queries are allowed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "SQL SELECT query to execute against the knowledge table. Columns: id, title, content, tags, created_at, source_url"
                    }
                },
                "required": ["sql"]
            },
        ),
        Tool(
            name="search_knowledge",
            description="Search the knowledge base by keyword (searches title, content, and tags).",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keyword or phrase"
                    }
                },
                "required": ["query"]
            },
        ),
        Tool(
            name="add_knowledge",
            description="Add a new entry to the knowledge base.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Entry title"},
                    "content": {"type": "string", "description": "Entry content"},
                    "tags": {"type": "string", "description": "Comma-separated tags"},
                    "source_url": {"type": "string", "description": "Source URL (optional)"}
                },
                "required": ["title", "content"]
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    conn = sqlite3.connect(str(DB_PATH))

    try:
        if name == "query_knowledge":
            sql = arguments["sql"].strip()
            if not sql.upper().startswith("SELECT"):
                return [TextContent(type="text", text="Error: Only SELECT queries are allowed.")]
            cursor = conn.execute(sql)
            columns = [desc[0] for desc in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return [TextContent(type="text", text=json.dumps(rows, indent=2))]

        elif name == "search_knowledge":
            query = f"%{arguments['query']}%"
            cursor = conn.execute(
                "SELECT id, title, content, tags FROM knowledge WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?",
                (query, query, query)
            )
            columns = [desc[0] for desc in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            if not rows:
                return [TextContent(type="text", text="No results found.")]
            return [TextContent(type="text", text=json.dumps(rows, indent=2))]

        elif name == "add_knowledge":
            conn.execute(
                "INSERT INTO knowledge (title, content, tags, source_url) VALUES (?, ?, ?, ?)",
                (
                    arguments["title"],
                    arguments["content"],
                    arguments.get("tags", ""),
                    arguments.get("source_url", ""),
                )
            )
            conn.commit()
            return [TextContent(type="text", text=f"Added: '{arguments['title']}'")]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    finally:
        conn.close()


# ── A2A Agent Card ───────────────────────────────────────────────────

AGENT_CARD = {
    "name": "Atlas Knowledge Agent",
    "description": "A personal knowledge base agent that stores and retrieves information.",
    "url": "http://localhost:8001",
    "version": "0.8",
    "capabilities": {
        "streaming": False,
        "push_notifications": False,
    },
    "skills": [
        {
            "id": "knowledge_search",
            "name": "Knowledge Search",
            "description": "Search a personal knowledge base by keyword or SQL query.",
            "input_modes": ["text/plain"],
            "output_modes": ["application/json"],
        },
        {
            "id": "knowledge_add",
            "name": "Add Knowledge",
            "description": "Store new information in the knowledge base.",
            "input_modes": ["application/json"],
            "output_modes": ["application/json"],
        },
    ],
}


# ── Main ─────────────────────────────────────────────────────────────

async def main():
    init_db()
    print(f"🧠 Atlas Knowledge MCP Server starting...")
    print(f"📚 Database: {DB_PATH}")
    print(f"🔌 Transport: stdio\n")

    # Save the A2A agent card
    card_path = Path(__file__).parent / ".well-known" / "agent.json"
    card_path.parent.mkdir(exist_ok=True)
    card_path.write_text(json.dumps(AGENT_CARD, indent=2))
    print(f"🪪 Agent Card saved to {card_path}\n")

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
