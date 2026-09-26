"""The UI's API: run folders read back, live runs streamed. No network, no API key, no database."""

import json
import shutil
from pathlib import Path

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from claimverify.api import live as live_module
from claimverify.api.app import create_app
from claimverify.api.live import LiveRunner, describe_failure
from claimverify.api.runs import RunStore
from claimverify.llm import LLMCallError
from test_events import answering_stages

ROOT = Path(__file__).parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "runs" / "20260101_090000_answering"


@pytest.fixture
def runs_dir(tmp_path):
    runs = tmp_path / "runs"
    shutil.copytree(FIXTURE, runs / FIXTURE.name)
    return runs


def client_for(runs_dir: Path, live: LiveRunner | None = None) -> TestClient:
    return TestClient(create_app(RunStore({"recorded": runs_dir}), live))


# --- recorded runs --------------------------------------------------------------------

def test_runs_list_summarizes_each_run(runs_dir):
    [summary] = client_for(runs_dir).get("/api/runs").json()
    assert summary["run_id"] == FIXTURE.name
    assert summary["pipeline"] == "answering"
    assert summary["status"] == "finished"
    assert summary["config_file"] == "experiments/smoke_k1.yaml"
    assert summary["verdict_counts"] == {"supported": 2, "contested": 1, "contradicted": 1,
                                         "unverifiable": 1, "error": 1}
    assert summary["usage"]["retries"] == 7  # 1 while decomposing + 6 while verifying


def test_run_detail_returns_every_event_in_order(runs_dir):
    detail = client_for(runs_dir).get(f"/api/runs/{FIXTURE.name}").json()
    types = [e["type"] for e in detail["events"]]
    assert types[0] == "run_started" and types[-1] == "run_finished"
    assert types.count("claim_verified") == 6
    contested = next(e["verdict"] for e in detail["events"]
                     if e["type"] == "claim_verified" and e["verdict"]["verdict"] == "contested")
    assert contested["supporting_sources"] and contested["contradicting_sources"]
    assert contested["evidence"][0]["text"]  # the passages the judge read


def test_an_unfinished_run_is_listed_as_incomplete(runs_dir):
    events = (runs_dir / FIXTURE.name / "events.jsonl").read_text().splitlines()
    partial = runs_dir / "20260102_090000_answering"
    partial.mkdir()
    (partial / "events.jsonl").write_text("\n".join(events[:5]) + "\n")
    summaries = {s["run_id"]: s for s in client_for(runs_dir).get("/api/runs").json()}
    assert summaries[partial.name]["status"] == "incomplete"


def test_an_unreadable_run_is_listed_not_fatal(runs_dir):
    broken = runs_dir / "20260103_090000_indexing"
    broken.mkdir()
    (broken / "events.jsonl").write_text("{not json\n")
    client = client_for(runs_dir)
    summaries = {s["run_id"]: s for s in client.get("/api/runs").json()}
    assert summaries[broken.name]["status"] == "unreadable"
    assert client.get(f"/api/runs/{broken.name}").status_code == 422


def test_unknown_run_is_404(runs_dir):
    assert client_for(runs_dir).get("/api/runs/20990101_000000_answering").status_code == 404


def test_folders_that_are_not_runs_are_ignored(runs_dir):
    (runs_dir / "notes").mkdir()
    (runs_dir / "notes" / "events.jsonl").write_text("")
    assert [s["run_id"] for s in client_for(runs_dir).get("/api/runs").json()] == [FIXTURE.name]


# --- live runs ------------------------------------------------------------------------

@pytest.fixture
def live_runner(runs_dir, monkeypatch):
    """A LiveRunner whose stages are the test fakes: nothing leaves the machine."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(live_module.psycopg2, "connect", lambda url: FakeConnection())
    monkeypatch.setattr(live_module, "build_answering", lambda settings, conn, embedder: answering_stages())
    monkeypatch.setattr(live_module, "build_embedder", lambda settings: None)
    return LiveRunner(ROOT, runs_dir, db_url="postgresql://fake")


class FakeConnection:
    def close(self):
        pass


def read_stream(client: TestClient, run_id: str) -> list[tuple[str, dict]]:
    messages = []
    with client.stream("GET", f"/api/live/{run_id}/stream") as response:
        kind = None
        for line in response.iter_lines():
            if line.startswith("event: "):
                kind = line.removeprefix("event: ")
            elif line.startswith("data: "):
                messages.append((kind, json.loads(line.removeprefix("data: "))))
    return messages


def test_a_live_run_streams_its_events_then_ends(live_runner, runs_dir):
    client = client_for(runs_dir, live_runner)
    response = client.post("/api/live", json={"question": "Q?", "config_file": "config.yaml"})
    assert response.status_code == 201
    run_id = response.json()["run_id"]

    messages = read_stream(client, run_id)
    kinds = [data["type"] for kind, data in messages if kind == "pipeline"]
    assert kinds[:3] == ["run_started", "question_started", "passages_retrieved"]
    assert kinds[-1] == "run_finished"
    assert messages[-1] == ("end", {"status": "finished"})
    # recorded like any run: it replays afterwards without API calls
    assert (runs_dir / run_id / "report.json").exists()
    assert client.get(f"/api/runs/{run_id}").json()["summary"]["status"] == "finished"


def test_live_run_refuses_to_start_without_a_key(live_runner, runs_dir, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    response = client_for(runs_dir, live_runner).post("/api/live", json={"question": "Q?"})
    assert response.status_code == 400
    assert "GROQ_API_KEY" in response.json()["detail"]


def test_a_failing_stage_ends_the_stream_with_a_clear_message(live_runner, runs_dir, monkeypatch):
    def too_large(*args, **kwargs):
        raise LLMCallError("draft : trop gros") from status_error(413)

    stages = answering_stages()
    stages.drafter.draft = too_large
    monkeypatch.setattr(live_module, "build_answering", lambda settings, conn, embedder: stages)
    client = client_for(runs_dir, live_runner)
    run_id = client.post("/api/live", json={"question": "Q?"}).json()["run_id"]

    kind, error = read_stream(client, run_id)[-1]
    assert kind == "failed" and error["kind"] == "request_too_large"
    assert client.get(f"/api/runs/{run_id}").json()["summary"]["status"] == "failed"


def test_live_info_estimates_the_cost_from_recorded_runs(live_runner, runs_dir):
    info = client_for(runs_dir, live_runner).get("/api/live").json()
    assert info["enabled"]
    assert info["estimate"]["basis_runs"] == 1
    assert info["estimate"]["tokens_per_question"] > 20_000
    assert {c["file"] for c in info["configs"]} >= {"config.yaml", "experiments/smoke_k1.yaml"}


def test_live_mode_can_be_disabled(runs_dir):
    client = client_for(runs_dir)
    assert client.get("/api/live").json() == {"enabled": False}
    assert client.post("/api/live", json={"question": "Q?"}).status_code == 403


def status_error(status: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "http://fake")
    return openai.APIStatusError("error", response=httpx.Response(status, request=request), body=None)


@pytest.mark.parametrize("status, kind", [(413, "request_too_large"), (429, "daily_limit"),
                                          (500, "gave_up")])
def test_run_stopping_errors_get_an_explanation(status, kind):
    try:
        raise LLMCallError("stop") from status_error(status)
    except LLMCallError as e:
        assert describe_failure(e)["kind"] == kind
