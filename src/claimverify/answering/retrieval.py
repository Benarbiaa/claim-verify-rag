"""
Retrieval for answering — question to Passages
==============================================

The search itself (pgvector SQL) is in components/store.py, and the query's
embedding in components/embedding.py. The retriever receives both: it creates
no model and no connection.

Two implementations, chosen in config.yaml (type):
    pgvector  by meaning only (embeddings)
    hybrid    by meaning AND by words (BM25), rankings fused
and, optionally (rerank), a RerankingRetriever that wraps either one: it asks
it for more candidates per document, has a cross-encoder reread them, and
keeps the best.
"""

from functools import cached_property
from typing import Protocol, runtime_checkable

from claimverify.components.embedding import Embedder
from claimverify.components.lexical import Bm25Index, reciprocal_rank_fusion
from claimverify.components.reranking import Reranker
from claimverify.components.store import (
    TOP_K_PER_DOC,
    load_chunk_texts,
    rank_all_per_document,
    search_per_document,
)
from claimverify.contracts import Passage


@runtime_checkable
class Retriever(Protocol):
    """Interface: finds the corpus passages relevant to a text."""

    def retrieve(self, query: str) -> list[Passage]: ...


class PgvectorRetriever:
    """Implementation: top-k PER document in pgvector (every source is represented)."""

    def __init__(self, embedder: Embedder, conn, top_k_per_doc: int = TOP_K_PER_DOC):
        self.embedder = embedder
        self.conn = conn
        self.top_k_per_doc = top_k_per_doc

    def retrieve(self, query: str) -> list[Passage]:
        return search_per_document(self.conn, self.embedder.embed_query(query), self.top_k_per_doc)


class HybridRetriever:
    """Implementation: top-k PER document, after fusing two rankings.

    Within one paper every chunk is about the same topic: embedding scores are
    very close, and the detail that makes the proof (a figure, a name) barely
    counts. BM25 ranks by exact words, weighted by their rarity in the corpus.
    The two rankings of each document are fused by their ranks
    (reciprocal_rank_fusion, no weight to tune). Measured on 44 quotes (make
    eval-retrieval): the proof is in its document's first 2 passages for
    31/44, against 23/44 by meaning alone.

    The BM25 index is built on the first call from the stored chunks, then
    kept: a new retriever is needed after a re-index (which is the case, the
    factory builds one per run)."""

    def __init__(self, embedder: Embedder, conn, top_k_per_doc: int = TOP_K_PER_DOC):
        self.embedder = embedder
        self.conn = conn
        self.top_k_per_doc = top_k_per_doc

    @cached_property
    def _lexical(self) -> tuple[Bm25Index, list[tuple[str, int]]]:
        rows = load_chunk_texts(self.conn)
        return Bm25Index([text for _, _, text in rows]), [(f, i) for f, i, _ in rows]

    def retrieve(self, query: str) -> list[Passage]:
        dense = rank_all_per_document(self.conn, self.embedder.embed_query(query))
        bm25, keys = self._lexical
        words = dict(zip(keys, bm25.scores(query), strict=True))

        results = []
        for filename, passages in dense.items():
            by_meaning = [p.chunk_index for p in passages]
            by_words = sorted(by_meaning, key=lambda i: words.get((filename, i), 0.0), reverse=True)
            best = reciprocal_rank_fusion([by_meaning, by_words])[:self.top_k_per_doc]
            chosen = {p.chunk_index: p for p in passages}
            results += [chosen[i] for i in best]  # the displayed score stays the cosine

        results.sort(key=lambda p: p.score, reverse=True)
        return results


class RerankingRetriever:
    """Wraps a retriever: its `candidates` best passages per document are
    reread by a cross-encoder (the claim and the passage TOGETHER), which keeps
    the `top_k_per_doc` that answer best.

    The search finds the proof among its candidates without ranking it well
    (embedding scores packed together within one paper); the reranker ranks
    it. Measured on 44 quotes (make eval-retrieval): the proof is in its
    document's first 2 passages for 37/44 with hybrid + reranker, 31/44 with
    hybrid alone, 23/44 by meaning alone."""

    def __init__(self, base: Retriever, reranker: Reranker, top_k_per_doc: int = TOP_K_PER_DOC):
        self.base = base          # built to bring `candidates` passages per document
        self.reranker = reranker
        self.top_k_per_doc = top_k_per_doc

    def retrieve(self, query: str) -> list[Passage]:
        by_doc: dict[str, list[Passage]] = {}
        for p in self.base.retrieve(query):
            by_doc.setdefault(p.filename, []).append(p)

        results = []
        for passages in by_doc.values():
            scores = self.reranker.scores(query, [p.text for p in passages])
            order = sorted(range(len(passages)), key=lambda j: scores[j], reverse=True)
            results += [passages[j] for j in order[:self.top_k_per_doc]]

        results.sort(key=lambda p: p.score, reverse=True)  # the displayed score stays the cosine
        return results


def format_evidence(passages: list[Passage]) -> str:
    blocks = []
    for p in passages:
        blocks.append(f"[Source: {p.filename} | chunk #{p.chunk_index} | type: {p.source_type}]\n{p.text}")
    return "\n\n---\n\n".join(blocks)
