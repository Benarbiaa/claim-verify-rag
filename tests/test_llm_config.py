"""Per-role LLM configuration (claimverify.llm): pure env-var resolution, no network."""

import pytest

from claimverify import llm as llm_mod

ENV_VARS = [
    f"{prefix}_{key}"
    for prefix in ("DRAFT", "DECOMPOSE", "VERIFY", "LLM")
    for key in ("MODEL", "BASE_URL", "API_KEY")
] + ["GROQ_API_KEY"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_use_a_different_model_family_for_verification(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    draft = llm_mod.get_config("draft")
    verify = llm_mod.get_config("verify")

    assert draft.base_url == verify.base_url == llm_mod.GROQ_BASE_URL
    assert draft.model != verify.model
    assert draft.api_key == verify.api_key == "gsk_test"


def test_role_specific_variables_override_defaults(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("VERIFY_MODEL", "qwen2.5:14b")
    monkeypatch.setenv("VERIFY_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("VERIFY_API_KEY", "ollama")

    verify = llm_mod.get_config("verify")
    assert (verify.model, verify.base_url, verify.api_key) == (
        "qwen2.5:14b", "http://localhost:11434/v1", "ollama")
    # other roles untouched
    assert llm_mod.get_config("draft").base_url == llm_mod.GROQ_BASE_URL


def test_legacy_llm_model_does_not_override_the_verifier(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-oss-120b")
    assert llm_mod.get_config("verify").model == llm_mod.DEFAULT_MODELS["verify"]


def test_groq_key_is_never_sent_to_another_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("VERIFY_BASE_URL", "https://api.mistral.ai/v1")
    with pytest.raises(RuntimeError, match="VERIFY_API_KEY"):
        llm_mod.get_config("verify")


def test_missing_key_fails_early():
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        llm_mod.get_config("draft")


def test_unknown_role_is_rejected(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    with pytest.raises(ValueError):
        llm_mod.get_config("judge")
