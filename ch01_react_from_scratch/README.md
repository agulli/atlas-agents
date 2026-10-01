# Chapter 1 — Anatomy of an Agent: ReAct from Scratch

> **Atlas v0.1** — a research agent in plain Python. No framework, just an LLM, two tools, and a loop.

## TL;DR

An "agent" is just an LLM called in a **loop**. On each turn the model either asks to call a tool or gives a final answer. You run the tool, append the result to the conversation, and call the model again. That loop is called **ReAct** (Reason + Act). Every framework in later chapters is a nicer wrapper around this.

```
question ─▶ LLM ──tool call?──yes──▶ run tool ─▶ append result ─┐
             ▲                                                   │
             └───────────────────────────────────────────────────┘
                   └──no──▶ final answer
```

## Key concepts

| Concept | What it means | Where to see it |
|---|---|---|
| **Agent loop** | `for i in range(MAX_ITERATIONS)`: call LLM → if no tool calls, return; else execute tools and loop. | `atlas_v01.py` → `run_atlas()` |
| **Tool schema** | A JSON Schema description of each function (`name`, `description`, `parameters`). The model reads it to decide *when* and *how* to call the tool. | `TOOL_SCHEMAS` |
| **Tool dispatch** | A plain dict mapping tool names to Python functions. Unknown names return an error string, never crash. | `TOOLS` |
| **Observation** | The tool's output, fed back as a `role: "tool"` message with the matching `tool_call_id`. | end of `run_atlas()` |
| **Iteration cap** | A hard stop (`MAX_ITERATIONS = 6`) so a confused model can't loop forever. Your first guardrail. | top of file |
| **Context budget** | Page text is truncated to 3,000 chars so a single page can't flood the context window. | `read_url()` |
| **System prompt rules** | "Always search first", "use ≤ 5 tool calls", "cite sources", "admit when unsure". The prompt is part of the program. | `SYSTEM_PROMPT` |

## What you build

`atlas_v01.py` — a CLI research assistant:
1. Takes a question.
2. Searches DuckDuckGo (`search_web`, top 5 results).
3. Reads pages (`read_url`, HTML → text with `HTMLParser`).
4. Synthesizes a cited answer.

## Files

| File | What it shows |
|---|---|
| `atlas_v01.py` | The chapter project: raw ReAct loop using the OpenAI tool-calling API. |
| `online/atlas_v01_anthropic.py` | Same loop on Claude's API. Note: Anthropic uses `input_schema` instead of `parameters`, and tool results come back as `tool_result` content blocks. |
| `online/atlas_v01_plan_and_execute.py` | **Plan-and-Execute** variant: one LLM call writes a step plan, each step runs independently, a final call synthesizes. Keeps context small on long tasks. |
| `online/atlas_v01_streaming.py` | Streams the model's text and tool calls in real time with the Anthropic streaming API. |

## What needs to be done

- [ ] Copy `.env.example` → `.env` at the repo root and set `OPENAI_API_KEY` (and `ANTHROPIC_API_KEY` for the online variants).
- [ ] `pip install -r requirements.txt` (the core project only needs `openai` + `python-dotenv`).
- [ ] Run the project and watch each iteration print the tool it chose and a preview of the result.
- [ ] Try a question that needs no search, and one that needs several. Count iterations.
- [ ] Set `MAX_ITERATIONS = 2` and see how the agent fails when it runs out of turns.
- [ ] Compare the ReAct and Plan-and-Execute outputs on the same multi-part question.

## Run it

```bash
cd ch01_react_from_scratch
python atlas_v01.py "What are the key differences between LangGraph and CrewAI?"

# Variants
python online/atlas_v01_anthropic.py "What is the Model Context Protocol?"
python online/atlas_v01_plan_and_execute.py "Research the top 3 AI agent frameworks"
python online/atlas_v01_streaming.py "What is the Model Context Protocol?"
```

## Run with Gemma 4 on Ollama

> **One-time setup:** follow *Run everything locally with Gemma 4 on Ollama* in the [root README](../README.md): Ollama running, `gemma4-longctx` created, `.env` set to Option B. Run every command below from the **repo root**.

**Status: ✅ Works.** The OpenAI-SDK loop talks to Ollama's `/v1` endpoint, and the Anthropic variants talk to its Messages endpoint.

### Setup

| `.env` key | Value | Used by |
|---|---|---|
| `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL` | `http://localhost:11434/v1` / `ollama` / `gemma4-longctx` | `atlas_v01.py`, `atlas_v01_plan_and_execute.py` |
| `ANTHROPIC_BASE_URL` / `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | `http://localhost:11434` / `ollama` / `gemma4-longctx` | `atlas_v01_anthropic.py`, `atlas_v01_streaming.py` |

```bash
pip install openai anthropic python-dotenv
```

### Commands

```bash
python ch01_react_from_scratch/atlas_v01.py "What is the Model Context Protocol?"
python ch01_react_from_scratch/online/atlas_v01_anthropic.py "What is the Model Context Protocol?"
python ch01_react_from_scratch/online/atlas_v01_plan_and_execute.py "Research the top 3 AI agent frameworks"
python ch01_react_from_scratch/online/atlas_v01_streaming.py "What is the Model Context Protocol?"
```

You should see `── Iteration 1 ──`, then `🔧 Calling: search_web({...})`, then a final answer.

### What to expect on Gemma 4

- The tools (`search_web`, `read_url`) still need internet access, since they hit DuckDuckGo and the target pages. Only the *model* is local.
- Gemma 4 sometimes answers from memory without searching, despite "Always search before answering". If it does, repeat the rule in the user message ("Search the web first, then answer").
- Three pages at 3,000 chars each plus the conversation is about 4k tokens. This is why the long-context model matters. With Ollama's default context, later iterations lose the system prompt.

### Troubleshooting

- **`Agent reached maximum iterations`**: the model keeps calling tools. Raise `MAX_ITERATIONS` to 8, or make the rule "use at most 3 tool calls" more explicit.
- **The tool is never called** (answer arrives on iteration 1): run the tool-calling `curl` check from the root README. If no `tool_calls` come back, update Ollama.

## Production notes

- Tools **return error strings** instead of raising. The model can read an error and recover; a Python exception just kills the loop.
- Always cap iterations *and* truncate tool output. The two most common failures are infinite loops and context overflow.
- ReAct suits short, exploratory tasks. For long multi-step work, planning up front (Plan-and-Execute) usually costs fewer tokens.

## Takeaways

1. An agent is `while not done: think → act → observe`.
2. The model never runs code. It only *asks* for a tool, and your code decides whether and how to run it.
3. Everything later in the book (frameworks, harnesses, guardrails, evals) exists to make this loop safer, cheaper, or more reliable.

**Next:** [Chapter 2 — Prompt Architecture](../ch02_prompt_architecture/README.md)
