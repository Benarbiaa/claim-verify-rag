"""LLM-facing steps tested with a fake client: no network, no GPU, no database."""

import json

import pytest

from claimverify.answering.decomposition import decompose_into_claims
from claimverify.answering.verification import judge_with_llm, should_continue
from claimverify.contracts import Claim, Draft
from fakes import fake_llm

DRAFT = Draft(question="Q?", text="RAG was introduced in 2020.", passages=[])


def test_decompose_returns_claims():
    payload = {"claims": [{"id": "c1", "claim": "RAG was introduced in 2020.", "cited_source": None}]}
    claims = decompose_into_claims(fake_llm(json.dumps(payload)), DRAFT)
    assert claims == [Claim(id="c1", claim="RAG was introduced in 2020.")]


def test_decompose_rejects_invalid_json():
    with pytest.raises(RuntimeError):
        decompose_into_claims(fake_llm("not json"), DRAFT)


def test_decompose_rejects_empty_claims():
    with pytest.raises(RuntimeError):
        decompose_into_claims(fake_llm('{"claims": []}'), DRAFT)


def test_decompose_rejects_a_malformed_claim_at_the_boundary():
    # e.g. a model that writes "text" instead of "claim": caught here, not inside verification
    with pytest.raises(RuntimeError, match="mal formé"):
        decompose_into_claims(fake_llm('{"claims": [{"id": "c1", "text": "X"}]}'), DRAFT)


CLAIM = Claim(id="c1", claim="X", cited_source="a.pdf")
EVIDENCE = "[Source: a.pdf | chunk #0 | type: peer_reviewed_paper]\n..."


def test_judge_parses_the_verdict():
    verdict = {
        "verdict": "supported",
        "justification": "a.pdf says so",
        "supporting_sources": ["a.pdf"],
        "contradicting_sources": [],
    }
    entry = judge_with_llm(fake_llm(json.dumps(verdict), model="judge-model"), CLAIM, EVIDENCE)
    assert entry.verdict == "supported"
    assert entry.original_cited_source == "a.pdf"
    assert entry.verifier == "llm_judge:judge-model"


def test_judge_falls_back_to_unverifiable_on_bad_json():
    assert judge_with_llm(fake_llm("oops"), CLAIM, EVIDENCE).verdict == "unverifiable"


def test_judge_falls_back_to_unverifiable_on_unknown_label():
    raw = '{"verdict": "probably", "justification": "?"}'
    assert judge_with_llm(fake_llm(raw), CLAIM, EVIDENCE).verdict == "unverifiable"


def test_should_continue_loops_until_claims_exhausted():
    state = {"claims": [Claim(id="c1", claim="a"), Claim(id="c2", claim="b")], "current_index": 1}
    assert should_continue(state) == "retrieve"
    assert should_continue({**state, "current_index": 2}) == "end"


def test_json_mode_is_requested_for_structured_steps():
    llm = fake_llm('{"claims": [{"id": "c1", "claim": "x", "cited_source": null}]}', model="m")
    decompose_into_claims(llm, DRAFT)
    call = llm.client.calls[0]
    assert call["model"] == "m"
    assert call["response_format"] == {"type": "json_object"}
