"""
Hierarchical Crew (Online Extra)
===================================
A Technical Lead manager agent dynamically assigns coding and QA tasks
and can send work back for revision multiple times.

Usage:
    python hierarchical_crew.py

Requires: pip install crewai
"""

import sys
from pathlib import Path

from crewai import Agent, Task, Crew, Process, LLM

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import LITELLM_MODEL  # also loads .env

# CrewAI routes through LiteLLM: "openai/gpt-4o" in the cloud, "ollama_chat/<model>" locally.
llm = LLM(model=LITELLM_MODEL)


# ── Agents ───────────────────────────────────────────────────────────

senior_dev = Agent(
    role="Senior Software Developer",
    goal="Write clean, production-ready code for the feature described",
    backstory="You are a 10-year veteran who writes idiomatic Python with full type hints and docstrings.",
    verbose=True,
    allow_delegation=False,
    llm=llm,
)

qa_engineer = Agent(
    role="QA Engineer",
    goal="Write comprehensive tests and verify code correctness",
    backstory="You are obsessive about edge cases and writing tests that catch real bugs.",
    verbose=True,
    allow_delegation=False,
    llm=llm,
)

technical_lead = Agent(
    role="Technical Lead",
    goal="Coordinate the dev and QA process, ensure quality standards are met",
    backstory="You are the team lead who reviews all work. You send code back for revision if it doesn't meet your standards.",
    verbose=True,
    allow_delegation=True,
    llm=llm,
)

# ── Tasks ────────────────────────────────────────────────────────────

code_task = Task(
    description="Implement a Python function that validates email addresses using regex. Include edge cases like subdomains and plus addressing.",
    expected_output="A complete Python module with the validation function.",
    agent=senior_dev,
)

test_task = Task(
    description="Write pytest tests for the email validation function. Cover valid emails, invalid emails, and edge cases.",
    expected_output="A pytest test file with at least 10 test cases.",
    agent=qa_engineer,
    context=[code_task],
)

# ── Hierarchical Crew ───────────────────────────────────────────────
# The tech lead reviews QA's report and may send work back to the dev.

crew = Crew(
    agents=[senior_dev, qa_engineer],
    tasks=[code_task, test_task],
    process=Process.hierarchical,
    manager_agent=technical_lead,
    verbose=True,
)

if __name__ == "__main__":
    print("👔 Hierarchical Crew Demo\n")
    result = crew.kickoff()
    print(f"\n{'='*60}")
    print("FINAL OUTPUT:")
    print(f"{'='*60}")
    print(result.raw)