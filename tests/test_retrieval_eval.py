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

    found = [index().find(t) for t in targets]
    report = retrieval_report({6: found, 4: found}, current_size=6, judge_k=1)
    assert "| 6 (config) |" in report and "| a.pdf | 2/3 | 3 |" in report
    assert "| g01.2 |" in report  # gamma quote, not in the best chunk for a beta claim


@pytest.mark.parametrize("bad", ["not in the text at all, really", "alpha alpha alpha"])
def test_a_missing_quote_is_an_error_not_a_miss(bad):
    with pytest.raises(ValueError, match="citation introuvable"):
        index().find(Target("t", "c", "a.pdf", bad))
