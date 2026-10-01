"""
dspy_agent_pipeline.py — DSPy Declarative Agent Pipeline
=========================================================
Chapter 7 Online Example: Replace hand-tuned prompts with compiled DSPy modules.

The key insight: DSPy treats your prompting strategy as a program you can
optimize automatically. Define signatures (what goes in, what comes out),
wire them into a Module, then compile against examples to get the best
prompt for your specific model — without touching a single f-string.

Usage:
    python dspy_agent_pipeline.py
    pip install dspy-ai
"""

import sys
from pathlib import Path

import dspy
from dspy.teleprompt import BootstrapFewShot

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import LITELLM_MODEL  # also loads .env


# ── Model Configuration ──────────────────────────────────────────────
# Swap the model string to use a different provider — nothing else changes.
# LITELLM_MODEL: "openai/gpt-4o" (default) or "ollama_chat/gemma4-longctx" (local).

lm = dspy.LM(LITELLM_MODEL, max_tokens=1024)
dspy.configure(lm=lm)


# ── Signatures ───────────────────────────────────────────────────────
# A Signature declares the interface: inputs → outputs.
# DSPy handles the prompt construction automatically.

class ResearchAnswer(dspy.Signature):
    """Answer a technical research question with citations and confidence level."""
    question: str = dspy.InputField()
    reasoning: str = dspy.OutputField(desc="Step-by-step reasoning process")
    answer: str = dspy.OutputField(desc="Final, concise answer with citations")
    confidence: str = dspy.OutputField(desc="One of: high, medium, low")


class FactCheck(dspy.Signature):
    """Verify a claim against a known answer and identify inaccuracies."""
    claim: str = dspy.InputField(desc="The claim to verify")
    reference: str = dspy.InputField(desc="Known correct information")
    verdict: str = dspy.OutputField(desc="ACCURATE, INACCURATE, or PARTIAL")
    issues: str = dspy.OutputField(desc="Specific inaccuracies found, or 'None'")


# ── Pipeline Module ───────────────────────────────────────────────────
# Modules compose Signatures into multi-step reasoning chains.

class ResearchAndVerify(dspy.Module):
    """
    Two-stage pipeline:
    1. Research: answer a question with chain-of-thought reasoning
    2. Verify: self-check the answer against the reasoning
    """

    def __init__(self):
        super().__init__()
        self.research = dspy.ChainOfThought(ResearchAnswer)
        self.verify = dspy.Predict(FactCheck)

    def forward(self, question: str) -> dspy.Prediction:
        # Stage 1: generate an answer
        research_result = self.research(question=question)

        # Stage 2: self-verify the answer against its own reasoning
        verify_result = self.verify(
            claim=research_result.answer,
            reference=research_result.reasoning,
        )

        return dspy.Prediction(
            question=question,
            reasoning=research_result.reasoning,
            answer=research_result.answer,
            confidence=research_result.confidence,
            verdict=verify_result.verdict,
            issues=verify_result.issues,
        )


# ── Compilation ───────────────────────────────────────────────────────
# DSPy automatically selects and injects few-shot examples
# that maximize the metric on your training set.

TRAINSET = [
    dspy.Example(
        question="What is the Model Context Protocol (MCP)?",
        answer="MCP is an open standard by Anthropic that defines how AI agents connect to external tools and data sources using a client-server architecture.",
        confidence="high",
    ).with_inputs("question"),
    dspy.Example(
        question="What is LangGraph used for?",
        answer="LangGraph is a library from LangChain for building stateful, multi-step agent workflows as directed graphs with persistent state.",
        confidence="high",
    ).with_inputs("question"),
    dspy.Example(
        question="What is DSPy?",
        answer="DSPy is a framework from Stanford that lets you define LLM pipelines declaratively and optimize them automatically against training data.",
        confidence="high",
    ).with_inputs("question"),
]


def accuracy_metric(example: dspy.Example, prediction: dspy.Prediction, trace=None) -> bool:
    """Simple metric: penalize low-confidence answers and inaccurate verifications."""
    if prediction.confidence == "low":
        return False
    if prediction.verdict == "INACCURATE":
        return False
    return True


def compile_pipeline(pipeline: dspy.Module) -> dspy.Module:
    """Compile the pipeline against training examples to optimize prompts."""
    optimizer = BootstrapFewShot(metric=accuracy_metric, max_bootstrapped_demos=2)
    return optimizer.compile(pipeline, trainset=TRAINSET)


# ── Demo ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pipeline = ResearchAndVerify()

    # Run without compilation first (zero-shot)
    print("=== Zero-Shot Run ===")
    result = pipeline(question="What is the A2A protocol and how does it relate to MCP?")
    print(f"Answer:     {result.answer}")
    print(f"Confidence: {result.confidence}")
    print(f"Verdict:    {result.verdict}")
    print(f"Issues:     {result.issues}\n")

    # Compile and run again — prompts are now optimized for this model
    print("=== Compiling Pipeline... ===")
    compiled = compile_pipeline(pipeline)

    print("\n=== Compiled Run ===")
    result = compiled(question="What is the A2A protocol and how does it relate to MCP?")
    print(f"Answer:     {result.answer}")
    print(f"Confidence: {result.confidence}")
    print(f"Verdict:    {result.verdict}")
    print(f"Issues:     {result.issues}")