"""Gold set: its format, its label rules, and the check of its quotes against the corpus."""

import json

import pytest
from pydantic import ValidationError

from claimverify.evaluation import CATEGORIES, GoldClaim, check_gold, load_gold

DOCS = {
    "a.pdf": "LumberChunker uses an LLM to find\nsemantic shifts in narra-\ntive text.",
    "b.pdf": "Fixed-size chunking remained competitive on most datasets we tested.",
}
QUOTE_A = "LumberChunker uses an LLM to find semantic shifts in narrative text."
QUOTE_B = "Fixed-size chunking remained competitive on most datasets"


def claim(expected="supported", evidence=None, category="single_source", **kw) -> dict:
    if evidence is None:
        evidence = [{"filename": "a.pdf", "stance": "supports", "quote": QUOTE_A}]
    return {"id": "g01", "category": category, "claim": "LumberChunker relies on an LLM.",
            "expected": expected, "evidence": evidence, **kw}


def one_per_category() -> list[GoldClaim]:
    return [GoldClaim.model_validate(claim(category=c) | {"id": f"g{i}"}) for i, c in enumerate(CATEGORIES)]


# --- label rules ---------------------------------------------------------------------

def test_a_supported_claim_needs_a_quote_for_it_and_none_against():
    GoldClaim.model_validate(claim())
    against = {"filename": "b.pdf", "stance": "contradicts", "quote": QUOTE_B}
    with pytest.raises(ValidationError, match="aucune contre"):
        GoldClaim.model_validate(claim(evidence=[claim()["evidence"][0], against]))


def test_a_contested_claim_needs_two_documents_that_disagree():
    pro = {"filename": "a.pdf", "stance": "supports", "quote": QUOTE_A}
    GoldClaim.model_validate(claim("contested", [pro, {"filename": "b.pdf", "stance": "contradicts", "quote": QUOTE_B}]))
    same_doc = {"filename": "a.pdf", "stance": "contradicts", "quote": QUOTE_A}
    with pytest.raises(ValidationError, match="documents différents"):
        GoldClaim.model_validate(claim("contested", [pro, same_doc]))


def test_an_unverifiable_claim_has_no_quote():
    GoldClaim.model_validate(claim("unverifiable", []))
    with pytest.raises(ValidationError, match="aucune citation"):
        GoldClaim.model_validate(claim("unverifiable"))


def test_error_is_never_an_expected_verdict():
    with pytest.raises(ValidationError):
        GoldClaim.model_validate(claim("error"))


def test_unknown_fields_and_categories_are_refused():
    with pytest.raises(ValidationError):
        GoldClaim.model_validate(claim(category="easy"))
    with pytest.raises(ValidationError):
        GoldClaim.model_validate(claim(expectd="supported"))


# --- loading ------------------------------------------------------------------------

def test_the_file_is_read_line_by_line_and_errors_name_the_line(tmp_path):
    path = tmp_path / "gold.jsonl"
    path.write_text(json.dumps(claim()) + "\n\n" + json.dumps(claim("unverifiable")) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ligne 3"):
        load_gold(path)
    path.write_text(json.dumps(claim()) + "\n", encoding="utf-8")
    assert [c.id for c in load_gold(path)] == ["g01"]


# --- check against the corpus ---------------------------------------------------------

def test_a_valid_gold_set_has_no_problem_even_across_line_breaks_and_split_words():
    # QUOTE_A is written on one line, "narrative" whole; the stored text has both broken
    assert check_gold(one_per_category(), DOCS) == []


def test_a_modified_or_invented_quote_is_caught():
    claims = one_per_category()
    claims[0].evidence[0].quote = "LumberChunker uses GPT-4 to find semantic shifts in narrative text."
    [problem] = check_gold(claims, DOCS)
    assert "citation introuvable dans a.pdf" in problem


def test_unknown_files_duplicate_ids_and_missing_categories_are_reported():
    claims = one_per_category()[:4]
    claims[1].id = claims[0].id
    claims[2].evidence[0].filename = "missing.pdf"
    problems = check_gold(claims, DOCS)
    assert any("id en double" in p for p in problems)
    assert any("missing.pdf n'est pas dans le corpus" in p for p in problems)
    assert any("aucun claim dans la catégorie out_of_corpus" in p for p in problems)
