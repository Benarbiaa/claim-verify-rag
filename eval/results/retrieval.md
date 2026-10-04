# Retrieval: does the search bring back the proof?

44 quotes (gold set + retrieval set). A quote counts as found at k when the chunk
containing it is among the k best chunks of its document (the search is per document).
In brackets: the 95 % Wilson interval, the honest range for so few items.
This is a lower bound: another chunk may state the same fact in other words (an
abstract repeating a result), which is enough for the judge but not detected here.

`config.yaml`: chunks of 400 tokens, the judge gets k = 2 per document.

## Recall by k and chunk size

| Chunk size | k = 1 | k = 2 | k = 3 | k = 5 | partly found at k = 2 |
|---|---|---|---|---|---|
| 256 | 16/44 (36 %, 24–51) | 24/44 (55 %, 40–68) | 30/44 (68 %, 53–80) | 34/44 (77 %, 63–87) | 24/44 |
| 400 (config) | 12/44 (27 %, 16–42) | 23/44 (52 %, 38–66) | 26/44 (59 %, 44–72) | 31/44 (70 %, 56–82) | 23/44 |
| 510 | 17/44 (39 %, 26–53) | 26/44 (59 %, 44–72) | 28/44 (64 %, 49–76) | 33/44 (75 %, 61–85) | 26/44 |

## By document (config, k = 2)

| Document | Found | Chunks in the document |
|---|---|---|
| anthropic-contextual-retrieval.md | 9/10 | 5 |
| lewis-rag-neurips2020.pdf | 3/10 | 53 |
| lumberchunker-emnlp2024.pdf | 5/12 | 27 |
| vectara-semantic-chunking-naacl2025.pdf | 6/12 | 35 |

## Quotes the judge would not see (config, k = 2)

| Id | Document | Rank of its chunk | Claim |
|---|---|---|---|
| r01 | lewis | 3 | RAG-Sequence relies on one retrieved document for the whole output, while RAG-Token can switch documents from one token to the next. |
| r11 | lumberchunker | 3 | Before asking the LLM, LumberChunker appends consecutive paragraphs into a group until a token threshold is passed. |
| r20 | vectara | 3 | To get documents long enough to chunk, Vectara stitched short documents together. |
| g06.2 | vectara | 4 | Chunking documents according to their content, rather than by a fixed rule, consistently improves retrieval. |
| g07 | anthropic | 4 | Adding chunk-specific context before indexing cut failed retrievals by about half in Anthropic's tests, and by about two thirds when combined with reranking. |
| r09 | lumberchunker | 4 | The LumberChunker authors built GutenQA: 3,000 question-answer pairs drawn from 100 public-domain narrative books. |
| r16 | lumberchunker | 4 | Because it calls an LLM, LumberChunker is slower and costlier than recursive chunking. |
| g03.2 | lumberchunker | 5 | LumberChunker gave its best retrieval results with prompts of about 1,000 tokens. |
| r10 | lumberchunker | 6 | LumberChunker beat the strongest baseline by 7.37% in DCG@20. |
| r21 | vectara | 6 | In Vectara's document retrieval, fixed-size chunking did best on natural data and semantic chunkers on stitched data. |
| g06.1 | lumberchunker | 7 | Chunking documents according to their content, rather than by a fixed rule, consistently improves retrieval. |
| r06 | lewis | 7 | RAG reached state-of-the-art results on Natural Questions, WebQuestions and CuratedTrec. |
| r24 | vectara | 8 | Vectara's reported numbers use the stella_en_1.5B_v5 embedding model, the best of those it tested. |
| r02 | lewis | 10 | The RAG generator is BART-large, a pre-trained seq2seq transformer of about 400 million parameters. |
| r22 | vectara | 10 | Vectara reports F1@5 because Recall@k and NDCG@k do not fit its setting. |
| g01 | lewis | 11 | In the original RAG model, passages are fetched by a DPR retriever and the answer is produced by a BART sequence-to-sequence model. |
| g05.2 | vectara | 13 | How documents are split into chunks has a large effect on retrieval quality. |
| r05 | lewis | 14 | The RAG passage index is searched with FAISS, using a Hierarchical Navigable Small World approximation. |
| g05.1 | lumberchunker | 16 | How documents are split into chunks has a large effect on retrieval quality. |
| r07 | lewis | 22 | On FEVER, RAG came within 4.3% of pipeline systems trained with strong retrieval supervision. |
| r04 | lewis | 25 | RAG's knowledge source is a Wikipedia dump cut into 100-word passages, about 21 million in total. |

## Chunk sizes compared quote by quote (k = 2, against 400)

| Chunk size | Gained | Lost |
|---|---|---|
| 256 | r01, r09, r11, r20 | g03.1, r15, r30 |
| 510 | r01, r02, r20, r24 | g03.1 |
