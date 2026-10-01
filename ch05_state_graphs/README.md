# Chapter 5 — Stateful Agent Graphs (LangGraph)

> **Atlas v0.5** — a self-correcting code-review agent built as a **graph** with typed state, conditional retry edges, checkpoints, and a human approval gate.

## TL;DR

Loops and handoffs hide control flow inside prompts. **LangGraph** makes it explicit. **Nodes** are Python functions that read and update a shared **typed state**. **Edges** (fixed or conditional) decide what runs next. A **checkpointer** saves the state after each step, which gives you persistence, pause/resume for humans, and "time travel" debugging.

```
START ─▶ fetch_pr ─▶ analyze ─▶ self_check ──score ≥ 7──────────────▶ human_gate ─▶ post_review ─▶ END
                        ▲            │ score < 7 and retries < 2           ▲
                        └──"retry"───┘ retries ≥ 2 ──"give_up"─────────────┘
```

## Key concepts

| Concept | What it means | Where to see it |
|---|---|---|
| **State schema** | A `TypedDict` shared by every node (`pr_diff`, `review_comments`, `quality_score`, `retry_count`, `approved`). | `ReviewState` |
| **Reducers** | `Annotated[list, add_messages]` / `operator.add` define how updates *merge* instead of overwrite. | `ReviewState.messages`, `online/parallel_fanout.py` |
| **Nodes** | Functions `state → partial state update`. | `fetch_pr`, `analyze`, `self_check`, … |
| **Conditional edges** | A router function returns a label, and the label picks the next node. | `should_retry()` |
| **Self-correction** | The agent scores its own review (1–10) and retries below 7, up to 2 times. | `self_check` + `should_retry` |
| **Checkpointer** | `MemorySaver` saves state per `thread_id`. Swap it for Postgres/SQLite in production. | `build_review_graph()` |
| **Human-in-the-loop** | `interrupt_before=[node]` pauses the graph until a human resumes it. | `online/approval_gateway.py` |
| **Parallel fan-out** | Several nodes run at once and their results merge through a reducer. | `online/parallel_fanout.py` |
| **Time travel** | Read state history, go back to an old checkpoint, patch the state, and replay. | `online/time_travel_debug.py` |

## Files

| File | What it shows |
|---|---|
| `code_review_agent.py` | The chapter project: review graph with self-check retry and a human gate (uses a sample JWT diff). |
| `online/approval_gateway.py` | Pause before a deployment node and resume after approval. |
| `online/parallel_fanout.py` | Search Reddit, arXiv, and GitHub in parallel, then summarize. |
| `online/time_travel_debug.py` | Find the step that corrupted state and replay from before it. |

## What needs to be done

- [ ] `pip install langgraph langchain-openai` and set `OPENAI_API_KEY`.
- [ ] Run the review agent and watch the self-check score. Lower the threshold from 7 to 9 to force retries.
- [ ] Replace the simulated `fetch_pr` diff with a real diff from one of your repos.
- [ ] Run `approval_gateway.py` and follow how the graph pauses and resumes.
- [ ] Run `time_travel_debug.py` and find the step that corrupts the data.
- [ ] (Stretch) Swap `MemorySaver` for a SQLite/Postgres checkpointer.

## Run it

```bash
cd ch05_state_graphs
python code_review_agent.py
python online/approval_gateway.py
python online/parallel_fanout.py
python online/time_travel_debug.py
```

## Run with Gemma 4 on Ollama

> **One-time setup:** follow *Run everything locally with Gemma 4 on Ollama* in the [root README](../README.md): Ollama running, `gemma4-longctx` created, `.env` set to Option B. Run every command below from the **repo root**.

**Status: ✅ Works.** `ChatOpenAI` gets `base_url=OPENAI_BASE_URL` from `.env`. The three `online/` demos make no LLM calls.

### Setup

`.env` keys: `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL=gemma4-longctx`.

```bash
pip install langgraph langchain-openai python-dotenv
```

### Commands

```bash
python ch05_state_graphs/code_review_agent.py      # analyze → self_check → (retry) → human_gate → post
python ch05_state_graphs/online/approval_gateway.py
python ch05_state_graphs/online/parallel_fanout.py
python ch05_state_graphs/online/time_travel_debug.py
```

### What to expect on Gemma 4

- The review and self-check prompts ask for JSON. Gemma often wraps it in ```` ```json ```` fences. The code parses that with `shared/llm_utils.parse_json`, so you'll see a proper list of comments instead of one raw blob.
- Gemma tends to score its own review generously (8–9). To see the retry edge fire, raise the threshold in `should_retry()` from 7 to 9.

### Troubleshooting

- **Requests go to api.openai.com**: an older `langchain-openai` ignores `base_url`. Upgrade (`pip install -U langchain-openai`).
- **`quality_score` is always 5**: the self-check reply had no JSON at all (5 is the fallback). Print `response.content` in `self_check()` to see what the model said.

## Production notes

- Every retry loop needs a counter in state and a "give up" edge.
- In-memory checkpoints disappear on restart. Use a durable checkpointer for anything long-running.
- Put approval gates in front of side effects (posting, deploying, deleting), not in front of analysis.

## Takeaways

1. Explicit graphs are easier to debug, test, and audit than control flow buried in prompts.
2. State plus checkpoints give you resumability and human approval with little extra code.
3. Self-correction is a conditional edge with a retry budget.

**Prev:** [Ch. 4](../ch04_handoffs/README.md) · **Next:** [Chapter 6 — Multi-Agent Collaboration](../ch06_multi_agent/README.md)
