"""
Atlas v0.11 — Personal Assistant with Memory
=============================================
Chapter 11 Project: Agent with persistent memory using Chroma.

Usage:
    python memory_agent.py "What is MCP?"
    python memory_agent.py "Remember that I prefer concise answers"
    python memory_agent.py "How should you format your answers?"

Requires: pip install chromadb anthropic
"""

import json
import sys
from pathlib import Path

import anthropic
import chromadb


sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.config import ANTHROPIC_FAST_MODEL, ANTHROPIC_MODEL  # also loads .env
from shared.llm_utils import parse_json


client = anthropic.Anthropic()

# ── Memory Store ─────────────────────────────────────────────────────

MEMORY_DIR = Path(__file__).parent / "memory_store"
chroma = chromadb.PersistentClient(path=str(MEMORY_DIR))

# Two collections: preferences and knowledge
preferences = chroma.get_or_create_collection("preferences")
knowledge = chroma.get_or_create_collection("knowledge")


def store_memory(text: str, memory_type: str = "knowledge", metadata: dict = None):
    """Store a memory in the appropriate collection."""
    collection = preferences if memory_type == "preference" else knowledge
    import hashlib
    doc_id = hashlib.md5(text.encode()).hexdigest()[:12]
    collection.upsert(
        documents=[text],
        metadatas=[metadata or {"type": memory_type}],
        ids=[doc_id],
    )
    return doc_id


def recall(query: str, n: int = 5) -> list[dict]:
    """Search both memory collections for relevant memories."""
    results = []

    for name, collection in [("preferences", preferences), ("knowledge", knowledge)]:
        try:
            hits = collection.query(query_texts=[query], n_results=min(n, collection.count() or 1))
            if hits["documents"] and hits["documents"][0]:
                for doc, dist in zip(hits["documents"][0], hits["distances"][0]):
                    results.append({
                        "text": doc,
                        "collection": name,
                        "relevance": 1 - dist,  # Convert distance to similarity
                    })
        except Exception:
            pass

    results.sort(key=lambda x: x["relevance"], reverse=True)
    return results[:n]


# ── Memory Extraction ────────────────────────────────────────────────

def extract_memories(user_message: str, assistant_response: str) -> list[dict]:
    """Automatically extract memorable facts from the conversation."""
    response = client.messages.create(
        model=ANTHROPIC_FAST_MODEL,
        system="""Analyze this conversation turn for facts worth remembering.

Return a JSON object with a 'memories' key containing an array of objects.
Each memory object must have 'text' and 'type'.

Types:
- "preference": User's likes, dislikes, or communication style.
- "fact": Concrete information about the user's work, life, or context.

Example: {"memories": [{"text": "User prefers Python", "type": "preference"}]}
If nothing worth remembering, return {"memories": []}

Respond with valid JSON only.""",
        messages=[
            {"role": "user", "content": f"User: {user_message}\nAssistant: {assistant_response}"}
        ],
        max_tokens=300,
    )
    try:
        result = parse_json(response.content[0].text)
        return result.get("memories", [])
    except (json.JSONDecodeError, KeyError):
        return []


# ── Agent ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Atlas, a personal research assistant with memory.

You remember the user's preferences and past conversations.
When relevant memories are available, use them to personalize your response.

If the user explicitly asks you to remember something, confirm that you'll remember it.
"""

def run_memory_agent(message: str) -> str:
    """Run the memory-augmented agent."""
    # 1. Recall relevant memories
    memories = recall(message, n=3)
    memory_context = ""
    if memories:
        memory_lines = [f"- {m['text']} (from: {m['collection']})" for m in memories]
        memory_context = f"\n\n## Relevant Memories\n" + "\n".join(memory_lines)

    # 2. Build prompt with memory context
    system = SYSTEM_PROMPT + memory_context

    # 3. Generate response
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        system=system,
        messages=[
            {"role": "user", "content": message},
        ],
        max_tokens=1024,
    )
    answer = response.content[0].text

    # 4. Extract and store new memories
    new_memories = extract_memories(message, answer)
    for mem in new_memories:
        mem_type = "preference" if mem.get("type") == "preference" else "knowledge"
        doc_id = store_memory(mem["text"], memory_type=mem_type)
        print(f"  💾 Stored memory: {mem['text'][:60]}... (id: {doc_id})")

    return answer


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python memory_agent.py \"Your question or instruction\"")
        print("Examples:")
        print('  python memory_agent.py "Remember that I prefer Python over JavaScript"')
        print('  python memory_agent.py "What programming language should I use?"')
        sys.exit(1)

    message = " ".join(sys.argv[1:])
    print(f"🧠 Atlas v0.11 — Memory Agent")
    print(f"📝 Input: {message}\n")

    # Show recalled memories
    memories = recall(message)
    if memories:
        print("📚 Recalled memories:")
        for m in memories:
            print(f"  • {m['text'][:80]}... (relevance: {m['relevance']:.2f})")
        print()

    answer = run_memory_agent(message)
    print(f"\n🤖 Atlas: {answer}")
