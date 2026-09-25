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

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

DEFAULT_CONFIG_PATH = Path("config.yaml")


class _Strict(BaseModel):
    # Une clé inconnue est une erreur, pas une clé ignorée en silence.
    model_config = ConfigDict(extra="forbid")


class ProviderSettings(_Strict):
    base_url: str
    api_key_env: str  # nom de la variable de .env qui contient la clé


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


class ChunkerSettings(_Strict):
    type: Literal["fixed_size"]
    chunk_size: PositiveInt
    overlap_ratio: float = Field(ge=0, lt=1)


class RetrieverSettings(_Strict):
    type: Literal["pgvector"]
    top_k_per_doc: PositiveInt


class VerifierSettings(_Strict):
    type: Literal["langgraph"]
    retriever: RetrieverSettings
    judge: LLMStageSettings


class IndexingSettings(_Strict):
    loader: LoaderSettings
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
    with open(path, encoding="utf-8") as f:
        return Settings.model_validate(yaml.safe_load(f))
