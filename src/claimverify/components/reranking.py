"""
Reranking — relire chaque candidat AVEC le claim
=================================================

L'embedding est un bi-encodeur : il transforme le claim et chaque chunk en
vecteurs SÉPARÉMENT, puis les compare. Il capte le sujet, pas la réponse.

Un cross-encodeur lit le claim et un chunk ENSEMBLE, dans une seule entrée :
son attention relie chaque mot de l'un à chaque mot de l'autre, et il juge si
le chunk répond au claim. Trop lent pour tout le corpus (un passage du modèle
par paire), il ne fait que RE-TRIER une courte liste de candidats ramenés par
la recherche.

Le modèle tourne en local (GPU) : aucun appel d'API.
"""

from functools import cached_property
from typing import Protocol, runtime_checkable

RERANKER_MODEL = "BAAI/bge-reranker-base"


@runtime_checkable
class Reranker(Protocol):
    """Interface : un score de pertinence par texte, pour une requête."""

    def scores(self, query: str, texts: list[str]) -> list[float]: ...


class CrossEncoderReranker:
    """Implémentation : un cross-encodeur de sentence-transformers."""

    def __init__(self, model_name: str = RERANKER_MODEL, device: str = "cuda"):
        self.model_name = model_name
        self.device = device

    @cached_property
    def model(self):
        # Chargé au premier usage seulement, comme l'embedder.
        from sentence_transformers import CrossEncoder
        return CrossEncoder(self.model_name, device=self.device)

    def scores(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        return [float(s) for s in self.model.predict([(query, t) for t in texts], show_progress_bar=False)]


def rerank(query: str, candidates: list[int], texts: list[str], reranker: Reranker) -> list[int]:
    """Re-trie `candidates` (indices dans `texts`) du plus au moins pertinent."""
    scores = reranker.scores(query, [texts[i] for i in candidates])
    order = sorted(range(len(candidates)), key=lambda j: scores[j], reverse=True)
    return [candidates[j] for j in order]
