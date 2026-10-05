"""
Reranking — rereading each candidate TOGETHER with the claim
============================================================

The embedder is a bi-encoder: it turns the claim and each chunk into vectors
SEPARATELY, then compares them. It captures the topic, not the answer.

A cross-encoder reads the claim and a chunk TOGETHER, in a single input: its
attention links every word of one to every word of the other, and it judges
whether the chunk answers the claim. Too slow for the whole corpus (one model
pass per pair), it only RE-SORTS a short list of candidates brought by the
search.

The model runs locally (GPU): no API call.
"""

from functools import cached_property
from typing import Protocol, runtime_checkable

RERANKER_MODEL = "BAAI/bge-reranker-base"


@runtime_checkable
class Reranker(Protocol):
    """Interface: one relevance score per text, for a query."""

    def scores(self, query: str, texts: list[str]) -> list[float]: ...


class CrossEncoderReranker:
    """Implementation: a sentence-transformers cross-encoder."""

    def __init__(self, model_name: str = RERANKER_MODEL, device: str = "cuda"):
        self.model_name = model_name
        self.device = device

    @cached_property
    def model(self):
        # Loaded on first use only, like the embedder.
        from sentence_transformers import CrossEncoder
        return CrossEncoder(self.model_name, device=self.device)

    def scores(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        return [float(s) for s in self.model.predict([(query, t) for t in texts], show_progress_bar=False)]


def rerank(query: str, candidates: list[int], texts: list[str], reranker: Reranker) -> list[int]:
    """Re-sorts `candidates` (indices into `texts`) from most to least relevant."""
    scores = reranker.scores(query, [texts[i] for i in candidates])
    order = sorted(range(len(candidates)), key=lambda j: scores[j], reverse=True)
    return [candidates[j] for j in order]
