# Atlas Agents — Hands-on AI Agents in Production

This repository contains the source code, examples, and project implementations for the book **"Hands-on AI Agents"** — a practical, code-first guide to building AI agents and, more importantly, putting them into production.

## 🚀 Book Overview

Where *Agentic Design Patterns* taught how to **write** agents, this book is about how to **run** them: the harnesses, guardrails, evals, loops, and deployment machinery that turn a demo into a system you can trust unattended. One project — **Atlas**, an autonomous engineering assistant — grows chapter by chapter from a fifty-line ReAct loop into a self-correcting, self-improving production system.

### Key Technologies
- **Claude API / OpenAI / Gemini**: multi-provider agent cores with structured outputs.
- **LangGraph & CrewAI**: stateful agent graphs and role-based multi-agent orchestration.
- **MCP & A2A**: universal tool connectivity and agent-to-agent discovery.
- **Claude Code & Antigravity**: agentic coding harnesses and loop primitives.
- **Agent Skills**: declarative, progressively-disclosed expertise (`SKILL.md`).
- **E2B / Docker sandboxes**: safe code execution boundaries.
- **Managed Agents**: server-run sessions, outcomes, and scheduled deployments.
- **LiteLLM, DSPy, Ollama**: model portability, routing, and local inference.

## 📁 Repository Structure

Each chapter folder holds the chapter's Atlas project. Extended examples that go beyond the printed text live in each chapter's `online/` subfolder.

Every chapter has its own **README** (linked below) with a TL;DR, the key concepts mapped to the code, a file guide, a hands-on checklist of what to do, run commands, and production notes. You can use them to learn the concepts without the book.

| Folder | Chapter |
|---|---|
| [`ch01_react_from_scratch/`](ch01_react_from_scratch/README.md) | Anatomy of an Agent — the minimal ReAct loop |
| [`ch02_prompt_architecture/`](ch02_prompt_architecture/README.md) | Prompt Architecture for Agents |
| [`ch03_tools_and_skills/`](ch03_tools_and_skills/README.md) | Tools, Skills, and Structured Outputs |
| [`ch04_handoffs/`](ch04_handoffs/README.md) | Handoffs and Routines — the support triage router |
| [`ch05_state_graphs/`](ch05_state_graphs/README.md) | Stateful Agent Graphs — LangGraph persistence and HITL |
| [`ch06_multi_agent/`](ch06_multi_agent/README.md) | Multi-Agent Collaboration — CrewAI and debate protocols |
| [`ch07_model_portability/`](ch07_model_portability/README.md) | One Agent, Many Models — LiteLLM, Ollama, DSPy |
| [`ch08_mcp_a2a/`](ch08_mcp_a2a/README.md) | Open Protocols — MCP servers and A2A discovery |
| [`ch09_agent_skills/`](ch09_agent_skills/README.md) | Agent Skills — the production skill library |
| [`ch10_claude_code_antigravity/`](ch10_claude_code_antigravity/README.md) | Claude Code and Antigravity |
| [`ch11_memory/`](ch11_memory/README.md) | Memory and Agentic RAG |
| [`ch12_sandboxes/`](ch12_sandboxes/README.md) | Code Execution and Sandbox Agents |
| [`ch13_multimodal/`](ch13_multimodal/README.md) | Multimodal and Voice Agents |
| [`ch14_guardrails/`](ch14_guardrails/README.md) | Guardrails and Agent Safety |
| [`ch15_agent_harness/`](ch15_agent_harness/README.md) | Agent Harness Engineering |
| [`ch16_always_on_agents/`](ch16_always_on_agents/README.md) | Always-On Agents — daemons, watchdogs, recovery |
| [`ch17_managed_agents/`](ch17_managed_agents/README.md) | Managed Agents — let the platform run it |
| [`ch18_evaluation/`](ch18_evaluation/README.md) | Evaluation and Observability |
| [`ch19_deployment/`](ch19_deployment/README.md) | Deployment, Async Agents, and Security |
| [`ch20_loop_engineering/`](ch20_loop_engineering/README.md) | Loop Engineering — the self-correcting fix loop |
| [`ch21_harness_engineer/`](ch21_harness_engineer/README.md) | The Harness Engineer — /learn, adversarial pairs, prose verifiers |
| [`ch22_capstone/`](ch22_capstone/README.md) | Capstone: Atlas — the Autonomous Engineering Assistant |
| [`ch23_future/`](ch23_future/README.md) | What's Next — scaffold optimization and reasoning benchmarks |
| `shared/` | Global config and declarative skill models used across chapters |

## 🛠️ Prerequisites

- Python 3.10+
- API keys as needed per chapter: Anthropic, OpenAI, Google Gemini (see `shared/config.py` — keys load from a `.env` at the repo root), **or** a local Ollama server (see below)
- `pip install -r requirements.txt` (per-chapter extras are noted in each file's header)
- Basic understanding of LLM prompting and Python

## ▶️ Running the Examples

Every script is self-contained and documents its own usage and dependencies in its module docstring:

```bash
cd ch20_loop_engineering
python fix_loop.py --repo ./orders-service --goal "pytest green, ruff clean"
```

## 🖥️ Run everything locally with Gemma 4 on Ollama

Every chapter reads its model names and endpoints from `.env` through `shared/config.py`. Point those at a local Ollama server and the code calls Gemma 4 instead of Claude or GPT, with no code edits.

This works without code changes because Ollama exposes two compatible APIs:

| The chapter uses… | It calls… | Ollama answers at |
|---|---|---|
| `openai` SDK (ch01–ch05) | Chat Completions, Embeddings | `http://localhost:11434/v1` |
| `anthropic` SDK (ch01 variants, ch10–ch23) | Messages API | `http://localhost:11434` (Ollama ≥ 0.14) |
| LiteLLM / CrewAI / DSPy (ch06, ch07, ch19) | `ollama_chat/<model>` | `http://localhost:11434` |

### Step 1: Install Ollama and start it

```bash
# macOS:  brew install ollama          Linux:  curl -fsSL https://ollama.com/install.sh | sh
ollama --version        # must be 0.14 or newer (needed for the Anthropic-compatible endpoint)
ollama serve            # leave running (the desktop app starts it automatically)
```

### Step 2: Create the `gemma4-longctx` model

The READMEs use the model name **`gemma4-longctx`**: Gemma 4 12B with a larger context window. Agents need the larger window because a system prompt, tool schemas, and a few tool results quickly exceed Ollama's small default context. When that happens, Ollama silently truncates the prompt, and the agent loses instructions or earlier tool results without any error.

If you already have `gemma4-longctx`, skip to step 3. Otherwise:

```bash
ollama pull gemma4:12b

cat > Modelfile.gemma4-longctx <<'EOF'
FROM gemma4:12b
PARAMETER num_ctx 32768
EOF
ollama create gemma4-longctx -f Modelfile.gemma4-longctx

ollama show gemma4-longctx      # Capabilities: tools, vision. Parameters: num_ctx 32768
```

Pick `num_ctx` to fit your memory: 16384 is fine on a 16 GB machine, and 32768 or more if you have headroom. Other sizes work the same way: `gemma4:e4b` (~5 GB, laptops, weaker at multi-step tool use) or `gemma4:26b` (stronger, more memory).

Optional extras used by some chapters:

```bash
ollama pull embeddinggemma      # embeddings: ch04 semantic router, ch06 crew memory
ollama pull gemma4:e4b          # a genuinely cheaper "fast" tier: ch14, ch18, ch20 learned router
```

### Step 3: Configure `.env`

```bash
cp .env.example .env
```

Delete the cloud keys at the top and uncomment **Option B**:

```ini
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
OPENAI_MODEL=gemma4-longctx
OPENAI_FAST_MODEL=gemma4-longctx

ANTHROPIC_BASE_URL=http://localhost:11434
ANTHROPIC_API_KEY=ollama
ANTHROPIC_MODEL=gemma4-longctx
ANTHROPIC_FAST_MODEL=gemma4-longctx
ANTHROPIC_STRONG_MODEL=gemma4-longctx

OLLAMA_MODEL=gemma4-longctx
LITELLM_MODEL=ollama_chat/gemma4-longctx
EMBED_MODEL=embeddinggemma
ENABLE_THINKING=false
```

- The API keys are placeholders. Ollama ignores them, but the SDKs refuse to start without one.
- Leave `GOOGLE_API_KEY` unset. The Gemini-only paths (ch13 PDF, ch18 third judge) fall back to local equivalents.
- `.env` is in `.gitignore`. Never commit it.

### Step 4: Check both endpoints

```bash
# OpenAI-compatible (ch01–ch07)
curl -s http://localhost:11434/v1/chat/completions -H 'content-type: application/json' \
  -d '{"model":"gemma4-longctx","messages":[{"role":"user","content":"Say OK"}]}' | head -c 300; echo

# Anthropic-compatible (ch10–ch23)
curl -s http://localhost:11434/v1/messages -H 'content-type: application/json' -H 'x-api-key: ollama' \
  -d '{"model":"gemma4-longctx","max_tokens":50,"messages":[{"role":"user","content":"Say OK"}]}' | head -c 300; echo

# Tool calling (what every agent loop depends on)
curl -s http://localhost:11434/v1/chat/completions -H 'content-type: application/json' -d '{
  "model":"gemma4-longctx",
  "messages":[{"role":"user","content":"What is the weather in Paris?"}],
  "tools":[{"type":"function","function":{"name":"get_weather","description":"Get weather for a city",
    "parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}]}' \
  | grep -o '"tool_calls".*' | head -c 300; echo
```

The last command should print a `tool_calls` entry naming `get_weather`. If it doesn't, update Ollama and re-pull the model.

Then run the first chapter:

```bash
pip install -r requirements.txt
python ch01_react_from_scratch/atlas_v01.py "What is the Model Context Protocol?"
```

### Chapter compatibility

| Chapter | Local status | Notes |
|---|---|---|
| ch01 ReAct, ch02 Prompts, ch03 Skills | ✅ | Pure OpenAI-compatible tool calling. |
| ch04 Handoffs | ✅ | `triage.py` switches the Agents SDK to Chat Completions and disables tracing automatically. The semantic router needs `embeddinggemma`. |
| ch05 LangGraph | ✅ | `ChatOpenAI` gets `base_url` from `.env`. |
| ch06 CrewAI | ✅ | Agents use `LITELLM_MODEL`. Crews are slow locally (many sequential calls). |
| ch07 Portability | ✅ | The benchmark compares cloud rows (when you have real keys) with your local model. DSPy uses `LITELLM_MODEL`. |
| ch08 MCP/A2A | ✅ | The server needs no LLM. Use Claude Code pointed at Ollama as the MCP client. |
| ch09 Skills, ch15 Harness | ✅ | No LLM of their own. Plug into the ch03 agent. |
| ch10 Claude Code | ⚠️ | Claude Code runs against Ollama, but a 12B model is far weaker at long agentic coding sessions. |
| ch11 Memory, ch12 Sandboxes, ch14 Guardrails, ch16 Always-on | ✅ | ch12's E2B is a cloud sandbox; without a key it uses the local subprocess fallback. |
| ch13 Multimodal | ⚠️ | Images and text work (Gemma 4 has vision). PDFs use the `pdftotext` fallback. **Voice agents are cloud-only.** |
| ch17 Managed Agents | ❌ | Hosted platform APIs. ch16 is the self-hosted equivalent. |
| ch18 Evaluation | ✅ | Pull a second model so the judges aren't all the same model. |
| ch19 Deployment | ✅ | From Docker, use `http://host.docker.internal:11434`. |
| ch20 Loops, ch21 Harness engineer, ch22 Capstone, ch23 Future | ✅ | Expect more loop attempts than with frontier models. ch23 runs with thinking off. |

Each chapter README has a **"Run with Gemma 4 on Ollama"** section with exact commands and chapter-specific issues.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `Connection refused` on port 11434 | Start Ollama (`ollama serve` or the desktop app). |
| `model "gemma4-longctx" not found` | Run step 2, or set every `*_MODEL` in `.env` to a model shown by `ollama list`. |
| `404` on `/v1/messages` | Ollama is older than 0.14. Upgrade it. |
| Calls still go to api.openai.com / api.anthropic.com | `.env` isn't at the repo root, or a shell `export` overrides it (shell variables win over `.env`). Check with `env \| grep -E 'OPENAI\|ANTHROPIC'`. |
| `Missing OPENAI_API_KEY` | Set `OPENAI_API_KEY=ollama` (any non-empty value). |
| Agent ignores its instructions on long tasks | Context overflow. Raise `num_ctx` in the Modelfile and run `ollama create` again. |
| Answers start with "Here is the JSON:" or wrap JSON in ```` ``` ```` | Normal for local models. The code parses it with `shared/llm_utils.parse_json`. |
| First response takes 30+ seconds | The model is loading into memory. Later calls are fast. Run `ollama ps` to see what's loaded. |
| Very slow everywhere | The model doesn't fit in GPU memory and is running on the CPU (`ollama ps` shows the split). Use a smaller tag or a smaller `num_ctx`. |
