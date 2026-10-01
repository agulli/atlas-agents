# Chapter 18 — Evaluation and Observability

> **Atlas v0.18** — a **50-case trajectory eval harness** that grades *how* the agent got the answer (tools, budget, latency), plus an LLM judge, CI regression gates, and trajectory visualization.

## TL;DR

"92% of answers contained the right keywords" says little if the agent used 15 tool calls, called a forbidden tool, or would fail on a slight rephrasing. **Trajectory evaluation** grades the whole run:

- **Answer**: keywords + an **LLM judge** scoring against reference facts (reasoning *before* score).
- **Tools**: required tools used, **forbidden tools never used**, tool-call budget respected.
- **Cost**: latency and tokens.

Then make evals part of CI: aggregate thresholds, a baseline for regression checks, and safety cases that must *all* pass.

## Key concepts

| Concept | What it means | Where to see it |
|---|---|---|
| **Eval case** | `input`, `expected_answer_keywords`, `expected_tools`, `forbidden_tools`, `max_tool_calls`, `max_latency_seconds`, `category`, `reference_facts`. | `EvalCase` |
| **Categories** | code_review, research, bug_analysis, architecture, **safety** (injection, destructive commands), general. | `EVAL_CASES` |
| **LLM-as-judge** | Sonnet scores 1–5 and flags hallucination. Asking for reasoning first gives consistent scores; asking for the score first gives noisy ones. | `llm_judge()` |
| **Pluggable agent** | `mock_agent()` is a stub; replace it with your real agent returning `answer`, `tools_used`, `total_tokens`. | `mock_agent()` |
| **CI regression gates** | pytest asserts: pass rate ≥ 70%, hallucinations ≤ 10%, judge avg ≥ 3.0, no errors, all safety cases pass, no budget overruns, no regression vs. baseline. | `online/ci_eval_runner.py` |
| **Multi-judge consensus** | Sonnet + Haiku + Gemini Flash majority vote, and disagreements go to human review. | `online/multi_judge_consensus.py` |
| **Trajectory visualization** | Turn raw JSON into a timeline of tool calls, latency, cost, and result previews. | `online/trajectory_visualizer.py` |

## Files

| File | What it shows |
|---|---|
| `eval_harness.py` | The chapter project: 50-case harness with filtering by category or case. |
| `online/ci_eval_runner.py` | Evals as pytest tests with thresholds and baseline comparison. |
| `online/multi_judge_consensus.py` | Three-judge majority voting. |
| `online/trajectory_visualizer.py` | Terminal timeline renderer for trajectory logs. |

## What needs to be done

- [ ] `pip install anthropic pytest` (plus `google-genai` for consensus) and set `ANTHROPIC_API_KEY`.
- [ ] Run one case, then one category, then the full suite.
- [ ] **Replace `mock_agent()`** with a real agent from an earlier chapter that reports its actual tool calls.
- [ ] Add 5 cases from your own failures, with `forbidden_tools` set on each.
- [ ] Save a baseline, change the agent's prompt, and see whether CI catches a regression.
- [ ] Run the consensus judge on a borderline case and compare verdicts.

## Run it

```bash
cd ch18_evaluation
python eval_harness.py --case tc-001
python eval_harness.py --category safety
python eval_harness.py

pytest online/ci_eval_runner.py -v
BASELINE_PATH=baseline.json pytest online/ci_eval_runner.py
python online/trajectory_visualizer.py trajectory.json
```

## Run with Gemma 4 on Ollama

> **One-time setup:** follow *Run everything locally with Gemma 4 on Ollama* in the [root README](../README.md): Ollama running, `gemma4-longctx` created, `.env` set to Option B. Run every command below from the **repo root**.

**Status: ✅ Works.** The agent under test, the LLM judge, and all three consensus judges run on Ollama.

### Setup

`.env` keys: `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, plus:

| Key | Role here | Suggested local value |
|---|---|---|
| `ANTHROPIC_FAST_MODEL` | `mock_agent` (the agent under test) and consensus judge 2 | `gemma4:e4b` |
| `ANTHROPIC_MODEL` | LLM judge and consensus judge 1 | `gemma4-longctx` |
| `ANTHROPIC_STRONG_MODEL` | Consensus judge 3 (replaces Gemini when `GOOGLE_API_KEY` is unset) | `gemma4:26b` or any other tool-capable model you have |

A judge that is the same model as the agent tends to grade itself kindly, and three identical judges always agree, which defeats the purpose. Use different models:

```bash
ollama pull gemma4:e4b
pip install anthropic pytest python-dotenv
```

### Commands

```bash
python ch18_evaluation/eval_harness.py --case tc-001
python ch18_evaluation/eval_harness.py --category safety
python ch18_evaluation/eval_harness.py --no-judge            # all 50 cases, fast (keywords + tools only)
python ch18_evaluation/eval_harness.py                       # all 50 with the judge: slow locally

python ch18_evaluation/online/multi_judge_consensus.py --case tc-001
pytest ch18_evaluation/online/ci_eval_runner.py -v
python ch18_evaluation/online/trajectory_visualizer.py --live "What is RAG?"
```

### What to expect on Gemma 4

- The judge prompt asks for reasoning before the score, and that matters even more for small judges. Expect noisier scores than with a frontier judge, which is the reason for consensus.
- **CI thresholds** (`PASS_RATE_THRESHOLD = 0.70`, etc.) were set for cloud models. For a local pipeline, run once, save a **local baseline**, and gate on *regression* against it instead of absolute numbers.
- The trajectory visualizer prices tokens at Claude rates. Ignore `$` locally and read latency and tool-call counts.

### Troubleshooting

- **`judge_score` is always 3**: that's the fallback for cases without reference facts, not a parsing problem. Only the hand-written cases have facts.
- **The full suite takes a long time**: use `--category` or `--no-judge` while iterating, and run the full judged suite before you commit.

## Production notes

- LLM evals are non-deterministic, so assert on **aggregates** and not single outputs.
- Safety cases are the exception. Require 100% on them.
- A single judge disagrees with itself on borderline answers. Use consensus or human review there.
- Record trajectories in production too. Tomorrow's eval cases come from today's failures.

## Takeaways

1. Evaluate the trajectory (tools, budget, safety) and not only the final answer.
2. Evals in CI turn "the prompt feels better" into a pass/fail check.
3. Every production incident should become an eval case.

**Prev:** [Ch. 17](../ch17_managed_agents/README.md) · **Next:** [Chapter 19 — Deployment, Async Agents, and Security](../ch19_deployment/README.md)
