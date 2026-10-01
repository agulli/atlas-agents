# Chapter 21 — The Harness Engineer

> **Atlas v0.21** — teach Atlas to `/learn`: turn a successful session into a reusable `SKILL.md`, **review it like a pull request**, check work with an **adversarial pair**, and give even "creative" work a **machine-checkable goal**.

## TL;DR

The engineer's job shifts from writing the agent's code to designing its **harness**: the loops, verifiers, reviewers, and skills around it. This chapter adds four tools for that:

1. **`/learn`**: read the session's trajectory log, extract the *procedure* (not the data), and write a `SKILL.md` to a **staging** folder.
2. **Skill review gate**: an agent-written skill is executable behavior, so audit it for embedded session data, unpinned installs, and tool scope creep before promoting it.
3. **Adversarial pair**: a builder produces, an adversary tries to break it, and humans review only the **disagreements**.
4. **Prose verifier**: marketing copy gets a pass/fail check too (reading grade, "you"-focus, passive voice, buzzwords, character limits), and none of it needs a model.

```
session.jsonl ─▶ learn_command.py ─▶ staging/<skill>/SKILL.md ─▶ skill_reviewer.py ─▶ human ─▶ skills/ (Ch. 9 loader)
                  (successful sessions only)                      (exit 1 on findings)
```

## Key concepts

| Concept | What it means | Where to see it |
|---|---|---|
| **Trajectory log** | JSONL events: `task`, `tool_call`, `tool_result`, `correction`, `outcome`. | `learn_command.py` docstring |
| **Procedure, not data** | Remove this session's figures, dates, and names. A skill with last quarter's numbers baked in will keep reporting them. | `DISTILL_PROMPT` |
| **Corrections become rules** | Each user correction becomes an explicit constraint in the skill. | `DISTILL_PROMPT` |
| **Success-only learning** | Refuses to distill unless `outcome.status == "success"`. | `main()` |
| **Staging + human gate** | Skills go to `staging/`, and only a human moves them to the trusted `skills/` folder. | `STAGING_DIR` |
| **Skill linting** | Flags embedded session data, unpinned `pip install`, and tools the task never needed. Wire it into CI. | `online/skill_reviewer.py` |
| **Review the disagreements** | The adversary gets no credit for agreeing. Track its block rate, because an adversary that never blocks is just a second bill. | `online/adversarial_pair.py` → `rubber_stamp_check()` |
| **Verifiable creative goals** | Flesch-Kincaid grade < 8, I/we-to-you ratio < 0.3, passive-voice regex, buzzword blocklist, platform limits (Google 90, Twitter 280, LinkedIn 3000). | `online/prose_verifier.py` |

## Files

| File | What it shows |
|---|---|
| `learn_command.py` | The chapter project: `/learn` → staged `SKILL.md`. |
| `online/skill_reviewer.py` | Standard-library linter for staged skills (exit code 0 = clean, 1 = findings). |
| `online/adversarial_pair.py` | Builder/adversary harness with block-rate stats. |
| `online/prose_verifier.py` | Standard-library prose verifier to use as a Ch. 20 loop verifier. |

## What needs to be done

- [ ] `pip install anthropic` and set `ANTHROPIC_API_KEY` (the reviewer and prose verifier need nothing).
- [ ] Write a small `session.jsonl` by hand (task → tool calls → one correction → success outcome) and run `/learn` on it.
- [ ] Run `skill_reviewer.py` on the result. Add a hardcoded date or an unpinned `pip install` and confirm it's flagged.
- [ ] Run the adversarial pair on a tricky function spec and read only the disagreements.
- [ ] Put `prose_verifier.py` in as the verifier of the Ch. 20 `EngineeredLoop` to generate ad copy that passes all checks.

## Run it

```bash
cd ch21_harness_engineer
python learn_command.py --session logs/session_0713.jsonl
python online/skill_reviewer.py staging/                       # --allowed-tools read,bash
python online/adversarial_pair.py "Write a Python function that parses ISO-8601 durations"
echo "Our seamless platform empowers you..." | python online/prose_verifier.py - --platform google
```

## Run with Gemma 4 on Ollama

> **One-time setup:** follow *Run everything locally with Gemma 4 on Ollama* in the [root README](../README.md): Ollama running, `gemma4-longctx` created, `.env` set to Option B. Run every command below from the **repo root**.

**Status: ✅ Works.** `/learn` and the adversarial pair run on Gemma. `skill_reviewer.py` and `prose_verifier.py` make no model calls.

### Setup

`.env` keys: `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_STRONG_MODEL=gemma4-longctx`.

```bash
pip install anthropic python-dotenv
```

### Commands

**1. Write a small trajectory log** (normally written by the Ch. 15 harness):

```bash
mkdir -p logs && cat > logs/session_demo.jsonl <<'EOF'
{"type": "task", "content": "Summarize Q3 revenue from sales.csv into a markdown table by region"}
{"type": "tool_call", "tool": "read_file", "input": {"path": "sales.csv"}}
{"type": "tool_result", "content": "region,revenue\nEMEA,120000\nAPAC,95000\nNA,210000"}
{"type": "correction", "content": "Always sort regions by revenue descending and include a total row"}
{"type": "tool_call", "tool": "write_file", "input": {"path": "summary.md"}}
{"type": "outcome", "status": "success", "attempt": 2}
EOF
```

**2. Distill a skill and review it:**

```bash
python ch21_harness_engineer/learn_command.py --session logs/session_demo.jsonl     # → staging/<name>/SKILL.md
python ch21_harness_engineer/online/skill_reviewer.py staging/ --allowed-tools read_file,write_file
```

**3. Adversarial pair and prose verifier:**

```bash
python ch21_harness_engineer/online/adversarial_pair.py "Write a Python function that parses ISO-8601 durations"
echo "Our seamless platform empowers you to leverage synergies." | python ch21_harness_engineer/online/prose_verifier.py - --platform google
```

### What to expect on Gemma 4

- **Check the distilled skill for leaked data.** Smaller models are more likely to copy session values (`EMEA 120000`, "Q3") into the procedure despite the instruction not to. `skill_reviewer.py` should flag them, which is why the review step exists.
- When builder and adversary are the **same local model**, it tends to agree with itself. Give the adversary a different model to get real disagreement: in `adversarial_pair.py`, change `model=MODEL` inside `attack()` to another local model, e.g. `model="gemma4:e4b"`.

### Troubleshooting

- **`Refusing to distill`**: the log's last `outcome` isn't `success`. Only successful sessions become skills.
- **The adversary returns no verdict**: its reply had no JSON. Run again, or use a larger model for the adversary.

## Production notes

- Never let the agent write straight into its trusted skill folder. Keep the staging + review step.
- Pin every package version inside skills, since instruction files keep running long after they're written.
- If the adversary's block rate is zero, fix its prompt or remove it.

## Takeaways

1. The harness engineer designs the system around the model: loops, verifiers, reviewers, skills.
2. Agents can learn new skills, but only through the same review a colleague's code would get.
3. Almost any goal, even a creative one, can be given a machine-checkable finish line.

**Prev:** [Ch. 20](../ch20_loop_engineering/README.md) · **Next:** [Chapter 22 — Capstone: Atlas](../ch22_capstone/README.md)
