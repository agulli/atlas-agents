# Chapter 17 — Managed Agents: Let the Platform Run It

> **Atlas v0.17** — replace Chapter 16's daemon, watchdog, and heartbeat with a **cloud-managed agent session** where the provider handles sandboxing, restarts, state, and context compaction.

## TL;DR

Chapter 16 showed how much infrastructure a self-hosted agent needs. **Managed Agents** move that work to the platform. You define three things and stream results back:

1. **Agent**: model + system prompt + enabled tools (create once, reuse).
2. **Environment**: a sandbox with limited networking and preinstalled packages (create once, reuse).
3. **Session**: binds an agent to an environment for a task. You stream **SSE events** (`tool_execution`, `text_delta`, `session_completed`, `error`).

The same shape (define → provision → invoke) appears on **Anthropic**, **AWS Bedrock**, and **Google Vertex AI**.

```
create_agent() ─┐
                ├─▶ POST /sessions ─▶ POST /sessions/{id}/events (stream SSE) ─▶ output
create_environment() ─┘
```

## Key concepts

| Concept | What it means | Where to see it |
|---|---|---|
| **Agent definition** | Model, system prompt, and tool toggles (`bash`, `file_operations`, `web_search`). | `create_agent()` |
| **Environment** | `anthropic_cloud_sandbox`, `networking: limited` (outbound only through an approved proxy), preinstalled packages. | `create_environment()` |
| **Session + SSE** | Parse `data:` lines, print tool executions, collect text deltas, stop on completion or error. | `run_task()` |
| **Beta header** | Every request needs `anthropic-beta: managed-agents-2026-04-01`. | `HEADERS` |
| **Reuse** | Pass `--agent-id` / `--env-id` to skip provisioning on later tasks. | `main()` |
| **Retries & cancellation** | Exponential retry on 503/429, list sessions, send a cancel event. | `online/claude_managed_agent.py` |
| **Bedrock lifecycle** | create → **prepare** (compile) → invoke, with IAM roles, Guardrails, CloudTrail, PrivateLink. | `online/bedrock_managed_agent.py` |
| **Governed skill registry** | Register a skill (for example BigQuery read-only) once and attach it to many agents, which inherit its IAM identity. | `online/gemini_managed_agent.py` |

## Files

| File | What it shows |
|---|---|
| `managed_agents.py` | The chapter project: Atlas on Anthropic Managed Agents (beta). |
| `online/claude_managed_agent.py` | Production version: retry, environment reuse, session listing, cancel. |
| `online/bedrock_managed_agent.py` | AWS Bedrock Managed Agents (`boto3`). |
| `online/gemini_managed_agent.py` | Vertex AI managed agents with a Skill Registry. |

## What needs to be done

- [ ] `pip install requests anthropic` and set `ANTHROPIC_API_KEY` (your account needs Managed Agents beta access).
- [ ] Run a research task and read the streamed tool executions.
- [ ] Re-run with `--agent-id` / `--env-id` to reuse resources, and compare startup time.
- [ ] Write down what you *no longer* maintain compared with Ch. 16 (supervisor, heartbeat, sandbox, compaction) and what you gave up (control, portability, data location).
- [ ] (Optional) Try the Bedrock or Vertex variant if your organization uses AWS or GCP.

## Run it

```bash
cd ch17_managed_agents
python managed_agents.py "Summarize recent research on RAG evaluation metrics"
python managed_agents.py --agent-id agent_01J... --env-id env_... "Follow-up question"

python online/claude_managed_agent.py --setup
python online/claude_managed_agent.py --agent-id <id> --list-sessions
```

## Run with Gemma 4 on Ollama

> **One-time setup:** follow *Run everything locally with Gemma 4 on Ollama* in the [root README](../README.md): Ollama running, `gemma4-longctx` created, `.env` set to Option B. Run every command below from the **repo root**.

**Status: ❌ Cloud-only.** Managed Agents are hosted services (Anthropic Managed Agents, AWS Bedrock, Vertex AI). The provider runs the model, the sandbox, and the session, so you can't swap in Gemma on Ollama.

### The local equivalent

The point of this chapter is **what the platform does for you**. To get the same capabilities locally with Gemma 4, combine:

| Managed Agents gives you | Local equivalent in this repo |
|---|---|
| Restarts and session state | Ch. 16: `watchdog_supervisor.py` + heartbeat |
| Sandboxed tool execution | Ch. 15: `AgentHarness` (+ Ch. 12 local fallback or E2B) |
| Streaming events | Ch. 19: `/agent/stream` SSE endpoint |
| Tool definitions | Ch. 3: `SkillRegistry` |

### What needs to be done locally

- [ ] Run the Ch. 16 daemon on Gemma 4 (see its README).
- [ ] List what you had to build and operate yourself for that. That list is the build-vs-buy decision this chapter is about.
- [ ] Note which concerns go away locally (data residency: nothing leaves your machine) and which get harder (scaling, uptime, upgrades).

## Production notes

- Beta APIs change. Isolate them behind a thin client (as `claude_managed_agent.py` does).
- Treat `networking: limited` as the default and open egress on purpose.
- Compliance needs (data residency, audit) often decide which platform you use more than model quality does.

## Takeaways

1. Build vs. buy applies to agent infrastructure too.
2. Managed platforms share one shape: agent + environment + session, with results streamed back.
3. You still own the prompt, tools, evals, and guardrails.

**Prev:** [Ch. 16](../ch16_always_on_agents/README.md) · **Next:** [Chapter 18 — Evaluation and Observability](../ch18_evaluation/README.md)
