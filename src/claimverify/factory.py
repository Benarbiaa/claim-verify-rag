"""
Factory — construit les étapes du pipeline à partir de config.yaml
====================================================================

Chaque registre associe un "type" de config.yaml à la classe qui l'implémente.
Ajouter une implémentation = écrire la classe, puis ajouter une ligne ici.
Le reste du code (orchestrateurs) ne manipule que les interfaces.

Rien n'est coûteux à la construction : aucun appel API, et le modèle
d'embedding n'est chargé qu'au premier usage (BgeEmbedder).
"""

import os
from dataclasses import dataclass, field

from claimverify.answering.decomposition import Decomposer, LLMDecomposer
from claimverify.answering.drafting import Drafter, LLMDrafter
from claimverify.answering.retrieval import HybridRetriever, PgvectorRetriever, Retriever
from claimverify.answering.verification import Judge, LangGraphVerifier, LLMJudge, Verifier
from claimverify.components.embedding import BgeEmbedder, Embedder
from claimverify.indexing.chunking import Chunker, FixedSizeChunker, Tokenizer
from claimverify.indexing.cleaning import Cleaner, MinimalCleaner, NoCleaner
from claimverify.indexing.loading import FileLoader, Loader
from claimverify.llm import LLM, RetryPolicy, UsageMeter, make_llm
from claimverify.settings import LLMStageSettings, RetrieverSettings, Settings

# ---------------------------------------------------------------------------
# Registres : type (dans config.yaml) -> constructeur
# ---------------------------------------------------------------------------

LOADERS = {
    "files": lambda cfg: FileLoader(),
}
CLEANERS = {
    "minimal": lambda cfg: MinimalCleaner(),
    "none": lambda cfg: NoCleaner(),
}
CHUNKERS = {
    "fixed_size": lambda cfg, tokenizer: FixedSizeChunker(tokenizer, cfg.chunk_size, cfg.overlap_ratio),
}
EMBEDDERS = {
    "bge": lambda cfg: BgeEmbedder(cfg.model, cfg.device),
}
RETRIEVERS = {
    "pgvector": lambda cfg, embedder, conn: PgvectorRetriever(embedder, conn, cfg.top_k_per_doc),
    "hybrid": lambda cfg, embedder, conn: HybridRetriever(embedder, conn, cfg.top_k_per_doc),
}
DRAFTERS = {
    "llm": lambda llm: LLMDrafter(llm),
}
DECOMPOSERS = {
    "llm": lambda llm: LLMDecomposer(llm),
}
JUDGES = {
    "llm": lambda llm: LLMJudge(llm),
}
VERIFIERS = {
    "langgraph": lambda retriever, judge: LangGraphVerifier(retriever, judge),
}


def _pick(registry: dict, type_: str, stage: str):
    if type_ not in registry:
        raise ValueError(f"{stage} : type inconnu '{type_}' (disponibles : {sorted(registry)})")
    return registry[type_]


# ---------------------------------------------------------------------------
# Constructeurs par étape
# ---------------------------------------------------------------------------

def build_llm(settings: Settings, stage: LLMStageSettings, role: str,
              meter: UsageMeter | None = None) -> LLM:
    provider = settings.providers[stage.provider]
    api_key = os.getenv(provider.api_key_env)
    if not api_key:
        raise RuntimeError(
            f"Clé API manquante : {provider.api_key_env} (fournisseur '{stage.provider}', "
            f"utilisé par {role}). La définir dans .env."
        )
    retry = RetryPolicy(provider.max_retries, provider.max_wait_seconds, provider.timeout_seconds)
    return make_llm(role, stage.model, provider.base_url, api_key, retry, meter)


def build_embedder(settings: Settings) -> Embedder:
    return _pick(EMBEDDERS, settings.embedding.type, "embedding")(settings.embedding)


def build_loader(settings: Settings) -> Loader:
    cfg = settings.indexing.loader
    return _pick(LOADERS, cfg.type, "indexing.loader")(cfg)


def build_cleaner(settings: Settings) -> Cleaner:
    cfg = settings.indexing.cleaner
    return _pick(CLEANERS, cfg.type, "indexing.cleaner")(cfg)


def build_chunker(settings: Settings, tokenizer: Tokenizer) -> Chunker:
    cfg = settings.indexing.chunker
    return _pick(CHUNKERS, cfg.type, "indexing.chunker")(cfg, tokenizer)


def build_retriever(cfg: RetrieverSettings, embedder: Embedder, conn, stage: str) -> Retriever:
    return _pick(RETRIEVERS, cfg.type, stage)(cfg, embedder, conn)


def build_drafter(settings: Settings, meter: UsageMeter | None = None) -> Drafter:
    cfg = settings.answering.drafter
    return _pick(DRAFTERS, cfg.type, "answering.drafter")(
        build_llm(settings, cfg, "draft", meter))


def build_decomposer(settings: Settings, meter: UsageMeter | None = None) -> Decomposer:
    cfg = settings.answering.decomposer
    return _pick(DECOMPOSERS, cfg.type, "answering.decomposer")(
        build_llm(settings, cfg, "decompose", meter))


def build_judge(settings: Settings, meter: UsageMeter | None = None) -> Judge:
    cfg = settings.answering.verifier.judge
    return _pick(JUDGES, cfg.type, "answering.verifier.judge")(
        build_llm(settings, cfg, "verify", meter))


def build_verifier(settings: Settings, embedder: Embedder, conn,
                   meter: UsageMeter | None = None) -> Verifier:
    cfg = settings.answering.verifier
    retriever = build_retriever(cfg.retriever, embedder, conn, "answering.verifier.retriever")
    return _pick(VERIFIERS, cfg.type, "answering.verifier")(retriever, build_judge(settings, meter))


# ---------------------------------------------------------------------------
# Assemblage des deux pipelines
# ---------------------------------------------------------------------------

@dataclass
class IndexingStages:
    loader: Loader
    cleaner: Cleaner
    chunker: Chunker
    embedder: Embedder


@dataclass
class AnsweringStages:
    retriever: Retriever
    drafter: Drafter
    decomposer: Decomposer
    verifier: Verifier
    # Partagé par tous les LLM du pipeline : l'orchestrateur y lit l'usage de
    # chaque étape sans savoir quelles étapes utilisent un LLM.
    meter: UsageMeter = field(default_factory=UsageMeter)


def build_indexing(settings: Settings, embedder: Embedder | None = None) -> IndexingStages:
    # Le chunker mesure avec l'embedder lui-même : les chunks sont comptés en
    # tokens du modèle qui va les lire, sans réglage à garder synchronisé.
    embedder = embedder or build_embedder(settings)
    if not isinstance(embedder, Tokenizer):
        raise TypeError(f"{type(embedder).__name__} ne fournit pas token_spans : "
                        "le chunker ne peut pas compter ses tokens.")
    return IndexingStages(
        loader=build_loader(settings),
        cleaner=build_cleaner(settings),
        chunker=build_chunker(settings, tokenizer=embedder),
        embedder=embedder,
    )


def build_answering(settings: Settings, conn, embedder: Embedder | None = None) -> AnsweringStages:
    # Un seul embedder pour tous les retrievers : les questions et les claims
    # doivent être embeddés comme les chunks l'ont été.
    embedder = embedder or build_embedder(settings)
    meter = UsageMeter()
    return AnsweringStages(
        retriever=build_retriever(settings.answering.retriever, embedder, conn,
                                  "answering.retriever"),
        drafter=build_drafter(settings, meter),
        decomposer=build_decomposer(settings, meter),
        verifier=build_verifier(settings, embedder, conn, meter),
        meter=meter,
    )
