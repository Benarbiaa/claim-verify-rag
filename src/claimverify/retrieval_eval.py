"""
Retrieval evaluation — does the search bring back the proof?
============================================================

Before the judge reads anything, the search must bring it the passage that
holds the proof. For each claim -> quote pair (gold set and retrieval set),
ALL the chunks of the quote's document are ranked by similarity to the claim,
as the per-document search does, and the RANK of the first chunk that holds
the quote is recorded:

    rank 1: the proof is in the document's best chunk
    rank 3: it is only seen with top_k_per_doc >= 3

So a single run gives the recall for every k (1, 2, 3, 5...). A quote that
straddles two chunks is only "partly found": the rank of the first chunk
holding a piece of it is recorded too.

This is a LOWER bound: another chunk may say the same thing differently (a
result repeated in the conclusion), which is enough for the judge but cannot
be detected automatically.

The search runs IN MEMORY (dot product of normalized vectors, i.e. pgvector's
cosine similarity): comparing chunk sizes does not touch the real table. No
LLM call.
"""

import math
import unicodedata
from dataclasses import dataclass

from claimverify.components.lexical import Bm25Index, reciprocal_rank_fusion
from claimverify.components.reranking import Reranker, rerank
from claimverify.contracts import Chunk, Document

K_VALUES = (1, 2, 3, 5)
METHODS = ("dense", "bm25", "hybrid", "rerank")
RERANK_CANDIDATES = 10  # candidates per document reread by the reranker


@dataclass(frozen=True)
class Target:
    """What is searched for: the quote `quote` of `filename`, for the claim `claim`."""
    id: str
    claim: str
    filename: str
    quote: str


@dataclass(frozen=True)
class Found:
    target: Target
    rank: int | None          # rank of the first chunk holding the whole quote
    rank_partial: int | None  # rank of the first chunk holding at least a piece of it
    chunks_in_doc: int
    score: float | None       # similarity of the chunk at rank `rank` (or partial)


# --- Where is the quote in the document? --------------------------------------------------

def quote_spans(text: str, quote: str) -> list[tuple[int, int]]:
    """Positions (start, end) of EACH occurrence of the quote in the original
    text, ignoring spaces, line breaks and hyphens, like the gold set's
    checker. A paper often repeats a sentence (abstract, introduction): the
    proof is seen if ANY of them is retrieved."""
    signature, positions = [], []
    for i, ch in enumerate(text):
        for c in unicodedata.normalize("NFKC", ch):
            if not c.isspace() and c != "-":
                signature.append(c)
                positions.append(i)
    wanted = "".join(c for c in unicodedata.normalize("NFKC", quote) if not c.isspace() and c != "-")
    joined, spans, start = "".join(signature), [], 0
    while wanted and (start := joined.find(wanted, start)) >= 0:
        spans.append((positions[start], positions[start + len(wanted) - 1] + 1))
        start += 1
    return spans


def chunk_spans(text: str, chunks: list[Chunk]) -> list[tuple[int, int]]:
    """Position of each chunk in its document: a chunk is an exact slice of
    the text, in order (see chunking.py)."""
    spans, cursor = [], 0
    for c in chunks:
        start = text.find(c.text, cursor)
        if start < 0:
            raise ValueError(f"{c.chunk_id} is not a slice of its document")
        spans.append((start, start + len(c.text)))
        cursor = start + 1  # chunks overlap: the next one starts after this one's start
    return spans


# --- The search, in memory ---------------------------------------------------------------

class InMemoryIndex:
    """A corpus's chunks, ranked per document as search_per_document does, but
    with no database, by one of four methods:

        dense   by meaning: cosine of the embeddings
        bm25    by words: BM25, word weights computed over the WHOLE corpus
        hybrid  both rankings fused by their ranks (RRF)
        rerank  hybrid, then its RERANK_CANDIDATES first re-sorted by a
                cross-encoder that reads the claim and each chunk together"""

    def __init__(self, documents: list[Document], chunks: list[Chunk], embedder,
                 reranker: Reranker | None = None, candidates: int = RERANK_CANDIDATES):
        self.embedder = embedder
        self.reranker, self.candidates = reranker, candidates
        self.chunk_texts = [c.text for c in chunks]
        self.texts = {d.filename: d.text for d in documents}
        self.vectors = embedder.embed_texts([c.text for c in chunks])
        self.bm25 = Bm25Index([c.text for c in chunks])
        # per document: (index of the chunk in `chunks`, its position in the text)
        self.by_doc: dict[str, list[tuple[int, tuple[int, int]]]] = {}
        for d in documents:
            mine = [i for i, c in enumerate(chunks) if c.filename == d.filename]
            spans = chunk_spans(d.text, [chunks[i] for i in mine])
            self.by_doc[d.filename] = list(zip(mine, spans, strict=True))

    def ranking(self, claim: str, filename: str, method: str = "dense") -> list[tuple[tuple[int, int], float]]:
        """(position, score) of each chunk of the document, best first."""
        if method not in METHODS:
            raise ValueError(f"unknown method {method!r} (available: {METHODS})")
        items = self.by_doc[filename]
        query = self.embedder.embed_query(claim)
        dense = {i: sum(a * b for a, b in zip(query, self.vectors[i], strict=True)) for i, _ in items}
        lexical = self.bm25.scores(claim)
        words = {i: lexical[i] for i, _ in items}
        span = dict(items)

        def by_score(scores: dict[int, float]) -> list[int]:
            return sorted(scores, key=lambda i: scores[i], reverse=True)

        if method == "dense":
            return [(span[i], dense[i]) for i in by_score(dense)]
        if method == "bm25":
            return [(span[i], words[i]) for i in by_score(words)]
        fused = reciprocal_rank_fusion([by_score(dense), by_score(words)])
        if method == "rerank":
            if self.reranker is None:
                raise ValueError("the 'rerank' method needs a reranker")
            head = rerank(claim, fused[:self.candidates], self.chunk_texts, self.reranker)
            fused = head + fused[self.candidates:]
        return [(span[i], dense[i]) for i in fused]  # displayed score: the cosine, to compare

    def find(self, target: Target, method: str = "dense") -> Found:
        quotes = quote_spans(self.texts[target.filename], target.quote)
        if not quotes:
            raise ValueError(f"{target.id}: quote not found in {target.filename}")
        ranking = self.ranking(target.claim, target.filename, method)
        rank = rank_partial = score = None
        for r, ((start, end), s) in enumerate(ranking, start=1):
            if rank_partial is None and any(start < q_end and q_start < end for q_start, q_end in quotes):
                rank_partial, score = r, s
            if any(start <= q_start and q_end <= end for q_start, q_end in quotes):
                rank, score = r, s
                break
        return Found(target, rank, rank_partial, len(ranking), score)


# --- Summaries -----------------------------------------------------------------------

def recall_at(found: list[Found], k: int, partial: bool = False) -> int:
    """Number of quotes whose chunk is among the first k of its document."""
    def rank(f: Found) -> int | None:
        return f.rank_partial if partial else f.rank
    return sum(1 for f in found if rank(f) is not None and rank(f) <= k)


def wilson_interval(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95 % confidence interval of a proportion measured on few items
    (Wilson): 9/11 -> about 52 % to 95 %."""
    if n == 0:
        return 0.0, 1.0
    p = hits / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, center - half), min(1.0, center + half)


def paired_changes(before: list[Found], after: list[Found], k: int) -> tuple[list[str], list[str]]:
    """Quote-by-quote comparison of two settings: (gained, lost) at rank k."""
    def hit(f: Found) -> bool:
        return f.rank is not None and f.rank <= k
    old = {f.target.id: hit(f) for f in before}
    gained = [f.target.id for f in after if hit(f) and not old[f.target.id]]
    lost = [f.target.id for f in after if not hit(f) and old[f.target.id]]
    return gained, lost
