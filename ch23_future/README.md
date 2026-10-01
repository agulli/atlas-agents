# Chapter 23 — What's Next: Reasoning Models, Self-Optimizing Scaffolds, and the Automation Ceiling

> Three runnable experiments for the book's forward-looking claims. Measure them on your own tasks instead of taking them on faith.

## TL;DR

1. **Reasoning models change the loop.** A ReAct loop makes many small LLM calls. With strong reasoning models, a **reasoning-first** design often wins on complex tasks: one large thinking call writes the plan, then tools run *deterministically*. ReAct usually stays cheaper on simple tasks.
2. **Self-improvement without retraining.** Change the *scaffolding* instead of the weights: watch sessions, detect wasteful routing (for example always running the reviewer after a trivial edit), and propose a leaner graph, **gated by evals**.
3. **Not everything can be automated yet.** Only a minority (~27%) of enterprise processes are fully automatable today. Model your own portfolio to see where agents pay off now and what guardrails or self-improvement would unlock next.

## Key concepts

| Concept | What it means | Where to see it |
|---|---|---|
| **ReAct vs. reasoning-first** | Interleaved think/act calls vs. plan once → execute deterministically. Compare latency, tokens, number of LLM calls, and judged quality. | `online/reasoning_vs_react_benchmark.py` |
| **Scaffold optimization** | Record node executions per session → detect inefficiencies → Claude proposes graph changes → validate before activating. | `online/scaffold_optimizer.py` |
| **Graphs are data** | A LangGraph topology is a Python structure, so it can be rewritten at runtime. | `generate_optimization()` |
| **Automation zones** | Processes are classified by exception rate, data quality, and compliance: **I** (<5% exceptions, clean data, no compliance → ~95% automatable), **II** (<25% exceptions → ~40%), **III** (<50% or strict compliance → ~10%), **IV** (mostly judgment). Guardrails and self-improvement push processes up a zone. | `online/enterprise_ceiling_calculator.py` → `BusinessProcess.zone()` |
| **Eval-gated change** | Any self-modification ships only if the benchmark doesn't regress (same rule as Ch. 20). | all three |

## Files

| File | What it shows |
|---|---|
| `online/reasoning_vs_react_benchmark.py` | Benchmarks the two architectures on 10 tasks with simulated tools and an LLM judge. |
| `online/scaffold_optimizer.py` | Detects wasteful routing and proposes a graph config (`--demo` generates sample sessions). |
| `online/enterprise_ceiling_calculator.py` | Models automation coverage and cost for a process portfolio (`--demo` or your own JSON). |

## What needs to be done

- [ ] `pip install anthropic` and set `ANTHROPIC_API_KEY`.
- [ ] Run the benchmark with `--tasks 5` first. Find the task complexity where reasoning-first starts to win.
- [ ] Run the scaffold optimizer demo, then feed it real session traces from your Ch. 22 runs.
- [ ] Describe 10 of your team's processes in JSON and run the ceiling calculator. Which are Zone I today?
- [ ] Pick one Zone II process and list the guardrails, evals, and harness pieces (Ch. 14–21) it would need.

## Run it

```bash
cd ch23_future
python online/reasoning_vs_react_benchmark.py --tasks 5
python online/scaffold_optimizer.py --demo
python online/enterprise_ceiling_calculator.py --demo
python online/enterprise_ceiling_calculator.py --processes processes.json
```

## Run with Gemma 4 on Ollama

> **One-time setup:** follow *Run everything locally with Gemma 4 on Ollama* in the [root README](../README.md): Ollama running, `gemma4-longctx` created, `.env` set to Option B. Run every command below from the **repo root**.

**Status: ✅ Works**, with extended thinking turned off (`ENABLE_THINKING=false`), since that parameter is part of Claude's API.

### Setup

`.env` keys: `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (ReAct runs), `ANTHROPIC_STRONG_MODEL` (the reasoning-first planner), `ANTHROPIC_FAST_MODEL` (the quality judge), and `ENABLE_THINKING=false`.

```bash
pip install anthropic python-dotenv
```

### Commands

```bash
python ch23_future/online/reasoning_vs_react_benchmark.py --tasks 3
python ch23_future/online/scaffold_optimizer.py --demo
python ch23_future/online/enterprise_ceiling_calculator.py --demo        # no LLM calls
```

### What to expect on Gemma 4

- With thinking off, the "reasoning-first" architecture still plans once and then executes deterministically. You're comparing **loop shapes** (many small calls vs. one plan), which is the chapter's main question.
- To compare *models* as well, set `ANTHROPIC_STRONG_MODEL=gemma4:26b` (planner) and `ANTHROPIC_MODEL=gemma4:e4b` (ReAct) and re-run. Bigger models gain more from planning up front.
- Gemma 4 itself supports thinking. If a later Ollama release maps the Anthropic `thinking` parameter onto it, try `ENABLE_THINKING=true`. If the request errors, set it back to `false`.
- Cost columns use Claude prices. Compare latency and LLM-call counts locally.

## Takeaways

1. Architecture should follow model capability. Re-check your loop design each model generation.
2. The cheapest self-improvement is changing the scaffolding, and it still needs an eval gate.
3. Pick automation targets on evidence: start with Zone I, and add harnesses to move up.

**Prev:** [Ch. 22](../ch22_capstone/README.md) · **Back to:** [Repository overview](../README.md)
