"""
Recherche lexicale — BM25 et fusion de classements
===================================================

L'embedding capte le SUJET d'un passage, pas le détail exact : dans un
article où tous les chunks parlent de "RAG", un chiffre ("400M", "7.37") ou
un nom ("FAISS") pèse à peine dans le vecteur. BM25 fait l'inverse : il ne
comprend pas le sens, il compte les mots, et un mot RARE dans le corpus pèse
beaucoup. Les deux se complètent ; reciprocal_rank_fusion fusionne leurs
classements.

Composant partagé : utilisé par la mesure du retrieval (retrieval_eval.py),
et par le pipeline si la mesure montre un gain.
"""

import math
import re
import unicodedata
from collections import Counter

# Mots, nombres et codes gardés entiers : "7.37", "400m", "bart-large", "f1@5".
_TOKEN = re.compile(r"\w+(?:[.\-@/]\w+)*")

K1 = 1.5   # saturation : la 10e occurrence d'un mot rapporte moins que la 2e
B = 0.75   # normalisation par la longueur : un long texte ne gagne pas juste parce qu'il est long
RRF_K = 60  # constante de la fusion par rangs (valeur de l'article d'origine, non réglée)


def tokenize(text: str) -> list[str]:
    """'BART-large with 400M parameters (7.37%)' -> ['bart-large', 'with', '400m', 'parameters', '7.37']"""
    return _TOKEN.findall(unicodedata.normalize("NFKC", text).lower())


class Bm25Index:
    """BM25 (Robertson) sur une liste de textes, avec l'IDF toujours positif de
    Lucene. Les poids des mots sont calculés sur TOUS les textes donnés."""

    def __init__(self, texts: list[str], k1: float = K1, b: float = B):
        self.k1, self.b = k1, b
        self.counts = [Counter(tokenize(t)) for t in texts]
        self.lengths = [sum(c.values()) for c in self.counts]
        self.avg_length = sum(self.lengths) / len(self.lengths) if texts else 0.0
        # Rareté d'un mot : présent dans peu de textes -> poids fort.
        n = len(texts)
        df = Counter(word for c in self.counts for word in c)
        self.idf = {word: math.log(1 + (n - d + 0.5) / (d + 0.5)) for word, d in df.items()}

    def scores(self, query: str) -> list[float]:
        """Un score par texte, dans l'ordre des textes donnés au constructeur."""
        words = set(tokenize(query))  # un mot répété dans la requête ne compte qu'une fois
        result = []
        for counts, length in zip(self.counts, self.lengths, strict=True):
            norm = self.k1 * (1 - self.b + self.b * length / self.avg_length) if self.avg_length else self.k1
            result.append(sum(
                self.idf[w] * counts[w] * (self.k1 + 1) / (counts[w] + norm)
                for w in words if counts[w]
            ))
        return result


def reciprocal_rank_fusion(rankings: list[list[int]], k: int = RRF_K) -> list[int]:
    """Fusionne plusieurs classements des mêmes éléments (du meilleur au moins
    bon) : score = somme de 1 / (k + rang). On fusionne des RANGS, pas des
    scores : un cosinus (0 à 1) et un score BM25 (sans borne) ne sont pas
    comparables, et aucun poids n'est à régler. À égalité, l'ordre du premier
    classement est gardé."""
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            fused[item] = fused.get(item, 0.0) + 1 / (k + rank)
    first = {item: i for i, item in enumerate(rankings[0])} if rankings else {}
    return sorted(fused, key=lambda item: (-fused[item], first.get(item, len(first))))
