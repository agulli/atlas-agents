# Chapter 6 — Multi-Agent Collaboration (CrewAI)

> **Atlas v0.6** — a four-agent **crew** (Researcher → Writer → Critic → Publisher) that produces a newsletter.

## TL;DR

Some work suits a *team* better than a single agent. **CrewAI** models each agent with a **role**, **goal**, and **backstory**, gives each a **Task** with an expected output, and runs them as a **process** (sequential or hierarchical). Tasks pass results forward through `context=[...]`. A **critic** agent adds a quality gate without any extra plumbing.

```
Researcher ──brief──▶ Writer ──draft──▶ Critic ──scores/notes──▶ Publisher ──▶ output/newsletter.md
  (tools: search, read)                  (≥ 7/10 = approve)
```

## Key concepts

| Concept | What it means | Where to see it |
|---|---|---|
| **Role / goal / backstory** | A persona that shapes each agent's behavior. The backstory works as a system prompt. | `researcher`, `writer`, `critic`, `publisher` |
| **Task** | `description` + `expected_output` + an assigned agent. The expected output acts as a spec. | `research_task`, … |
| **Task context** | `context=[research_task]` feeds earlier outputs into later tasks. | `writing_task`, `critique_task` |
| **Sequential process** | Tasks run in order, like an assembly line. | `Process.sequential` |
| **Hierarchical process** | A manager agent assigns work and can send it back for revision. | `online/hierarchical_crew.py` |
| **Debate + jury** | Two agents argue opposite sides and a manager combines the strongest points. Reduces one-sided answers. | `online/debate_with_jury.py` |
| **Crew memory** | Vector memory so agents remember across tasks and runs. | `online/crew_with_memory.py` |
| **Tool reuse** | Crew tools wrap `shared.skills.WebSkill` from Ch. 3. | `search_tool`, `read_tool` |

## Files

| File | What it shows |
|---|---|
| `newsletter_crew.py` | The chapter project: sequential 4-agent crew. Writes `output/newsletter.md`. |
| `online/hierarchical_crew.py` | A Tech Lead manager assigns coding and QA tasks and sends work back for revision. |
| `online/debate_with_jury.py` | Adversarial debate with a jury that synthesizes the answer. |
| `online/crew_with_memory.py` | Turning on CrewAI memory. |

## What needs to be done

- [ ] `pip install crewai crewai-tools` and set `OPENAI_API_KEY`.
- [ ] Run the crew on a topic you know and judge whether the Critic caught real problems.
- [ ] Change the critic's approval bar or scoring dimensions and compare the outputs.
- [ ] Switch to a hierarchical process and compare cost (token usage) with sequential.
- [ ] Try the debate pattern on a contested technical question ("monolith vs. microservices").

## Run it

```bash
cd ch06_multi_agent
python newsletter_crew.py "AI agent frameworks in 2025"
python online/hierarchical_crew.py
python online/debate_with_jury.py
```

## Run with Gemma 4 on Ollama

> **One-time setup:** follow *Run everything locally with Gemma 4 on Ollama* in the [root README](../README.md): Ollama running, `gemma4-longctx` created, `.env` set to Option B. Run every command below from the **repo root**.

**Status: ✅ Works, slowly.** Every agent gets `llm=LLM(model=LITELLM_MODEL)`. With `LITELLM_MODEL=ollama_chat/gemma4-longctx`, CrewAI goes through LiteLLM to Ollama's native chat API.

### Setup

`.env` keys: `LITELLM_MODEL=ollama_chat/gemma4-longctx`, plus `EMBED_MODEL=embeddinggemma` for `crew_with_memory.py`. Its embedder switches to Ollama automatically when the `.env` points at localhost.

```bash
ollama pull embeddinggemma
pip install crewai crewai-tools python-dotenv
```

### Commands

```bash
python ch06_multi_agent/newsletter_crew.py "AI agent frameworks in 2026"   # writes ch06_multi_agent/output/newsletter.md
python ch06_multi_agent/online/debate_with_jury.py
python ch06_multi_agent/online/hierarchical_crew.py
python ch06_multi_agent/online/crew_with_memory.py
```

### What to expect on Gemma 4

- A 4-agent sequential crew makes many LLM calls, each with long backstories and task context. On a 12B model, expect **several minutes** per run. That makes the "every agent adds cost and latency" point concrete.
- **Hierarchical** crews (`debate_with_jury`, `hierarchical_crew`) need the manager to delegate through tool calls, and that's where small models struggle most. If the manager loops or answers without delegating, cap it with `max_iter=3` on the manager agent, or try `gemma4:26b`.
- The newsletter Researcher's web tools need internet access.

### Troubleshooting

- **`LLM Provider NOT provided`**: `LITELLM_MODEL` is missing the `ollama_chat/` prefix.
- **Memory demo asks for an OpenAI key**: `.env` doesn't point at localhost, so the embedder stayed on OpenAI. Check `OPENAI_BASE_URL`.

## Production notes

- Every added agent adds cost and latency. Use multiple agents only when roles really differ.
- Critics that never reject anything are useless (Ch. 21 comes back to this with "rubber-stamp" detection).
- Hierarchical crews can loop. Cap revisions.

## Takeaways

1. Split work by **role**, and give each role one clear deliverable.
2. Critic and debate patterns improve quality through structured disagreement.
3. Sequential is predictable. Hierarchical is flexible but costs more.

**Prev:** [Ch. 5](../ch05_state_graphs/README.md) · **Next:** [Chapter 7 — One Agent, Many Models](../ch07_model_portability/README.md)
