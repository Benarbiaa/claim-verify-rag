"""
The shape of config.yaml — validated at startup
===============================================

config.yaml says WHICH implementation each stage uses, with which settings.
This module describes its shape with Pydantic: an unknown key (a typo), an
unknown stage type, an undeclared provider or an out-of-range value stops the
program at startup, with a clear message.

Secrets (API keys, DB_URL) stay in .env: config.yaml only holds the NAME of
the variable that carries the key (api_key_env).

To add an implementation (e.g. an "nli" judge): add its settings model here,
and one line to the registry in factory.py.
"""

import argparse
import os
import warnings
from pathlib import Path
from typing import Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    model_validator,
)

import claimverify.config  # noqa: F401  (loads .env before it is read below)

DEFAULT_CONFIG_PATH = Path("config.yaml")

# Old .env variables (per-role config): replaced by config.yaml.
LEGACY_ENV_VARS = [f"{role}_{key}" for role in ("DRAFT", "DECOMPOSE", "VERIFY", "LLM")
                   for key in ("MODEL", "BASE_URL", "API_KEY")]


class _Strict(BaseModel):
    # An unknown key is an error, not a key silently ignored.
    model_config = ConfigDict(extra="forbid")


class ProviderSettings(_Strict):
    base_url: str
    api_key_env: str  # name of the .env variable that holds the key
    # Retries (see llm.py): limits differ from one provider to another.
    max_retries: NonNegativeInt = 6
    max_wait_seconds: PositiveFloat = 60
    timeout_seconds: PositiveFloat = 120


class LLMStageSettings(_Strict):
    type: Literal["llm"]
    provider: str
    model: str


class EmbeddingSettings(_Strict):
    type: Literal["bge"]
    model: str
    device: str = "cuda"


class LoaderSettings(_Strict):
    type: Literal["files"]


class CleanerSettings(_Strict):
    type: Literal["minimal", "none"]


class ChunkerSettings(_Strict):
    type: Literal["fixed_size"]
    chunk_size: PositiveInt
    overlap_ratio: float = Field(ge=0, lt=1)


class RerankSettings(_Strict):
    model: str
    candidates: PositiveInt = 10   # passages per document reread by the reranker
    device: str = "cuda"


class RetrieverSettings(_Strict):
    type: Literal["pgvector", "hybrid"]  # by meaning only, or meaning + exact words (BM25)
    top_k_per_doc: PositiveInt
    rerank: RerankSettings | None = None  # absent: no reranker

    @model_validator(mode="after")
    def _enough_candidates(self) -> "RetrieverSettings":
        if self.rerank and self.rerank.candidates < self.top_k_per_doc:
            raise ValueError(f"rerank.candidates ({self.rerank.candidates}) must be >= "
                             f"top_k_per_doc ({self.top_k_per_doc})")
        return self


class VerifierSettings(_Strict):
    type: Literal["langgraph"]
    retriever: RetrieverSettings
    judge: LLMStageSettings


class IndexingSettings(_Strict):
    loader: LoaderSettings
    cleaner: CleanerSettings
    chunker: ChunkerSettings


class AnsweringSettings(_Strict):
    retriever: RetrieverSettings
    drafter: LLMStageSettings
    decomposer: LLMStageSettings
    verifier: VerifierSettings


class Settings(_Strict):
    providers: dict[str, ProviderSettings]
    embedding: EmbeddingSettings
    indexing: IndexingSettings
    answering: AnsweringSettings

    @model_validator(mode="after")
    def _providers_exist(self) -> "Settings":
        a = self.answering
        for stage, cfg in [("drafter", a.drafter), ("decomposer", a.decomposer),
                           ("verifier.judge", a.verifier.judge)]:
            if cfg.provider not in self.providers:
                raise ValueError(f"answering.{stage}: unknown provider '{cfg.provider}' "
                                 f"(declared: {sorted(self.providers)})")
        return self


def load_settings(path: Path = DEFAULT_CONFIG_PATH) -> Settings:
    legacy = [name for name in LEGACY_ENV_VARS if os.getenv(name)]
    if legacy:
        warnings.warn(f"Ignored variables (models are chosen in {path}): "
                      f"{', '.join(legacy)}. Remove them from .env.", stacklevel=2)
    with open(path, encoding="utf-8") as f:
        return Settings.model_validate(yaml.safe_load(f))


def add_config_argument(parser: argparse.ArgumentParser) -> None:
    """Adds --config (default: config.yaml) to a script."""
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH,
                        help="Pipeline configuration file (default: config.yaml).")
