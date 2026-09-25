"""
Pipeline d'ingestion — Agentic RAG avec vérification de véracité
==================================================================

Étapes : parser (PDF + MD) -> chunker -> embedder (bge-base-en-v1.5, GPU) -> stocker (pgvector)

Prérequis (à exécuter en local, pas dans ce sandbox) :
    pip install pypdf sentence-transformers psycopg2-binary tqdm

    # Postgres avec l'extension pgvector activée :
    #   CREATE EXTENSION IF NOT EXISTS vector;
    # Voir setup_db() ci-dessous pour le schéma de la table.

Usage (--db_url facultatif si DB_URL est dans .env, voir config.py) :
    python -m claimverify.ingest --corpus_dir ./data/corpus
"""

import argparse
import hashlib
import re
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from claimverify.config import add_db_url_argument

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
EMBEDDING_DIM = 768  # dimension de sortie de bge-base-en-v1.5
CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_RATIO = 0.15  # 15%


# ---------------------------------------------------------------------------
# 1. Parsing — PDF et Markdown vers texte brut
# ---------------------------------------------------------------------------

def parse_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def parse_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_corpus(corpus_dir: Path) -> list[dict]:
    """Retourne une liste de {doc_id, filename, source_type, text}."""
    documents = []
    for path in sorted(corpus_dir.iterdir()):
        if path.suffix.lower() == ".pdf":
            text = parse_pdf(path)
            source_type = "peer_reviewed_paper"
        elif path.suffix.lower() == ".md":
            text = parse_markdown(path)
            source_type = "blog_post"  # à ajuster si le .md n'est pas un article de blog
        else:
            continue

        doc_id = hashlib.sha1(path.name.encode()).hexdigest()[:12]
        documents.append({
            "doc_id": doc_id,
            "filename": path.name,
            "source_type": source_type,
            "text": text,
        })
    return documents


# ---------------------------------------------------------------------------
# 2. Chunking — taille fixe avec chevauchement (baseline volontairement simple)
# ---------------------------------------------------------------------------

def simple_tokenize(text: str) -> list[str]:
    # Découpage naïf par mots ; suffisant pour une baseline de chunking par
    # nombre de tokens approximatif. À remplacer par un vrai tokenizer
    # (ex. tiktoken) si besoin de précision.
    return re.findall(r"\S+", text)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_TOKENS,
               overlap_ratio: float = CHUNK_OVERLAP_RATIO) -> list[str]:
    words = simple_tokenize(text)
    overlap = int(chunk_size * overlap_ratio)
    step = chunk_size - overlap

    chunks = []
    for start in range(0, len(words), step):
        chunk_words = words[start:start + chunk_size]
        if not chunk_words:
            break
        chunks.append(" ".join(chunk_words))
        if start + chunk_size >= len(words):
            break
    return chunks


def build_chunks(documents: list[dict]) -> list[dict]:
    """Retourne une liste de {chunk_id, doc_id, filename, source_type, chunk_index, text}."""
    all_chunks = []
    for doc in documents:
        pieces = chunk_text(doc["text"])
        for i, piece in enumerate(pieces):
            chunk_id = f"{doc['doc_id']}_{i:04d}"
            all_chunks.append({
                "chunk_id": chunk_id,
                "doc_id": doc["doc_id"],
                "filename": doc["filename"],
                "source_type": doc["source_type"],
                "chunk_index": i,
                "text": piece,
            })
    return all_chunks


# ---------------------------------------------------------------------------
# 3. Embedding — bge-base-en-v1.5 sur GPU si disponible
# ---------------------------------------------------------------------------

def embed_chunks(chunks: list[dict], model_name: str = EMBEDDING_MODEL) -> list[dict]:
    model = SentenceTransformer(model_name, device="cuda")  # passe à "cpu" si pas de GPU dispo
    texts = [c["text"] for c in chunks]

    # bge recommande un préfixe pour les documents (pas pour les queries) —
    # cf. la doc du modèle sur Hugging Face pour bge-base-en-v1.5.
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True,  # cosine similarity <-> produit scalaire
    )

    for chunk, emb in zip(chunks, embeddings):
        chunk["embedding"] = emb.tolist()
    return chunks


# ---------------------------------------------------------------------------
# 4. Stockage — pgvector
# ---------------------------------------------------------------------------

def setup_db(conn):
    with conn.cursor() as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                source_type TEXT NOT NULL,
                chunk_index INT NOT NULL,
                text TEXT NOT NULL,
                embedding VECTOR({EMBEDDING_DIM})
            );
        """)
        # Index approximatif pour la recherche par similarité (IVFFlat).
        # À créer après avoir inséré des données pour de meilleures perfs
        # (nécessite un minimum de lignes pour être efficace, mais fonctionne
        # aussi bien pour un petit corpus de test).
        cur.execute("""
            CREATE INDEX IF NOT EXISTS chunks_embedding_idx
            ON chunks USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 10);
        """)
    conn.commit()


def store_chunks(conn, chunks: list[dict]):
    rows = [
        (
            c["chunk_id"], c["doc_id"], c["filename"], c["source_type"],
            c["chunk_index"], c["text"], c["embedding"],
        )
        for c in chunks
    ]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO chunks (chunk_id, doc_id, filename, source_type, chunk_index, text, embedding)
            VALUES %s
            ON CONFLICT (chunk_id) DO UPDATE SET
                text = EXCLUDED.text,
                embedding = EXCLUDED.embedding;
            """,
            rows,
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus_dir", type=Path, required=True)
    add_db_url_argument(parser)
    args = parser.parse_args()

    print(f"Chargement du corpus depuis {args.corpus_dir}...")
    documents = load_corpus(args.corpus_dir)
    print(f"  {len(documents)} documents chargés : {[d['filename'] for d in documents]}")

    print("Découpage en chunks...")
    chunks = build_chunks(documents)
    print(f"  {len(chunks)} chunks générés")

    print(f"Génération des embeddings avec {EMBEDDING_MODEL}...")
    chunks = embed_chunks(chunks)

    print("Connexion à la base et stockage...")
    conn = psycopg2.connect(args.db_url)
    setup_db(conn)
    store_chunks(conn, chunks)
    conn.close()

    print("Terminé.")


if __name__ == "__main__":
    main()