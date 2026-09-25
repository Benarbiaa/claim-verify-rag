"""
Pipeline d'indexation — Étape A
=================================

Étapes : charger (PDF + MD) -> chunker -> embedder (bge-base-en-v1.5, GPU) -> stocker (pgvector)
Chaque étape vit dans son module (loading, chunking, components/embedding,
components/store) ; ce fichier ne fait que les enchaîner.

Usage (--db_url facultatif si DB_URL est dans .env, voir config.py) :
    python -m claimverify.indexing.ingest --corpus_dir ./data/corpus
"""

import argparse
from pathlib import Path

import psycopg2

from claimverify.components.embedding import EMBEDDING_MODEL, embed_chunks
from claimverify.components.store import setup_db, store_chunks
from claimverify.config import add_db_url_argument
from claimverify.indexing.chunking import build_chunks
from claimverify.indexing.loading import load_corpus


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus_dir", type=Path, required=True)
    add_db_url_argument(parser)
    args = parser.parse_args()

    print(f"Chargement du corpus depuis {args.corpus_dir}...")
    documents = load_corpus(args.corpus_dir)
    print(f"  {len(documents)} documents chargés : {[d.filename for d in documents]}")

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