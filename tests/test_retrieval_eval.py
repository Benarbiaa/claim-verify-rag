"""Retrieval evaluation: locating a quote, ranking chunks in memory, recall, intervals, comparisons."""

import pytest

from claimverify.contracts import Document
from claimverify.evaluation import GoldClaim, RetrievalPair, retrieval_report, retrieval_targets
from claimverify.indexing.chunking import FixedSizeChunker
from claimverify.retrieval_eval import (
    Found,
    InMemoryIndex,
    Target,
    chunk_spans,
    chunks_report,
    details_report,
    one_line,
    paired_changes,
    quote_spans,
    recall_at,
    wilson_interval,
)
from fakes import WordTokenizer

TOPICS = ("alpha", "beta", "gamma")


class KeywordEmbedder:
    """One dimension per topic word: a text is close to a query sharing its topic."""

    def _vector(self, text):
        counts = [text.lower().count(t) for t in TOPICS]
        norm = sum(c * c for c in counts) ** 0.5 or 1.0
        return [c / norm for c in counts]

    def embed_texts(self, texts):
        return [self._vector(t) for t in texts]

    def embed_query(self, text):
        return self._vector(text)


# 3 chunks of 6 words, no overlap: one per topic
TEXT = ("alpha one alpha two alpha three "
        "beta one beta two beta three "
        "gamma one gamma two gamma three")
DOC = Document(doc_id="d", filename="a.pdf", source_type="peer_reviewed_paper", text=TEXT)


def index() -> InMemoryIndex:
    chunks = FixedSizeChunker(WordTokenizer(), chunk_size=6, overlap_ratio=0.0).chunk([DOC])
    return InMemoryIndex([DOC], chunks, KeywordEmbedder())


def test_a_quote_is_located_across_line_breaks_and_split_words():
    text = "Before. Semantic chunk-\ning is not worth\nits cost. After."
    [(start, end)] = quote_spans(text, "Semantic chunking is not worth its cost.")
    assert text[start:end] == "Semantic chunk-\ning is not worth\nits cost."
    assert quote_spans(text, "a sentence that is not there") == []


def test_a_quote_repeated_in_the_paper_is_found_wherever_it_is_retrieved():
    # 3 chunks: alpha / beta + the quote / gamma + the quote again (an abstract and its body)
    text = "alpha one alpha two the key fact. beta beta beta two the key fact. gamma gamma"
    doc = Document(doc_id="d", filename="b.pdf", source_type="peer_reviewed_paper", text=text)
    chunks = FixedSizeChunker(WordTokenizer(), chunk_size=7, overlap_ratio=0.0).chunk([doc])
    found = InMemoryIndex([doc], chunks, KeywordEmbedder()).find(Target("t", "beta", "b.pdf", "two the key fact."))
    assert len(quote_spans(text, "two the key fact.")) == 2
    assert found.rank == 1  # the beta chunk holds the second occurrence


def test_overlapping_chunks_are_placed_in_their_document():
    chunks = FixedSizeChunker(WordTokenizer(), chunk_size=4, overlap_ratio=0.5).chunk([DOC])
    spans = chunk_spans(TEXT, chunks)
    assert [TEXT[s:e] for s, e in spans] == [c.text for c in chunks]
    assert spans[1][0] < spans[0][1]  # the second chunk starts inside the first


def test_the_proof_chunk_gets_its_rank_among_the_documents_chunks():
    found = index().find(Target("t", "something about beta", "a.pdf", "beta two beta three"))
    assert (found.rank, found.chunks_in_doc) == (1, 3)
    found = index().find(Target("t", "something about beta", "a.pdf", "gamma one gamma two"))
    assert found.rank in (2, 3) and found.rank_partial == found.rank


def test_a_quote_split_across_two_chunks_is_only_partly_found():
    found = index().find(Target("t", "something about beta", "a.pdf", "beta three gamma one"))
    assert found.rank is None
    assert found.rank_partial == 1  # its beta half is in the best chunk


def test_recall_counts_quotes_whose_chunk_is_in_the_top_k():
    def f(rank, partial=None):
        return Found(Target(f"t{rank}", "c", "a.pdf", "q"), rank, partial or rank, 10, 0.5)
    found = [f(1), f(2), f(4), f(None, 1)]
    assert [recall_at(found, k) for k in (1, 2, 5)] == [1, 2, 3]
    assert recall_at(found, 1, partial=True) == 2


def test_the_wilson_interval_is_wide_for_few_items():
    low, high = wilson_interval(9, 11)
    assert (round(low, 2), round(high, 2)) == (0.52, 0.95)
    low40, high40 = wilson_interval(33, 40)
    assert high40 - low40 < high - low


def test_two_settings_are_compared_quote_by_quote():
    def f(target_id, rank):
        return Found(Target(target_id, "c", "a.pdf", "q"), rank, rank, 10, 0.5)
    before = [f("a", 1), f("b", 3), f("c", 2)]
    after = [f("a", 1), f("b", 2), f("c", None)]
    assert paired_changes(before, after, k=2) == (["b"], ["c"])


def test_every_quote_becomes_a_target_and_the_report_lists_misses():
    gold = GoldClaim.model_validate({
        "id": "g01", "category": "single_source", "claim": "Something about beta.", "expected": "supported",
        "evidence": [{"filename": "a.pdf", "stance": "supports", "quote": "beta one beta two beta"},
                     {"filename": "a.pdf", "stance": "supports", "quote": "gamma one gamma two gamma"}]})
    pair = RetrievalPair(id="r01", claim="About alpha here.", filename="a.pdf", quote="alpha one alpha two alpha")
    targets = retrieval_targets([gold], [pair])
    assert [t.id for t in targets] == ["g01.1", "g01.2", "r01"]

    dense = [index().find(t) for t in targets]
    hybrid = [index().find(t, "hybrid") for t in targets]
    report = retrieval_report({(6, "dense"): dense, (6, "hybrid"): hybrid}, current_size=6, judge_k=1)
    assert "| 6 | dense (today) |" in report
    assert "| a.pdf | 3 | 2/3 | 2/3 |" in report      # by document: dense, hybrid
    assert "| 6 | hybrid | 2/3 | – | – | none | not met |" in report  # no gain: the rule is not met
    assert "| g01.2 | a.pdf | 3 | 3 |" in report     # gamma quote: last chunk for a beta claim


def test_an_exact_word_breaks_a_tie_between_chunks_on_the_same_topic():
    # both chunks are "beta" for the embedder; only one holds the exact figure of the claim
    text = "beta model trained on data with 400m parameters. beta model trained on other data and logs."
    doc = Document(doc_id="d", filename="b.pdf", source_type="peer_reviewed_paper", text=text)
    chunks = FixedSizeChunker(WordTokenizer(), chunk_size=8, overlap_ratio=0.0).chunk([doc])
    idx = InMemoryIndex([doc], chunks, KeywordEmbedder())
    target = Target("t", "the beta model has 400m parameters", "b.pdf", "trained on data with 400m parameters.")

    assert idx.find(target, "bm25").rank == 1
    assert idx.find(target, "hybrid").rank == 1
    with pytest.raises(ValueError, match="unknown method"):
        idx.ranking("beta", "b.pdf", "magic")


@pytest.mark.parametrize("bad", ["not in the text at all, really", "alpha alpha alpha"])
def test_a_missing_quote_is_an_error_not_a_miss(bad):
    with pytest.raises(ValueError, match="quote not found"):
        index().find(Target("t", "c", "a.pdf", bad))


def test_a_chunk_is_shown_on_one_line_with_the_quote_marked():
    text = "alpha one\nalpha two beta"
    assert one_line(text, (0, len(text)), [(10, 19)]) == "alpha one <mark>alpha two</mark> beta"
    # a quote starting before the chunk is marked from the chunk's start
    assert one_line(text, (10, len(text)), [(6, 19)]) == "<mark>alpha two</mark> beta"


def test_the_details_show_the_chunks_read_and_the_proof_left_out():
    idx = index()
    found = Target("hit", "something about beta", "a.pdf", "beta two beta three")
    missed = Target("miss", "something about beta", "a.pdf", "gamma one gamma two")
    report = details_report(idx, [found, missed], "dense", k=1, size=6)

    assert "Missed: 1/2: miss (" in report
    assert "## hit · a.pdf · found, rank 1" in report
    assert "**Rank 1 (proof)** · chunk #1" in report
    assert "beta one <mark>beta two beta three</mark>" in report
    assert "Proof's chunk, rank" in report  # the gamma chunk, ranked below k = 1
    assert "<mark>gamma one gamma two</mark> gamma three" in report


def test_the_chunk_dump_lists_every_chunk_of_every_document():
    chunks = FixedSizeChunker(WordTokenizer(), chunk_size=6, overlap_ratio=0.0).chunk([DOC])
    report = chunks_report([DOC], chunks, size=6, overlap_ratio=0.0)
    assert "| a.pdf | 3 |" in report
    assert report.count("tokens\n\n> ") == 3
    assert "> gamma one gamma two gamma three" in report


class GammaReranker:
    """Prefers the gamma chunk, whatever the first steps said."""

    def scores(self, query, texts):
        return [float("gamma" in t) for t in texts]


def test_the_trace_records_each_step_and_gives_the_final_order():
    idx = InMemoryIndex([DOC], FixedSizeChunker(WordTokenizer(), chunk_size=6, overlap_ratio=0.0).chunk([DOC]),
                        KeywordEmbedder(), GammaReranker(), candidates=2)
    rows = idx.trace("something about beta", "a.pdf", "rerank")

    assert [r.rank for r in rows] == [1, 2, 3]
    assert [s for s, _ in idx.ranking("something about beta", "a.pdf", "rerank")] == [r.span for r in rows]
    beta = next(r for r in rows if "beta" in TEXT[r.span[0]:r.span[1]])
    assert (beta.dense_rank, beta.bm25_rank, beta.hybrid_rank) == (1, 1, 1)
    assert beta.fused == pytest.approx(2 / 61)
    # the reranker only rereads the 2 hybrid candidates; the third keeps its place, unscored
    assert sum(r.rerank is not None for r in rows) == 2
    assert rows[2].rerank is None and rows[2].hybrid_rank == 3


def test_the_details_trace_each_step():
    report = details_report(index(), [Target("hit", "something about beta", "a.pdf", "beta two beta three")],
                            "dense", k=1, size=6)
    assert "**Ranking, step by step**" in report
    assert "| **1** read · **proof** | #1 | 1 · " in report
