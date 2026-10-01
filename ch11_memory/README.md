# Chapter 11 — Memory and Agentic RAG

> **Atlas v0.11** — a personal assistant with **persistent memory** in Chroma: it recalls before answering and extracts new memories afterward.

## TL;DR

LLMs are stateless, so every call starts from zero. **Memory** is retrieval: store useful facts as embeddings, pull back the most relevant ones for each new message, and put them in the prompt. The loop is **recall → respond → extract → store**. Keeping memory *useful* over time takes more: chunking that respects document structure, **decay** so stale facts fade, and **graphs** for questions that need several hops through relationships.

```
message ─▶ recall(top-k from Chroma) ─▶ system prompt + "## Relevant Memories" ─▶ LLM answer
                                                                                 │
                     Chroma ◀── store ◀── extract_memories (Haiku, JSON) ◀───────┘
```

## Key concepts

| Concept | What it means | Where to see it |
|---|---|---|
| **Memory types** | Separate collections for **preferences** (style, likes) and **knowledge** (facts about the user's work). | `preferences`, `knowledge` collections |
| **Recall** | Vector-search both collections, convert distance to relevance, and keep the top-k. | `recall()` |
| **Automatic extraction** | A cheap model reads each turn and returns `{"memories": [...]}` JSON worth keeping. | `extract_memories()` |
| **Idempotent writes** | Doc id = hash of the text, and `upsert` prevents duplicates. | `store_memory()` |
| **Persistent store** | `chromadb.PersistentClient` writes to `memory_store/`, so memory survives restarts. | top of file |
| **Structure-aware chunking** | Split on Markdown headers instead of character counts, and keep the header path as metadata. | `online/adaptive_chunker.py` |
| **Memory decay / salience** | Score = similarity × recency × access frequency, and prune below a threshold. | `online/memory_decay.py` |
| **Graph RAG** | Multi-hop questions ("who funds the project Bob works on?") are one Cypher query on a knowledge graph but are hard for vector search. | `online/graph_rag_neo4j.py` |

## Files

| File | What it shows |
|---|---|
| `memory_agent.py` | The chapter project: memory-augmented Claude agent on Chroma. |
| `online/adaptive_chunker.py` | Side-by-side comparison of naive and header-aware chunking (no API key needed). |
| `online/memory_decay.py` | Time-weighted salience scoring and pruning (no API key needed). |
| `online/graph_rag_neo4j.py` | Knowledge-graph RAG with multi-hop Cypher on Neo4j. |

## What needs to be done

- [ ] `pip install chromadb anthropic` and set `ANTHROPIC_API_KEY`.
- [ ] Run the three demo commands below **in order** and check that the third answer uses the preference from the second.
- [ ] Look at what got stored. Did the extractor keep anything it shouldn't have (PII, one-off details)?
- [ ] Run `adaptive_chunker.py` and find a chunk the naive splitter broke.
- [ ] Run `memory_decay.py` and tune the half-life until old memories fade the way you want.
- [ ] (Stretch) Start Neo4j in Docker and run the graph RAG demo.

## Run it

```bash
cd ch11_memory
python memory_agent.py "What is MCP?"
python memory_agent.py "Remember that I prefer concise answers"
python memory_agent.py "How should you format your answers?"

python online/adaptive_chunker.py
python online/memory_decay.py
```

## Run with Gemma 4 on Ollama

> **One-time setup:** follow *Run everything locally with Gemma 4 on Ollama* in the [root README](../README.md): Ollama running, `gemma4-longctx` created, `.env` set to Option B. Run every command below from the **repo root**.

**Status: ✅ Fully local.** The answer and the memory extractor run on Gemma via the Anthropic-compatible endpoint, and **Chroma embeds locally** with its built-in default embedding model, which needs no API key.

### Setup

`.env` keys: `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL=gemma4-longctx` (answers), `ANTHROPIC_FAST_MODEL` (memory extraction).

```bash
pip install chromadb anthropic python-dotenv
```

The first run downloads Chroma's small embedding model (about 80 MB) once; after that it works offline.

### Commands

Run them **in order**, because memory persists in `ch11_memory/memory_store/` between runs:

```bash
python ch11_memory/memory_agent.py "What is MCP?"
python ch11_memory/memory_agent.py "Remember that I prefer concise answers"
python ch11_memory/memory_agent.py "How should you format your answers?"     # should mention "concise"

python ch11_memory/online/adaptive_chunker.py     # no LLM
python ch11_memory/online/memory_decay.py         # no LLM
```

Reset memory with `rm -rf ch11_memory/memory_store`.

### What to expect on Gemma 4

- The extractor must return `{"memories": [...]}`. Gemma often adds fences or a lead-in sentence, which `parse_json` handles. If the 💾 "stored" line never appears, the reply had no JSON at all; print `response.content[0].text` in `extract_memories()`.
- Gemma tends to **over-extract** (storing trivia like "User asked about MCP"). Tighten the extractor prompt with an explicit "do NOT store questions the user asked" rule.
- Memory makes the most sense fully local: none of the personal data leaves your machine.

### Troubleshooting

- **Chroma tries to reach the internet on every run**: only the first run downloads the model. If you're offline from the start, pre-download it on a connected machine (it's cached under `~/.cache/chroma`).

## Production notes

- Memory is a **privacy surface**. Decide what may be stored and how users can delete it.
- Without decay, retrieval quality drops as the store grows.
- Use vectors for "similar to", and a graph for "related to via X".
- Chapter 20 reuses this retrieval pattern for *experience*: stored lessons from past successful runs.

## Takeaways

1. Memory = storage + retrieval + injection into the prompt.
2. What you extract matters more than what you store. Be selective.
3. Chunking, decay, and graphs are what keep memory useful at scale.

**Prev:** [Ch. 10](../ch10_claude_code_antigravity/README.md) · **Next:** [Chapter 12 — Code Execution and Sandbox Agents](../ch12_sandboxes/README.md)
