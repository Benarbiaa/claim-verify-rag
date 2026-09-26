"""Data contracts (claimverify.contracts): validation and JSON round trip. No I/O."""

import pytest
from pydantic import ValidationError

from claimverify.contracts import (
    JUDGE_LABELS,
    VERDICT_ICONS,
    VERDICT_LABELS,
    Claim,
    Draft,
    Passage,
    Verdict,
)


def test_verdict_labels_are_defined_once():
    assert JUDGE_LABELS == ("supported", "contradicted", "contested", "unverifiable")
    # "error" is set by our code, never offered to the judge
    assert VERDICT_LABELS == (*JUDGE_LABELS, "error")


def verdict(label, supporting=(), contradicting=()):
    return Verdict(claim_id="c1", claim="X", verdict=label, justification="...", verifier="test",
                   supporting_sources=list(supporting), contradicting_sources=list(contradicting))


def test_contradicted_must_name_a_contradicting_source():
    with pytest.raises(ValidationError, match="contradicted"):
        verdict("contradicted", supporting=["a.pdf"])  # the smoke-run c7 case
    assert verdict("contradicted", contradicting=["a.pdf"]).verdict == "contradicted"


def test_contested_must_name_sources_on_both_sides():
    with pytest.raises(ValidationError, match="contested"):
        verdict("contested", supporting=["a.pdf"])
    assert verdict("contested", supporting=["a.pdf"], contradicting=["b.pdf"]).verdict == "contested"


def test_every_verdict_label_has_an_icon():
    assert set(VERDICT_ICONS) == set(VERDICT_LABELS)


def test_unknown_verdict_label_is_rejected():
    with pytest.raises(ValidationError):
        Verdict(claim_id="c1", claim="X", verdict="probably", justification="?", verifier="test")


def test_missing_required_field_is_rejected():
    with pytest.raises(ValidationError):
        Claim(id="c1")  # no claim text


def test_draft_survives_a_json_round_trip():
    # This is what lets a stage run alone: save its output, load it in the next stage.
    passage = Passage(filename="a.pdf", source_type="peer_reviewed_paper", chunk_index=3,
                      text="Evidence.", score=0.82)
    draft = Draft(question="Q?", text="Answer [a.pdf].", passages=[passage])
    assert Draft.model_validate_json(draft.model_dump_json()) == draft
