"""
Semantic Router (Online Extra)
================================
Uses embedding similarity for sub-millisecond query routing —
no LLM call needed. Dramatically cheaper than LLM-based classification.

Usage:
    python dynamic_routing.py "I need a refund for my last purchase"

Requires: pip install openai numpy
"""

import sys
import numpy as np
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import require_key

client = OpenAI(api_key=require_key("openai"))

EMBED_MODEL = "text-embedding-3-small"


def embed(text: str) -> np.ndarray:
    """Get embedding vector for a text string."""
    response = client.embeddings.create(model=EMBED_MODEL, input=text)
    return np.array(response.data[0].embedding)


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


class SemanticRouter:
    """Routes queries to agents using embedding similarity instead of LLM calls."""

    def __init__(self):
        # Pre-embed the route descriptions (do this once at startup)
        self.routes = {
            "billing": embed("I need a refund, credit card issues, billing invoice dispute, payment problem"),
            "technical": embed("The API is down, 500 error, integration failure, webhooks broken, bug report"),
            "sales": embed("Enterprise pricing, talk to sales, schedule a demo, upgrade my plan"),
        }

    def route(self, query: str) -> tuple[str, float]:
        """Route a query to the best-matching agent. Returns (route, score)."""
        query_vec = embed(query)
        scores = {name: cosine_sim(query_vec, vec) for name, vec in self.routes.items()}
        best = max(scores, key=scores.get)
        return best, scores[best]

    def route_with_details(self, query: str) -> dict:
        """Route with full breakdown of all scores."""
        query_vec = embed(query)
        scores = {name: cosine_sim(query_vec, vec) for name, vec in self.routes.items()}
        best = max(scores, key=scores.get)
        return {"route": best, "confidence": scores[best], "all_scores": scores}


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "I need a refund for my last purchase"
    print(f"📨 Query: {query}\n")

    router = SemanticRouter()
    result = router.route_with_details(query)

    print(f"🏷️ Route: {result['route']} (confidence: {result['confidence']:.3f})")
    print(f"\nAll scores:")
    for name, score in sorted(result["all_scores"].items(), key=lambda x: -x[1]):
        bar = "█" * int(score * 50)
        print(f"  {name:12s} {score:.3f} {bar}")