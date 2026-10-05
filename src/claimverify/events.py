"""
Pipeline events — what each stage produced
==========================================

After each stage, the orchestrator (indexing/ingest.py, answering/pipeline.py)
emits an event holding the stage's OUTPUT. "Sinks" receive them (see
reporting.py): one short line in the terminal, the full record in
runs/<run_id>/events.jsonl, and the UI.

The stages themselves emit nothing: they stay independent of any display
(observer pattern, the orchestrator being the only emitter).

Every event has a "type" field: an events.jsonl file reads back into
identical objects (load_events in reporting.py).
"""

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from claimverify.contracts import Chunk, Claim, Draft, Passage, Verdict

Pipeline = Literal["indexing", "answering"]


class Usage(BaseModel):
    """LLM calls during a stage (all zero for a stage without an LLM)."""
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    retries: int = 0            # new attempts after a temporary error
    waited_seconds: float = 0   # time spent waiting before those attempts
    seconds: float = 0          # total duration of the calls, waits included

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(**{name: getattr(self, name) + getattr(other, name)
                        for name in type(self).model_fields})


class Event(BaseModel):
    """Common fields, filled in by Run.emit (reporting.py)."""
    run_id: str
    pipeline: Pipeline
    time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- Both pipelines -----------------------------------------------------------------

class RunStarted(Event):
    type: Literal["run_started"] = "run_started"
    config: dict       # the whole config.yaml, to reproduce the run
    inputs: dict       # e.g. {"corpus_dir": ...} or {"questions": [...]}


class RunFinished(Event):
    type: Literal["run_finished"] = "run_finished"
    summary: dict
    seconds: float


# --- Indexing ----------------------------------------------------------------------

class DocumentSummary(BaseModel):
    """A document without its text (the text is in data/corpus/)."""
    doc_id: str
    filename: str
    source_type: str
    characters: int


class DocumentsLoaded(Event):
    type: Literal["documents_loaded"] = "documents_loaded"
    documents: list[DocumentSummary]
    seconds: float


class CleaningSummary(BaseModel):
    """What the cleaning changed in a document (the text is not copied)."""
    filename: str
    characters_before: int
    characters_after: int
    changes: dict[str, int]  # rule -> number of repairs


class DocumentsCleaned(Event):
    type: Literal["documents_cleaned"] = "documents_cleaned"
    documents: list[CleaningSummary]
    seconds: float


class ChunksBuilt(Event):
    type: Literal["chunks_built"] = "chunks_built"
    chunks: list[Chunk]  # without vectors: the vectors are in the database
    seconds: float


class ChunksEmbedded(Event):
    type: Literal["chunks_embedded"] = "chunks_embedded"
    count: int
    dimension: int
    seconds: float


class ChunksStored(Event):
    type: Literal["chunks_stored"] = "chunks_stored"
    count: int
    seconds: float


# --- Answering a question (question_index: position in the run) ---------------------

class QuestionStarted(Event):
    type: Literal["question_started"] = "question_started"
    question_index: int
    question: str


class PassagesRetrieved(Event):
    type: Literal["passages_retrieved"] = "passages_retrieved"
    question_index: int
    passages: list[Passage]
    seconds: float
    usage: Usage = Usage()


class DraftWritten(Event):
    type: Literal["draft_written"] = "draft_written"
    question_index: int
    draft: Draft
    seconds: float
    usage: Usage = Usage()


class ClaimsExtracted(Event):
    type: Literal["claims_extracted"] = "claims_extracted"
    question_index: int
    claims: list[Claim]
    seconds: float
    usage: Usage = Usage()


class ClaimVerified(Event):
    type: Literal["claim_verified"] = "claim_verified"
    question_index: int
    position: int      # 1, 2, ... out of `total`
    total: int
    verdict: Verdict   # holds the passages judged (evidence)
    usage: Usage = Usage()


class LLMWaiting(Event):
    """An LLM call waits before a new attempt (e.g. a per-minute limit).
    Emitted DURING a stage, unlike the others: a UI can show the countdown
    instead of looking frozen."""
    type: Literal["llm_waiting"] = "llm_waiting"
    question_index: int | None = None
    role: str          # draft, decompose, verify
    model: str
    seconds: float     # announced wait
    attempt: int       # the attempt that just failed
    reason: str        # rate_limit, server_error, connection


class QuestionFinished(Event):
    type: Literal["question_finished"] = "question_finished"
    question_index: int
    verdict_counts: dict[str, int]
    seconds: float


AnyEvent = Annotated[
    RunStarted | RunFinished
    | DocumentsLoaded | DocumentsCleaned | ChunksBuilt | ChunksEmbedded | ChunksStored
    | QuestionStarted | PassagesRetrieved | DraftWritten | ClaimsExtracted | ClaimVerified
    | LLMWaiting | QuestionFinished,
    Field(discriminator="type"),
]
