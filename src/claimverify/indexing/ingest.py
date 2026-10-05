"""
Indexing pipeline — Step A
==========================

Stages: load -> clean -> chunk -> embed -> store (pgvector)
The implementations and their settings come from config.yaml (the indexing
section, and embedding, which is shared with the answering pipeline); this
file only chains them through their interfaces and emits an event after each
stage (see events.py): one line in the terminal, and the full output in
runs/<run_id>/events.jsonl.

Usage (--db_url is optional when DB_URL is in .env, see config.py):
    python -m claimverify.indexing.ingest --corpus_dir ./data/corpus
    python -m claimverify.indexing.ingest --corpus_dir ./data/corpus --config other.yaml
"""

import argparse
import time
from pathlib import Path

import psycopg2

from claimverify.components.embedding import embed_chunks
from claimverify.components.store import replace_chunks, setup_db
from claimverify.config import add_db_url_argument
from claimverify.events import (
    ChunksBuilt,
    ChunksEmbedded,
    ChunksStored,
    CleaningSummary,
    DocumentsCleaned,
    DocumentsLoaded,
    DocumentSummary,
    RunFinished,
    RunStarted,
)
from claimverify.factory import IndexingStages, build_indexing
from claimverify.reporting import Run
from claimverify.settings import Settings, add_config_argument, load_settings


def run_indexing(stages: IndexingStages, corpus_dir: Path, conn, run: Run,
                 settings: Settings) -> None:
    start = time.perf_counter()
    run.emit(RunStarted, config=settings.model_dump(), inputs={"corpus_dir": str(corpus_dir)})

    t = time.perf_counter()
    documents = stages.loader.load(corpus_dir)
    run.emit(DocumentsLoaded, seconds=time.perf_counter() - t, documents=[
        DocumentSummary(doc_id=d.doc_id, filename=d.filename, source_type=d.source_type,
                        characters=len(d.text))
        for d in documents
    ])

    t = time.perf_counter()
    cleaned = stages.cleaner.clean(documents)
    documents = [c.document for c in cleaned]
    run.emit(DocumentsCleaned, seconds=time.perf_counter() - t, documents=[
        CleaningSummary(filename=c.document.filename, characters_before=c.characters_before,
                        characters_after=len(c.document.text), changes=c.changes)
        for c in cleaned
    ])

    t = time.perf_counter()
    chunks = stages.chunker.chunk(documents)
    run.emit(ChunksBuilt, chunks=chunks, seconds=time.perf_counter() - t)

    t = time.perf_counter()
    chunks = embed_chunks(chunks, stages.embedder)
    run.emit(ChunksEmbedded, count=len(chunks), seconds=time.perf_counter() - t,
             dimension=len(chunks[0].embedding) if chunks else 0)

    t = time.perf_counter()
    setup_db(conn)
    replace_chunks(conn, chunks)
    run.emit(ChunksStored, count=len(chunks), seconds=time.perf_counter() - t)

    run.emit(RunFinished, seconds=time.perf_counter() - start, summary={
        "documents": len(documents), "chunks": len(chunks), "run_dir": str(run.dir),
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus_dir", type=Path, required=True)
    add_db_url_argument(parser)
    add_config_argument(parser)
    args = parser.parse_args()

    settings = load_settings(args.config)
    stages = build_indexing(settings)
    conn = psycopg2.connect(args.db_url)
    try:
        run_indexing(stages, args.corpus_dir, conn, Run("indexing"), settings)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
