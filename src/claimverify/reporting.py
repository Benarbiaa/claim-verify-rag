"""
Suivi d'un run — les événements vers le terminal et vers le disque
===================================================================

Un Run a un identifiant (date-heure + pipeline) et un dossier :
    runs/<run_id>/events.jsonl   un événement complet par ligne (voir events.py)
    runs/<run_id>/report.*       le rapport final (pipeline de réponse)

Les sinks reçoivent chaque événement :
    ConsoleSink   une ligne courte dans le terminal
    RecorderSink  l'événement complet dans events.jsonl, écrit tout de suite :
                  le fichier est lisible pendant le run et survit à un plantage
Une interface (ou une base de données) sera un sink de plus, sans changer
les orchestrateurs.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import TypeAdapter

from claimverify.contracts import VERDICT_ICONS
from claimverify.events import AnyEvent, Event, Pipeline

RUNS_DIR = Path("runs")


@runtime_checkable
class EventSink(Protocol):
    """Interface : reçoit les événements d'un run."""

    def handle(self, event: Event) -> None: ...


class ConsoleSink:
    """Une ligne courte par événement. Le détail complet est dans events.jsonl."""

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
        if t == "question_finished":
            counts = ", ".join(f"{n} {label}" for label, n in event.verdict_counts.items() if n)
            return f"[done] {counts} ({s})"
        if t == "run_finished":
            return f"[run] finished ({s}) -> {event.summary.get('run_dir', '')}"
        return ""


def _usage_note(event: Event) -> str:
    """", 4.5K tokens, 1 retry (waited 21s)" pour une étape qui a appelé un LLM, sinon ""."""
    usage = getattr(event, "usage", None)
    if not usage or not usage.calls:
        return ""
    note = f", {(usage.tokens_in + usage.tokens_out) / 1000:.1f}K tokens"
    if usage.retries:
        plural = "retry" if usage.retries == 1 else "retries"
        note += f", {usage.retries} {plural} (waited {usage.waited_seconds:.0f}s)"
    return note


class RecorderSink:
    """Ajoute chaque événement complet, en JSON, à un fichier (une ligne par événement)."""

    def __init__(self, path: Path):
        self.path = path

    def handle(self, event: Event) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")


class Run:
    """Un run : son identifiant, son dossier, et les sinks qui reçoivent ses événements."""

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
    """Relit un events.jsonl en objets identiques à ceux émis (pour l'interface, le rejeu)."""
    with open(path, encoding="utf-8") as f:
        return [_EVENT.validate_json(line) for line in f if line.strip()]
