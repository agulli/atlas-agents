"""
write_policy.py — Memory extraction and post-processing as two steps.

Production memory pipelines pair an extraction step (identify candidate facts
from a conversation) with a separate post-processing step (deduplicate, resolve
conflicts, decide ADD / UPDATE / DELETE / NOOP against existing memories).
Treating these as one operation hides the timing tradeoff that actually
matters in production.

This file is an educational demonstration. It runs the same conversation
through two extraction timings, speaker-turn vs. session-level, so the cost
and quality differences are directly comparable.

Concepts demonstrated:
  1. Extraction and post-processing as two distinct steps.
  2. ADD / UPDATE / DELETE / NOOP routing (Mem0 pattern).
  3. Speaker-turn vs. session-level extraction tradeoff.

The demo surfaces a real tradeoff, not a verdict. Session-level extraction
is a strong default for most conversational agents because the active
context window already handles within-session needs. Turn-level extraction
is the right choice when real-time cross-session persistence matters, for
example agents that need to recall a fact mid-conversation across sessions
interleaved within seconds. Both modes are demonstrated side by side so
readers can pick the appropriate default for their product.

References:
  - Mem0 architecture paper: https://arxiv.org/abs/2504.19413

Usage:
    python write_policy.py

Requires: pip install anthropic
"""

import json
import re
from dataclasses import dataclass, field
from typing import Literal

import anthropic

client = anthropic.Anthropic()


def parse_json_response(text: str) -> dict:
    """Parse JSON from a Claude response.

    Claude often wraps structured output in markdown fences (```json ... ```)
    even when the system prompt requests JSON only. This helper extracts the
    outermost {...} block and parses it. Returns {} on failure.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}

# ── Models ─────────────────────────────────────────────────────────────

EXTRACT_MODEL = "claude-haiku-4-5"
DECIDE_MODEL = "claude-haiku-4-5"

# ── Fixture (exported; imported by memory_eval.py) ─────────────────────

FIXTURE_CONVERSATION = [
    {
        "speaker": "user",
        "text": (
            "I'm a senior backend engineer at a fintech in NYC. Been there 4 years. "
            "Thinking about moving to a staff role somewhere else, but I'm not sure if I'm ready."
        ),
    },
    {
        "speaker": "assistant",
        "text": "What's making you consider the move now specifically?",
    },
    {
        "speaker": "user",
        "text": (
            "Honestly the growth path here is capped. My manager told me last review that there's "
            "no staff slot opening this year. I also want to work somewhere with more ML "
            "infrastructure exposure, that's where I want my next 5 years to go."
        ),
    },
    {
        "speaker": "assistant",
        "text": "Have you started looking, or is this still in the thinking-about-it stage?",
    },
    {
        "speaker": "user",
        "text": (
            "I've had two preliminary chats: one with Anthropic, one with a series-B startup. "
            "Both went well. I need to make a decision in the next 6 weeks because my partner "
            "and I are signing on a house and we want stability before that."
        ),
    },
    {
        "speaker": "assistant",
        "text": "Got it. Want me to help you frame the tradeoffs between a frontier lab and an early-stage startup for your situation?",
    },
]

# ── Dataclasses ────────────────────────────────────────────────────────


@dataclass
class Memory:
    id: str
    text: str
    decisions: list[str] = field(default_factory=list)


@dataclass
class Decision:
    operation: Literal["ADD", "UPDATE", "DELETE", "NOOP"]
    candidate: str
    target_id: str | None
    reasoning: str


# ── Step 1: Extract candidate facts from conversation turns ────────────


def extract_candidates(turns: list[dict]) -> list[str]:
    """Pull atomic, source-grounded candidate facts from a slice of turns.

    This is the extraction step in isolation. The output is a list of
    candidate facts. Nothing is stored yet and no conflict resolution has
    happened. Post-processing is the next step.
    """
    transcript = "\n".join(f"{t['speaker']}: {t['text']}" for t in turns)
    response = client.messages.create(
        model=EXTRACT_MODEL,
        max_tokens=500,
        system=(
            "Extract atomic factual claims about the user from the conversation.\n\n"
            "Each claim should:\n"
            "  1. Be a single fact (do not join multiple facts with 'and').\n"
            "  2. Stand alone (no pronouns or vague references).\n"
            "  3. Be source-grounded (only claims supported by the transcript).\n\n"
            'Return JSON: {"facts": ["fact 1", "fact 2", ...]}\n'
            "Respond with valid JSON only."
        ),
        messages=[{"role": "user", "content": transcript}],
    )
    return parse_json_response(response.content[0].text).get("facts", [])


# ── Step 2: Post-process (ADD / UPDATE / DELETE / NOOP) ────────────────


def post_process(candidate: str, existing: list[Memory]) -> Decision:
    """Decide how to integrate a candidate fact relative to existing memories.

    Mirrors Mem0's four-operation pattern (arXiv 2504.19413):
        ADD:    a genuinely new fact, not present in the store.
        UPDATE: refines or corrects an existing memory; needs target_id.
        DELETE: contradicts an existing memory; needs target_id.
        NOOP:   duplicate or not worth storing.

    In production this step consults the top-k semantically similar
    memories via embedding search rather than the full store. The
    structure of the decision is what matters pedagogically; the retrieval
    optimization is a separate concern.
    """
    existing_block = (
        "\n".join(f"  ({m.id}) {m.text}" for m in existing) if existing else "  (none yet)"
    )
    response = client.messages.create(
        model=DECIDE_MODEL,
        max_tokens=400,
        system=(
            "You decide how to integrate a new candidate fact into a memory store.\n\n"
            f"Existing memories:\n{existing_block}\n\n"
            f'Candidate fact: "{candidate}"\n\n'
            "Return JSON with this exact shape:\n"
            '  {"operation": "ADD" | "UPDATE" | "DELETE" | "NOOP",\n'
            '   "target_id": "<id of existing memory, or null>",\n'
            '   "reasoning": "<one sentence>"}\n\n'
            "Rules:\n"
            "  1. ADD if the candidate is a genuinely new fact.\n"
            "  2. UPDATE if it refines or corrects an existing memory; set target_id.\n"
            "  3. DELETE if it contradicts an existing memory; set target_id.\n"
            "  4. NOOP if it duplicates an existing memory or is not worth storing.\n\n"
            "Respond with valid JSON only."
        ),
        messages=[{"role": "user", "content": "Decide."}],
    )
    data = parse_json_response(response.content[0].text)
    if "operation" not in data:
        return Decision(
            operation="NOOP",
            candidate=candidate,
            target_id=None,
            reasoning="parse_error",
        )
    return Decision(
        operation=data["operation"],
        candidate=candidate,
        target_id=data.get("target_id"),
        reasoning=data.get("reasoning", ""),
    )


# ── Apply a decision to the in-memory store ────────────────────────────


def apply_decision(decision: Decision, store: dict[str, Memory]) -> None:
    """Mutate the store in-place based on the post-processing decision.

    The store is a plain dict for educational clarity. In production this
    is Chroma, Qdrant, or a managed memory service.
    """
    if decision.operation == "ADD":
        new_id = f"m{len(store) + 1}"
        store[new_id] = Memory(
            id=new_id,
            text=decision.candidate,
            decisions=[f"ADD: {decision.reasoning}"],
        )
    elif decision.operation == "UPDATE" and decision.target_id in store:
        store[decision.target_id].text = decision.candidate
        store[decision.target_id].decisions.append(f"UPDATE: {decision.reasoning}")
    elif decision.operation == "DELETE" and decision.target_id in store:
        store[decision.target_id].decisions.append(f"DELETE: {decision.reasoning}")
        del store[decision.target_id]
    # NOOP: intentionally do nothing.


# ── Mode 1: Turn-level extraction (Mem0-style) ─────────────────────────


def run_turn_level(conversation: list[dict]) -> tuple[dict[str, Memory], dict]:
    """Extract after each user turn, post-process immediately.

    Cost:   1 extract call + N post-process calls per user turn.
    Effect: each per-turn extraction sees only a narrow window, so candidates
            can be redundant across turns and multi-turn facts may be missed
            unless post-processing reconciles them via UPDATE/NOOP routing.

    Right choice when real-time cross-session persistence matters, for
    example an agent that needs to recall a fact mid-conversation across
    sessions interleaved within seconds. Production systems sometimes also
    use turn-level to surface facts as soon as they appear (e.g. safety
    flags) where any delay would degrade the product.
    """
    store: dict[str, Memory] = {}
    counts = {"extract_calls": 0, "decide_calls": 0, "ADD": 0, "UPDATE": 0, "DELETE": 0, "NOOP": 0}

    for i, turn in enumerate(conversation):
        if turn["speaker"] != "user":
            continue
        window = conversation[max(0, i - 1) : i + 1]
        candidates = extract_candidates(window)
        counts["extract_calls"] += 1
        for cand in candidates:
            decision = post_process(cand, list(store.values()))
            counts["decide_calls"] += 1
            counts[decision.operation] += 1
            apply_decision(decision, store)
    return store, counts


# ── Mode 2: Session-level extraction (Zep-style, recommended default) ──


def run_session_level(conversation: list[dict]) -> tuple[dict[str, Memory], dict]:
    """Extract once at end-of-session over the full transcript.

    Cost:   1 extract call total + N post-process calls (one per candidate).
    Effect: sees the full conversational arc, produces cleaner atomic
            candidates, fewer NOOPs.

    Why this works as a default for most conversational agents: the active
    context window already captures within-session needs as short-term
    memory, so deferring long-term extraction to session-end has minimal
    conversation-quality impact. Coupling this to a context-compaction event
    is natural, since both fire at the same boundary. Products that need
    real-time cross-session recall should prefer turn-level instead.
    """
    store: dict[str, Memory] = {}
    counts = {"extract_calls": 0, "decide_calls": 0, "ADD": 0, "UPDATE": 0, "DELETE": 0, "NOOP": 0}

    candidates = extract_candidates(conversation)
    counts["extract_calls"] = 1
    for cand in candidates:
        decision = post_process(cand, list(store.values()))
        counts["decide_calls"] += 1
        counts[decision.operation] += 1
        apply_decision(decision, store)
    return store, counts


# ── Demo ───────────────────────────────────────────────────────────────


def print_summary(label: str, store: dict[str, Memory], counts: dict) -> None:
    print(f"\n{label}")
    print(f"  Extract calls: {counts['extract_calls']}")
    print(f"  Decide calls:  {counts['decide_calls']}")
    print(
        f"  Decisions:     ADD={counts['ADD']}, UPDATE={counts['UPDATE']}, "
        f"DELETE={counts['DELETE']}, NOOP={counts['NOOP']}"
    )
    print(f"  Final store ({len(store)} memories):")
    for m in store.values():
        print(f"    - {m.text}")


def main():
    print("write_policy.py — extract / post-process pipeline")
    print(f"Fixture: {len(FIXTURE_CONVERSATION)}-turn career-coaching conversation.")

    print("\n" + "─" * 72)
    print("Mode 1: TURN-LEVEL extraction (Mem0-style)")
    print("─" * 72)
    turn_store, turn_counts = run_turn_level(FIXTURE_CONVERSATION)
    print_summary("Result:", turn_store, turn_counts)

    print("\n" + "─" * 72)
    print("Mode 2: SESSION-LEVEL extraction (Zep-style, recommended default)")
    print("─" * 72)
    session_store, session_counts = run_session_level(FIXTURE_CONVERSATION)
    print_summary("Result:", session_store, session_counts)

    print("\n" + "═" * 72)
    print("TRADEOFF")
    print("═" * 72)
    print(f"{'Mode':<20}{'extract':>10}{'decide':>10}{'memories':>12}")
    print(
        f"{'turn-level':<20}{turn_counts['extract_calls']:>10}"
        f"{turn_counts['decide_calls']:>10}{len(turn_store):>12}"
    )
    print(
        f"{'session-level':<20}{session_counts['extract_calls']:>10}"
        f"{session_counts['decide_calls']:>10}{len(session_store):>12}"
    )
    print(
        "\nTurn-level fires the extractor on each user turn and can produce\n"
        "redundant candidates because each window is narrow. It is the right\n"
        "choice when real-time cross-session persistence matters.\n"
        "Session-level extracts once at end-of-session over the full arc and\n"
        "is the cleaner default for most conversational agents, since the\n"
        "active context window already handles within-session needs as\n"
        "short-term memory. Pick the mode that fits the product."
    )


if __name__ == "__main__":
    main()
