"""Rules shared by every test: no network, no API key, no GPU, no database.

A real model (embedder or reranker) would be downloaded and run on a GPU: any attempt to load
one fails at once, with a message naming the fake to use instead.
"""

import pytest

from claimverify.components.embedding import BgeEmbedder
from claimverify.components.reranking import CrossEncoderReranker


def _refuse(name: str, fake: str):
    def load(self):
        raise RuntimeError(f"a test tried to load the real {name} model: use {fake} instead")
    return property(load)


@pytest.fixture(autouse=True)
def no_real_models(monkeypatch):
    monkeypatch.setattr(BgeEmbedder, "model", _refuse("embedding", "a fake embedder"))
    monkeypatch.setattr(CrossEncoderReranker, "model", _refuse("reranker", "a fake reranker"))
