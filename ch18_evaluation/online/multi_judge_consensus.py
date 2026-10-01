"""
multi_judge_consensus.py — Eliminate single-judge noise with majority voting.

A single LLM judge is itself a probabilistic system. On borderline answers,
it will disagree with itself 20-30% of the time across runs. The fix: run
the same eval through multiple models and take the majority verdict.

This script runs each eval case through three judges:
  1. Claude Sonnet 4.6
  2. Claude Haiku 4.5 (fast, cheap cross-check)
  3. Gemini 2.5 Flash (different model family, different biases)

Majority verdict: if 2/3 agree, that's the final score. Disagreements are
flagged for human review — they're usually the genuinely ambiguous cases
that deserve manual attention anyway.

Usage:
    python multi_judge_consensus.py --case tc-001
    python multi_judge_consensus.py --category research

Requires: pip install anthropic google-genai
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
from eval_harness import EVAL_CASES, mock_agent


sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import (  # also loads .env
    ANTHROPIC_FAST_MODEL, ANTHROPIC_MODEL, ANTHROPIC_STRONG_MODEL, GEMINI_MODEL, GOOGLE_API_KEY,
)
from shared.llm_utils import parse_json


anthropic_client = anthropic.Anthropic()
# The third judge should come from a different model family. Without a Google key
# (e.g. fully local on Ollama) it falls back to ANTHROPIC_STRONG_MODEL, so point
# that at a different local model than the other two judges.
if GOOGLE_API_KEY:
    from google import genai as google_genai
    gemini_client = google_genai.Client()
else:
    gemini_client = None

# ── Judge implementations ─────────────────────────────────────────────

JUDGE_SYSTEM = (
    "You are an impartial evaluator. Grade the agent's answer based ONLY on "
    "the provided Reference Facts. Output valid JSON only."
)

JUDGE_PROMPT_TEMPLATE = """\
Question: {question}

Reference Facts:
{facts}

Agent Answer: {answer}

Output JSON:
{{"reasoning": "step-by-step evaluation", "score": 1-5, "hallucinated": true/false}}
"""


def claude_sonnet_judge(question: str, answer: str, facts: list[str]) -> dict:
    facts_text = "\n".join(f"- {f}" for f in facts)
    resp = anthropic_client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=512,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": JUDGE_PROMPT_TEMPLATE.format(
            question=question, facts=facts_text, answer=answer
        )}],
    )
    return parse_json(resp.content[0].text)


def claude_haiku_judge(question: str, answer: str, facts: list[str]) -> dict:
    facts_text = "\n".join(f"- {f}" for f in facts)
    resp = anthropic_client.messages.create(
        model=ANTHROPIC_FAST_MODEL,
        max_tokens=256,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": JUDGE_PROMPT_TEMPLATE.format(
            question=question, facts=facts_text, answer=answer
        )}],
    )
    return parse_json(resp.content[0].text)


def gemini_flash_judge(question: str, answer: str, facts: list[str]) -> dict:
    facts_text = "\n".join(f"- {f}" for f in facts)
    prompt = JUDGE_SYSTEM + "\n\n" + JUDGE_PROMPT_TEMPLATE.format(
        question=question, facts=facts_text, answer=answer
    )
    if gemini_client is None:
        resp = anthropic_client.messages.create(
            model=ANTHROPIC_STRONG_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_json(resp.content[0].text)
    resp = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    return parse_json(resp.text)


JUDGES = {
    "claude-sonnet": claude_sonnet_judge,
    "claude-haiku":  claude_haiku_judge,
    "gemini-flash":  gemini_flash_judge,
}


# ── Consensus logic ───────────────────────────────────────────────────

@dataclass
class ConsensusResult:
    case_id:         str
    final_score:     float        # Average of agreeing judges
    final_verdict:   str          # "pass", "fail", "disputed"
    hallucinated:    bool         # Majority voted hallucinated
    per_judge:       dict         # {judge_name: {score, hallucinated}}
    disagreement:    bool         # True if judges disagreed significantly


def judge_with_consensus(
    case_id: str,
    question: str,
    answer: str,
    facts: list[str],
) -> ConsensusResult:
    """Run all three judges and compute consensus."""
    per_judge: dict = {}

    for name, fn in JUDGES.items():
        try:
            result = fn(question, answer, facts)
            per_judge[name] = {
                "score":       result.get("score", 0),
                "hallucinated": result.get("hallucinated", False),
                "reasoning":   result.get("reasoning", ""),
            }
        except Exception as e:
            per_judge[name] = {"score": 0, "hallucinated": False, "error": str(e)}

    scores       = [v["score"] for v in per_judge.values() if "score" in v]
    halluc_votes = [v["hallucinated"] for v in per_judge.values()]

    avg_score       = sum(scores) / len(scores) if scores else 0
    hallucinated    = sum(halluc_votes) > len(halluc_votes) / 2  # majority
    score_range     = max(scores) - min(scores) if scores else 0
    disagreement    = score_range >= 2  # judges disagree by 2+ points

    if disagreement:
        verdict = "disputed"
    elif avg_score >= 3.5:
        verdict = "pass"
    else:
        verdict = "fail"

    return ConsensusResult(
        case_id=case_id, final_score=avg_score, final_verdict=verdict,
        hallucinated=hallucinated, per_judge=per_judge, disagreement=disagreement,
    )


# ── Main ──────────────────────────────────────────────────────────────

def run_consensus_eval(cases=None, category=None):
    if cases is None:
        cases = EVAL_CASES
    if category:
        cases = [c for c in cases if c.category == category]

    print(f"Multi-Judge Consensus Eval — {len(cases)} cases, {len(JUDGES)} judges\n")

    results: list[ConsensusResult] = []
    disputed: list[str] = []

    for case in cases:
        print(f"  {case.id}...", end=" ", flush=True)
        output = mock_agent(case.input)
        answer = output.get("answer", "")

        cr = judge_with_consensus(case.id, case.input, answer, case.reference_facts)
        results.append(cr)

        if cr.disagreement:
            disputed.append(case.id)
            print(f"⚠️  DISPUTED  (scores: {[v['score'] for v in cr.per_judge.values()]})")
        elif cr.final_verdict == "pass":
            print(f"✅ PASS  (avg={cr.final_score:.1f})")
        else:
            print(f"❌ FAIL  (avg={cr.final_score:.1f})")

    # Summary
    total      = len(results)
    passed     = sum(1 for r in results if r.final_verdict == "pass")
    failed     = sum(1 for r in results if r.final_verdict == "fail")
    hallucin   = sum(1 for r in results if r.hallucinated)

    print(f"\n{'='*55}")
    print(f"CONSENSUS REPORT  ({len(JUDGES)} judges)")
    print(f"{'='*55}")
    print(f"  Pass:       {passed}/{total}")
    print(f"  Fail:       {failed}/{total}")
    print(f"  Disputed:   {len(disputed)}/{total}  ← review manually")
    print(f"  Hallucinated: {hallucin}/{total}")

    if disputed:
        print(f"\nDisputed cases (major judge disagreement):")
        for case_id in disputed:
            r = next(cr for cr in results if cr.case_id == case_id)
            print(f"  {case_id}:")
            for judge, v in r.per_judge.items():
                print(f"    {judge}: score={v.get('score')} hallucinated={v.get('hallucinated')}")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--case",     default=None)
    parser.add_argument("--category", default=None)
    args = parser.parse_args()

    cases = None
    if args.case:
        cases = [c for c in EVAL_CASES if c.id == args.case]

    run_consensus_eval(cases=cases, category=args.category)
