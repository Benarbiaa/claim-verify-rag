# Introducing Contextual Retrieval

**Source:** Anthropic (Engineering at Anthropic)
**Published:** September 19, 2024
**URL:** https://www.anthropic.com/engineering/contextual-retrieval
**Type:** Company engineering blog post (not peer-reviewed)

---

For an AI model to be useful in specific contexts, it often needs access to background knowledge. For example, customer support chatbots need knowledge about the specific business they're being used for, and legal analyst bots need to know about a vast array of past cases.

Developers typically enhance an AI model's knowledge using Retrieval-Augmented Generation (RAG). RAG is a method that retrieves relevant information from a knowledge base and appends it to the user's prompt, significantly enhancing the model's response. The problem is that traditional RAG solutions remove context when encoding information, which often results in the system failing to retrieve the relevant information from the knowledge base.

In this post, Anthropic outlines a method that dramatically improves the retrieval step in RAG. The method is called "Contextual Retrieval" and uses two sub-techniques: Contextual Embeddings and Contextual BM25. This method can reduce the number of failed retrievals by 49%, and when combined with reranking, by 67%.

## A note on simply using a longer prompt

If your knowledge base is smaller than 200,000 tokens (about 500 pages of material), you can just include the entire knowledge base in the prompt you give the model, with no need for RAG or similar methods — especially with prompt caching, which reduces latency by more than 2x and costs by up to 90%.

However, as your knowledge base grows, you'll need a more scalable solution. That's where Contextual Retrieval comes in.

## A primer on RAG: scaling to larger knowledge bases

RAG works by preprocessing a knowledge base:
1. Break the corpus into smaller chunks of text (usually a few hundred tokens)
2. Use an embedding model to convert chunks into vector embeddings
3. Store embeddings in a vector database searchable by semantic similarity

At runtime, the most relevant chunks (by semantic similarity to the query) are retrieved and added to the prompt.

Embedding models excel at capturing semantic relationships but can miss exact matches. BM25 (Best Matching 25), an older lexical-matching ranking function built on TF-IDF, complements embeddings by finding precise word/phrase matches — useful for queries with unique identifiers or technical terms (e.g., an error code like "TS-999").

Combining embeddings and BM25:
1. Break the corpus into chunks
2. Create TF-IDF encodings and semantic embeddings for each chunk
3. Use BM25 to find top chunks by exact match
4. Use embeddings to find top chunks by semantic similarity
5. Combine and deduplicate results via rank fusion
6. Add the top-K chunks to the prompt

### The context conundrum in traditional RAG

Splitting documents into small chunks can strip away context. Example: in a collection of SEC filings, a chunk might read "The company's revenue grew by 3% over the previous quarter" without specifying which company or time period — making it hard to retrieve correctly or use effectively.

## Introducing Contextual Retrieval

Contextual Retrieval solves this by prepending chunk-specific explanatory context to each chunk before embedding ("Contextual Embeddings") and before creating the BM25 index ("Contextual BM25").

Example transformation:
```
original_chunk = "The company's revenue grew by 3% over the previous quarter."

contextualized_chunk = "This chunk is from an SEC filing on ACME corp's performance in Q2 2023; the previous quarter's revenue was $314 million. The company's revenue grew by 3% over the previous quarter."
```

Other context-improving approaches exist in prior work — adding generic document summaries to chunks (Anthropic reports limited gains from this), hypothetical document embeddings (HyDE), and summary-based indexing (Anthropic reports low performance from this) — but Contextual Retrieval differs from these.

### Implementing Contextual Retrieval

Anthropic used Claude (Claude 3 Haiku in their writeup) to generate a short, chunk-specific context (usually 50-100 tokens) for each chunk, prepended before embedding and BM25 indexing. Prompt caching makes this affordable: the one-time cost to generate contextualized chunks is reported at about $1.02 per million document tokens (assuming 800-token chunks, 8k-token documents, 50-token instructions, 100 tokens of context per chunk).

### Methodology

Anthropic experimented across knowledge domains (codebases, fiction, ArXiv papers, science papers), embedding models, retrieval strategies, and evaluation metrics, using 1 − recall@20 as the evaluation metric (percentage of relevant documents that fail to be retrieved within the top 20 chunks).

### Performance improvements

- **Contextual Embeddings** reduced the top-20-chunk retrieval failure rate by **35%** (5.7% → 3.7%)
- **Contextual Embeddings + Contextual BM25** reduced the failure rate by **49%** (5.7% → 2.9%)

### Implementation considerations

1. **Chunk boundaries** — chunk size, boundary placement, and overlap affect retrieval performance
2. **Embedding model** — Contextual Retrieval improves performance across all tested embedding models, but Gemini and Voyage embeddings were found particularly effective
3. **Custom contextualizer prompts** — domain-tailored prompts (e.g., including a glossary) may outperform the generic prompt
4. **Number of chunks** — more chunks increase the chance of including relevant info but can distract the model; Anthropic found 20 chunks more performant than 5 or 10 in their tests

## Further boosting performance with reranking

Reranking is a filtering step: after initial retrieval (Anthropic used top 150), a reranking model scores each chunk's relevance to the query and selects the top-K (they used top 20) to pass to the model. Anthropic tested with the Cohere reranker.

### Performance improvements

**Reranked Contextual Embedding + Contextual BM25** reduced the top-20-chunk retrieval failure rate by **67%** (5.7% → 1.9%).

### Cost and latency considerations

Reranking adds latency (even though scoring happens in parallel across chunks) and there's a trade-off between reranking more chunks (better performance) versus fewer (lower latency/cost).

## Conclusion

Summary of findings across many tested combinations (embedding model, BM25, contextual retrieval, reranker, top-K):
1. Embeddings + BM25 is better than embeddings alone
2. Voyage and Gemini had the best embeddings of those tested
3. Passing the top-20 chunks was more effective than top-10 or top-5
4. Adding context to chunks improves retrieval accuracy substantially
5. Reranking is better than no reranking
6. All these benefits stack — combining contextual embeddings, contextual BM25, and reranking, with top-20 chunks, gave the best results

## Acknowledgements

Research and writing by Daniel Ford, Anthropic. Feedback from Orowa Sikder, Gautam Mittal, Kenneth Lien; cookbook implementation by Samuel Flamini; project coordination by Lauren Polansky; additional shaping by Alex Albert, Susan Payne, Stuart Ritchie, Brad Abrams.
