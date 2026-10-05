"""Reranking: the candidates re-sorted by a reader of (claim, chunk) pairs. Fake reranker, no model."""

import pytest

from claimverify.components.reranking import CrossEncoderReranker, Reranker, rerank
from claimverify.contracts import Document
from claimverify.indexing.chunking import FixedSizeChunker
from claimverify.retrieval_eval import InMemoryIndex, Target
from fakes import WordTokenizer
from test_retrieval_eval import KeywordEmbedder


class OverlapReranker:
    """Scores a text by the number of query words it contains: reads both together."""

    def __init__(self):
        self.calls = []

    def scores(self, query, texts):
        self.calls.append(len(texts))
        words = set(query.lower().split())
        return [float(len(words & set(t.lower().split()))) for t in texts]


def test_both_rerankers_satisfy_the_interface():
    assert isinstance(OverlapReranker(), Reranker)
    assert isinstance(CrossEncoderReranker(device="cpu"), Reranker)  # lazy: no model loaded


def test_rerank_puts_the_best_reading_first():
    texts = ["nothing here", "bart large generator", "bart"]
    assert rerank("bart large", [0, 1, 2], texts, OverlapReranker()) == [1, 2, 0]


# 4 beta chunks, equal by meaning; only the 4th answers the claim's exact question
TEXT = ("beta one beta one. beta two beta two. beta three beta three. "
        "generator has 400m parameters.")
DOC = Document(doc_id="d", filename="b.pdf", source_type="peer_reviewed_paper", text=TEXT)


def index(reranker=None, candidates=10) -> InMemoryIndex:
    chunks = FixedSizeChunker(WordTokenizer(), chunk_size=4, overlap_ratio=0.0).chunk([DOC])
    return InMemoryIndex([DOC], chunks, KeywordEmbedder(), reranker, candidates)


def test_the_reranker_lifts_the_chunk_that_answers_the_claim():
    target = Target("t", "beta generator has 400m parameters", "b.pdf", "generator has 400m parameters.")
    assert index(OverlapReranker()).find(target, "rerank").rank == 1


def test_only_the_candidates_are_reread():
    reranker = OverlapReranker()
    ranking = index(reranker, candidates=2).ranking("beta generator", "b.pdf", "rerank")
    hybrid = index().ranking("beta generator", "b.pdf", "hybrid")
    assert reranker.calls == [2]
    assert ranking[2:] == hybrid[2:]  # beyond the candidates, the hybrid order is kept
    assert sorted(ranking[:2]) == sorted(hybrid[:2])


def test_rerank_without_a_reranker_is_an_error():
    with pytest.raises(ValueError, match="needs a reranker"):
        index().ranking("beta", "b.pdf", "rerank")
