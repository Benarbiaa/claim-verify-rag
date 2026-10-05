"""
The pipeline's data contracts
=============================

The objects passed between stages, defined here once. Each stage knows the
others only through these contracts: a stage's implementation (another LLM, a
local model, a classifier...) can be replaced without touching the rest, as
long as it consumes and produces these objects.

    INDEXING    Document -> Chunk
    ANSWERING   question -> Passage -> Draft -> Claim -> Verdict

Every contract is a Pydantic model: it validates the data (useful for LLM
outputs) and serializes to JSON, so each stage can run on its own, from the
file the previous stage produced.
"""

from typing import Literal, get_args

from pydantic import BaseModel, model_validator

# The possible verdicts, defined once. Any stage that needs them (report,
# summary, evaluation) imports them from here instead of copying them.
#
# The 4 verdicts a judge can give:
#   supported     at least one source backs the claim, none contradicts it
#   contradicted  the sources contradict the claim, none backs it
#   contested     the sources contradict EACH OTHER on this claim
#   unverifiable  no source deals with the claim's subject
JudgeLabel = Literal["supported", "contradicted", "contested", "unverifiable"]
JUDGE_LABELS: tuple[str, ...] = get_args(JudgeLabel)
# "error" is never offered to the judge: our code sets it when the judge's
# answer is unusable. It is not a judgment about the sources, so it is counted
# separately (and a new attempt can fix it).
VerdictLabel = Literal[JudgeLabel, "error"]
VERDICT_LABELS: tuple[str, ...] = (*JUDGE_LABELS, "error")
# Icon shown for each verdict in summaries and reports.
VERDICT_ICONS: dict[str, str] = {
    "supported": "✓", "contradicted": "✗", "contested": "⚠", "unverifiable": "?", "error": "!",
}


# --- Indexing -----------------------------------------------------------------

class Document(BaseModel):
    """A corpus file, converted to plain text."""
    doc_id: str
    filename: str
    source_type: str
    text: str


class CleanedDocument(BaseModel):
    """The cleaner's output: the repaired document, and what each rule changed."""
    document: Document
    characters_before: int
    changes: dict[str, int] = {}  # rule -> number of repairs


class Chunk(BaseModel):
    """A piece of a document, the unit stored and searched."""
    chunk_id: str
    doc_id: str
    filename: str
    source_type: str
    chunk_index: int
    text: str
    tokens: int | None = None  # size in the embedder's tokens (absent from older runs)
    embedding: list[float] | None = None  # filled in by the embedder


# --- Answering a question ------------------------------------------------------

class Passage(BaseModel):
    """A chunk returned by the retriever, with its similarity score."""
    filename: str
    source_type: str
    chunk_index: int
    text: str
    score: float


class Draft(BaseModel):
    """The draft answer, and the passages it relies on."""
    question: str
    text: str
    passages: list[Passage]


class Claim(BaseModel):
    """An atomic assertion extracted from the draft."""
    id: str
    claim: str
    cited_source: str | None = None


class Verdict(BaseModel):
    """The verifier's judgment on a claim."""
    claim_id: str
    claim: str
    verdict: VerdictLabel
    justification: str
    supporting_sources: list[str] = []
    contradicting_sources: list[str] = []
    original_cited_source: str | None = None
    verifier: str  # which implementation judged (e.g. "llm_judge:qwen/qwen3.8-27b")
    evidence: list[Passage] = []  # the passages the judge read for this verdict

    @model_validator(mode="after")
    def _sources_match_the_verdict(self) -> "Verdict":
        # A verdict must be consistent with the sources it cites, whatever the
        # judge's implementation (LLM, classifier...).
        if self.verdict == "contradicted" and not self.contradicting_sources:
            raise ValueError("a 'contradicted' verdict must cite at least one contradicting source")
        if self.verdict == "contested" and not (self.supporting_sources and self.contradicting_sources):
            raise ValueError("a 'contested' verdict must cite sources on both sides")
        return self
