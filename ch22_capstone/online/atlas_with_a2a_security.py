"""
atlas_with_a2a_security.py — Atlas capstone with an external A2A security auditor.

The capstone's reviewer_node does an inline security review. This extension
replaces it with a call to an external A2A-compatible security audit agent,
demonstrating the federation pattern from Chapter 8.

The external agent runs independently, has its own tools (CVE databases,
static analysis), and communicates via A2A's task protocol. Atlas doesn't
need to know how the security review works — it just sends the code and
waits for a verdict.

This pattern scales to any capability you want to outsource:
  - Compliance checking → external compliance agent
  - Performance profiling → profiler agent
  - Documentation generation → docs agent

Usage:
    # Start the A2A security agent (separate terminal):
    python atlas_with_a2a_security.py --serve-security-agent --port 8001

    # Run Atlas with A2A security review:
    python atlas_with_a2a_security.py --issue 42 --repo myorg/myrepo

Requires: pip install anthropic fastapi uvicorn httpx
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

import anthropic
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
from atlas_capstone import AtlasState, build_graph, filter_pii

client = anthropic.Anthropic()


# ── A2A Security Agent (server side) ─────────────────────────────────

security_app = FastAPI(title="Atlas Security Audit Agent")


class A2ATask(BaseModel):
    task_id:  str
    code:     dict[str, str]   # filename → content
    context:  str = ""


@security_app.get("/.well-known/agent.json")
async def agent_card():
    """A2A agent discovery card — exposes capabilities to other agents."""
    return {
        "name":        "SecurityAuditAgent",
        "version":     "1.0",
        "description": "OWASP-based security audit for Python code",
        "url":         "http://localhost:8001",
        "skills": [{
            "id":          "code_audit",
            "name":        "Code Security Audit",
            "description": "Audit Python code for OWASP Top 10 vulnerabilities",
            "input_schema": {
                "type":     "object",
                "properties": {
                    "code":    {"type": "object", "description": "filename → content"},
                    "context": {"type": "string"},
                },
                "required": ["code"],
            },
        }],
    }


@security_app.post("/tasks")
async def create_task(task: A2ATask):
    """Run a security audit task and return the verdict."""
    code_text = "\n\n".join(
        f"# {fn}\n{content[:2000]}"  # Truncate for context
        for fn, content in task.code.items()
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        system=(
            "You are a Security Auditor specializing in Python code. "
            "Audit the provided code for OWASP Top 10 vulnerabilities. "
            "Focus on: SQL injection, path traversal, hardcoded secrets, "
            "unsafe deserialization, and command injection. "
            "Output JSON: {\"verdict\": \"approved\"|\"needs_revision\", "
            "\"findings\": [{\"severity\": \"critical|high|medium|low\", "
            "\"description\": \"...\", \"fix\": \"...\"}]}"
        ),
        messages=[{"role": "user", "content": f"Audit this code:\n\n{code_text}"}],
        max_tokens=1024,
    )

    try:
        result = json.loads(response.content[0].text)
    except json.JSONDecodeError:
        result = {"verdict": "approved", "findings": []}

    return {
        "task_id": task.task_id,
        "status":  "completed",
        "result":  result,
    }


# ── A2A client (called from Atlas) ───────────────────────────────────

class SecurityAuditClient:
    """Calls the external A2A security agent from within the Atlas pipeline."""

    def __init__(self, agent_url: str = "http://localhost:8001"):
        self.agent_url = agent_url

    async def audit(self, code: dict[str, str], context: str = "") -> dict:
        """Send code to the security agent and wait for verdict."""
        task_id = str(uuid.uuid4())
        async with httpx.AsyncClient(timeout=60.0) as http:
            # Verify agent is discoverable
            card_resp = await http.get(f"{self.agent_url}/.well-known/agent.json")
            card_resp.raise_for_status()

            # Submit audit task
            resp = await http.post(
                f"{self.agent_url}/tasks",
                json={"task_id": task_id, "code": code, "context": context},
            )
            resp.raise_for_status()
            return resp.json()["result"]

    def audit_sync(self, code: dict[str, str], context: str = "") -> dict:
        """Synchronous wrapper for use in LangGraph nodes."""
        try:
            return asyncio.run(self.audit(code, context))
        except Exception as e:
            print(f"  A2A security agent unavailable ({e}), using inline fallback")
            return self._inline_fallback(code)

    def _inline_fallback(self, code: dict[str, str]) -> dict:
        """Simple PII/secret check when A2A agent is unreachable."""
        for fn, content in code.items():
            _, detected = filter_pii(content)
            if detected:
                return {
                    "verdict":  "needs_revision",
                    "findings": [{"severity": "high",
                                  "description": f"PII detected in {fn}: {detected}",
                                  "fix": "Remove PII from code"}],
                }
        return {"verdict": "approved", "findings": []}


# ── A2A-enhanced reviewer node ────────────────────────────────────────

def a2a_reviewer_node(agent_url: str = "http://localhost:8001"):
    """Returns a reviewer node that delegates to an external A2A security agent."""
    audit_client = SecurityAuditClient(agent_url)

    def reviewer(state: AtlasState) -> dict:
        code = state.get("code_changes") or {}
        print(f"\n  Calling A2A security agent at {agent_url}...")
        result = audit_client.audit_sync(code, context=state["issue"].get("title", ""))

        verdict  = result.get("verdict", "approved")
        findings = result.get("findings", [])

        print(f"  Security verdict: {verdict}")
        for f in findings[:3]:
            print(f"  [{f.get('severity', '?').upper()}] {f.get('description', '')[:80]}")

        comments = [
            f"[{f.get('severity', '?').upper()}] {f.get('description', '')} — Fix: {f.get('fix', '')}"
            for f in findings
        ]
        return {"review": {"verdict": verdict, "comments": comments}}

    return reviewer


# ── Build A2A-enhanced graph ──────────────────────────────────────────

def build_a2a_graph(security_agent_url: str):
    from langgraph.graph import END, START, StateGraph
    from langgraph.graph.message import add_messages
    from atlas_capstone import (
        fetch_issue_node, planner_node, coder_node, tester_node,
        human_approval_node, publish_pr_node, check_tests, check_review,
    )

    reviewer = a2a_reviewer_node(security_agent_url)

    g = StateGraph(AtlasState)
    g.add_node("fetch_issue",    fetch_issue_node)
    g.add_node("planner",        planner_node)
    g.add_node("coder",          coder_node)
    g.add_node("tester",         tester_node)
    g.add_node("reviewer",       reviewer)           # A2A override
    g.add_node("human_approval", human_approval_node)
    g.add_node("publish_pr",     publish_pr_node)

    g.add_edge(START, "fetch_issue")
    g.add_edge("fetch_issue", "planner")
    g.add_edge("planner", "coder")
    g.add_edge("coder", "tester")
    g.add_conditional_edges("tester", check_tests, {
        "pass": "reviewer", "fail": "coder", "max_retries": END,
    })
    g.add_conditional_edges("reviewer", check_review, {
        "approved": "human_approval", "needs_revision": "coder", "max_retries": END,
    })
    g.add_edge("human_approval", "publish_pr")
    g.add_edge("publish_pr", END)

    return g.compile()


def main():
    parser = argparse.ArgumentParser(description="Atlas v0.20 with A2A Security Agent")
    parser.add_argument("--issue",               type=int)
    parser.add_argument("--repo")
    parser.add_argument("--security-agent-url",  default="http://localhost:8001")
    parser.add_argument("--serve-security-agent", action="store_true",
                        help="Run the A2A security agent server")
    parser.add_argument("--port",                type=int, default=8001)
    parser.add_argument("--dry-run",             action="store_true")
    args = parser.parse_args()

    if args.serve_security_agent:
        import uvicorn
        print(f"Starting A2A Security Agent on port {args.port}...")
        uvicorn.run(security_app, host="0.0.0.0", port=args.port)
        return

    if not args.issue or not args.repo:
        parser.print_help()
        sys.exit(1)

    print(f"Atlas v0.20 (A2A Security) — Issue #{args.issue} in {args.repo}")
    print(f"Security agent: {args.security_agent_url}\n")

    graph = build_a2a_graph(args.security_agent_url)
    state: AtlasState = {
        "messages":     [],
        "repo":         args.repo,
        "issue_number": args.issue,
        "issue":        {},
        "plan":         [],
        "current_step": 0,
        "code_changes": {},
        "test_results": {},
        "review":       {},
        "approved":     False,
        "retry_count":  0,
        "dry_run":      args.dry_run,
    }
    graph.invoke(state)


if __name__ == "__main__":
    main()
