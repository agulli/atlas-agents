"""
Debate with Jury (Online Extra)
=================================
Two agents argue opposing sides. A hierarchical manager agent
acts as the jury, synthesizing the best answer from both perspectives.

Usage:
    python debate_with_jury.py

Requires: pip install crewai
"""

import sys
from pathlib import Path

from crewai import Agent, Task, Crew, Process, LLM

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import LITELLM_MODEL  # also loads .env

# CrewAI routes through LiteLLM: "openai/gpt-4o" in the cloud, "ollama_chat/<model>" locally.
llm = LLM(model=LITELLM_MODEL)


# ── Debaters ─────────────────────────────────────────────────────────

researcher_pro = Agent(
    role="Advocate",
    goal="Build the strongest possible case IN FAVOR of {topic}",
    backstory="You are a persuasive debater who finds the best evidence supporting a position.",
    verbose=True,
    allow_delegation=False,
    llm=llm,
)

researcher_con = Agent(
    role="Critic",
    goal="Build the strongest possible case AGAINST {topic}",
    backstory="You are a rigorous skeptic who identifies risks, flaws, and counterarguments.",
    verbose=True,
    allow_delegation=False,
    llm=llm,
)

# ── Debate Tasks ─────────────────────────────────────────────────────

debate_task_pro = Task(
    description="Present 3 strong arguments IN FAVOR of: {topic}. Support each with evidence.",
    expected_output="3 well-supported arguments for the position.",
    agent=researcher_pro,
)

debate_task_con = Task(
    description="Present 3 strong arguments AGAINST: {topic}. Identify risks and counterpoints.",
    expected_output="3 well-supported arguments against the position.",
    agent=researcher_con,
)

# ── Crew with Hierarchical Manager ───────────────────────────────────
# Process.hierarchical automatically creates a manager agent that:
# 1. Delegates tasks to sub-agents
# 2. Reviews their outputs
# 3. Synthesizes a balanced verdict

crew = Crew(
    agents=[researcher_pro, researcher_con],
    tasks=[debate_task_pro, debate_task_con],
    process=Process.hierarchical,
    manager_llm=llm,  # The judge model
    verbose=True,
)

if __name__ == "__main__":
    topic = "Using AI agents in production without human oversight"
    print(f"⚖️ Debate: {topic}\n")
    result = crew.kickoff(inputs={"topic": topic})
    print(f"\n{'='*60}")
    print("JURY VERDICT:")
    print(f"{'='*60}")
    print(result.raw)