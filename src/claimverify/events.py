"""
Événements des pipelines — ce que chaque étape a produit
=========================================================

Après chaque étape, l'orchestrateur (indexing/ingest.py, answering/pipeline.py)
émet un événement qui contient la SORTIE de l'étape. Des "sinks" les reçoivent
(voir reporting.py) : une ligne courte dans le terminal, l'enregistrement
complet dans runs/<run_id>/events.jsonl, et plus tard l'interface.

Les étapes elles-mêmes n'émettent rien : elles restent indépendantes de tout
affichage (patron observateur, l'orchestrateur étant le seul émetteur).

Chaque événement a un champ "type" : un fichier events.jsonl se relit en
objets identiques (load_events dans reporting.py).
"""

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from claimverify.contracts import Chunk, Claim, Draft, Passage, Verdict

Pipeline = Literal["indexing", "answering"]


class Usage(BaseModel):
    """Appels aux LLM pendant une étape (tout à zéro pour une étape sans LLM)."""
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    retries: int = 0            # nouvelles tentatives après une erreur temporaire
    waited_seconds: float = 0   # temps passé à attendre avant ces tentatives
    seconds: float = 0          # durée totale des appels, attentes comprises

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(**{name: getattr(self, name) + getattr(other, name)
                        for name in type(self).model_fields})


class Event(BaseModel):
    """Champs communs, remplis par Run.emit (reporting.py)."""
    run_id: str
    pipeline: Pipeline
    time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- Les deux pipelines -----------------------------------------------------------

class RunStarted(Event):
    type: Literal["run_started"] = "run_started"
    config: dict       # config.yaml complet, pour reproduire le run
    inputs: dict       # ex. {"corpus_dir": ...} ou {"questions": [...]}


class RunFinished(Event):
    type: Literal["run_finished"] = "run_finished"
    summary: dict
    seconds: float


# --- Indexation --------------------------------------------------------------------

class DocumentSummary(BaseModel):
    """Un document sans son texte (le texte est dans data/corpus/)."""
    doc_id: str
    filename: str
    source_type: str
    characters: int


class DocumentsLoaded(Event):
    type: Literal["documents_loaded"] = "documents_loaded"
    documents: list[DocumentSummary]
    seconds: float


class ChunksBuilt(Event):
    type: Literal["chunks_built"] = "chunks_built"
    chunks: list[Chunk]  # sans vecteur : les vecteurs sont dans la base
    seconds: float


class ChunksEmbedded(Event):
    type: Literal["chunks_embedded"] = "chunks_embedded"
    count: int
    dimension: int
    seconds: float


class ChunksStored(Event):
    type: Literal["chunks_stored"] = "chunks_stored"
    count: int
    seconds: float


# --- Réponse à une question (question_index : position dans le run) -----------------

class QuestionStarted(Event):
    type: Literal["question_started"] = "question_started"
    question_index: int
    question: str


class PassagesRetrieved(Event):
    type: Literal["passages_retrieved"] = "passages_retrieved"
    question_index: int
    passages: list[Passage]
    seconds: float
    usage: Usage = Usage()


class DraftWritten(Event):
    type: Literal["draft_written"] = "draft_written"
    question_index: int
    draft: Draft
    seconds: float
    usage: Usage = Usage()


class ClaimsExtracted(Event):
    type: Literal["claims_extracted"] = "claims_extracted"
    question_index: int
    claims: list[Claim]
    seconds: float
    usage: Usage = Usage()


class ClaimVerified(Event):
    type: Literal["claim_verified"] = "claim_verified"
    question_index: int
    position: int      # 1, 2, ... sur `total`
    total: int
    verdict: Verdict   # contient les passages jugés (evidence)
    usage: Usage = Usage()


class QuestionFinished(Event):
    type: Literal["question_finished"] = "question_finished"
    question_index: int
    verdict_counts: dict[str, int]
    seconds: float


AnyEvent = Annotated[
    RunStarted | RunFinished
    | DocumentsLoaded | ChunksBuilt | ChunksEmbedded | ChunksStored
    | QuestionStarted | PassagesRetrieved | DraftWritten | ClaimsExtracted | ClaimVerified
    | QuestionFinished,
    Field(discriminator="type"),
]
