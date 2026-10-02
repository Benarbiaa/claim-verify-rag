"""config.yaml validation (claimverify.settings) and stage building (claimverify.factory).

No network: API keys are fake, no request is sent, and the embedding model is never loaded.
"""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from claimverify.answering.decomposition import LLMDecomposer
from claimverify.answering.drafting import LLMDrafter
from claimverify.answering.retrieval import PgvectorRetriever
from claimverify.answering.verification import LangGraphVerifier, LLMJudge
from claimverify.components.embedding import BgeEmbedder
from claimverify.factory import build_answering, build_indexing
from claimverify.indexing.chunking import FixedSizeChunker
from claimverify.indexing.cleaning import MinimalCleaner, NoCleaner
from claimverify.indexing.loading import FileLoader
from claimverify.settings import LEGACY_ENV_VARS, Settings, load_settings

CONFIG = Path(__file__).parent.parent / "config.yaml"


@pytest.fixture(autouse=True)
def no_legacy_env(monkeypatch):
    # Tests must not depend on the developer's .env.
    for name in LEGACY_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def raw_config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


# --- settings: the real config.yaml, and invalid variants ------------------------

def test_config_yaml_holds_todays_values():
    s = load_settings(CONFIG)
    assert (s.indexing.chunker.chunk_size, s.indexing.chunker.overlap_ratio) == (512, 0.15)
    assert s.answering.retriever.top_k_per_doc == s.answering.verifier.retriever.top_k_per_doc == 2
    assert s.answering.drafter.model == "openai/gpt-oss-120b"
    assert s.answering.verifier.judge.model == "qwen/qwen3.8-27b"


def test_a_typo_in_a_key_is_rejected():
    cfg = raw_config()
    cfg["indexing"]["chunker"]["chunk_sise"] = cfg["indexing"]["chunker"].pop("chunk_size")
    with pytest.raises(ValidationError, match="chunk_sise"):
        Settings.model_validate(cfg)


def test_an_unknown_stage_type_is_rejected():
    cfg = raw_config()
    cfg["answering"]["verifier"]["judge"]["type"] = "nli"
    with pytest.raises(ValidationError):
        Settings.model_validate(cfg)


def test_an_undeclared_provider_is_rejected():
    cfg = raw_config()
    cfg["answering"]["drafter"]["provider"] = "openrouter"
    with pytest.raises(ValidationError, match="fournisseur inconnu 'openrouter'"):
        Settings.model_validate(cfg)


@pytest.mark.parametrize("section, key, value", [
    ("chunker", "chunk_size", 0),
    ("chunker", "overlap_ratio", 1.5),
])
def test_out_of_range_values_are_rejected(section, key, value):
    cfg = raw_config()
    cfg["indexing"][section][key] = value
    with pytest.raises(ValidationError):
        Settings.model_validate(cfg)


# --- factory: config.yaml -> ready-to-use stages ----------------------------------

@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_fake")
    return load_settings(CONFIG)


def test_build_indexing(settings):
    stages = build_indexing(settings)
    assert isinstance(stages.loader, FileLoader)
    assert isinstance(stages.cleaner, MinimalCleaner)
    assert isinstance(stages.chunker, FixedSizeChunker)
    assert (stages.chunker.chunk_size, stages.chunker.overlap_ratio) == (512, 0.15)
    assert isinstance(stages.embedder, BgeEmbedder)
    # chunks are measured by the very model that will embed them
    assert stages.chunker.tokenizer is stages.embedder


def test_an_embedder_that_cannot_count_tokens_is_refused(settings):
    from test_interfaces import FakeEmbedder
    with pytest.raises(TypeError, match="token_spans"):
        build_indexing(settings, embedder=FakeEmbedder())


def test_cleaning_can_be_turned_off_for_comparison(settings):
    raw = settings.model_copy(deep=True)
    raw.indexing.cleaner.type = "none"
    assert isinstance(build_indexing(raw).cleaner, NoCleaner)


def test_build_answering(settings):
    stages = build_answering(settings, conn=None)
    assert isinstance(stages.retriever, PgvectorRetriever)
    assert isinstance(stages.drafter, LLMDrafter)
    assert isinstance(stages.decomposer, LLMDecomposer)
    assert isinstance(stages.verifier, LangGraphVerifier)
    assert isinstance(stages.verifier.judge, LLMJudge)
    assert stages.drafter.llm.model == "openai/gpt-oss-120b"
    assert stages.verifier.judge.llm.model == "qwen/qwen3.8-27b"
    assert stages.verifier.judge.llm.base_url == "https://api.groq.com/openai/v1"


def test_every_retriever_shares_one_embedder(settings):
    stages = build_answering(settings, conn=None)
    assert stages.retriever.embedder is stages.verifier.retriever.embedder


def test_a_config_change_swaps_the_judge_without_code_changes(settings, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    cfg = settings.model_dump()
    cfg["answering"]["verifier"]["judge"].update(provider="gemini", model="gemini-3.5-flash")
    judge = build_answering(Settings.model_validate(cfg), conn=None).verifier.judge
    assert (judge.llm.model, judge.llm.base_url) == (
        "gemini-3.5-flash", "https://generativelanguage.googleapis.com/v1beta/openai/")


def test_a_missing_api_key_names_the_env_variable(settings, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        build_answering(settings, conn=None)


def test_the_judge_uses_a_different_model_from_the_drafter():
    # The core idea of the project: the judge must not grade its own work.
    a = load_settings(CONFIG).answering
    assert a.verifier.judge.model != a.drafter.model


def test_each_provider_only_receives_its_own_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    cfg = load_settings(CONFIG).model_dump()
    cfg["answering"]["verifier"]["judge"].update(provider="gemini", model="gemini-3.5-flash")
    stages = build_answering(Settings.model_validate(cfg), conn=None)
    assert stages.drafter.llm.client.api_key == "groq-key"
    assert stages.verifier.judge.llm.client.api_key == "gemini-key"


def test_legacy_model_variables_trigger_a_warning(monkeypatch):
    monkeypatch.setenv("VERIFY_MODEL", "some-model")
    with pytest.warns(UserWarning, match="VERIFY_MODEL"):
        load_settings(CONFIG)


def test_llms_get_the_providers_retry_settings_and_one_shared_meter(settings):
    stages = build_answering(settings, conn=None)
    judge_llm = stages.verifier.judge.llm
    assert (judge_llm.retry.max_retries, judge_llm.retry.max_wait_seconds) == (6, 60)
    assert stages.drafter.llm.meter is judge_llm.meter is stages.meter
