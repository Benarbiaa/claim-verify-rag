"""
Following a run — events to the terminal and to disk
====================================================

A Run has an id (date-time + pipeline) and a folder:
    runs/<run_id>/events.jsonl   one full event per line (see events.py)
    runs/<run_id>/report.*       the final report (answering pipeline)

Sinks receive every event:
    ConsoleSink   one short line in the terminal
    RecorderSink  the full event in events.jsonl, written at once: the file
                  can be read during the run and survives a crash
A UI (or a database) is one more sink, with no change to the orchestrators.
"""

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import TypeAdapter

from claimverify.contracts import VERDICT_ICONS
from claimverify.events import AnyEvent, Event, Pipeline

RUNS_DIR = Path("runs")


@runtime_checkable
class EventSink(Protocol):
    """Interface: receives the events of a run."""

    def handle(self, event: Event) -> None: ...


class ConsoleSink:
    """One short line per event. The full detail is in events.jsonl."""

    def handle(self, event: Event) -> None:
        line = self.describe(event)
        if line:
            print(line, flush=True)

    @staticmethod
    def describe(event: Event) -> str:
        t = event.type
        s = f"{getattr(event, 'seconds', 0):.1f}s" + _usage_note(event)
        if t == "run_started":
            return f"[run] {event.run_id}"
        if t == "documents_loaded":
            return f"[load] {len(event.documents)} documents ({s})"
        if t == "documents_cleaned":
            changed = sum(1 for d in event.documents if any(d.changes.values()))
            total = Counter()
            for d in event.documents:
                total.update(d.changes)
            detail = ", ".join(f"{rule.replace('_', ' ')} {n}" for rule, n in total.items())
            return (f"[clean] {changed} of {len(event.documents)} documents repaired"
                    + (f": {detail}" if detail else "") + f" ({s})")
        if t == "chunks_built":
            return f"[chunk] {len(event.chunks)} chunks ({s})"
        if t == "chunks_embedded":
            return f"[embed] {event.count} vectors of dimension {event.dimension} ({s})"
        if t == "chunks_stored":
            return f"[store] {event.count} chunks written ({s})"
        if t == "question_started":
            return f"\n[question {event.question_index}] {event.question}"
        if t == "passages_retrieved":
            docs = len({p.filename for p in event.passages})
            return f"[retrieve] {len(event.passages)} passages from {docs} documents ({s})"
        if t == "draft_written":
            return f"[draft] {len(event.draft.text.split())} words ({s})"
        if t == "claims_extracted":
            return f"[decompose] {len(event.claims)} claims ({s})"
        if t == "claim_verified":
            v = event.verdict
            note = _usage_note(event).removeprefix(", ")
            return (f"[verify {event.position}/{event.total}] {VERDICT_ICONS[v.verdict]} {v.verdict}: "
                    f"{v.claim}" + (f" ({note})" if note else ""))
        if t == "llm_waiting":
            return (f"[wait] {event.role}: {event.reason.replace('_', ' ')}, "
                    f"retrying in {event.seconds:.0f}s (attempt {event.attempt + 1})")
        if t == "question_finished":
            counts = ", ".join(f"{n} {label}" for label, n in event.verdict_counts.items() if n)
            return f"[done] {counts} ({s})"
        if t == "run_finished":
            return f"[run] finished ({s}) -> {event.summary.get('run_dir', '')}"
        return ""


def _usage_note(event: Event) -> str:
    """", 4.5K tokens, 1 retry (waited 21s)" for a stage that called an LLM, else ""."""
    usage = getattr(event, "usage", None)
    if not usage or not usage.calls:
        return ""
    note = f", {(usage.tokens_in + usage.tokens_out) / 1000:.1f}K tokens"
    if usage.retries:
        plural = "retry" if usage.retries == 1 else "retries"
        note += f", {usage.retries} {plural} (waited {usage.waited_seconds:.0f}s)"
    return note


class RecorderSink:
    """Appends each full event, as JSON, to a file (one line per event)."""

    def __init__(self, path: Path):
        self.path = path

    def handle(self, event: Event) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")


class Run:
    """A run: its id, its folder, and the sinks that receive its events."""

    def __init__(self, pipeline: Pipeline, sinks: list[EventSink] | None = None,
                 runs_dir: Path = RUNS_DIR):
        self.pipeline = pipeline
        self.run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{pipeline}"
        self.dir = runs_dir / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.jsonl"
        self.sinks = sinks if sinks is not None else [ConsoleSink(), RecorderSink(self.events_path)]

    def emit(self, event_type: type[Event], **fields) -> Event:
        event = event_type(run_id=self.run_id, pipeline=self.pipeline, **fields)
        for sink in self.sinks:
            sink.handle(event)
        return event


_EVENT = TypeAdapter(AnyEvent)


def load_events(path: Path) -> list[Event]:
    """Reads an events.jsonl back into objects identical to those emitted (for the UI, replay)."""
    with open(path, encoding="utf-8") as f:
        return [_EVENT.validate_json(line) for line in f if line.strip()]
