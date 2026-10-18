"""Gold set: its format, its label rules, and the check of its quotes against the corpus."""

import json

import pytest
from pydantic import ValidationError

from claimverify.evaluation import (
    CATEGORIES,
    QUESTION_CATEGORIES,
    GoldClaim,
    GoldQuestion,
    check_gold,
    check_questions,
    load_gold,
    load_questions,
)

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
    with pytest.raises(ValidationError, match="none against"):
        GoldClaim.model_validate(claim(evidence=[claim()["evidence"][0], against]))


def test_a_contested_claim_needs_two_documents_that_disagree():
    pro = {"filename": "a.pdf", "stance": "supports", "quote": QUOTE_A}
    GoldClaim.model_validate(claim("contested", [pro, {"filename": "b.pdf", "stance": "contradicts", "quote": QUOTE_B}]))
    same_doc = {"filename": "a.pdf", "stance": "contradicts", "quote": QUOTE_A}
    with pytest.raises(ValidationError, match="different documents"):
        GoldClaim.model_validate(claim("contested", [pro, same_doc]))


def test_an_unverifiable_claim_has_no_quote():
    GoldClaim.model_validate(claim("unverifiable", []))
    with pytest.raises(ValidationError, match="no quote"):
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
    with pytest.raises(ValueError, match="line 3"):
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
    assert "quote not found in a.pdf" in problem


def test_unknown_files_duplicate_ids_and_missing_categories_are_reported():
    claims = one_per_category()[:4]
    claims[1].id = claims[0].id
    claims[2].evidence[0].filename = "missing.pdf"
    problems = check_gold(claims, DOCS)
    assert any("duplicate id" in p for p in problems)
    assert any("missing.pdf is not in the corpus" in p for p in problems)
    assert any("no claim in the category out_of_corpus" in p for p in problems)


# --- question set (end to end) ----------------------------------------------------------

def question(category="single_source", evidence=None, **kw) -> dict:
    if evidence is None:
        evidence = [{"filename": "a.pdf", "stance": "supports", "quote": QUOTE_A}]
    return {"id": "q01", "category": category, "question": "How does LumberChunker find chunk boundaries?",
            "evidence": evidence, **kw}


PRO_A = {"filename": "a.pdf", "stance": "supports", "quote": QUOTE_A}
PRO_B = {"filename": "b.pdf", "stance": "supports", "quote": QUOTE_B}
CON_A = {"filename": "a.pdf", "stance": "contradicts", "quote": QUOTE_A}
CON_B = {"filename": "b.pdf", "stance": "contradicts", "quote": QUOTE_B}


def one_question_per_category() -> list[GoldQuestion]:
    cases = {
        "single_source": question(),
        "multi_source": question("multi_source", [PRO_A, PRO_B]),
        "conflict": question("conflict", [PRO_A, CON_B], statement="Semantic chunking beats fixed-size chunking."),
        "false_premise": question("false_premise", [CON_A], statement="LumberChunker uses no LLM."),
        "out_of_corpus": question("out_of_corpus", []),
    }
    assert set(cases) == set(QUESTION_CATEGORIES)
    return [GoldQuestion.model_validate(q | {"id": f"q{i}"}) for i, q in enumerate(cases.values())]


def test_the_documents_to_use_are_those_holding_a_quote():
    q = GoldQuestion.model_validate(question("multi_source", [PRO_A, PRO_B]))
    assert q.documents == {"a.pdf", "b.pdf"}
    assert GoldQuestion.model_validate(question("out_of_corpus", [])).documents == set()


def test_single_and_multi_source_questions_need_one_or_several_documents():
    with pytest.raises(ValidationError, match="all from one document"):
        GoldQuestion.model_validate(question(evidence=[PRO_A, PRO_B]))
    with pytest.raises(ValidationError, match="at least two documents"):
        GoldQuestion.model_validate(question("multi_source"))


def test_a_conflict_needs_two_documents_on_opposite_sides_of_a_statement():
    statement = {"statement": "Semantic chunking beats fixed-size chunking."}
    with pytest.raises(ValidationError, match="different documents"):
        GoldQuestion.model_validate(question("conflict", [PRO_A, CON_A], **statement))
    with pytest.raises(ValidationError, match="needs statement"):
        GoldQuestion.model_validate(question("conflict", [PRO_A, CON_B]))


def test_a_false_premise_is_only_contradicted_and_other_categories_take_no_statement():
    with pytest.raises(ValidationError, match="none for it"):
        GoldQuestion.model_validate(question("false_premise", [CON_A, PRO_B], statement="LumberChunker uses no LLM."))
    with pytest.raises(ValidationError, match="takes no statement"):
        GoldQuestion.model_validate(question(statement="LumberChunker uses no LLM."))
    with pytest.raises(ValidationError, match="no quote"):
        GoldQuestion.model_validate(question("out_of_corpus"))


def test_the_question_set_is_checked_against_the_corpus_like_the_gold_set(tmp_path):
    questions = one_question_per_category()
    assert check_questions(questions, DOCS) == []
    path = tmp_path / "questions.jsonl"
    path.write_text("".join(q.model_dump_json() + "\n" for q in questions), encoding="utf-8")
    assert load_questions(path) == questions

    questions[0].evidence[0].quote = "LumberChunker uses GPT-4 to find semantic shifts in narrative text."
    problems = check_questions(questions[1:4] + questions[:1], DOCS)
    assert any("q0: quote not found in a.pdf" in p for p in problems)
    assert any("no question in the category out_of_corpus" in p for p in problems)
