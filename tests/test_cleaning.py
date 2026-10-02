"""Cleaning: each repair on small strings, and the no-content-lost guarantee."""

import pytest

from claimverify.contracts import Document
from claimverify.indexing.cleaning import (
    Cleaner,
    MinimalCleaner,
    NoCleaner,
    check_no_content_lost,
    collapse_spaces,
    rejoin_line_end_hyphens,
    remove_page_numbers,
)
from claimverify.indexing.loading import PAGE_BREAK


def pdf(text: str, filename: str = "a.pdf") -> Document:
    return Document(doc_id="d", filename=filename, source_type="peer_reviewed_paper", text=text)


def test_both_implementations_are_cleaners():
    assert isinstance(MinimalCleaner(), Cleaner)
    assert isinstance(NoCleaner(), Cleaner)


# --- page numbers ------------------------------------------------------------------

def test_a_page_number_is_removed_only_when_it_matches_its_page():
    pages, removed = remove_page_numbers(["intro text\n1", "more text\n2", "a table\n7"])
    assert pages == ["intro text", "more text", "a table\n7"]  # 7 on page 3 is a value
    assert removed == 2


def test_a_number_inside_a_page_is_never_removed():
    pages, removed = remove_page_numbers(["Table 1\n2\n0.81\nend of page"])
    assert pages == ["Table 1\n2\n0.81\nend of page"] and removed == 0


# --- spaces --------------------------------------------------------------------------

def test_tabs_and_repeated_spaces_become_one_space_but_lines_stay():
    assert collapse_spaces("The\tDivine   Comedy \n second  line ") == "The Divine Comedy\nsecond line"


# --- words split at line ends ----------------------------------------------------------

def test_a_split_word_is_joined_when_the_document_uses_the_joined_word():
    text, joined, kept = rejoin_line_end_hyphens("maintaining rele-\nvance. Relevance matters.")
    assert text == "maintaining relevance. Relevance matters."
    assert (joined, kept) == (1, 0)


def test_a_real_compound_keeps_its_hyphen():
    text, joined, kept = rejoin_line_end_hyphens("a non-\nparametric memory and non-parametric models")
    assert text == "a non-parametric memory and non-parametric models"
    assert (joined, kept) == (0, 1)


def test_without_evidence_only_the_line_break_goes():
    text, _, kept = rejoin_line_end_hyphens("a cross-\nencoder")
    assert text == "a cross-encoder" and kept == 1


# --- the whole document --------------------------------------------------------------

def test_a_sentence_split_across_pages_comes_back_whole():
    raw = "while negative cosine\n1" + PAGE_BREAK + "similarity values are\ntreated as 0.\n2"
    cleaned = MinimalCleaner().clean([pdf(raw)])[0]
    assert cleaned.document.text == "while negative cosine\nsimilarity values are\ntreated as 0."
    assert cleaned.changes["page_numbers"] == 2


def test_nfkc_replaces_ligatures_and_counts_them():
    cleaned = MinimalCleaner().clean([pdf("ﬁne-tuning is ﬂexible")])[0]
    assert cleaned.document.text == "fine-tuning is flexible"
    assert cleaned.changes["nfkc"] == 2


def test_markdown_is_left_exactly_as_written():
    md = Document(doc_id="m", filename="post.md", source_type="blog_post", text="# Title\n\n**ﬁ**  x")
    assert MinimalCleaner().clean([md])[0].document == md


def test_no_cleaner_only_turns_page_breaks_into_line_breaks():
    raw = "page one\n1" + PAGE_BREAK + "page  two"
    assert NoCleaner().clean([pdf(raw)])[0].document.text == "page one\n1\npage  two"


def test_cleaning_keeps_metadata_and_records_the_size_before():
    doc = pdf("x" * 10 + "\n1")
    cleaned = MinimalCleaner().clean([doc])[0]
    assert cleaned.document.model_dump(exclude={"text"}) == doc.model_dump(exclude={"text"})
    assert cleaned.characters_before == 12 and cleaned.document.text == "x" * 10


# --- the guarantee ---------------------------------------------------------------------

def test_the_guarantee_accepts_layout_repairs():
    check_no_content_lost("rele-\nvance of\tthe ﬁrst", "relevance of the first", "a.pdf")


def test_the_guarantee_rejects_any_lost_word():
    with pytest.raises(RuntimeError, match="a modifié le contenu"):
        check_no_content_lost("results do not improve", "results do improve", "a.pdf")
