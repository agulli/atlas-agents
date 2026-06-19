"""
Atlas v0.6 — Automated Newsletter Crew (CrewAI)
=================================================
Chapter 6 Project: Four-agent crew that produces a newsletter.

Usage:
    python newsletter_crew.py "AI agent frameworks in 2025"

Requires: pip install crewai crewai-tools
"""

import sys
from pathlib import Path
from crewai import Agent, Task, Crew, Process

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.config import require_key
from shared.skills import WebSearchSkill

# ── Tools ────────────────────────────────────────────────────────────

web_skill = WebSearchSkill(api_key=require_key("tavily"))

def search_tool(query: str) -> str:
    """Search the web for {query}."""
    return web_skill.execute("web_search", {"query": query})

def read_tool(url: str) -> str:
    """Read the text content of a web page at {url}."""
    return web_skill.execute("web_read_page", {"url": url})


# ── Agents ───────────────────────────────────────────────────────────

researcher = Agent(
    role="Senior Research Analyst",
    goal="Find comprehensive, up-to-date information on {topic}",
    backstory="""You are a veteran research analyst with 15 years of experience
    in technology reporting. You are meticulous about source quality and always
    cross-reference findings across at least 3 independent sources.
    You never accept a single source as truth.""",
    verbose=True,
    allow_delegation=False,
    tools=[search_tool, read_tool],
)

writer = Agent(
    role="Tech Content Writer",
    goal="Write an engaging, well-structured newsletter about {topic}",
    backstory="""You are a tech writer known for making complex topics
    accessible. You write in a conversational but authoritative tone.
    Your articles consistently get high engagement on social media.
    You structure articles as: Hook → Key Points → Analysis → Takeaway.""",
    verbose=True,
    allow_delegation=False,
)

critic = Agent(
    role="Editorial Critic",
    goal="Ensure the newsletter meets publication quality standards",
    backstory="""You are a strict editor with impossibly high standards.
    You check for factual accuracy, clarity, logical flow, and engagement.
    You give specific, actionable feedback — never vague comments like
    'make it better'. You score articles on a 1-10 scale.""",
    verbose=True,
    allow_delegation=False,
)

publisher = Agent(
    role="Publication Manager",
    goal="Format and finalize the newsletter for distribution",
    backstory="""You handle the final mile: compelling subject lines,
    TL;DR sections, clean formatting, and source attribution.
    You ensure every newsletter looks professional and is ready to send.""",
    verbose=True,
    allow_delegation=False,
)


# ── Tasks ────────────────────────────────────────────────────────────

research_task = Task(
    description="""Research the topic: {topic}

    Your deliverables:
    1. Find at least 3 high-quality sources (blogs, papers, official docs)
    2. Summarize key points from each source
    3. Identify 2-3 notable trends or insights
    4. Include relevant quotes if available
    5. Note any conflicting information between sources

    Output a structured research brief.""",
    expected_output="A structured research brief with sources, key points, trends, and quotes.",
    agent=researcher,
)

writing_task = Task(
    description="""Write a newsletter article based on the research brief.

    Structure:
    1. **Hook** — An opening that grabs attention (question, stat, or bold claim)
    2. **Key Points** — 3-5 main findings, each with supporting evidence
    3. **Analysis** — Your synthesis: what does this mean for the reader?
    4. **Takeaway** — One clear action item or insight to remember

    Requirements:
    - Length: 600-800 words
    - Tone: Conversational but authoritative
    - Include at least 2 source citations (inline)
    - No jargon without explanation""",
    expected_output="A complete newsletter article in markdown, 600-800 words.",
    agent=writer,
    context=[research_task],
)

critique_task = Task(
    description="""Review the newsletter article for quality.

    Evaluate on these dimensions (score each 1-10):
    1. **Factual accuracy** — Cross-reference claims with the research brief
    2. **Clarity** — Is every paragraph clear on first read?
    3. **Engagement** — Would a reader share this? Is the hook compelling?
    4. **Structure** — Does it follow Hook → Points → Analysis → Takeaway?
    5. **Source citations** — Are sources properly attributed?

    Overall score = average of the 5 dimensions.
    If overall >= 7: APPROVE for publication.
    If overall < 7: Provide specific revision notes.""",
    expected_output="A quality review with dimensional scores and specific feedback.",
    agent=critic,
    context=[research_task, writing_task],
)

publish_task = Task(
    description="""Prepare the final newsletter for distribution.

    1. Add a compelling subject line (max 60 chars)
    2. Add a TL;DR section at the top (3 bullet points max)
    3. Clean up markdown formatting
    4. Add a "Sources" section at the bottom with numbered references
    5. Add a sign-off: "— The Atlas Newsletter Team"

    Output the publication-ready newsletter.""",
    expected_output="A publication-ready newsletter with subject line, TL;DR, and clean formatting.",
    agent=publisher,
    context=[writing_task, critique_task],
)


# ── Crew ─────────────────────────────────────────────────────────────

newsletter_crew = Crew(
    agents=[researcher, writer, critic, publisher],
    tasks=[research_task, writing_task, critique_task, publish_task],
    process=Process.sequential,
    verbose=True,
)


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        topic = "The rise of AI agent frameworks in 2025"
    else:
        topic = " ".join(sys.argv[1:])

    print(f"📰 Atlas v0.6 — Newsletter Crew")
    print(f"📝 Topic: {topic}\n")

    result = newsletter_crew.kickoff(inputs={"topic": topic})

    print("\n" + "=" * 60)
    print("FINAL NEWSLETTER")
    print("=" * 60)
    print(result.raw)

    # Save to file
    output_path = Path(__file__).parent / "output" / "newsletter.md"
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(result.raw, encoding="utf-8")
    print(f"\n💾 Saved to {output_path}")
