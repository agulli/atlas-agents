"""
Atlas v0.5 — Self-Correcting Code Review Agent (LangGraph)
============================================================
Chapter 5 Project: Graph-based code review with retry and human approval.

Usage:
    python code_review_agent.py

Requires: pip install langgraph langchain-openai
"""

import json
import sys
from typing import Annotated, TypedDict, Literal
from pathlib import Path

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.config import require_key, OPENAI_MODEL, OPENAI_BASE_URL
from shared.llm_utils import parse_json

require_key("openai")
# base_url is empty for OpenAI's cloud, or http://localhost:11434/v1 for Ollama.
llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0, base_url=OPENAI_BASE_URL or None)


# ── State ────────────────────────────────────────────────────────────

class ReviewState(TypedDict):
    messages: Annotated[list, add_messages]
    pr_diff: str
    review_comments: list[str]
    quality_score: int
    retry_count: int
    approved: bool


# ── Nodes ────────────────────────────────────────────────────────────

def fetch_pr(state: ReviewState) -> dict:
    """Fetch PR diff (simulated)."""
    sample_diff = '''
--- a/utils/auth.py
+++ b/utils/auth.py
@@ -15,6 +15,12 @@ class AuthManager:
     def validate_token(self, token: str) -> bool:
-        return token == self.secret_key
+        if not token:
+            return False
+        try:
+            decoded = jwt.decode(token, self.secret_key, algorithms=["HS256"])
+            return decoded.get("exp", 0) > time.time()
+        except jwt.InvalidTokenError:
+            return False
'''
    return {
        "pr_diff": sample_diff,
        "messages": [{"role": "system", "content": f"PR diff loaded:\n{sample_diff}"}],
    }


def analyze(state: ReviewState) -> dict:
    """Analyze the PR diff and generate review comments."""
    response = llm.invoke([
        {"role": "system", "content": """You are a senior code reviewer.
        Analyze this PR diff and provide review comments.
        Focus on: security, correctness, edge cases, code style.
        Format each comment as a JSON array of strings."""},
        {"role": "user", "content": f"Review this diff:\n{state['pr_diff']}"}
    ])
    try:
        comments = parse_json(response.content)
    except json.JSONDecodeError:
        comments = [response.content]

    return {"review_comments": comments, "messages": [response]}


def self_check(state: ReviewState) -> dict:
    """Self-review: score the quality of our own review."""
    comments = state["review_comments"]
    response = llm.invoke([
        {"role": "system", "content": """Rate the quality of these code review comments.
        Score from 1-10. Consider: specificity, actionability, completeness.
        Respond with ONLY a JSON: {"score": N, "reason": "..."}"""},
        {"role": "user", "content": f"Review comments:\n{json.dumps(comments)}"}
    ])
    try:
        result = parse_json(response.content)
        score = result.get("score", 5)
    except (json.JSONDecodeError, AttributeError):
        score = 5

    return {
        "quality_score": score,
        "retry_count": state.get("retry_count", 0) + (1 if score < 7 else 0),
        "messages": [response],
    }


def human_gate(state: ReviewState) -> dict:
    """Human reviews and approves the comments."""
    print("\n" + "=" * 50)
    print("HUMAN REVIEW REQUIRED")
    print("=" * 50)
    print(f"\nQuality Score: {state['quality_score']}/10")
    print(f"Review Comments:")
    for i, comment in enumerate(state["review_comments"], 1):
        print(f"  {i}. {comment}")
    print()
    return {"approved": True}


def post_review(state: ReviewState) -> dict:
    """Post the review comments to the PR."""
    print("\n✅ Review posted to PR!")
    for comment in state["review_comments"]:
        print(f"  💬 {comment}")
    return {"messages": [{"role": "assistant", "content": "Review posted."}]}


# ── Routing ──────────────────────────────────────────────────────────

def should_retry(state: ReviewState) -> Literal["retry", "approve", "give_up"]:
    if state["quality_score"] >= 7:
        return "approve"
    if state["retry_count"] >= 2:
        return "give_up"
    return "retry"


# ── Build Graph ──────────────────────────────────────────────────────

def build_review_graph():
    graph = StateGraph(ReviewState)

    graph.add_node("fetch_pr", fetch_pr)
    graph.add_node("analyze", analyze)
    graph.add_node("self_check", self_check)
    graph.add_node("human_gate", human_gate)
    graph.add_node("post_review", post_review)

    graph.add_edge(START, "fetch_pr")
    graph.add_edge("fetch_pr", "analyze")
    graph.add_edge("analyze", "self_check")

    graph.add_conditional_edges("self_check", should_retry, {
        "retry": "analyze",
        "approve": "human_gate",
        "give_up": "human_gate",
    })

    graph.add_edge("human_gate", "post_review")
    graph.add_edge("post_review", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🔍 Atlas v0.5 — Self-Correcting Code Review Agent\n")

    app = build_review_graph()

    config = {"configurable": {"thread_id": "review-001"}}
    initial_state = {
        "messages": [],
        "pr_diff": "",
        "review_comments": [],
        "quality_score": 0,
        "retry_count": 0,
        "approved": False,
    }

    result = app.invoke(initial_state, config=config)

    print(f"\n📊 Final quality score: {result['quality_score']}/10")
    print(f"🔄 Retries needed: {result['retry_count']}")
