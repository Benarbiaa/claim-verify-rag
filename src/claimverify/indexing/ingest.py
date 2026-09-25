"""
Pipeline d'indexation — Étape A
=================================

Étapes : charger -> chunker -> embedder -> stocker (pgvector)
Les implémentations et leurs réglages viennent de config.yaml (section
indexing, et embedding qui est partagée avec le pipeline de réponse) ; ce
fichier ne fait que les enchaîner, via leurs interfaces.

Usage (--db_url facultatif si DB_URL est dans .env, voir config.py) :
    python -m claimverify.indexing.ingest --corpus_dir ./data/corpus
    python -m claimverify.indexing.ingest --corpus_dir ./data/corpus --config autre.yaml
"""

import argparse
from pathlib import Path

import psycopg2

from claimverify.components.embedding import embed_chunks
from claimverify.components.store import setup_db, store_chunks
from claimverify.config import add_db_url_argument
from claimverify.factory import build_indexing
from claimverify.settings import add_config_argument, load_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus_dir", type=Path, required=True)
    add_db_url_argument(parser)
    add_config_argument(parser)
    args = parser.parse_args()

    stages = build_indexing(load_settings(args.config))

    print(f"Chargement du corpus depuis {args.corpus_dir}...")
    documents = stages.loader.load(args.corpus_dir)
    print(f"  {len(documents)} documents chargés : {[d.filename for d in documents]}")

    print("Découpage en chunks...")
    chunks = stages.chunker.chunk(documents)
    print(f"  {len(chunks)} chunks générés")

    print("Génération des embeddings...")
    chunks = embed_chunks(chunks, stages.embedder)

    print("Connexion à la base et stockage...")
    conn = psycopg2.connect(args.db_url)
    setup_db(conn)
    store_chunks(conn, chunks)
    conn.close()

    print("Terminé.")


if __name__ == "__main__":
    main()
