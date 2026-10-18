# Label reviews

A label is "the truth" every measurement is compared with. Changing one after seeing results can
turn a failure into a success without the system improving, so each change made after a run is
recorded here: what changed, why, when, and the scores before and after. The previous labels stay
in the git history.

## 2026-10-18 — g05 and q06: a scope difference read as a conflict

**Changed after seeing the results.** The judge evaluation (2026-10-05) and the end-to-end smoke
test (2026-10-12) had both run on the old labels.

### What happened

Gold claim g05, *"How documents are split into chunks has a large effect on retrieval quality"*,
was labelled `contested`, with Vectara's conclusion as the evidence against:

> Vectara, conclusion: "The impact of chunking strategy was often overshadowed by other factors,
> such as the quality of embeddings"

against the evidence for it, in LumberChunker and Vectara's own introduction:

> LumberChunker: "how textual content is segmented into 'chunks', which can significantly impact
> the dense retrieval quality"
>
> Vectara, introduction: "cutting documents into smaller units called 'chunks' has a crucial
> effect on the quality of both retrieval and generation tasks"

The judge answered `supported` both times:

| Run | Judge's passages | Verdict | Blamed on |
|---|---|---|---|
| Judge evaluation, 2026-10-05 | did not include the conclusion | `supported` | retrieval |
| End-to-end q06, 2026-10-12 | **included** the conclusion (claim 1 read Vectara chunk #9) | `supported` | judge |

With the search now bringing the conclusion, the failure moved from retrieval to the judge. Before
calling it a judge bug, the label itself was reviewed.

### Why the label was wrong

1. **The two Vectara sentences are about different things.** The introduction is about chunking
   itself (how documents are cut matters). The conclusion is about choosing between the strategies
   it tested (semantic or fixed-size), which mattered less than the embedding model. Both are true
   at once, and the authors wrote both in one paper.
2. **"Overshadowed" is relative and hedged.** An effect can be large and still be smaller than
   another one; the sentence also says *often*, *especially when* resources are limited or
   documents have a standard structure. That weakens the claim; it does not contradict it.
3. **`contested` requires incompatible statements.** The gold set's own rule. A judge calling this
   `contested` would be over-flagging, the false alarm the complementary category exists to catch.

### What changed

| Item | Before | After |
|---|---|---|
| g05 | `cross_source_conflict`, expected `contested` | `complementary`, expected `supported`: kept as a trap, reading a scope difference as a contradiction is a false alarm |
| q06 | `conflict` question with a statement | `multi_source`: both papers say chunking matters; tests that the scope difference is not flagged |
| q05 | "Does semantic chunking improve retrieval compared to fixed-size chunking?" | "Does chunking documents by their content, for example with an LLM, consistently improve retrieval over simpler chunking methods?" (reworded before its first end-to-end run) |
| End-to-end smoke set | q01 q04 **q06** q07 q09 | q01 q04 **q05** q07 q09 |

q05's old wording asked about semantic versus fixed-size chunking, on which both papers agree:
LumberChunker's embedding-based "Semantic Chunking" baseline scores lowest in its own Table 1. In a
recorded run (2026-09-26) the draft said both papers agree, with both proofs read.

### Scores

| Evaluation | Original labels | After this review |
|---|---|---|
| Judge on the gold set | **9/10** (contested 1/2, complementary 2/2) | **10/10** (contested 1/1, complementary 3/3) |
| End-to-end smoke test | 4/5 (q06 failed "conflict found") | 4/4 run, q05 not run yet; q06 passes as `multi_source` |

No verdict was re-run: the same recorded verdicts were scored against the reviewed labels
(`make eval-judge RESUME=1` with every verdict saved makes no LLM call; the original run's cost,
41K tokens and 232 s of rate-limit waits, is in the git history of `results/judge.md`). The
judge did not improve; the labels did. Read the 10/10 with that in mind.

g05's `supported` verdict is right, but the quotes now proving it were not among the passages the
judge read for that verdict: it rests on other passages saying the same thing.

### The same standard applied to the other conflicts

Every apparent disagreement in the corpus was checked with one question: *are the two quotes
about the same proposition, and incompatible?*

| Case | Same proposition? | Decision |
|---|---|---|
| g05 / q06, "chunking has a large effect" | No: chunking itself vs choosing a strategy | relabelled |
| g06 / q05, "content-based chunking consistently improves retrieval" | The papers test different methods (LumberChunker an LLM, Vectara embedding similarity), but both bear on the general claim in opposite directions | **kept** `contested` |
| Semantic vs fixed-size chunking | Yes, and the papers agree (semantic is not better) | not a conflict |
| Whole document in the prompt vs RAG | Anthropic gives advice ("you can just include the entire knowledge base" under 200K tokens); LumberChunker measures RAG beating Gemini 1.5 Pro | not incompatible |

### What it reveals

**The corpus has no clean contradiction.** Its disagreements are differences of scope, method or
emphasis. `contested`, the project's headline verdict, now rests on a single gold claim (g06) and a
single question (q05), both about a general claim tested on different methods. Getting a sharp
conflict (same method, same kind of data, opposite results) needs a new document in the corpus.

### Rule kept from this incident

A `contested` label needs quotes that make incompatible statements about the same proposition. A
weaker, narrower or relative statement is not a contradiction.
