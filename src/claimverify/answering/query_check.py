"""
Retrieval check — a sanity check of the search, with no LLM
===========================================================

Queries the database with a few test questions and prints the closest
chunks, to check by hand that retrieval makes sense.

Usage (--db_url is optional when DB_URL is in .env, see config.py):
    python -m claimverify.answering.query_check
    python -m claimverify.answering.query_check --query "Does semantic chunking improve retrieval?"
    python -m claimverify.answering.query_check --query "..." --per_document

--per_document shows what the DRAFTER receives: the same retriever as the
pipeline, built by the factory from config.yaml (answering.retriever). The
judge has its own retriever (answering.verifier.retriever): for what it
reads, see `verification --debug_claim`.
"""

import argparse

import psycopg2

from claimverify.components.store import search_global
from claimverify.config import add_db_url_argument
from claimverify.factory import build_embedder, build_retriever
from claimverify.settings import add_config_argument, load_settings

TOP_K = 5

# A few test questions covering the corpus's expected axes:
# - a question on which two papers of the corpus should disagree
# - a simple factual question (a clean "supported" case)
# - a question on a different axis (enriching chunks, not how to cut them)
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
                         help="If given, runs only this question instead of the default set.")
    parser.add_argument("--top_k", type=int, default=TOP_K)
    parser.add_argument("--per_document", action="store_true",
                         help="Uses the per-document search (top-k per source) "
                              "instead of the global top-k. This is the mode used for "
                              "drafting and claim verification.")
    parser.add_argument("--top_k_per_doc", type=int, default=None,
                         help="Overrides config.yaml's top_k_per_doc for this run "
                              "(answering.retriever), to compare.")
    args = parser.parse_args()

    settings = load_settings(args.config)
    embedder = build_embedder(settings)

    conn = psycopg2.connect(args.db_url)
    cfg = settings.answering.retriever
    if args.top_k_per_doc is not None:
        cfg = cfg.model_copy(update={"top_k_per_doc": args.top_k_per_doc})
    retriever = build_retriever(cfg, embedder, conn, "answering.retriever")

    queries = [args.query] if args.query else DEFAULT_TEST_QUERIES
    for query in queries:
        if args.per_document:
            results = retriever.retrieve(query)
        else:
            results = search_global(conn, embedder.embed_query(query), args.top_k)
        print_results(query, results)

    conn.close()


if __name__ == "__main__":
    main()