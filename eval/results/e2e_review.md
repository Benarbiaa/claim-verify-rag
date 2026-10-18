# End-to-end review sheet

Each claim the pipeline wrote, its verdict and its justification. Mark each verdict
right or wrong by hand: the automatic checks only test the question as a whole.

## q01 (single_source): How does LumberChunker decide where one chunk ends and the next one begins?

### Draft

LumberChunker first splits a document into consecutive paragraphs. It then builds a temporary group \(G_i\) by appending successive paragraphs until a pre‑defined token budget \(\theta\) is exceeded. The whole group \(G_i\) is fed to a large language model (Gemini). The model is prompted to point out the paragraph where the “content starts diverging” – i.e., where a significant semantic shift begins. That paragraph index is taken as the boundary: the start of the next group \(G_{i+1}\) and the end of the current chunk. By repeating this step cyclically over the whole text, LumberChunker produces dynamically‑sized, mutually independent chunks [ lumberchunker‑emnlp2024.pdf | chunk #2 ]; the process is illustrated in Figure 1 of the same paper [ lumberchunker‑emnlp2024.pdf | chunk #3 ].

### Verdicts

- **supported** (for: lumberchunker-emnlp2024.pdf; against: –): LumberChunker first splits a document into consecutive paragraphs.
  - The source document lumberchunker-emnlp2024.pdf explicitly states in the methodology section (Section 3.1) and Figure 1 caption that LumberChunker's first step is to "splitting the target document paragraph-wise" and "segment a document paragraph-wise". This confirms the claim that it first splits the document into consecutive paragraphs.
  - Read: lumberchunker #2, lumberchunker #4, vectara #2, vectara #27, anthropic #2, lewis #16, lewis #9, anthropic #1
  - Right? ☐ yes ☐ no

- **supported** (for: lumberchunker-emnlp2024.pdf; against: –): LumberChunker then builds a temporary group Gi by appending successive paragraphs until a pre‑defined token budget θ is exceeded.
  - The source document 'lumberchunker-emnlp2024.pdf' explicitly describes the methodology in Section 3.1 and Figure 1, stating that paragraphs are sequentially concatenated into a group (Gi) until their token count exceeds a predefined threshold, θ. This matches the claim exactly.
  - Read: lumberchunker #2, lumberchunker #4, anthropic #2, vectara #17, vectara #27, lewis #8, anthropic #3, lewis #0
  - Right? ☐ yes ☐ no

- **supported** (for: lumberchunker-emnlp2024.pdf; against: –): The whole group Gi is fed to a large language model named Gemini.
  - The source lumberchunker-emnlp2024.pdf explicitly describes the LumberChunker process, stating in the caption of Figure 1 that 'Gi is fed as context to Gemini, which determines the ID where a significant content shift starts to appear'. This directly supports the claim that the group Gi is fed to Gemini.
  - Read: lumberchunker #13, lewis #0, lewis #40, anthropic #3, vectara #13, lumberchunker #2, vectara #12, anthropic #4
  - Right? ☐ yes ☐ no

- **supported** (for: lumberchunker-emnlp2024.pdf; against: –): The Gemini model is prompted to point out the paragraph where the content starts diverging, i.e., where a significant semantic shift begins.
  - The source document 'lumberchunker-emnlp2024.pdf' explicitly describes the LumberChunker method, which uses the Gemini model (Gemini 1.0-Pro) to identify the specific paragraph within a sequence where the content is perceived to diverge significantly or where a significant content shift starts to appear. This matches the claim that the model is prompted to point out the paragraph where the content starts diverging.
  - Read: lumberchunker #5, vectara #27, vectara #25, lumberchunker #2, lewis #52, anthropic #3, anthropic #4, lewis #24
  - Right? ☐ yes ☐ no

- **supported** (for: lumberchunker-emnlp2024.pdf; against: –): The paragraph index identified by the model is taken as the boundary that marks the start of the next group G_{i+1} and the end of the current chunk.
  - The source lumberchunker-emnlp2024.pdf (specifically chunk #2 and chunk #3) explicitly states that the model determines the ID where a significant content shift starts, which defines "the start of G_{i+1} and the end of the current chunk." This directly supports the claim that the identified paragraph index marks the boundary for the next group and the end of the current chunk.
  - Read: vectara #34, lumberchunker #3, lumberchunker #2, vectara #26, anthropic #2, lewis #2, anthropic #3, lewis #24
  - Right? ☐ yes ☐ no

- **supported** (for: lumberchunker-emnlp2024.pdf; against: –): By repeating this step cyclically over the whole text, LumberChunker produces dynamically‑sized, mutually independent chunks.
  - The source 'lumberchunker-emnlp2024.pdf' explicitly states that LumberChunker proposes a method based on the principle that chunks should be as independent as possible and that this is achieved by allowing chunks to be of dynamic sizes. It further describes the mechanism in the caption of Figure 1, stating that the process of identifying content shifts is 'cyclically repeated for the entire document', which directly supports the claim that the step is repeated cyclically over the whole text to produce dynamically-sized, mutually independent chunks.
  - Read: lumberchunker #2, lumberchunker #3, vectara #27, vectara #17, anthropic #2, anthropic #1, lewis #6, lewis #24
  - Right? ☐ yes ☐ no

- **unverifiable** (for: –; against: –): The process is illustrated in Figure 1 of the same paper.
  - The claim states that a specific process is illustrated in Figure 1 of the 'same paper'. While the sources from 'lumberchunker-emnlp2024.pdf' confirm that Figure 1 illustrates the LumberChunker process, and 'vectara-semantic-chunking-naacl2025.pdf' confirms Figure 1 illustrates three chunkers, the claim uses the relative reference 'same paper' without specifying which paper is the subject (the antecedent). Since the claim does not identify the specific process or the specific paper it refers to as 'the same paper', it cannot be definitively verified against the provided sources which describe different Figure 1s in different documents. Without the context of what 'the process' is, we cannot determine if the claim is true or false for a specific document.
  - Read: lumberchunker #4, vectara #33, anthropic #2, vectara #2, lumberchunker #2, lewis #7, lewis #2, anthropic #3
  - Right? ☐ yes ☐ no

## q04 (multi_source): Which language models do LumberChunker and Anthropic's contextual retrieval use to process chunks, and for what?

### Draft

- **LumberChunker**  
  - Uses a **large language model (LLM)** as a “contextualizer” that is prompted iteratively to find points where the content shifts, thereby **segmenting the document into chunks** that are semantically independent. (LumberChunker‑EMNLP 2024, “leveraging an LLM to dynamically segment documents… identify the point … where the content begins to shift”)  

- **Anthropic’s contextual retrieval**  
  - Generates **contextual embeddings for each chunk** with embedding models; the experiments found **Gemini and Voyage embeddings** to be the most effective. (Anthropic‑contextual‑retrieval.md, “Embedding model … Gemini and Voyage embeddings were found particularly effective”)  
  - After retrieval, it **reranks the chunks** with a **Cohere reranker model**, scoring each chunk’s relevance to the query and selecting the top‑K to pass to the downstream generator. (Anthropic‑contextual‑retrieval.md, “Anthropic tested with the Cohere reranker”)  

So, LumberChunker relies on an LLM to **create** the chunks, while Anthropic’s system relies on **embedding models (Gemini, Voyage) to represent** the chunks and a **Cohere reranker to rank** them for relevance.

### Verdicts

- **supported** (for: lumberchunker-emnlp2024.pdf; against: –): LumberChunker uses a large language model as a contextualizer.
  - The source document lumberchunker-emnlp2024.pdf explicitly states in the abstract that LumberChunker is a method "leveraging an LLM to dynamically segment documents" and that the method "iteratively prompts the LLM to identify the point within a group of sequential passages where the content begins to shift." This confirms that a large language model is used to provide the contextual understanding for segmenting the document.
  - Read: lumberchunker #3, lumberchunker #0, vectara #27, anthropic #1, lewis #40, anthropic #3, vectara #13, lewis #23
  - Right? ☐ yes ☐ no

- **supported** (for: lumberchunker-emnlp2024.pdf; against: –): The LLM in LumberChunker is prompted iteratively to find points where the content shifts.
  - The source lumberchunker-emnlp2024.pdf explicitly states in the abstract that LumberChunker "iteratively prompts the LLM to identify the point within a group of sequential passages where the content begins to shift." Additionally, the introduction and Figure 1 description confirm that the model is repeatedly instructed to determine where content starts diverging in a cyclic process.
  - Read: lumberchunker #0, lumberchunker #2, vectara #5, anthropic #2, vectara #6, lewis #52, lewis #25, anthropic #3
  - Right? ☐ yes ☐ no

- **supported** (for: lumberchunker-emnlp2024.pdf; against: –): LumberChunker segments the document into chunks that are semantically independent.
  - The source document lumberchunker-emnlp2024.pdf explicitly states in Section 3.1 that LumberChunker is a method that 'employs an LLM to dynamically segment documents into semantically independent chunks.' It further explains that the goal is for each chunk to 'encapsulate a complete, standalone idea.'
  - Read: lumberchunker #9, lumberchunker #4, vectara #2, vectara #0, anthropic #2, anthropic #1, lewis #9, lewis #15
  - Right? ☐ yes ☐ no

- **supported** (for: anthropic-contextual-retrieval.md; against: –): Anthropic’s contextual retrieval generates contextual embeddings for each chunk using embedding models.
  - The source passage from anthropic-contextual-retrieval.md explicitly states that Contextual Retrieval works by 'prepending chunk-specific explanatory context to each chunk before embedding' and refers to the resulting vectors as 'Contextual Embeddings'. It confirms that these contextualized chunks are used to generate embeddings, which aligns with the claim that contextual embeddings for each chunk are generated using embedding models (standard embedding models applied to the augmented text).
  - Read: anthropic #4, anthropic #2, lumberchunker #3, vectara #4, vectara #9, lumberchunker #22, lewis #23, lewis #9
  - Right? ☐ yes ☐ no

- **supported** (for: anthropic-contextual-retrieval.md; against: –): Experiments found Gemini embeddings to be among the most effective for Anthropic’s contextual retrieval.
  - The source document 'anthropic-contextual-retrieval.md' explicitly states in its implementation considerations and conclusion that "Voyage and Gemini had the best embeddings of those tested" and that they were found "particularly effective" for the contextual retrieval method. This directly supports the claim that Gemini embeddings were among the most effective.
  - Read: anthropic #3, anthropic #4, vectara #4, lumberchunker #6, lewis #23, lewis #51, vectara #23, lumberchunker #0
  - Right? ☐ yes ☐ no

- **supported** (for: anthropic-contextual-retrieval.md; against: –): Experiments found Voyage embeddings to be among the most effective for Anthropic’s contextual retrieval.
  - The source 'anthropic-contextual-retrieval.md' explicitly states in its conclusion that 'Voyage and Gemini had the best embeddings of those tested' and in the implementation considerations that 'Gemini and Voyage embeddings were found particularly effective'. This directly supports the claim that experiments found Voyage embeddings to be among the most effective.
  - Read: anthropic #4, anthropic #3, lumberchunker #3, lumberchunker #4, vectara #4, lewis #23, vectara #23, lewis #51
  - Right? ☐ yes ☐ no

- **supported** (for: anthropic-contextual-retrieval.md; against: –): Anthropic’s contextual retrieval reranks chunks with a Cohere reranker model after retrieval.
  - The source anthropic-contextual-retrieval.md explicitly states that in the 'Further boosting performance with reranking' section, 'Anthropic tested with the Cohere reranker'. It describes reranking as a filtering step after initial retrieval where a model scores each chunk's relevance. The other sources discuss different chunking methods or retrieval architectures (RAG, LumberChunker) and do not contradict this specific detail about Anthropic's methodology.
  - Read: anthropic #4, anthropic #3, vectara #26, lumberchunker #3, vectara #22, lumberchunker #22, lewis #6, lewis #13
  - Right? ☐ yes ☐ no

- **supported** (for: anthropic-contextual-retrieval.md; against: –): The Cohere reranker scores each chunk’s relevance to the query.
  - The source passage from anthropic-contextual-retrieval.md explicitly states that "a reranking model scores each chunk's relevance to the query" and confirms that "Anthropic tested with the Cohere reranker," directly supporting the claim.
  - Read: anthropic #4, vectara #22, vectara #33, lumberchunker #23, anthropic #3, lumberchunker #22, lewis #9, lewis #10
  - Right? ☐ yes ☐ no

- **supported** (for: anthropic-contextual-retrieval.md; against: –): Anthropic’s system selects the top K chunks to pass to the downstream generator.
  - The source 'anthropic-contextual-retrieval.md' explicitly states that in Anthropic's system, a reranking model selects the top-K chunks (specifically citing they used top 20) to pass to the model (downstream generator).
  - Read: anthropic #4, anthropic #3, vectara #1, lumberchunker #3, lumberchunker #2, vectara #5, lewis #6, lewis #9
  - Right? ☐ yes ☐ no

- **supported** (for: lumberchunker-emnlp2024.pdf; against: –): LumberChunker relies on an LLM to create the chunks.
  - The source lumberchunker-emnlp2024.pdf explicitly states in the Abstract that LumberChunker is a method 'leveraging an LLM to dynamically segment documents' and in the Conclusions that it is a method 'leveraging LLM textual capabilities to dynamically segment documents into semantically coherent chunks.' This directly supports the claim that LumberChunker relies on an LLM to create the chunks.
  - Read: lumberchunker #9, lumberchunker #0, vectara #5, vectara #10, lewis #9, anthropic #1, anthropic #3, lewis #3
  - Right? ☐ yes ☐ no

- **supported** (for: anthropic-contextual-retrieval.md; against: –): Anthropic’s system relies on embedding models (Gemini and Voyage) to represent the chunks.
  - The source document anthropic-contextual-retrieval.md confirms that Anthropic's system utilizes embedding models to process and retrieve chunks. Specifically, chunk #3 states that "Gemini and Voyage embeddings were found particularly effective" and lists them as the specific models tested for embedding chunks. While the text says "Gemini" rather than a specific version (and the claim says "Voyage"), it identifies these as the embedding models used to represent the retrieved chunks in the context of Anthropic's experiments. The other sources (LumberChunker, Vectara, Lewis RAG) discuss different systems or general RAG concepts but do not contradict the specific details of Anthropic's implementation described in the Anthropic source.
  - Read: anthropic #4, anthropic #3, vectara #25, lumberchunker #1, vectara #4, lumberchunker #2, lewis #9, lewis #23
  - Right? ☐ yes ☐ no

- **supported** (for: anthropic-contextual-retrieval.md; against: –): Anthropic’s system relies on a Cohere reranker to rank the chunks for relevance.
  - The source anthropic-contextual-retrieval.md explicitly states in chunk #4 that 'Anthropic tested with the Cohere reranker' as part of their filtering step to score chunk relevance. While the text uses the word 'tested', it identifies the Cohere reranker as the component used in their evaluated system configuration for ranking chunks.
  - Read: anthropic #4, anthropic #3, vectara #22, vectara #10, lumberchunker #23, lumberchunker #22, lewis #13, lewis #9
  - Right? ☐ yes ☐ no

## q05 (conflict): Does chunking documents by their content, for example with an LLM, consistently improve retrieval over simpler chunking methods?

Statement: *Chunking documents according to their content, rather than by a fixed rule, consistently improves retrieval.*

### Draft

The evidence is mixed.

* **Vectara’s systematic evaluation** of “semantic chunking” (which includes LLM‑driven, content‑aware splitting) found that the extra computational cost “is not justified by consistent performance gains” when compared with simpler fixed‑size chunking across several retrieval‑related tasks【vectara-semantic-chunking-naacl2025.pdf | chunk #0】.  

* **LumberChunker**, an LLM‑based dynamic segmenter, reports the opposite for narrative‑style documents: it “outperforms the most competitive baseline by 7.37 % in retrieval performance (DCG@20)” and yields higher QA accuracy than recursive (fixed‑size) chunking when integrated into a RAG pipeline【lumberchunker-emnlp2024.pdf | chunk #0】【lumberchunker-emnlp2024.pdf | chunk #9】. The authors note, however, that this method is more expensive and slower than traditional chunkers【lumberchunker-emnlp2024.pdf | chunk #9】.

**Conclusion:** Chunking by content with an LLM can improve retrieval in certain domains (e.g., long narrative texts) but does **not** consistently outperform simpler fixed‑size chunking across all datasets and tasks. The benefit appears to depend on the nature of the documents and the trade‑off between performance gains and computational cost.

### Verdicts

- **unverifiable** (for: –; against: –): The evidence is mixed.
  - The provided sources discuss specific results for various chunking and retrieval methods (e.g., Vectara's findings on semantic vs. fixed-size chunkers, Anthropic's performance improvements with Contextual Retrieval, and LumberChunker's proposal). While vectara-semantic-chunking-naacl2025.pdf suggests semantic chunkers may not have an edge in real-life scenarios compared to fixed-size ones, and other sources report positive results for their respective methods, none of the passages explicitly state or summarize the overall body of evidence as 'mixed'. The claim is a high-level synthesis of the field's findings that is not directly asserted in the provided texts.
  - Read: vectara #23, lumberchunker #1, lewis #18, lewis #12, vectara #7, lumberchunker #4, anthropic #2, anthropic #3
  - Right? ☐ yes ☐ no

- **supported** (for: vectara-semantic-chunking-naacl2025.pdf; against: –): Vectara’s systematic evaluation found that the extra computational cost of semantic chunking is not justified by consistent performance gains compared with simpler fixed-size chunking across several retrieval-related tasks.
  - The source document 'vectara-semantic-chunking-naacl2025.pdf' explicitly states in its Abstract that the study 'systematically evaluates' semantic chunking using 'three common retrieval-related tasks' (document retrieval, evidence retrieval, and retrieval-based answer generation) and concludes that 'the computational costs associated with semantic chunking are not justified by consistent performance gains' compared to fixed-size chunking. This aligns perfectly with the claim.
  - Read: vectara #0, vectara #1, lumberchunker #25, lumberchunker #8, anthropic #3, anthropic #4, lewis #52, lewis #22
  - Right? ☐ yes ☐ no

- **supported** (for: lumberchunker-emnlp2024.pdf; against: –): LumberChunker outperforms the most competitive baseline by 7.37% in retrieval performance (DCG@20) for narrative-style documents.
  - The source document lumberchunker-emnlp2024.pdf explicitly states in its abstract that 'LumberChunker not only outperforms the most competitive baseline by 7.37% in retrieval performance (DCG@20)'. This directly supports the claim.
  - Read: lumberchunker #9, lumberchunker #0, vectara #5, anthropic #3, anthropic #4, vectara #4, lewis #22, lewis #23
  - Right? ☐ yes ☐ no

- **supported** (for: lumberchunker-emnlp2024.pdf; against: –): LumberChunker yields higher QA accuracy than recursive (fixed-size) chunking when integrated into a RAG pipeline.
  - The source 'lumberchunker-emnlp2024.pdf' explicitly states that LumberChunker, when integrated into a RAG pipeline, demonstrates superior average accuracy compared to most baselines, specifically noting that it "outperforms again Recursive chunking." This directly supports the claim. While 'vectara-semantic-chunking-naacl2025.pdf' argues that semantic chunking generally does not yield significant gains over fixed-size chunking, it evaluates different methods (Breakpoint Clustering) and does not contradict the specific empirical result reported for LumberChunker in its own context.
  - Read: lumberchunker #9, lumberchunker #3, vectara #1, vectara #8, lewis #10, lewis #15, anthropic #1, anthropic #0
  - Right? ☐ yes ☐ no

- **supported** (for: lumberchunker-emnlp2024.pdf; against: –): The LumberChunker method is more expensive than traditional chunkers.
  - The source document lumberchunker-emnlp2024.pdf explicitly states in its Limitations section that LumberChunker "requires the use of an LLM, which automatically renders it more expensive and slower compared to traditional methods like Recursive chunking." It further notes that for highly structured texts, LumberChunker would achieve similar segmentations "but at a more expensive cost."
  - Read: lumberchunker #10, lumberchunker #9, vectara #8, vectara #27, anthropic #4, lewis #52, anthropic #1, lewis #9
  - Right? ☐ yes ☐ no

- **supported** (for: lumberchunker-emnlp2024.pdf; against: –): The LumberChunker method is slower than traditional chunkers.
  - The source document lumberchunker-emnlp2024.pdf explicitly states in its Limitations section that LumberChunker 'automatically renders it more expensive and slower compared to traditional methods like Recursive chunking'.
  - Read: lumberchunker #10, lumberchunker #9, vectara #8, vectara #27, anthropic #4, lewis #52, lewis #9, anthropic #1
  - Right? ☐ yes ☐ no

- **supported** (for: lumberchunker-emnlp2024.pdf; against: –): LLM-based content chunking can improve retrieval in certain domains such as long narrative texts.
  - The source 'lumberchunker-emnlp2024.pdf' explicitly proposes LLM-based content chunking (LumberChunker) and demonstrates in its experiments (Table 1 and Figure 3) that it improves retrieval performance (DCG@20) and QA accuracy specifically for long-form narrative documents (GutenQA benchmark). While 'vectara-semantic-chunking-naacl2025.pdf' notes that semantic chunking benefits are inconsistent in its specific evaluation setup, it does not address the specific domain of long narrative texts where LumberChunker showed consistent improvement, thus the claim remains supported by the evidence provided.
  - Read: lumberchunker #0, vectara #5, lumberchunker #9, vectara #2, lewis #24, anthropic #3, anthropic #4, lewis #52
  - Right? ☐ yes ☐ no

- **supported** (for: vectara-semantic-chunking-naacl2025.pdf; against: –): LLM-based content chunking does not consistently outperform simpler fixed-size chunking across all datasets and tasks.
  - The source 'vectara-semantic-chunking-naacl2025.pdf' explicitly states that semantic chunking (which includes LLM-based methods) shows benefits that are 'inconsistent' and 'highly task-dependent,' challenging the assumption that it consistently outperforms fixed-size chunking. This directly supports the claim that LLM-based/semantic chunking does not consistently outperform simpler methods across all datasets and tasks. While 'lumberchunker-emnlp2024.pdf' reports that its specific LLM-based method outperforms baselines on its specific benchmark (GutenQA), this single positive result does not contradict the general claim that performance is not consistent across *all* contexts, especially given the explicit findings of inconsistency in the broader evaluation provided by the Vectara paper.
  - Read: vectara #1, vectara #2, lumberchunker #0, lumberchunker #9, anthropic #3, anthropic #4, lewis #51, lewis #49
  - Right? ☐ yes ☐ no

- **supported** (for: vectara-semantic-chunking-naacl2025.pdf, lumberchunker-emnlp2024.pdf; against: –): The benefit of LLM-based content chunking depends on the nature of the documents and the trade‑off between performance gains and computational cost.
  - The claim is supported by the sources. 'vectara-semantic-chunking-naacl2025.pdf' explicitly discusses the trade-off, stating that the computational costs of semantic (often LLM-based) chunking are 'not justified by consistent performance gains' and that benefits are 'highly task-dependent'. 'lumberchunker-emnlp2024.pdf' supports the dependency on document nature, noting that LLM-based chunking performance varies by document type (narrative vs. factual) and highlighting the significant computational cost compared to non-LLM methods. Together, these sources confirm that the benefit depends on document characteristics and the performance/cost trade-off.
  - Read: vectara #0, vectara #1, lumberchunker #25, lumberchunker #9, anthropic #3, anthropic #4, lewis #25, lewis #21
  - Right? ☐ yes ☐ no

## q07 (false_premise): Why does RAG fine-tune its document encoder together with the generator?

Statement: *RAG fine-tunes its document encoder during training.*

### Draft

According to the original RAG paper, the document encoder is **not** fine‑tuned together with the generator. The authors point out that updating the document encoder (and rebuilding the index) during training is expensive, and they found that this extra step is unnecessary for achieving strong results. Consequently they keep the document encoder (and its index) fixed and only fine‑tune the query encoder and the BART generator [lewis-rag-neurips2020.pdf, chunk #8].

### Verdicts

- **supported** (for: lewis-rag-neurips2020.pdf; against: –): According to the original RAG paper, the document encoder is not fine‑tuned together with the generator.
  - The source document lewis-rag-neurips2020.pdf explicitly states in Section 2.4 (Training) that the document encoder (BERTd) and index are kept fixed during training, and only the query encoder (BERTq) and the BART generator are fine-tuned. This directly supports the claim that the document encoder is not fine-tuned.
  - Read: lewis #8, lewis #7, lumberchunker #3, lumberchunker #1, vectara #0, vectara #1, anthropic #1, anthropic #0
  - Right? ☐ yes ☐ no

- **supported** (for: lewis-rag-neurips2020.pdf; against: –): The authors point out that updating the document encoder and rebuilding the index during training is expensive.
  - The source lewis-rag-neurips2020.pdf explicitly states that "Updating the document encoder BERTd during training is costly as it requires the document index to be periodically updated". This directly supports the claim that the authors pointed out this process is expensive.
  - Read: lewis #7, lewis #8, anthropic #3, anthropic #2, lumberchunker #10, vectara #21, lumberchunker #22, vectara #7
  - Right? ☐ yes ☐ no

- **supported** (for: lewis-rag-neurips2020.pdf; against: –): The authors found that updating the document encoder and rebuilding the index during training is unnecessary for achieving strong results.
  - The source lewis-rag-neurips2020.pdf explicitly states in Section 2.4 (Training) that updating the document encoder is costly because it requires periodically updating the document index, and the authors state: "We do not find this step necessary for strong performance, and keep the document encoder (and index) fixed". This directly supports the claim.
  - Read: lewis #7, vectara #25, lewis #8, vectara #26, anthropic #3, anthropic #2, lumberchunker #8, lumberchunker #25
  - Right? ☐ yes ☐ no

- **supported** (for: lewis-rag-neurips2020.pdf; against: –): Consequently, they keep the document encoder and its index fixed.
  - The claim is directly supported by the source lewis-rag-neurips2020.pdf. In chunk #7 and chunk #8, the authors state: "We do not find this step necessary for strong performance, and keep the document encoder (and index) fixed, only fine-tuning the query encoder BERTq and the BART generator." This matches the claim that they keep the document encoder and its index fixed.
  - Read: lewis #7, vectara #34, vectara #22, lewis #8, anthropic #2, lumberchunker #8, lumberchunker #25, anthropic #0
  - Right? ☐ yes ☐ no

- **supported** (for: lewis-rag-neurips2020.pdf; against: –): They only fine‑tune the query encoder and the BART generator.
  - The source lewis-rag-neurips2020.pdf explicitly states in Section 2.4 (Training) that the authors "keep the document encoder (and index) fixed, only fine-tuning the query encoder BERTq and the BART generator." This directly supports the claim.
  - Read: lewis #7, lewis #8, vectara #23, lumberchunker #1, vectara #22, anthropic #3, anthropic #4, lumberchunker #8
  - Right? ☐ yes ☐ no

## q09 (out_of_corpus): How does RAPTOR build its tree of recursive summaries for retrieval?

### Draft

The provided passages do not contain any description of RAPTOR or how it constructs a tree of recursive summaries for retrieval. Consequently, I cannot answer that question based on the given sources.

### Verdicts

### Set aside as being about the answer itself (not verified)

- The provided passages do not contain any description of RAPTOR.
  - Really about the answer, not the topic? ☐ yes ☐ no

- The provided passages do not contain any description of how RAPTOR constructs a tree of recursive summaries for retrieval.
  - Really about the answer, not the topic? ☐ yes ☐ no

- I cannot answer the question based on the given sources.
  - Really about the answer, not the topic? ☐ yes ☐ no
