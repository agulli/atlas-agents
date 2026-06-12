"""
memory_eval.py — Evaluating the quality of extracted memory.

Mem0, Zep, and similar libraries extract memories from conversations
automatically. How does a reader know the extraction is any good on
their own data? This file is an educational demonstration of three
metrics from the literature that answer that question at the extraction
layer specifically, distinct from end-to-end QA benchmarks.

Metrics:
  - Faithfulness        (RAGAS):    are the extracted memories actually
                                    supported by the source conversation?
  - Decontextualization (Claimify): can each memory stand alone, without
                                    referring back to the source?
  - Coverage            (Claimify): are any salient facts from the source
                                    missing from the extracted set?

This is illustrative, not authoritative. Every metric uses a single
LLM-as-judge call pattern for clarity. Production systems would
parallelize, ensemble across judges, and calibrate against human labels.

References:
  - Claimify (Metropolitansky & Larson, 2025): https://arxiv.org/abs/2502.10855
  - RAGAS Faithfulness:
        https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/

Usage:
    python memory_eval.py

Requires: pip install anthropic
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

# Shared fixture conversation and JSON parsing helper live in write_policy.py.
sys.path.insert(0, str(Path(__file__).parent))
from write_policy import FIXTURE_CONVERSATION, parse_json_response

client = anthropic.Anthropic()

# ── Models ──────────────────────────────────────────────────────────────

JUDGE_MODEL = "claude-haiku-4-5"

# ── Dataclasses ─────────────────────────────────────────────────────────


@dataclass
class FaithfulnessVerdict:
    memory: str
    supported: bool
    reasoning: str


@dataclass
class DecontextVerdict:
    memory: str
    self_contained: bool
    unresolved: list[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class CoverageVerdict:
    captured_count: int
    missing: list[str] = field(default_factory=list)
    score: float = 0.0


@dataclass
class EvalResult:
    faithfulness: float
    decontextualization: float
    coverage: float
    faithfulness_details: list[FaithfulnessVerdict]
    decontext_details: list[DecontextVerdict]
    coverage_details: CoverageVerdict


# ── Shared judge primitive ──────────────────────────────────────────────


def judge(system_prompt: str, user_payload: str) -> dict:
    """Single LLM-as-judge call. All three metrics route through this.

    Returns the parsed JSON verdict. Uses claude-haiku-4-5 because judge
    calls are frequent and the task is well-defined.
    """
    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=500,
        system=system_prompt,
        messages=[{"role": "user", "content": user_payload}],
    )
    return parse_json_response(response.content[0].text)


# ── Helper: render source conversation as a transcript ──────────────────


def format_transcript(conversation: list[dict]) -> str:
    return "\n".join(f"{t['speaker']}: {t['text']}" for t in conversation)


# ── Metric 1: Faithfulness (RAGAS) ──────────────────────────────────────


def score_faithfulness(
    memories: list[str], source_conversation: list[dict]
) -> tuple[float, list[FaithfulnessVerdict]]:
    """For each memory, ask: is this entailed by the source?

    Mirrors RAGAS's claim-level NLI step. RAGAS first decomposes a
    response into atomic claims; here we treat each memory as already
    atomic. If a memory bundles multiple facts (e.g. 'X and Y'), a
    production implementation would re-decompose before the NLI call.

    Score = supported / total.
    """
    transcript = format_transcript(source_conversation)
    verdicts: list[FaithfulnessVerdict] = []
    for memory in memories:
        verdict = judge(
            system_prompt=(
                "You evaluate whether a single extracted memory is supported by "
                "a source conversation.\n\n"
                f"Source conversation:\n{transcript}\n\n"
                "A memory is supported only if the source conversation directly "
                "states it or clearly entails it. Do not infer beyond the source.\n\n"
                "Return JSON:\n"
                '  {"supported": true | false, "reasoning": "<one sentence>"}\n\n'
                "Respond with valid JSON only."
            ),
            user_payload=f'Extracted memory: "{memory}"',
        )
        verdicts.append(
            FaithfulnessVerdict(
                memory=memory,
                supported=bool(verdict.get("supported", False)),
                reasoning=verdict.get("reasoning", ""),
            )
        )
    supported = sum(1 for v in verdicts if v.supported)
    score = supported / len(verdicts) if verdicts else 1.0
    return score, verdicts


# ── Metric 2: Decontextualization (Claimify) ────────────────────────────


def score_decontextualization(
    memories: list[str],
) -> tuple[float, list[DecontextVerdict]]:
    """For each memory in isolation, ask: does it stand alone?

    Claimify methodology: a claim is decontextualized if it can be
    understood and evaluated without the source document. Failure modes
    are unresolved referents (pronouns, vague nouns, undefined acronyms,
    ambiguous quantifiers).

    Score = self_contained / total.
    """
    verdicts: list[DecontextVerdict] = []
    for memory in memories:
        verdict = judge(
            system_prompt=(
                "You evaluate whether a single extracted memory can stand on its own,\n"
                "without referring back to the conversation it came from.\n\n"
                "A memory passes if it is self-contained. It fails if it contains:\n"
                "  1. pronouns with no clear antecedent (this, that, they, it).\n"
                "  2. vague nouns (the project, the company) with no name attached.\n"
                "  3. undefined acronyms or ambiguous quantifiers (recently, often).\n\n"
                "Return JSON:\n"
                '  {"self_contained": true | false,\n'
                '   "unresolved": ["<flagged token>", ...],\n'
                '   "reasoning": "<one sentence>"}\n\n'
                "Respond with valid JSON only."
            ),
            user_payload=f'Memory in isolation: "{memory}"',
        )
        verdicts.append(
            DecontextVerdict(
                memory=memory,
                self_contained=bool(verdict.get("self_contained", False)),
                unresolved=verdict.get("unresolved", []),
                reasoning=verdict.get("reasoning", ""),
            )
        )
    passed = sum(1 for v in verdicts if v.self_contained)
    score = passed / len(verdicts) if verdicts else 1.0
    return score, verdicts


# ── Metric 3: Coverage (missing-fact detection) ─────────────────────────


def score_coverage(
    memories: list[str], source_conversation: list[dict]
) -> CoverageVerdict:
    """Identify salient facts in the source that the extraction missed.

    Practitioner's framing of coverage: not 'recall against a gold set',
    but 'what did we miss?'. One judge call returns the list of missing
    salient facts. Score = captured / (captured + missed).

    Tradeoff: the judge's notion of 'salient' is its own opinion, not
    ground truth. In production, periodic human spot-checks on the
    judge's missing-fact lists calibrate the metric to the domain.
    """
    transcript = format_transcript(source_conversation)
    memory_block = "\n".join(f"  - {m}" for m in memories) if memories else "  (none)"
    verdict = judge(
        system_prompt=(
            "You audit an extracted memory set against a source conversation,\n"
            "identifying any salient facts the extraction missed.\n\n"
            f"Source conversation:\n{transcript}\n\n"
            f"Extracted memories:\n{memory_block}\n\n"
            "Only include facts a memory system should remember: user attributes,\n"
            "decisions, constraints, preferences, plans. Ignore small talk.\n\n"
            "Return JSON listing salient facts NOT expressed by any extracted memory:\n"
            '  {"missing": ["fact 1", "fact 2", ...]}\n\n'
            "Respond with valid JSON only."
        ),
        user_payload="Identify missing facts.",
    )
    missing = verdict.get("missing", [])
    captured = len(memories)
    total = captured + len(missing)
    score = captured / total if total > 0 else 1.0
    return CoverageVerdict(captured_count=captured, missing=missing, score=score)


# ── Top-level: run all three metrics ────────────────────────────────────


def evaluate(memories: list[str], source_conversation: list[dict]) -> EvalResult:
    """Run all three metrics over a single extracted memory set."""
    f_score, f_details = score_faithfulness(memories, source_conversation)
    d_score, d_details = score_decontextualization(memories)
    c_details = score_coverage(memories, source_conversation)
    return EvalResult(
        faithfulness=f_score,
        decontextualization=d_score,
        coverage=c_details.score,
        faithfulness_details=f_details,
        decontext_details=d_details,
        coverage_details=c_details,
    )


# ── Fixtures (use FIXTURE_CONVERSATION imported from write_policy) ──────

CLEAN_EXTRACTION = [
    "User is a senior backend engineer at a NYC fintech with 4 years tenure",
    "User is considering moving to a staff engineer role at another company",
    "User's growth path at current company is capped; no staff slot opening this year",
    "User wants more ML infrastructure exposure in their next role",
    "User has had preliminary chats with Anthropic and a series-B startup",
    "User has 6 weeks to make a decision because of a pending house purchase",
]

# Designed failure modes:
#   1. "This is capped this year"               -> decontextualization fail
#   2. "User has accepted an offer from Anthropic" -> faithfulness fail (fabricated)
#   3. Missing: 6-week deadline, house purchase, tenure, role seniority
#                                               -> coverage will surface these
LOSSY_EXTRACTION = [
    "User works at a fintech",
    "User wants ML infrastructure exposure",
    "This is capped this year",
    "User has accepted an offer from Anthropic",
    "User has talked to a startup",
]


# ── Demo ────────────────────────────────────────────────────────────────


def print_eval_row(label: str, result: EvalResult) -> None:
    print(
        f"  {label:<10}  faithfulness={result.faithfulness:.2f}  "
        f"decontextualization={result.decontextualization:.2f}  "
        f"coverage={result.coverage:.2f}"
    )


def print_per_failure(label: str, result: EvalResult) -> None:
    print(f"\n  {label} extraction, per-failure reasoning:")

    faith_fails = [v for v in result.faithfulness_details if not v.supported]
    decontext_fails = [v for v in result.decontext_details if not v.self_contained]

    for v in faith_fails:
        print(f"    [faithfulness fail]      {v.memory!r}")
        print(f"        reason: {v.reasoning}")
    for v in decontext_fails:
        unresolved = ", ".join(v.unresolved) if v.unresolved else "(none flagged)"
        print(f"    [decontextualization fail] {v.memory!r}")
        print(f"        unresolved: {unresolved}")
        print(f"        reason: {v.reasoning}")
    if result.coverage_details.missing:
        print(f"    [coverage miss] salient facts not in the extracted set:")
        for m in result.coverage_details.missing:
            print(f"        - {m}")
    if not faith_fails and not decontext_fails and not result.coverage_details.missing:
        print("    (no failures)")


def main():
    print("memory_eval.py - extraction-quality evaluation")
    print(f"Source: {len(FIXTURE_CONVERSATION)}-turn career-coaching fixture.")
    print(
        "Metrics: Faithfulness (RAGAS), Decontextualization (Claimify), "
        "Coverage (Claimify-style, missing-fact detection).\n"
    )

    print("Evaluating CLEAN extraction (atomic, source-grounded memories)...")
    clean_result = evaluate(CLEAN_EXTRACTION, FIXTURE_CONVERSATION)

    print("Evaluating LOSSY extraction (mix of valid memories + designed failures)...")
    lossy_result = evaluate(LOSSY_EXTRACTION, FIXTURE_CONVERSATION)

    print("\n" + "═" * 72)
    print("RESULTS")
    print("═" * 72)
    print_eval_row("CLEAN", clean_result)
    print_eval_row("LOSSY", lossy_result)

    print("\n" + "─" * 72)
    print("FAILURE BREAKDOWN")
    print("─" * 72)
    print_per_failure("CLEAN", clean_result)
    print_per_failure("LOSSY", lossy_result)


if __name__ == "__main__":
    main()
