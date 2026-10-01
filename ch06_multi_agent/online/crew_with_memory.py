"""
CrewAI with Memory (Online Extra)
====================================
Demonstrates enabling vector-based memory in CrewAI so agents
remember context across tasks and crew runs.

Usage (conceptual — requires CrewAI with agents defined):
    python crew_with_memory.py

Requires: pip install crewai
"""

import sys
from pathlib import Path

from crewai import Crew, Agent, Task, Process, LLM

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import LITELLM_MODEL, EMBED_MODEL, is_local  # also loads .env

# CrewAI routes through LiteLLM: "openai/gpt-4o" in the cloud, "ollama_chat/<model>" locally.
llm = LLM(model=LITELLM_MODEL)


# ── Agents ───────────────────────────────────────────────────────────

research_agent = Agent(
    role="Research Analyst",
    goal="Find comprehensive information on the given topic",
    backstory="You are a meticulous researcher who cross-references sources.",
    verbose=True,
    allow_delegation=False,
    llm=llm,
)

writer_agent = Agent(
    role="Content Writer",
    goal="Write engaging content based on research findings",
    backstory="You turn complex research into clear, engaging prose.",
    verbose=True,
    allow_delegation=False,
    llm=llm,
)

# ── Tasks ────────────────────────────────────────────────────────────

research_task = Task(
    description="Research the topic: {topic}. Find key facts and trends.",
    expected_output="A research brief with 3-5 key findings.",
    agent=research_agent,
)

writing_task = Task(
    description="Write a 300-word summary based on the research brief.",
    expected_output="A polished summary article.",
    agent=writer_agent,
    context=[research_task],
)

# ── Crew with Memory ────────────────────────────────────────────────
# Enabling memory=True connects CrewAI to a local vector store.
# Agents can recall facts from previous tasks and crew runs.
# This is powered by ChromaDB under the hood.

crew = Crew(
    agents=[research_agent, writer_agent],
    tasks=[research_task, writing_task],
    process=Process.sequential,
    memory=True,  # Enables short-term, long-term, and entity memory
    embedder={
        "provider": "ollama" if is_local() else "openai",
        "config": {"model": EMBED_MODEL},
    },
    verbose=True,
)

if __name__ == "__main__":
    print("🧠 CrewAI with Memory Demo\n")
    result = crew.kickoff(inputs={"topic": "AI agent memory architectures"})
    print(f"\n{'='*50}")
    print(result.raw)