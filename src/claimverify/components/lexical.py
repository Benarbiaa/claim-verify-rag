"""
Lexical search — BM25 and rank fusion
=====================================

An embedding captures the TOPIC of a passage, not the exact detail: in a
paper where every chunk talks about "RAG", a figure ("400M", "7.37") or a name
("FAISS") barely weighs in the vector. BM25 does the opposite: it does not
understand meaning, it counts words, and a word that is RARE in the corpus
weighs a lot. The two complement each other; reciprocal_rank_fusion merges
their rankings.

Shared component: used by the retrieval measurement (retrieval_eval.py) and
by the pipeline's hybrid search (answering/retrieval.py).
"""

import math
import re
import unicodedata
from collections import Counter

# Words, numbers and codes kept whole: "7.37", "400m", "bart-large", "f1@5".
_TOKEN = re.compile(r"\w+(?:[.\-@/]\w+)*")

K1 = 1.5   # saturation: the 10th occurrence of a word adds less than the 2nd
B = 0.75   # length normalization: a long text does not win just for being long
RRF_K = 60  # rank fusion constant (the original paper's value, not tuned)


def tokenize(text: str) -> list[str]:
    """'BART-large with 400M parameters (7.37%)' -> ['bart-large', 'with', '400m', 'parameters', '7.37']"""
    return _TOKEN.findall(unicodedata.normalize("NFKC", text).lower())


class Bm25Index:
    """BM25 (Robertson) over a list of texts, with Lucene's always-positive IDF.
    Word weights are computed over ALL the texts given."""

    def __init__(self, texts: list[str], k1: float = K1, b: float = B):
        self.k1, self.b = k1, b
        self.counts = [Counter(tokenize(t)) for t in texts]
        self.lengths = [sum(c.values()) for c in self.counts]
        self.avg_length = sum(self.lengths) / len(self.lengths) if texts else 0.0
        # Rarity of a word: present in few texts -> high weight.
        n = len(texts)
        df = Counter(word for c in self.counts for word in c)
        self.idf = {word: math.log(1 + (n - d + 0.5) / (d + 0.5)) for word, d in df.items()}

    def scores(self, query: str) -> list[float]:
        """One score per text, in the order of the texts given to the constructor."""
        words = set(tokenize(query))  # a word repeated in the query counts once
        result = []
        for counts, length in zip(self.counts, self.lengths, strict=True):
            norm = self.k1 * (1 - self.b + self.b * length / self.avg_length) if self.avg_length else self.k1
            result.append(sum(
                self.idf[w] * counts[w] * (self.k1 + 1) / (counts[w] + norm)
                for w in words if counts[w]
            ))
        return result


def reciprocal_rank_fusion(rankings: list[list[int]], k: int = RRF_K) -> list[int]:
    """Merges several rankings of the same items (best first): score = sum of
    1 / (k + rank). RANKS are merged, not scores: a cosine (0 to 1) and a BM25
    score (unbounded) are not comparable, and no weight needs tuning. On a
    tie, the order of the first ranking is kept."""
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            fused[item] = fused.get(item, 0.0) + 1 / (k + rank)
    first = {item: i for i, item in enumerate(rankings[0])} if rankings else {}
    return sorted(fused, key=lambda item: (-fused[item], first.get(item, len(first))))
