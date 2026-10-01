# Chapter 4 — Handoffs and Routines

> **Atlas v0.4** — a customer-support **triage router** that hands conversations to specialist agents (OpenAI Agents SDK).

## TL;DR

One agent with 30 tools and a 5-page prompt gets confused. Split it into **specialists**, each with a short prompt and a few tools, and put a **triage agent** in front whose only job is to route. The switch from one agent to another is a **handoff**. An **input guardrail** runs before any agent and can stop the run.

```
                    ┌─▶ Billing Specialist   (get_invoice, process_refund, update_payment)
customer ─▶ [guardrail] ─▶ Triage Router ─┼─▶ Technical Support    (search_docs, create_ticket, check_status)
                    └─▶ General Support ──▶ (can hand off to billing/technical)
```

## Key concepts

| Concept | What it means | Where to see it |
|---|---|---|
| **Routine** | A specialist = instructions + a small toolset for one job. | `billing_agent`, `technical_agent`, `general_agent` |
| **Handoff** | An agent passes control (and the conversation) to another agent. Declared with `handoffs=[...]`. | `triage_agent`, `general_agent` |
| **Triage router** | An agent told "do NOT answer, route immediately". | `triage_agent.instructions` |
| **Input guardrail / tripwire** | An async check that runs first. `tripwire_triggered=True` raises `InputGuardrailTripwireTriggered` and stops the run. | `profanity_check()` |
| **Context compression** | Summarize the history before a handoff so the next agent's context stays small. | `online/handoff_with_context.py` |
| **Semantic routing** | Route by embedding similarity instead of an LLM call. Much faster and cheaper. | `online/dynamic_routing.py` |
| **Escalation chain** | Watch the agent's trajectory and send it to a human after repeated tool failures. | `online/escalation_chains.py` |

## What you build

`triage.py` — three specialists plus a triage router on the **OpenAI Agents SDK** (`Agent`, `Runner`, `InputGuardrail`). It prints which agent produced the final answer (`result.last_agent.name`). The tools are stubs that return realistic strings.

## Files

| File | What it shows |
|---|---|
| `triage.py` | The chapter project: triage router, specialists, handoffs, and a guardrail. |
| `online/handoff_with_context.py` | Compresses conversation history with a fast model before the handoff. |
| `online/dynamic_routing.py` | `SemanticRouter`: cosine similarity between query and route embeddings, with no LLM call. |
| `online/escalation_chains.py` | Trajectory monitor that escalates to a human queue on repeated failures. |

## What needs to be done

- [ ] `pip install openai-agents` and set `OPENAI_API_KEY`.
- [ ] Send one billing, one technical, and one general question. Check which agent answers each.
- [ ] Send a message containing a blocked word and confirm the guardrail stops it.
- [ ] Add a fourth specialist (for example "Sales") with its own tool and add it to the triage handoffs.
- [ ] Compare LLM routing (`triage.py`) with embedding routing (`dynamic_routing.py`) for latency and accuracy.

## Run it

```bash
cd ch04_handoffs
python triage.py "I was charged twice for my subscription"
python triage.py "My API key stopped working after the update"
python triage.py "What are your business hours?"
python online/dynamic_routing.py "I need a refund for my last purchase"
```

## Run with Gemma 4 on Ollama

> **One-time setup:** follow *Run everything locally with Gemma 4 on Ollama* in the [root README](../README.md): Ollama running, `gemma4-longctx` created, `.env` set to Option B. Run every command below from the **repo root**.

**Status: ✅ Works.** `triage.py` detects `OPENAI_BASE_URL` and switches the OpenAI Agents SDK to Chat Completions (Ollama has no Responses API). It also turns off tracing, which would otherwise try to upload to OpenAI.

### Setup

`.env` keys: `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL=gemma4-longctx`, `OPENAI_FAST_MODEL` (history compression), and `EMBED_MODEL=embeddinggemma` (semantic router).

```bash
ollama pull embeddinggemma
pip install openai-agents openai numpy python-dotenv
```

### Commands

```bash
python ch04_handoffs/triage.py "I was charged twice for my subscription"   # → Billing Specialist
python ch04_handoffs/triage.py "My API key stopped working"                 # → Technical Support
python ch04_handoffs/triage.py "What are your business hours?"              # → General Support
python ch04_handoffs/triage.py "This is stupid"                              # → 🚫 blocked by guardrail (no LLM call)

python ch04_handoffs/online/dynamic_routing.py "I need a refund for my last purchase"   # embeddings via embeddinggemma
python ch04_handoffs/online/handoff_with_context.py
```

### What to expect on Gemma 4

- Handoffs are tool calls under the hood (`transfer_to_billing_specialist`, …), so routing quality depends on tool calling. Gemma 4 handles 3 clearly separated specialists well.
- Sometimes the triage agent answers itself instead of handing off. Strengthen its instructions ("You MUST call a transfer tool. Never answer.") and re-test.
- The semantic router makes no LLM call at all, so it's the fastest way to route locally.

### Troubleshooting

- **`404 … /v1/responses`**: `OPENAI_BASE_URL` isn't set, so the SDK used the Responses API. Check `.env`.
- **`model "text-embedding-3-small" not found`**: set `EMBED_MODEL=embeddinggemma`.
- **Tracing errors / 401 from api.openai.com**: you're running an older copy of `triage.py`. Pull the latest code, which calls `set_tracing_disabled(True)`.

## Production notes

- Handoffs pass the **whole conversation** by default. Compress it for long sessions.
- Put cheap guardrails (regex, keyword) before expensive LLM calls.
- Log which agent handled each request, because misroutes are the #1 triage bug.

## Takeaways

1. Many small, focused agents beat one large one.
2. A router should only route. Keep it from answering.
3. Guardrails and escalation paths belong in the architecture from day one.

**Prev:** [Ch. 3](../ch03_tools_and_skills/README.md) · **Next:** [Chapter 5 — Stateful Agent Graphs](../ch05_state_graphs/README.md)
