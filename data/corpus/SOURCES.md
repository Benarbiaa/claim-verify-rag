# Corpus sources

Files were renamed to short, filesystem-safe slugs. The originals had colons, a `?`, and in one
case a line break in the name, which break on Windows and in many tools.

| File | Original title | Venue | Role in the corpus |
|---|---|---|---|
| `vectara-semantic-chunking-naacl2025.pdf` | Is Semantic Chunking Worth the Computational Cost? | NAACL 2025 Findings (Vectara) | Argues sophisticated chunking rarely pays off vs. fixed-size |
| `lumberchunker-emnlp2024.pdf` | LumberChunker: Long-Form Narrative Document Segmentation | EMNLP 2024 Findings | LLM-based chunking beats every baseline, incl. semantic chunking |
| `lewis-rag-neurips2020.pdf` | Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks | NeurIPS 2020 (Lewis et al.) | Original RAG paper: clean baseline / definitional claims |
| `anthropic-contextual-retrieval.md` | Introducing Contextual Retrieval | Anthropic engineering blog, 2024 | Different axis (chunk enrichment): tests "complementary" vs "contradicts" |

The `filename` column in the `chunks` table (and therefore every citation in drafts and
verdicts) uses these new names. Drop the table and re-ingest after pulling this change
(`make db-reset ingest`), otherwise old and new rows will coexist and each paper will be
retrieved twice.
