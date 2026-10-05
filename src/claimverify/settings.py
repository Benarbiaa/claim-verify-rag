"""
Forme de config.yaml — validée au démarrage
=============================================

config.yaml décrit QUELLE implémentation chaque étape utilise et avec quels
réglages. Ce module en décrit la forme avec Pydantic : une clé inconnue (faute
de frappe), un type d'étape inconnu, un fournisseur non déclaré ou une valeur
hors limites arrêtent le programme au démarrage, avec un message clair.

Les secrets (clés API, DB_URL) restent dans .env : config.yaml ne contient que
le NOM de la variable qui porte la clé (api_key_env).

Pour ajouter une implémentation (ex. un juge "nli") : ajouter son modèle de
réglages ici, et une ligne dans le registre de factory.py.
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

import claimverify.config  # noqa: F401  (charge le .env avant de le lire ci-dessous)

DEFAULT_CONFIG_PATH = Path("config.yaml")

# Anciennes variables de .env (config par rôle) : remplacées par config.yaml.
LEGACY_ENV_VARS = [f"{role}_{key}" for role in ("DRAFT", "DECOMPOSE", "VERIFY", "LLM")
                   for key in ("MODEL", "BASE_URL", "API_KEY")]


class _Strict(BaseModel):
    # Une clé inconnue est une erreur, pas une clé ignorée en silence.
    model_config = ConfigDict(extra="forbid")


class ProviderSettings(_Strict):
    base_url: str
    api_key_env: str  # nom de la variable de .env qui contient la clé
    # Nouvelles tentatives (voir llm.py) : les limites varient d'un fournisseur à l'autre.
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
    candidates: PositiveInt = 10   # passages par document relus par le reranker
    device: str = "cuda"


class RetrieverSettings(_Strict):
    type: Literal["pgvector", "hybrid"]  # par le sens seulement, ou sens + mots exacts (BM25)
    top_k_per_doc: PositiveInt
    rerank: RerankSettings | None = None  # absent : pas de reranker

    @model_validator(mode="after")
    def _enough_candidates(self) -> "RetrieverSettings":
        if self.rerank and self.rerank.candidates < self.top_k_per_doc:
            raise ValueError(f"rerank.candidates ({self.rerank.candidates}) doit être >= "
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
                raise ValueError(f"answering.{stage}: fournisseur inconnu '{cfg.provider}' "
                                 f"(déclarés : {sorted(self.providers)})")
        return self


def load_settings(path: Path = DEFAULT_CONFIG_PATH) -> Settings:
    legacy = [name for name in LEGACY_ENV_VARS if os.getenv(name)]
    if legacy:
        warnings.warn(f"Variables ignorées (les modèles se choisissent dans {path}) : "
                      f"{', '.join(legacy)}. Les retirer de .env.", stacklevel=2)
    with open(path, encoding="utf-8") as f:
        return Settings.model_validate(yaml.safe_load(f))


def add_config_argument(parser: argparse.ArgumentParser) -> None:
    """Ajoute --config (défaut : config.yaml) à un script."""
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH,
                        help="Fichier de configuration du pipeline (défaut : config.yaml).")
