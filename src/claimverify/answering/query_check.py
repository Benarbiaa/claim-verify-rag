"""
Vérification de retrieval — sanity check avant d'attaquer l'agent LangGraph
=============================================================================

Interroge la base pgvector avec quelques questions de test et affiche les
chunks les plus proches, pour vérifier manuellement que le retrieval a du
sens avant de construire la couche agentique par-dessus.

Usage (--db_url facultatif si DB_URL est dans .env, voir config.py) :
    python -m claimverify.answering.query_check
    python -m claimverify.answering.query_check --query "Does semantic chunking improve retrieval?"
    python -m claimverify.answering.query_check --query "..." --per_document
"""

import argparse

import psycopg2

from claimverify.components.store import search_global, search_per_document
from claimverify.config import add_db_url_argument
from claimverify.factory import build_embedder
from claimverify.settings import add_config_argument, load_settings

TOP_K = 5

# Quelques questions de test couvrant les axes attendus du corpus :
# - une question où deux papiers du corpus sont censés être en désaccord
# - une question factuelle simple (cas "supporté" propre)
# - une question sur un axe différent (enrichissement de chunk, pas méthode de chunking)
DEFAULT_TEST_QUERIES = [
    "Does semantic chunking improve retrieval performance compared to fixed-size chunking?",
    "What is the original definition of Retrieval-Augmented Generation?",
    "How does contextual retrieval reduce retrieval failure rate?",
    "What chunking method does LumberChunker use?",
]


def print_results(query: str, results):
    print("=" * 100)
    print(f"QUERY: {query}")
    print("=" * 100)
    for rank, p in enumerate(results, 1):
        preview = p.text[:220].replace("\n", " ")
        print(f"\n[{rank}] score={p.score:.4f}  source={p.filename} (#{p.chunk_index}, {p.source_type})")
        print(f"    {preview}...")
    print()


def main():
    parser = argparse.ArgumentParser()
    add_db_url_argument(parser)
    add_config_argument(parser)
    parser.add_argument("--query", type=str, default=None,
                         help="Si fourni, exécute uniquement cette question au lieu du jeu par défaut.")
    parser.add_argument("--top_k", type=int, default=TOP_K)
    parser.add_argument("--per_document", action="store_true",
                         help="Utilise la recherche par document (top-k par source) "
                              "au lieu du top-k global. C'est le mode utilisé pour "
                              "la génération de réponse et la vérification de claims.")
    parser.add_argument("--top_k_per_doc", type=int, default=3)
    args = parser.parse_args()

    embedder = build_embedder(load_settings(args.config))

    conn = psycopg2.connect(args.db_url)

    queries = [args.query] if args.query else DEFAULT_TEST_QUERIES
    for query in queries:
        query_embedding = embedder.embed_query(query)
        if args.per_document:
            results = search_per_document(conn, query_embedding, args.top_k_per_doc)
        else:
            results = search_global(conn, query_embedding, args.top_k)
        print_results(query, results)

    conn.close()


if __name__ == "__main__":
    main()