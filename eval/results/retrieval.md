# Retrieval: does the search bring back the proof?

44 quotes (gold set + retrieval set). A quote counts as found at k when the chunk
containing it is among the k best chunks of its document (the search is per document).
In brackets: the 95 % Wilson interval, the honest range for so few items.
This is a lower bound: another chunk may state the same fact in other words (an
abstract repeating a result), which is enough for the judge but not detected here.

`config.yaml`: chunks of 400 tokens, the judge gets k = 2 per document.
Methods: `dense` = by meaning (today's search), `bm25` = by exact words,
`hybrid` = both rankings merged by reciprocal rank fusion.

## Recall by k

| Chunk size | Method | k = 1 | k = 2 | k = 3 | k = 5 |
|---|---|---|---|---|---|
| 256 | bm25 | 33/44 (75 %, 61–85) | 37/44 (84 %, 71–92) | 40/44 (91 %, 79–96) | 43/44 (98 %, 88–100) |
| 256 | dense | 16/44 (36 %, 24–51) | 24/44 (55 %, 40–68) | 30/44 (68 %, 53–80) | 34/44 (77 %, 63–87) |
| 256 | hybrid | 25/44 (57 %, 42–70) | 32/44 (73 %, 58–84) | 35/44 (80 %, 65–89) | 39/44 (89 %, 76–95) |
| 400 | bm25 | 30/44 (68 %, 53–80) | 38/44 (86 %, 73–94) | 40/44 (91 %, 79–96) | 44/44 (100 %, 92–100) |
| 400 | dense (today) | 12/44 (27 %, 16–42) | 23/44 (52 %, 38–66) | 26/44 (59 %, 44–72) | 31/44 (70 %, 56–82) |
| 400 | hybrid | 16/44 (36 %, 24–51) | 31/44 (70 %, 56–82) | 37/44 (84 %, 71–92) | 39/44 (89 %, 76–95) |
| 510 | bm25 | 31/44 (70 %, 56–82) | 40/44 (91 %, 79–96) | 43/44 (98 %, 88–100) | 43/44 (98 %, 88–100) |
| 510 | dense | 17/44 (39 %, 26–53) | 26/44 (59 %, 44–72) | 28/44 (64 %, 49–76) | 33/44 (75 %, 61–85) |
| 510 | hybrid | 27/44 (61 %, 47–74) | 30/44 (68 %, 53–80) | 35/44 (80 %, 65–89) | 42/44 (95 %, 85–99) |

## Against today's search, quote by quote (k = 2)

Rule fixed before measuring: keep a method if it gains at least 4 quotes net and
no document loses proofs.

| Chunk size | Method | Found | Gained | Lost | Documents losing proofs | Rule |
|---|---|---|---|---|---|---|
| 256 | bm25 | 37/44 | g01, g05.1, g06.1, g07, r01, r02, r04, r05, r06, r07, r10, r11, r16, r22, r24 | r30 | none | met |
| 256 | dense | 24/44 | r01, r09, r11, r20 | g03.1, r15, r30 | anthropic | not met |
| 256 | hybrid | 32/44 | g05.1, g06.1, r01, r02, r05, r09, r10, r11, r16, r20, r24 | g03.1, r30 | anthropic | not met |
| 400 | bm25 | 38/44 | g03.2, g05.1, g06.1, g07, r01, r02, r04, r05, r06, r07, r09, r10, r11, r16, r22, r24 | r03 | none | met |
| 400 | hybrid | 31/44 | g03.2, g06.1, g07, r06, r09, r11, r16, r22 | – | none | met |
| 510 | bm25 | 40/44 | g01, g06.1, g06.2, g07, r01, r02, r04, r05, r06, r07, r09, r10, r11, r16, r21, r22, r24 | – | none | met |
| 510 | dense | 26/44 | r01, r02, r20, r24 | g03.1 | lumberchunker | not met |
| 510 | hybrid | 30/44 | g06.1, g06.2, r01, r02, r11, r16, r24 | – | none | met |

## By document (400 tokens, k = 2)

| Document | Chunks | bm25 | dense | hybrid |
|---|---|---|---|---|
| anthropic-contextual-retrieval.md | 5 | 10/10 | 9/10 | 10/10 |
| lewis-rag-neurips2020.pdf | 53 | 8/10 | 3/10 | 4/10 |
| lumberchunker-emnlp2024.pdf | 27 | 12/12 | 5/12 | 10/12 |
| vectara-semantic-chunking-naacl2025.pdf | 35 | 8/12 | 6/12 | 7/12 |

## Rank of each quote's chunk (400 tokens; > 2: the judge does not see it)

| Id | Document | bm25 | dense | hybrid | Claim |
|---|---|---|---|---|---|
| g01 | lewis | 4 | 11 | 6 | In the original RAG model, passages are fetched by a DPR retriever and the answer is produced by a BART sequence-to-sequence model. |
| g02.1 | vectara | 1 | 1 | 1 | In Vectara's evidence-retrieval experiments, fixed-size chunking scored best on three of the five datasets, and the gaps with semantic chunking were minimal. |
| g02.2 | vectara | 1 | 1 | 1 | In Vectara's evidence-retrieval experiments, fixed-size chunking scored best on three of the five datasets, and the gaps with semantic chunking were minimal. |
| g03.1 | lumberchunker | 1 | 1 | 1 | LumberChunker gave its best retrieval results with prompts of about 1,000 tokens. |
| g03.2 | lumberchunker | 2 | 5 | 2 | LumberChunker gave its best retrieval results with prompts of about 1,000 tokens. |
| g04 | lewis | 1 | 1 | 1 | In RAG, the non-parametric memory is a dense vector index of the Common Crawl web corpus. |
| g05.1 | lumberchunker | 1 | 16 | 8 | How documents are split into chunks has a large effect on retrieval quality. |
| g05.2 | vectara | 3 | 13 | 6 | How documents are split into chunks has a large effect on retrieval quality. |
| g06.1 | lumberchunker | 1 | 7 | 2 | Chunking documents according to their content, rather than by a fixed rule, consistently improves retrieval. |
| g06.2 | vectara | 3 | 4 | 3 | Chunking documents according to their content, rather than by a fixed rule, consistently improves retrieval. |
| g07 | anthropic | 1 | 4 | 2 | Adding chunk-specific context before indexing cut failed retrievals by about half in Anthropic's tests, and by about two thirds when combined with reranking. |
| g08 | anthropic | 1 | 2 | 2 | Cutting documents into small chunks can remove the context needed to retrieve a passage correctly. |
| r01 | lewis | 2 | 3 | 3 | RAG-Sequence relies on one retrieved document for the whole output, while RAG-Token can switch documents from one token to the next. |
| r02 | lewis | 1 | 10 | 3 | The RAG generator is BART-large, a pre-trained seq2seq transformer of about 400 million parameters. |
| r03 | lewis | 4 | 2 | 2 | When fine-tuning RAG, the document encoder and its index are kept frozen; only the query encoder and the generator are trained. |
| r04 | lewis | 1 | 25 | 11 | RAG's knowledge source is a Wikipedia dump cut into 100-word passages, about 21 million in total. |
| r05 | lewis | 1 | 14 | 4 | The RAG passage index is searched with FAISS, using a Hierarchical Navigable Small World approximation. |
| r06 | lewis | 1 | 7 | 2 | RAG reached state-of-the-art results on Natural Questions, WebQuestions and CuratedTrec. |
| r07 | lewis | 1 | 22 | 5 | On FEVER, RAG came within 4.3% of pipeline systems trained with strong retrieval supervision. |
| r08 | lewis | 1 | 1 | 1 | RAG shows that open-domain QA can reach the state of the art without a re-ranker or an extractive reader. |
| r09 | lumberchunker | 2 | 4 | 2 | The LumberChunker authors built GutenQA: 3,000 question-answer pairs drawn from 100 public-domain narrative books. |
| r10 | lumberchunker | 1 | 6 | 3 | LumberChunker beat the strongest baseline by 7.37% in DCG@20. |
| r11 | lumberchunker | 1 | 3 | 1 | Before asking the LLM, LumberChunker appends consecutive paragraphs into a group until a token threshold is passed. |
| r12 | lumberchunker | 2 | 1 | 1 | The GutenQA questions were generated with gpt-3.5-turbo. |
| r13 | lumberchunker | 1 | 1 | 1 | At k = 20, LumberChunker reached a DCG of 62.09, ahead of recursive chunking at 54.72. |
| r14 | lumberchunker | 1 | 1 | 1 | Proposition-level chunking suits factual text such as Wikipedia but works less well on narratives. |
| r15 | lumberchunker | 1 | 2 | 1 | In the question-answering test, only hand-made chunks did better than LumberChunker. |
| r16 | lumberchunker | 2 | 4 | 2 | Because it calls an LLM, LumberChunker is slower and costlier than recursive chunking. |
| r17 | vectara | 2 | 2 | 1 | Vectara's fixed-size baseline puts a set number of sentences in each chunk. |
| r18 | vectara | 1 | 2 | 2 | Vectara's breakpoint-based chunker starts a new chunk when two consecutive sentences are semantically far apart. |
| r19 | vectara | 1 | 2 | 1 | Vectara's clustering-based chunker combines positional distance and cosine distance in a weighted sum. |
| r20 | vectara | 4 | 3 | 3 | To get documents long enough to chunk, Vectara stitched short documents together. |
| r21 | vectara | 5 | 6 | 6 | In Vectara's document retrieval, fixed-size chunking did best on natural data and semantic chunkers on stitched data. |
| r22 | vectara | 1 | 10 | 2 | Vectara reports F1@5 because Recall@k and NDCG@k do not fit its setting. |
| r23 | vectara | 1 | 2 | 2 | For answer generation, semantic chunkers were only marginally better than fixed-size chunking on BERTScore. |
| r24 | vectara | 1 | 8 | 3 | Vectara's reported numbers use the stella_en_1.5B_v5 embedding model, the best of those it tested. |
| r25 | anthropic | 1 | 2 | 2 | If the knowledge base is under 200,000 tokens, it can simply be put in the prompt instead of using RAG. |
| r26 | anthropic | 1 | 1 | 1 | BM25 complements embeddings by catching exact word matches such as error codes or technical terms. |
| r27 | anthropic | 1 | 2 | 2 | Anthropic generated a short context of about 50 to 100 tokens for each chunk. |
| r28 | anthropic | 1 | 1 | 1 | Thanks to prompt caching, contextualizing the chunks costs about $1.02 per million document tokens. |
| r29 | anthropic | 2 | 2 | 2 | Contextual embeddings alone lowered the top-20 retrieval failure rate from 5.7% to 3.7%. |
| r30 | anthropic | 1 | 1 | 1 | Anthropic found that passing 20 chunks to the model worked better than 5 or 10. |
| r31 | anthropic | 2 | 2 | 2 | Anthropic's reranker scored the top 150 retrieved chunks and kept the best 20. |
| r32 | anthropic | 1 | 1 | 1 | Reranking improves results but adds latency. |
