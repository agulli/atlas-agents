# Chapter 10 — Claude Code and Antigravity

> **Atlas v0.10** — run Atlas inside an **agentic coding harness**, governed by a behavioral contract (`AGENTS.md`), permission rules, and hooks (`.claude/settings.json`).

## TL;DR

Agentic coding tools (Claude Code, Antigravity) already provide a strong agent loop, file tools, and a terminal. Your job shifts from *building* the loop to *governing* it:

- **`AGENTS.md`** is the contract: what the agent may and must not do, behavior rules, a quality gate, and when to escalate.
- **`settings.json`** enforces it: an allow/deny list for shell commands and **hooks** that run automatically (lint after every edit, audit-log every command, run tests at stop).
- **Headless mode** (`claude --print`) runs the same agent in CI with no UI.

Prompt rules are *requests*. Permissions and hooks are *enforcement*. Use both.

## Key concepts

| Concept | What it means | Where to see it |
|---|---|---|
| **Behavioral contract** | Identity, capabilities (MAY / MUST NOT), behavior rules, quality gate, escalation triggers. | `AGENTS.md` |
| **Quality gate** | "Done" only when tests pass, new behavior is tested, the linter is clean, and changed files are listed. | `AGENTS.md` → Quality Gate |
| **Permission allow/deny** | `pytest*`, `ruff*`, `mypy*`, and read-only git are allowed; `git push`, `git commit`, `rm -rf`, `pip install` are denied. | `.claude/settings.json` |
| **PostToolUse hook** | After any Write/Edit, run `ruff check --fix` automatically. | `.claude/settings.json` |
| **PreToolUse hook** | Append every Bash command with a timestamp to `.claude/bash_audit.log`. | `.claude/settings.json` |
| **Stop hook** | Run the test suite when the agent says it's finished. | `.claude/settings.json` |
| **Autonomy levels** | Supervised → semi-autonomous → fully autonomous, each with its own trade-off in accuracy, speed, and human effort. | `online/autonomy_benchmarker.py` |
| **Contract testing** | Send adversarial prompts and check that the agent stays inside `AGENTS.md`. | `online/spec_validator.py` |
| **Headless CI** | `claude --print` for PR review, security scan, and test generation, with results posted as a PR comment. | `online/claude_code_ci.py` |

## Files

| File | What it shows |
|---|---|
| `AGENTS.md` | The chapter project: Atlas's behavioral contract. |
| `.claude/settings.json` | Model, permissions, and hooks that enforce the contract. |
| `online/autonomy_benchmarker.py` | Compares accuracy, cost, and interventions across autonomy levels. |
| `online/spec_validator.py` | Parses `AGENTS.md` into a contract and runs adversarial validation cases. |
| `online/claude_code_ci.py` | GitHub Actions wrapper for headless Claude Code review (includes a sample workflow in its docstring). |

## What needs to be done

- [ ] Copy `AGENTS.md` and `.claude/settings.json` into a sandbox repo with a `workspace/` and `tests/`.
- [ ] Open Claude Code there and ask for a small feature. Check that the hooks ran (lint output, `bash_audit.log`, tests at stop).
- [ ] Ask the agent to `git push` or `rm -rf` something and confirm the deny rules block it.
- [ ] Write one new MUST NOT rule in `AGENTS.md` and a matching deny/hook in `settings.json`.
- [ ] Run `spec_validator.py` against your agent endpoint and fix any contract violations.
- [ ] (Stretch) Wire `claude_code_ci.py` into a GitHub Actions workflow on a test repo.

## Run it

```bash
cd ch10_claude_code_antigravity
python online/autonomy_benchmarker.py --tasks 20
python online/spec_validator.py --agents-md ./AGENTS.md --agent-url http://localhost:8000
```

## Run with Gemma 4 on Ollama

> **One-time setup:** follow *Run everything locally with Gemma 4 on Ollama* in the [root README](../README.md): Ollama running, `gemma4-longctx` created, `.env` set to Option B. Run every command below from the **repo root**.

**Status: ⚠️ Works, with weaker results.** Claude Code can run on Ollama through the Anthropic-compatible endpoint, and `AGENTS.md`, the permissions, and the hooks all work the same. A 12B model is much less capable at long, multi-file coding sessions than a frontier model, though.

### Setup

```bash
npm install -g @anthropic-ai/claude-code
pip install anthropic requests python-dotenv
```

Make a sandbox repo with the contract:

```bash
mkdir -p ~/atlas-sandbox/workspace/tests && cd ~/atlas-sandbox && git init
cp -r /path/to/atlas-agents/ch10_claude_code_antigravity/{AGENTS.md,.claude} .
```

### Commands

**Claude Code on Gemma 4** (the `--model` flag overrides the `"model"` in `.claude/settings.json`):

```bash
ANTHROPIC_BASE_URL=http://localhost:11434 ANTHROPIC_AUTH_TOKEN=ollama ANTHROPIC_API_KEY="" \
  claude --model gemma4-longctx
```

Then check that the enforcement works regardless of the model:

- "Add a `slugify()` function in workspace/utils.py with a test." → after the edit, the **PostToolUse** hook runs `ruff --fix`; `.claude/bash_audit.log` gets every command (**PreToolUse**); tests run when it stops (**Stop**).
- "Commit and push this." → blocked by the **deny** rules, whatever the model wants.

**The Python tools** (from the atlas-agents repo root, using your `.env`):

```bash
python ch10_claude_code_antigravity/online/autonomy_benchmarker.py --tasks 5          # uses ANTHROPIC_FAST_MODEL
python ch10_claude_code_antigravity/online/spec_validator.py --agents-md ch10_claude_code_antigravity/AGENTS.md
```

Without `--agent-url`, `spec_validator.py` calls the model directly with `AGENTS.md` as the system prompt, so it tests how well **Gemma** respects the contract.

### What to expect on Gemma 4

- This is the clearest local demonstration of the chapter's point: **deny rules and hooks enforce the contract even when the model is weaker.** A prompt rule is only as reliable as the model following it.
- The spec validator will likely find more contract violations on Gemma than on Claude. Use them to tighten `AGENTS.md` wording.
- `claude_code_ci.py` passes `--model` from `ANTHROPIC_MODEL`. In CI, the runner would need network access to an Ollama host, so it is mainly a cloud workflow.

### Troubleshooting

- **Claude Code says the model doesn't support tools**: check `ollama show gemma4-longctx` lists `tools`, and that Ollama is 0.14 or newer.
- **Session forgets earlier steps quickly**: Claude Code's system prompt is large. Use a bigger `num_ctx` (64k if you have the memory).

## Production notes

- Deny rules beat prompt rules. An instruction in `AGENTS.md` can be ignored or overridden by an injection; a denied command cannot run.
- Hooks make verification happen **every time** without depending on the model to remember.
- Start supervised, measure, and grant autonomy per task type as the data supports it.

## Takeaways

1. With a coding harness, your job becomes writing the contract and the enforcement.
2. `AGENTS.md` states intent, and `settings.json` makes it hold.
3. The same agent runs interactively and headless in CI.

**Prev:** [Ch. 9](../ch09_agent_skills/README.md) · **Next:** [Chapter 11 — Memory and Agentic RAG](../ch11_memory/README.md)
