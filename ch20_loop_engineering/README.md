# Chapter 20 — Loop Engineering: The Self-Correcting Fix Loop

> **Atlas v0.20** — point it at a repo with failing tests: **verify → patch → re-verify** until `pytest` is green and `ruff` is clean, or **escalate** to a human when it stops making progress.

## TL;DR

A good agent loop is a small control system with five parts:

| Part | Role in `fix_loop.py` |
|---|---|
| **Trigger** | You run it once, and it iterates on its own. |
| **Verifier** | `pytest` + `ruff` exit codes decide "done", not the model's opinion. |
| **Memory** | Each failed attempt is compressed into **one-line lessons** fed into the next attempt (not the full transcript). |
| **Escalation** | A **failure fingerprint** (hash of failing lines) detects a loop that keeps producing the same failure. It stops and writes `escalation_state.json` for a human. |
| **Distillation** | A win that took real work is saved to `experience/` as a worked example and retrieved on similar future goals. |

```
retrieve experience ─▶ ┌─▶ verify ──green──▶ distill win ─▶ success
                       │     │ red
                       │   fingerprint same N times? ──yes──▶ escalate
                       │     │ no
                       └── generate + apply patch ◀── lessons (compacted by Haiku)
```

## Key concepts

| Concept | What it means | Where to see it |
|---|---|---|
| **Machine-checkable goal** | Only a test or linter exit code ends the loop. | `verify()` |
| **Stall detection** | Same fingerprint `STALL_LIMIT + 1` times in a row → escalate. | `failure_fingerprint()`, `run_loop()` |
| **Lesson compaction** | A cheap model writes "Attempt N: tried X — failed because Y." | `summarize_failure()` |
| **Focused context** | Include only files mentioned in the failure output, not the whole repo. | `gather_sources()` |
| **Constrained output** | The model returns JSON file replacements, and paths escaping the repo are rejected. | `generate_and_apply()` |
| **Budgets** | `MAX_ATTEMPTS = 4`. The reusable class also caps spend in dollars. | top of file, `online/loop_harness.py` |
| **Experience distillation** | Store a procedure (not data) from a hard win so the next similar task can succeed on the first attempt. | `distill_trajectory()`, `online/experience_distiller.py` |
| **Prompt critic** | A weekly job clusters failures, proposes a sharper system prompt, and merges it **only if evals don't regress**. | `online/prompt_critic.py` |
| **Learned routing** | The routing table updates from outcomes: downgrade to the cheap model only above 95% success with ≥ 20 samples, and keep 10% exploration. | `online/learned_router.py` |

## Files

| File | What it shows |
|---|---|
| `fix_loop.py` | The chapter project: self-correcting fix loop for a repo. |
| `online/loop_harness.py` | `EngineeredLoop`: the same pattern as a reusable class with pluggable verifier/generator, dollar budget, and escalation hook. The demo needs no broken repo. |
| `online/experience_distiller.py` | Distill → store in Chroma → retrieve → one-shot success demo. |
| `online/prompt_critic.py` | Scheduled failure clustering + prompt rewrite gated by evals. |
| `online/learned_router.py` | Self-updating model routing table (simulate 300 tasks or `--live`). |

## What needs to be done

- [ ] `pip install anthropic pytest ruff` and set `ANTHROPIC_API_KEY`.
- [ ] Make a throwaway repo with one or two failing tests (or break a working one).
- [ ] Run `fix_loop.py` and read the lessons after each attempt.
- [ ] Create an unfixable failure (for example a test that asserts `1 == 2`) and confirm the loop **escalates** instead of spinning.
- [ ] Run the same kind of fix twice and see `experience/` being retrieved the second time.
- [ ] Run `learned_router.py` and watch task types move to the cheap model as evidence builds up.

## Run it

```bash
cd ch20_loop_engineering
python fix_loop.py --repo ./orders-service --goal "pytest green, ruff clean"

python online/loop_harness.py
python online/experience_distiller.py
python online/learned_router.py            # --live to route real requests
python online/prompt_critic.py --logs failures.jsonl --prompt system_prompt.txt
```

## Run with Gemma 4 on Ollama

> **One-time setup:** follow *Run everything locally with Gemma 4 on Ollama* in the [root README](../README.md): Ollama running, `gemma4-longctx` created, `.env` set to Option B. Run every command below from the **repo root**.

**Status: ✅ Works.** Every loop component runs on Gemma. Expect **more attempts** per fix than with a frontier model, which makes the escalation and fingerprinting logic easier to observe.

### Setup

`.env` keys: `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_STRONG_MODEL=gemma4-longctx` (patches, distillation, critic), and `ANTHROPIC_FAST_MODEL` (lesson compaction, failure clustering, learned router's cheap tier).

```bash
ollama pull gemma4:e4b                 # .env: ANTHROPIC_FAST_MODEL=gemma4:e4b  (a real cheap/strong split)
pip install anthropic pytest ruff chromadb python-dotenv
```

### Commands

**1. Make a small broken repo** (the bug raises inside `orders.py`, so the loop sends that file to the model):

```bash
mkdir -p /tmp/orders-service && cd /tmp/orders-service
cat > orders.py <<'EOF'
def total(items):
    return sum(i["price"] * i["quantity"] for i in items)
EOF
cat > test_orders.py <<'EOF'
from orders import total

def test_total_uses_qty():
    assert total([{"price": 2.0, "qty": 3}]) == 6.0
EOF
git init -q && git add -A && git commit -qm "broken"
cd -
```

**2. Run the loop** (it writes `experience/` and `escalation_state.json` in the current directory):

```bash
python ch20_loop_engineering/fix_loop.py --repo /tmp/orders-service --goal "pytest green, ruff clean"
```

**3. The other mechanisms:**

```bash
python ch20_loop_engineering/online/loop_harness.py           # toy JSON task
python ch20_loop_engineering/online/learned_router.py         # simulation (no model)
python ch20_loop_engineering/online/learned_router.py --live  # routes real requests to FAST vs STRONG
python ch20_loop_engineering/online/experience_distiller.py
```

To reset the broken repo between runs: `git -C /tmp/orders-service checkout -- .`

### What to expect on Gemma 4

- The patch prompt asks for a **JSON array of full file contents**. Gemma often wraps it in fences, which `parse_json` handles. If it writes prose with no JSON, that attempt fails and becomes a lesson.
- **Context:** failure output, up to 6 source files of 8k chars each, lessons, and a long reply. Use `num_ctx` ≥ 32768 or the loop loses the source files.
- Budget figures in `loop_harness.py` assume Claude prices. Locally, `MAX_ATTEMPTS` and the stall fingerprint do the limiting.
- With `ANTHROPIC_FAST_MODEL=gemma4:e4b`, `learned_router.py --live` shows two local tiers with very different speeds, the same trade-off as Haiku vs Opus.

### Troubleshooting

- **`No module named ruff`**: the verifier runs `python -m ruff`. Install ruff in the same environment.
- **Immediate escalation** ("same failure 3x"): the model keeps writing the same wrong patch. Read the lessons in `escalation_state.json`; this is the loop working as designed. Try `gemma4:26b` as `ANTHROPIC_STRONG_MODEL` to compare.

## Production notes

- A loop that can't fail will burn your budget. Every loop needs a way to give up and hand off to a human.
- Feed forward **lessons**, not transcripts. Attempt 6 should build on what attempts 1–5 learned without paying for their full text.
- Self-modification (prompts, routes) must be **gated by evals** from Ch. 18.
- `fix_loop.py` overwrites files in place, so run it on a clean git working tree.

## Takeaways

1. The verifier decides when the work is done, not the model.
2. Compacted memory makes each retry smarter, and fingerprints tell you when to stop.
3. Distill successful runs into reusable experience and improve prompts and routing from data, always behind an eval gate.

**Prev:** [Ch. 19](../ch19_deployment/README.md) · **Next:** [Chapter 21 — The Harness Engineer](../ch21_harness_engineer/README.md)
