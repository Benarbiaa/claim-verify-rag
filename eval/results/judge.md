# Judge evaluation on the gold set

Judge: `qwen/qwen3.8-27b`. 10 claims, each verdict compared to its proven label.
A smoke test (2 claims per category): read the counts, not percentages.

**Correct verdicts: 9/10.** This run: 10 judge calls, 41440 tokens, 232 s of rate-limit waits.

## By category

| Category | Correct |
|---|---|
| single_source | 2/2 |
| perturbed_fact | 2/2 |
| cross_source_conflict | 1/2 |
| complementary | 2/2 |
| out_of_corpus | 2/2 |

False contradictions on complementary claims: 0/2.

## Confusion matrix (rows: expected, columns: judge)

| expected \ judge | supported | contradicted | contested | unverifiable | error |
|---|---|---|---|---|---|
| supported | 4 | · | · | · | · |
| contradicted | · | 2 | · | · | · |
| contested | 1 | · | 1 | · | · |
| unverifiable | · | · | · | 2 | · |

## Why the wrong verdicts are wrong

- retrieval: proof not read: 1

## Every claim

| Id | Category | Expected | Judge | Proof read | Sources | Cause | Justification |
|---|---|---|---|---|---|---|---|
| g01 | single_source | supported | ✓ supported | yes | ok | – | The source lewis-rag-neurips2020.pdf explicitly states in chunk #3 that the RAG model uses a "Dense Passage Retriever [26], henceforth DPR" for retrieval and a "seq2seq model (BART [32])" for generation. This directly su |
| g02 | single_source | supported | ✓ supported | yes | ok | – | The claim is directly supported by source vectara-semantic-chunking-naacl2025.pdf (chunk #8), which states in section 4.3 'Evidence Retrieval' that 'Fixed-size Chunker performed best on 3 out of 5 datasets' and that 'the |
| g03 | perturbed_fact | contradicted | ✓ contradicted | yes | ok | – | The claim states that LumberChunker's best retrieval results were achieved with prompts of about 1,000 tokens. However, the source lumberchunker-emnlp2024.pdf explicitly states in Section 5.1 that "θ = 550 leads to the b |
| g04 | perturbed_fact | contradicted | ✓ contradicted | yes | ok | – | The claim states that in RAG, the non-parametric memory is a dense vector index of the Common Crawl web corpus. The source lewis-rag-neurips2020.pdf, which introduces the RAG model, explicitly states that 'the non-parame |
| g05 | cross_source_conflict | contested | ✗ supported | **no** | wrong | retrieval: proof not read | Multiple sources explicitly state that document chunking strategies have a significant impact on retrieval quality. 'lumberchunker-emnlp2024.pdf' states that "ineffective chunking strategies can lead to chunks with incom |
| g06 | cross_source_conflict | contested | ✓ contested | **no** | ok | – | The sources disagree on the consistency and effectiveness of content-based (semantic) chunking for retrieval. 'vectara-semantic-chunking-naacl2025.pdf' explicitly states that there is "no systematic evidence" of a consis |
| g07 | complementary | supported | ✓ supported | yes | ok | – | The source 'anthropic-contextual-retrieval.md' explicitly states that the Contextual Retrieval method reduces the number of failed retrievals by 49% (which is approximately half) and, when combined with reranking, by 67% |
| g08 | complementary | supported | ✓ supported | yes | ok | – | The claim is directly supported by anthropic-contextual-retrieval.md, which states: 'Splitting documents into small chunks can strip away context... making it hard to retrieve correctly or use effectively.' Additionally, |
| g09 | out_of_corpus | unverifiable | ✓ unverifiable | – | ok | – | None of the provided source passages discuss ColBERT, its token-level embedding mechanism, or its late interaction scoring method. The sources discuss RAG (Retrieval-Augmented Generation), LumberChunker, Contextual Retri |
| g10 | out_of_corpus | unverifiable | ✓ unverifiable | – | ok | – | The provided source passages do not contain the specific formula or definition for Reciprocal Rank Fusion (RRF). While anthropic-contextual-retrieval.md mentions 'rank fusion' in the context of combining BM25 and embeddi |
