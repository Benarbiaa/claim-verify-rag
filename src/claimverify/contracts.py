"""
Contrats de données du pipeline
================================

Les objets qui circulent entre les étapes, définis ici une seule fois.
Chaque étape ne connaît des autres que ces contrats : on peut remplacer
l'implémentation d'une étape (autre LLM, modèle local, classifieur...) sans
toucher au reste, tant qu'elle consomme et produit ces objets.

    INDEXATION   Document -> Chunk
    RÉPONSE      question -> Passage -> Draft -> Claim -> Verdict

Tous les contrats sont des modèles Pydantic : ils valident les données (utile
pour les sorties de LLM) et se sérialisent en JSON, ce qui permet de lancer
chaque étape seule, à partir du fichier produit par l'étape précédente.
"""

from typing import Literal, get_args

from pydantic import BaseModel

# Les verdicts possibles, définis une seule fois. Toute étape qui en a besoin
# (rapport, résumé, évaluation) les importe d'ici au lieu de les recopier.
VerdictLabel = Literal["supported", "contradicted", "unverifiable"]
VERDICT_LABELS: tuple[str, ...] = get_args(VerdictLabel)


# --- Indexation ---------------------------------------------------------------

class Document(BaseModel):
    """Un fichier du corpus, converti en texte brut."""
    doc_id: str
    filename: str
    source_type: str
    text: str


class Chunk(BaseModel):
    """Un morceau de document, l'unité stockée et recherchée."""
    chunk_id: str
    doc_id: str
    filename: str
    source_type: str
    chunk_index: int
    text: str
    embedding: list[float] | None = None  # rempli par l'embedder


# --- Réponse à une question ----------------------------------------------------

class Passage(BaseModel):
    """Un chunk renvoyé par le retriever, avec son score de similarité."""
    filename: str
    source_type: str
    chunk_index: int
    text: str
    score: float


class Draft(BaseModel):
    """La réponse brouillon, et les passages sur lesquels elle s'appuie."""
    question: str
    text: str
    passages: list[Passage]


class Claim(BaseModel):
    """Une affirmation atomique extraite du brouillon."""
    id: str
    claim: str
    cited_source: str | None = None


class Verdict(BaseModel):
    """Le jugement porté sur un claim par le vérifieur."""
    claim_id: str
    claim: str
    verdict: VerdictLabel
    justification: str
    supporting_sources: list[str] = []
    contradicting_sources: list[str] = []
    original_cited_source: str | None = None
    verifier: str  # quelle implémentation a jugé (ex. "llm_judge:qwen/qwen3.8-27b")
