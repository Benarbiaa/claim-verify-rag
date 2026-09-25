"""Data contracts (claimverify.contracts): validation and JSON round trip. No I/O."""

import pytest
from pydantic import ValidationError

from claimverify.contracts import VERDICT_LABELS, Claim, Draft, Passage, Verdict


def test_verdict_labels_are_defined_once():
    assert VERDICT_LABELS == ("supported", "contradicted", "unverifiable")


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
