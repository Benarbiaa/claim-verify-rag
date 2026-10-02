"""Pipeline events: emitted after each stage, recorded to disk, reloadable. No network, no database."""

import json
from pathlib import Path

from claimverify.answering.decomposition import LLMDecomposer
from claimverify.answering.drafting import LLMDrafter
from claimverify.answering.pipeline import run_single_question
from claimverify.answering.verification import LangGraphVerifier, LLMJudge
from claimverify.contracts import Chunk, Document
from claimverify.events import ClaimVerified, DraftWritten, LLMWaiting
from claimverify.factory import AnsweringStages, IndexingStages
from claimverify.indexing import ingest
from claimverify.indexing.cleaning import MinimalCleaner
from claimverify.reporting import ConsoleSink, RecorderSink, Run, load_events
from claimverify.settings import load_settings
from fakes import fake_llm
from test_interfaces import PASSAGE, FakeEmbedder, FakeRetriever

CONFIG = Path(__file__).parent.parent / "config.yaml"
CLAIMS = json.dumps({"claims": [{"id": "c1", "claim": "A"}, {"id": "c2", "claim": "B"}]})
VERDICT = json.dumps({"verdict": "supported", "justification": "a.pdf says so",
                      "supporting_sources": ["a.pdf"], "contradicting_sources": []})


class ListSink:
    def __init__(self):
        self.events = []

    def handle(self, event):
        self.events.append(event)


def answering_stages() -> AnsweringStages:
    return AnsweringStages(
        retriever=FakeRetriever(),
        drafter=LLMDrafter(fake_llm("Draft answer [a.pdf].")),
        decomposer=LLMDecomposer(fake_llm(CLAIMS)),
        verifier=LangGraphVerifier(FakeRetriever(), LLMJudge(fake_llm(VERDICT))),
    )


def test_answering_emits_one_event_per_stage_and_per_verdict(tmp_path):
    sink = ListSink()
    run = Run("answering", sinks=[sink], runs_dir=tmp_path)
    run_single_question("Q?", answering_stages(), run)

    assert [e.type for e in sink.events] == [
        "question_started", "passages_retrieved", "draft_written", "claims_extracted",
        "claim_verified", "claim_verified", "question_finished",
    ]
    verified = [e for e in sink.events if isinstance(e, ClaimVerified)]
    assert [(e.position, e.total) for e in verified] == [(1, 2), (2, 2)]
    # each stage's full output is in its event, including what the judge read
    assert verified[0].verdict.evidence == [PASSAGE]
    assert next(e for e in sink.events if isinstance(e, DraftWritten)).draft.text == "Draft answer [a.pdf]."
    assert all(e.run_id == run.run_id and e.pipeline == "answering" for e in sink.events)


def test_indexing_emits_one_event_per_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "setup_db", lambda conn: None)
    monkeypatch.setattr(ingest, "replace_chunks", lambda conn, chunks: None)
    doc = Document(doc_id="d", filename="a.pdf", source_type="peer_reviewed_paper", text="x\ty z\n1")

    class FakeLoader:
        def load(self, corpus_dir):
            return [doc]

    class FakeChunker:
        def chunk(self, documents):
            return [Chunk(chunk_id="d_0000", doc_id="d", filename="a.pdf",
                          source_type="peer_reviewed_paper", chunk_index=0, text="x y z")]

    sink = ListSink()
    run = Run("indexing", sinks=[sink], runs_dir=tmp_path)
    stages = IndexingStages(loader=FakeLoader(), cleaner=MinimalCleaner(), chunker=FakeChunker(),
                            embedder=FakeEmbedder())
    ingest.run_indexing(stages, Path("corpus"), None, run, load_settings(CONFIG))

    assert [e.type for e in sink.events] == [
        "run_started", "documents_loaded", "documents_cleaned", "chunks_built", "chunks_embedded",
        "chunks_stored", "run_finished",
    ]
    assert sink.events[1].documents[0].characters == 7
    # page number removed, tab collapsed: the summary says what changed, without the text
    cleaned = sink.events[2].documents[0]
    assert (cleaned.characters_before, cleaned.characters_after) == (7, 5)
    assert cleaned.changes["page_numbers"] == 1
    assert sink.events[3].chunks[0].embedding is None  # vectors are not saved in events
    assert sink.events[4].dimension == 2


def test_recorded_events_reload_identically(tmp_path):
    run = Run("answering", runs_dir=tmp_path, sinks=[])
    run.sinks = [RecorderSink(run.events_path)]
    run_single_question("Q?", answering_stages(), run)

    lines = run.events_path.read_text(encoding="utf-8").splitlines()
    reloaded = load_events(run.events_path)
    assert len(lines) == len(reloaded) == 7
    assert [e.model_dump_json() for e in reloaded] == lines


def test_run_folder_is_named_after_its_id(tmp_path):
    run = Run("indexing", sinks=[], runs_dir=tmp_path)
    assert run.dir == tmp_path / run.run_id and run.dir.is_dir()
    assert run.run_id.endswith("_indexing")


def test_console_prints_one_short_line_per_answering_event(tmp_path, capsys):
    run = Run("answering", sinks=[ConsoleSink()], runs_dir=tmp_path)
    run_single_question("Q?", answering_stages(), run)
    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    assert len(lines) == 7
    assert lines[4].startswith("[verify 1/2] ✓ supported")


def test_console_summarizes_the_cleaning_in_one_line():
    from claimverify.events import CleaningSummary, DocumentsCleaned
    event = DocumentsCleaned(run_id="r", pipeline="indexing", seconds=0.1, documents=[
        CleaningSummary(filename="a.pdf", characters_before=9, characters_after=8,
                        changes={"page_numbers": 2, "hyphens_joined": 3}),
        CleaningSummary(filename="b.md", characters_before=5, characters_after=5, changes={}),
    ])
    assert ConsoleSink.describe(event) == (
        "[clean] 1 of 2 documents repaired: page numbers 2, hyphens joined 3 (0.1s)")


def test_stage_events_carry_their_llm_usage(tmp_path):
    sink = ListSink()
    stages = answering_stages()
    meter = stages.meter
    for llm in (stages.drafter.llm, stages.decomposer.llm, stages.verifier.judge.llm):
        object.__setattr__(llm, "meter", meter)  # shared meter, as the factory does
    run_single_question("Q?", stages, Run("answering", sinks=[sink], runs_dir=tmp_path))

    by_type = {}
    for e in sink.events:
        by_type.setdefault(e.type, []).append(e)
    assert by_type["passages_retrieved"][0].usage.calls == 0   # retrieval uses no LLM
    assert by_type["draft_written"][0].usage.calls == 1
    assert by_type["draft_written"][0].usage.tokens_in == 100
    assert [e.usage.calls for e in by_type["claim_verified"]] == [1, 1]  # one judge call each


def test_a_wait_during_a_stage_is_emitted_before_the_stage_ends(tmp_path):
    from claimverify.llm import WaitNotice

    class WaitingDrafter:
        """Announces a rate-limit wait through the shared meter, as LLM.chat does."""
        def __init__(self, meter, drafter):
            self.meter, self.drafter = meter, drafter

        def draft(self, question, passages):
            self.meter.on_wait(WaitNotice("draft", "m", 29.0, 1, "rate_limit"))
            return self.drafter.draft(question, passages)

    sink = ListSink()
    stages = answering_stages()
    stages.drafter = WaitingDrafter(stages.meter, stages.drafter)
    run_single_question("Q?", stages, Run("answering", sinks=[sink], runs_dir=tmp_path), question_index=2)

    types = [e.type for e in sink.events]
    assert types.index("llm_waiting") == types.index("draft_written") - 1
    wait = next(e for e in sink.events if isinstance(e, LLMWaiting))
    assert (wait.question_index, wait.role, wait.seconds, wait.attempt, wait.reason) == (
        2, "draft", 29.0, 1, "rate_limit")
    assert ConsoleSink.describe(wait) == "[wait] draft: rate limit, retrying in 29s (attempt 2)"
