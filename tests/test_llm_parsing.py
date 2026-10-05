"""LLM-facing steps tested with a fake client: no network, no GPU, no database."""

import json

import pytest
from openai import BadRequestError

from claimverify.answering.decomposition import decompose_into_claims
from claimverify.answering.verification import judge_with_llm, read_claims_file, should_continue
from claimverify.contracts import Claim, Draft, Passage
from fakes import failing_llm, fake_llm, provider_error

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
    with pytest.raises(RuntimeError, match="malformed"):
        decompose_into_claims(fake_llm('{"claims": [{"id": "c1", "text": "X"}]}'), DRAFT)


CLAIM = Claim(id="c1", claim="X", cited_source="a.pdf")
PASSAGES = [Passage(filename="a.pdf", source_type="peer_reviewed_paper", chunk_index=0,
                    text="Evidence.", score=0.8)]


def judge(raw: str):
    return judge_with_llm(fake_llm(raw, model="judge-model"), CLAIM, PASSAGES)


def test_judge_parses_the_verdict_and_records_its_evidence():
    entry = judge(json.dumps({"verdict": "supported", "justification": "a.pdf says so",
                              "supporting_sources": ["a.pdf"], "contradicting_sources": []}))
    assert entry.verdict == "supported"
    assert entry.original_cited_source == "a.pdf"
    assert entry.verifier == "llm_judge:judge-model"
    assert entry.evidence == PASSAGES


def test_judge_accepts_contested():
    entry = judge(json.dumps({"verdict": "contested", "justification": "a vs b",
                              "supporting_sources": ["a.pdf"], "contradicting_sources": ["b.pdf"]}))
    assert entry.verdict == "contested"


# Every unusable answer becomes "error" (never "unverifiable"), keeping the raw answer.
@pytest.mark.parametrize("raw", [
    '{"verdict": "supported", "justification": "The source states tha',     # truncated
    'Here is my verdict: {"verdict": "supported", "justification": "x"}',   # text around the JSON
    "",                                                                      # empty answer
    '{"verdict": "probably", "justification": "?"}',                         # unknown verdict
    '{"verdict": "Supported", "justification": "x"}',                        # wrong case
    '{"verdict": "supported"}',                                              # missing field
    '[{"verdict": "supported", "justification": "x"}]',                      # not an object
    '{"verdict": "contradicted", "justification": "x", "supporting_sources": ["a.pdf"]}',  # smoke c7
    '{"verdict": "error", "justification": "x"}',                            # judge may not say error
])
def test_unusable_judge_answers_become_error(raw):
    entry = judge(raw)
    assert entry.verdict == "error"
    assert entry.evidence == PASSAGES  # we still know what the judge was shown


def test_provider_json_rejection_becomes_error_instead_of_crashing():
    llm = failing_llm(provider_error("json_validate_failed"))
    entry = judge_with_llm(llm, CLAIM, PASSAGES)
    assert entry.verdict == "error"
    assert "rejected by the provider" in entry.justification


def test_other_provider_errors_are_not_hidden():
    with pytest.raises(BadRequestError):
        judge_with_llm(failing_llm(provider_error("invalid_api_key")), CLAIM, PASSAGES)


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


@pytest.mark.parametrize("content", [
    {"claims": [{"id": "c1", "claim": "A"}]},   # what decomposition.py saves
    [{"id": "c1", "claim": "A"}],               # a plain list of claims
])
def test_a_claims_file_is_read_in_both_formats(tmp_path, content):
    path = tmp_path / "claims.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    assert read_claims_file(str(path)) == [Claim(id="c1", claim="A")]
