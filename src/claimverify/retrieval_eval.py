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

from claimverify.components.lexical import RRF_K, Bm25Index, reciprocal_rank_fusion
from claimverify.components.reranking import Reranker
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


@dataclass(frozen=True)
class TraceRow:
    """One chunk's score and rank at each step of the search (InMemoryIndex.trace)."""
    chunk: int              # index in the index's chunks
    span: tuple[int, int]   # position in the document
    dense: float            # cosine with the claim
    dense_rank: int
    bm25: float
    bm25_rank: int
    fused: float            # reciprocal rank fusion: 1/(RRF_K + dense rank) + 1/(RRF_K + BM25 rank)
    hybrid_rank: int
    rerank: float | None    # cross-encoder score; None: not a candidate, or no reranking
    rank: int               # final rank for the method


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
        self.chunks = chunks
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
        """(position, score) of each chunk of the document, best first. Displayed
        score: BM25's for bm25, otherwise the cosine, to compare."""
        return [(row.span, row.bm25 if method == "bm25" else row.dense)
                for row in self.trace(claim, filename, method)]

    def trace(self, claim: str, filename: str, method: str = "dense") -> list["TraceRow"]:
        """Every chunk of the document with its score and rank at each step of
        the search, in the method's final order (ranking() is read from it)."""
        if method not in METHODS:
            raise ValueError(f"unknown method {method!r} (available: {METHODS})")
        if method == "rerank" and self.reranker is None:
            raise ValueError("the 'rerank' method needs a reranker")
        items = self.by_doc[filename]
        query = self.embedder.embed_query(claim)
        dense = {i: sum(a * b for a, b in zip(query, self.vectors[i], strict=True)) for i, _ in items}
        lexical = self.bm25.scores(claim)
        words = {i: lexical[i] for i, _ in items}

        def by_score(scores: dict[int, float]) -> list[int]:
            return sorted(scores, key=lambda i: scores[i], reverse=True)

        def ranks(order: list[int]) -> dict[int, int]:
            return {i: r for r, i in enumerate(order, start=1)}

        dense_order, bm25_order = by_score(dense), by_score(words)
        fused_order = reciprocal_rank_fusion([dense_order, bm25_order])
        dense_rank, bm25_rank, hybrid_rank = ranks(dense_order), ranks(bm25_order), ranks(fused_order)
        fused = {i: 1 / (RRF_K + dense_rank[i]) + 1 / (RRF_K + bm25_rank[i]) for i, _ in items}
        cross: dict[int, float] = {}
        final = {"dense": dense_order, "bm25": bm25_order, "hybrid": fused_order}.get(method)
        if method == "rerank":
            # the cross-encoder rereads the hybrid search's first candidates; the
            # others keep their hybrid order (same sort as reranking.rerank)
            head = fused_order[:self.candidates]
            cross = dict(zip(head, self.reranker.scores(claim, [self.chunk_texts[i] for i in head]), strict=True))
            final = sorted(head, key=lambda i: cross[i], reverse=True) + fused_order[self.candidates:]
        span = dict(items)
        return [TraceRow(i, span[i], dense[i], dense_rank[i], words[i], bm25_rank[i], fused[i],
                         hybrid_rank[i], cross.get(i), r) for r, i in enumerate(final, start=1)]

    def find(self, target: Target, method: str = "dense") -> Found:
        return self.locate(target, self.ranking(target.claim, target.filename, method))

    def locate(self, target: Target, ranking: list[tuple[tuple[int, int], float]]) -> Found:
        """Where the quote's chunk is in a ranking already computed."""
        quotes = quote_spans(self.texts[target.filename], target.quote)
        if not quotes:
            raise ValueError(f"{target.id}: quote not found in {target.filename}")
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


# --- Details: the chunks themselves -----------------------------------------------------

def one_line(text: str, span: tuple[int, int], quotes: list[tuple[int, int]] = ()) -> str:
    """The slice `span` of `text` on one line, the pieces of `quotes` it holds in <mark>."""
    start, end = span
    parts, cursor = [], start
    for q_start, q_end in sorted(quotes):
        s, e = max(q_start, cursor), min(q_end, end)
        if s < e:
            parts += [text[cursor:s], "<mark>", text[s:e], "</mark>"]
            cursor = e
    parts.append(text[cursor:end])
    return " ".join("".join(parts).split())


def _chunk_block(label: str, chunk: Chunk, text: str, span: tuple[int, int],
                 quotes: list[tuple[int, int]]) -> list[str]:
    return [f"**{label}** · chunk #{chunk.chunk_index} · {chunk.tokens} tokens", "",
            "> " + one_line(text, span, quotes), ""]


def _trace_table(rows: list[TraceRow], text: str, method: str, k: int, shown: int,
                 proof_rank: int | None, numbers: dict[int, int]) -> list[str]:
    """The first `shown` chunks of the final ranking, and the proof's chunk,
    with their rank and score at each step."""
    rerank = method == "rerank"
    lines = ["**Ranking, step by step**", "",
             "| Final | Chunk | Dense: rank · cosine | BM25: rank · score | Hybrid: rank · fused |"
             + (" Rerank score |" if rerank else "") + " Starts with |",
             "|---|---|---|---|---|" + ("---|" if rerank else "") + "---|"]
    for row in rows:
        if row.rank > shown and row.rank != proof_rank:
            continue
        final = f"**{row.rank}** read" if row.rank <= k else str(row.rank)
        if row.rank == proof_rank:
            final += " · **proof**"
        start = one_line(text, row.span)[:60].replace("|", "\\|")
        cross = ("–" if row.rerank is None else f"{row.rerank:.3f}") if rerank else None
        lines.append(f"| {final} | #{numbers[row.chunk]} | {row.dense_rank} · {row.dense:.3f} "
                     f"| {row.bm25_rank} · {row.bm25:.1f} | {row.hybrid_rank} · {row.fused:.4f} |"
                     + (f" {cross} |" if rerank else "") + f" {start}… |")
    return lines + [""]


def details_report(index: InMemoryIndex, targets: list[Target], method: str, k: int, size: int) -> str:
    """For each quote: the k chunks of its document the judge would read, then
    the proof's chunk if it is not among them. The quote is in <mark>."""
    sections, missed = [], []
    for t in targets:
        rows = index.trace(t.claim, t.filename, method)
        ranking = [(row.span, row.dense) for row in rows]
        found = index.locate(t, ranking)
        text = index.texts[t.filename]
        quotes = quote_spans(text, t.quote)
        chunk_at = {span: index.chunks[i] for i, span in index.by_doc[t.filename]}

        if found.rank is not None and found.rank <= k:
            status = f"found, rank {found.rank}"
        elif found.rank is not None:
            status = f"**missed**, proof at rank {found.rank}"
            missed.append(f"{t.id} ({found.rank})")
        else:
            status = "**missed**, the quote is never whole in one chunk"
            missed.append(f"{t.id} (split)")
        if found.rank_partial is not None and found.rank_partial != found.rank:
            status += f"; a piece of it at rank {found.rank_partial}"

        lines = [f"## {t.id} · {t.filename} · {status}", "", f"**Claim:** {t.claim}", "",
                 f"**Quote:** {t.quote}", ""]
        lines += _trace_table(rows, text, method, k, index.candidates, found.rank or found.rank_partial,
                              {r.chunk: index.chunks[r.chunk].chunk_index for r in rows})
        for r, (span, _) in enumerate(ranking[:k], start=1):
            label = f"Rank {r}" + (" (proof)" if r == found.rank else "")
            lines += _chunk_block(label, chunk_at[span], text, span, quotes)
        proof_rank = found.rank or found.rank_partial
        if proof_rank and proof_rank > k:
            span = ranking[proof_rank - 1][0]
            lines += _chunk_block(f"Proof's chunk, rank {proof_rank} (not read)", chunk_at[span], text, span, quotes)
        sections.append("\n".join(lines))

    head = [f"# What the judge would read: {method}, chunks of {size} tokens, k = {k}", "",
            f"For each quote, the {k} best chunks of its document for the claim, then the chunk holding",
            "the proof when it is not among them. The proof is <mark>highlighted</mark>. Only the claim is",
            "searched; the quote is only used to find the proof's chunk.", "",
            "Each section starts with the ranking step by step: for each chunk, its rank and score by",
            "meaning (cosine), by exact words (BM25), after fusing these two ranks (hybrid: the fused",
            f"score is 1/({RRF_K} + dense rank) + 1/({RRF_K} + BM25 rank)), and, for rerank, the",
            f"cross-encoder's score: it rereads only the hybrid search's first {index.candidates}",
            "candidates (– for the others, which keep their hybrid order).", "",
            f"Missed: {len(missed)}/{len(targets)}: " + (", ".join(missed) or "none") + " (rank of the proof).", ""]
    return "\n".join(head) + "\n" + "\n\n".join(sections) + "\n"


def chunks_report(documents: list[Document], chunks: list[Chunk], size: int, overlap_ratio: float) -> str:
    """Every chunk of the corpus, document by document, as the chunker cuts it."""
    lines = [f"# The corpus in chunks of {size} tokens", "",
             f"{len(chunks)} chunks, {overlap_ratio:.0%} overlap. Cut in memory: the database holds only",
             "the size of `config.yaml` at the last `make ingest`.", "",
             "| Document | Chunks |", "|---|---|"]
    for d in documents:
        lines.append(f"| {d.filename} | {sum(c.filename == d.filename for c in chunks)} |")
    for d in documents:
        mine = [c for c in chunks if c.filename == d.filename]
        lines += ["", f"## {d.filename} ({len(mine)} chunks)", ""]
        for c, span in zip(mine, chunk_spans(d.text, mine), strict=True):
            lines += [f"**#{c.chunk_index}** · {c.tokens} tokens", "", "> " + one_line(d.text, span), ""]
    return "\n".join(lines) + "\n"
