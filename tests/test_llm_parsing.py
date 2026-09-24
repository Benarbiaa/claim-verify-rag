"""LLM-facing steps tested with a fake client: no network, no GPU, no database."""

import json
from types import SimpleNamespace

import pytest

from claimverify.decompose_claims import decompose_into_claims
from claimverify.llm import LLM
from claimverify.verify_claims import should_continue, verdict_node


class FakeClient:
    """Mimics openai.OpenAI().chat.completions.create and returns a fixed string."""

    def __init__(self, content: str):
        message = SimpleNamespace(content=content)
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        self.calls = []

        def create(**kwargs):
            self.calls.append(kwargs)
            return response

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def fake_llm(content: str, model: str = "fake-model") -> LLM:
    return LLM(role="test", model=model, base_url="http://fake", client=FakeClient(content))


def test_decompose_returns_claims():
    payload = {"claims": [{"id": "c1", "claim": "RAG was introduced in 2020.", "cited_source": None}]}
    claims = decompose_into_claims(fake_llm(json.dumps(payload)), "draft")
    assert claims == payload["claims"]


def test_decompose_rejects_invalid_json():
    with pytest.raises(RuntimeError):
        decompose_into_claims(fake_llm("not json"), "draft")


def test_decompose_rejects_empty_claims():
    with pytest.raises(RuntimeError):
        decompose_into_claims(fake_llm('{"claims": []}'), "draft")


def _state(llm, claims=None, index=0):
    return {
        "claims": claims or [{"id": "c1", "claim": "X", "cited_source": "a.pdf"}],
        "current_index": index,
        "verdicts": [],
        "embed_model": None,
        "db_conn": None,
        "llm": llm,
        "current_evidence": "[Source: a.pdf | chunk #0 | type: peer_reviewed_paper]\n...",
    }


def test_verdict_node_parses_verdict_and_advances():
    verdict = {
        "verdict": "supported",
        "justification": "a.pdf says so",
        "supporting_sources": ["a.pdf"],
        "contradicting_sources": [],
    }
    update = verdict_node(_state(fake_llm(json.dumps(verdict), model="judge-model")))
    assert update["current_index"] == 1
    entry = update["verdicts"][0]
    assert entry["verdict"] == "supported"
    assert entry["original_cited_source"] == "a.pdf"
    assert entry["verifier_model"] == "judge-model"


def test_verdict_node_falls_back_to_unverifiable_on_bad_json():
    update = verdict_node(_state(fake_llm("oops")))
    assert update["verdicts"][0]["verdict"] == "unverifiable"


def test_should_continue_loops_until_claims_exhausted():
    claims = [{"id": "c1", "claim": "a"}, {"id": "c2", "claim": "b"}]
    assert should_continue(_state(None, claims, index=1)) == "retrieve"
    assert should_continue(_state(None, claims, index=2)) == "end"


def test_json_mode_is_requested_for_structured_steps():
    llm = fake_llm('{"claims": [{"id": "c1", "claim": "x", "cited_source": null}]}', model="m")
    decompose_into_claims(llm, "draft")
    call = llm.client.calls[0]
    assert call["model"] == "m"
    assert call["response_format"] == {"type": "json_object"}
