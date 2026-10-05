"""Lexical search: tokens, BM25 weights, and rank fusion. Pure functions, no model."""

from claimverify.components.lexical import Bm25Index, reciprocal_rank_fusion, tokenize


def test_figures_codes_and_compound_words_stay_whole():
    assert tokenize("BART-large with 400M parameters (7.37%), F1@5 and n/a.") == [
        "bart-large", "with", "400m", "parameters", "7.37", "f1@5", "and", "n/a"]


def test_a_rare_word_weighs_more_than_a_common_one():
    texts = ["rag model faiss", "rag model", "rag model", "rag model"]
    index = Bm25Index(texts)
    assert index.idf["faiss"] > index.idf["rag"] > 0
    scores = index.scores("rag faiss")
    assert scores[0] == max(scores)


def test_a_long_text_does_not_win_just_by_being_long():
    short, long_ = "faiss index", "faiss index " + "filler words " * 20
    scores = Bm25Index([short, long_, "other text"]).scores("faiss")
    assert scores[0] > scores[1] > 0


def test_repeating_a_word_has_diminishing_returns():
    once, ten = Bm25Index(["faiss x", "faiss " * 10, "y z"]).scores("faiss")[:2]
    assert once < ten < 10 * once


def test_a_text_without_the_query_words_scores_zero():
    assert Bm25Index(["alpha beta", "gamma"]).scores("delta") == [0.0, 0.0]


def test_rank_fusion_favours_items_ranked_well_by_both():
    # item 2: 2nd and 1st -> best overall; item 0: 1st then last
    assert reciprocal_rank_fusion([[0, 2, 1], [2, 1, 0]])[0] == 2
    # ties keep the order of the first ranking
    assert reciprocal_rank_fusion([[0, 1], [1, 0]]) == [0, 1]
