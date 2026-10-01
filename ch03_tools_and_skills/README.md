# Chapter 3 — Tools, Skills, and Structured Outputs

> **Atlas v0.3** — move tools out of the agent loop into pluggable **Skills** managed by a **SkillRegistry**.

## TL;DR

In Chapter 1 the tools were hard-coded dicts. That doesn't scale. A **Skill** is a class that bundles related tools (web, files, code) with their JSON schemas and one `execute()` method. A **SkillRegistry** collects the skills, hands every tool schema to the model, and routes each tool call to the right skill. The agent loop stays the same size however many tools you add.

```
            ┌─────────── SkillRegistry ───────────┐
LLM ─call─▶ │ WebSkill   FileSkill   CodeSkill ...│ ─▶ result string
            └─────────────────────────────────────┘
```

## Key concepts

| Concept | What it means | Where to see it |
|---|---|---|
| **Skill base class** | Each skill declares its tools (`get_tools()`) and implements `execute(name, args)`. | `shared/skills.py` → `Skill` |
| **SkillRegistry** | `register()` skills, `get_all_tools()` for the LLM, `execute_tool()` to dispatch. | `shared/skills.py` → `SkillRegistry` |
| **Built-in skills** | `WebSkill` (search/read), `FileSkill` (sandboxed to a `base_dir`), `CodeSkill` (Python subprocess with a timeout). | `shared/skills.py` |
| **Safe tool design** | Truncate large responses, set timeouts, return errors as strings, restrict mutations. | `online/api_skill.py`, `online/database_skill.py` |
| **Declarative skills** | Skills written as Markdown with YAML frontmatter (`description`) and loaded at runtime, so there is no Python to write. This leads into Ch. 9. | `online/skill_auto_discovery.py`, `shared/declarative_skills/` |
| **Structured outputs** | Tool schemas are JSON Schema, so the model's arguments come back as parseable JSON. | tool schemas in `shared/skills.py` |

## What you build

`atlas_v03.py` — the Ch. 1 ReAct loop, but tools come from `registry.get_all_tools()` and calls go through `registry.execute_tool()`. The default task researches LangGraph news and **saves a Markdown file** to `./workspace` using `FileSkill`.

## Files

| File | What it shows |
|---|---|
| `atlas_v03.py` | The chapter project: modular agent built on `SkillRegistry`. |
| `../shared/skills.py` | The `Skill`, `SkillRegistry`, `WebSkill`, `FileSkill`, and `CodeSkill` implementations. |
| `online/api_skill.py` | `RestAPISkill`: wraps any REST endpoint with timeouts and truncates responses at 2,000 chars. |
| `online/database_skill.py` | A read-only SQL tool that blocks mutating keywords. **This is a teaching example, not real security**; use a read-only DB user in production. |
| `online/skill_auto_discovery.py` | Parses YAML frontmatter from `shared/declarative_skills/*.md` into a skill list. |

## What needs to be done

- [ ] Set `OPENAI_API_KEY` in `.env`.
- [ ] Run the default task and check that `workspace/langgraph_news.md` gets written.
- [ ] Read `shared/skills.py` and write a new `Skill` subclass (for example `DateTimeSkill`), then register it in `atlas_v03.py`. The loop needs no changes.
- [ ] Run `skill_auto_discovery.py` against `shared/declarative_skills/` and inspect the loaded descriptions.
- [ ] Try to bypass `database_skill.py` (hint: comments, casing, `WITH ... DELETE`). This shows why keyword blocking isn't enough.

## Run it

```bash
cd ch03_tools_and_skills
python atlas_v03.py "Summarize the latest changes in the LangGraph library"
```

## Run with Gemma 4 on Ollama

> **One-time setup:** follow *Run everything locally with Gemma 4 on Ollama* in the [root README](../README.md): Ollama running, `gemma4-longctx` created, `.env` set to Option B. Run every command below from the **repo root**.

**Status: ✅ Works.** Same OpenAI-compatible tool-calling loop as Ch. 1, with tools from `SkillRegistry`.

### Setup

`.env` keys: `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL=gemma4-longctx`.

```bash
pip install openai python-dotenv pyyaml
```

### Commands

```bash
python ch03_tools_and_skills/atlas_v03.py "Summarize the latest changes in the LangGraph library and save them to langgraph_news.md"
ls workspace/            # FileSkill writes here (relative to where you ran the command)

# Declarative skills (no model call)
python -c "import sys; sys.path.insert(0,'ch03_tools_and_skills/online'); \
from skill_auto_discovery import dynamically_load_skills as d; \
[print(s['name'], '-', s['description']) for s in d('shared/declarative_skills/')]"
```

### What to expect on Gemma 4

- The registry offers 6 tools (`web_search`, `web_read_page`, `file_read`, `file_write`, `file_list`, `code_execute`). A 12B model chooses among 6 well-described tools reliably. If it confuses them, the fix is better tool `description`s, not a bigger model.
- `code_execute` runs Python **on your machine** (subprocess with a timeout). That is the same as with a cloud model, but worth remembering.
- Web tools still need internet access.

### Troubleshooting

- **The file isn't saved**: Gemma sometimes says "I saved the file" without calling `file_write`. Ask explicitly: "use the file_write tool to save…".

## Production notes

- The tool **description** is a prompt. Vague descriptions cause wrong tool choices.
- Every tool needs a timeout, an output size cap, and an error path.
- Enforce permissions (read-only, sandboxed paths) *in code*, not in the prompt.

## Takeaways

1. Keep the loop small and move capabilities into skills.
2. A registry lets you add or remove capabilities without touching agent logic.
3. Skills can be code (Python classes) or content (Markdown + YAML). Chapter 9 goes further with the second.

**Prev:** [Ch. 2](../ch02_prompt_architecture/README.md) · **Next:** [Chapter 4 — Handoffs and Routines](../ch04_handoffs/README.md)
