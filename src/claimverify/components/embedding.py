"""
Embedding — composant partagé par les deux pipelines
======================================================

L'indexation embedde les chunks, la réponse embedde les questions et les
claims : les deux DOIVENT utiliser le même modèle, sinon les vecteurs ne
sont plus comparables et le retrieval se dégrade sans erreur visible.
"""

from sentence_transformers import SentenceTransformer

from claimverify.contracts import Chunk

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
EMBEDDING_DIM = 768  # dimension de sortie de bge-base-en-v1.5


def load_embedding_model(device: str = "cuda") -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL, device=device)


def embed_query(model: SentenceTransformer, text: str):
    instructed = f"Represent this sentence for searching relevant passages: {text}"
    return model.encode(instructed, normalize_embeddings=True).tolist()


def embed_chunks(chunks: list[Chunk], model_name: str = EMBEDDING_MODEL) -> list[Chunk]:
    """Retourne de NOUVEAUX chunks avec leur embedding : la liste reçue n'est pas modifiée."""
    model = SentenceTransformer(model_name, device="cuda")  # passe à "cpu" si pas de GPU dispo
    texts = [c.text for c in chunks]

    # bge recommande un préfixe pour les documents (pas pour les queries) —
    # cf. la doc du modèle sur Hugging Face pour bge-base-en-v1.5.
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True,  # cosine similarity <-> produit scalaire
    )

    return [
        chunk.model_copy(update={"embedding": emb.tolist()})
        for chunk, emb in zip(chunks, embeddings)
    ]
