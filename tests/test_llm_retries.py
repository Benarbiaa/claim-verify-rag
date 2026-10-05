"""Retries, stop conditions and usage accounting in LLM.chat. Fake client and fake clock: no waiting."""

from types import SimpleNamespace

import httpx
import openai
import pytest

from claimverify.llm import LLM, LLMCallError, RetryPolicy, UsageMeter

REQUEST = httpx.Request("POST", "http://fake/chat/completions")


def status_error(status: int, message: str = "error", retry_after: str | None = None):
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(status, headers=headers, request=REQUEST)
    cls = {429: openai.RateLimitError, 400: openai.BadRequestError,
           500: openai.InternalServerError}.get(status, openai.APIStatusError)
    return cls(message, response=response, body=None)


def answer(content="ok", tokens_in=100, tokens_out=20):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=tokens_in, completion_tokens=tokens_out),
    )


class ScriptedClient:
    """Raises or answers following a script, one step per call."""

    def __init__(self, *script):
        self.script, self.calls = list(script), 0

        def create(**kwargs):
            step = self.script[self.calls]
            self.calls += 1
            if isinstance(step, Exception):
                raise step
            return step

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def llm_with(*script, max_retries=6, max_wait=60, meter=None):
    sleeps = []
    llm = LLM(role="verify", model="m", base_url="http://fake", client=ScriptedClient(*script),
              retry=RetryPolicy(max_retries, max_wait, 120), meter=meter or UsageMeter(),
              sleep=sleeps.append)
    return llm, sleeps


# --- what is retried --------------------------------------------------------------

def test_rate_limit_waits_as_asked_then_succeeds():
    llm, sleeps = llm_with(status_error(429, retry_after="7"), status_error(429, retry_after="3"),
                           answer("done"))
    assert llm.chat([]) == "done"
    assert sleeps == [7.0, 3.0]
    usage = llm.meter.take()
    assert (usage.calls, usage.retries, usage.waited_seconds) == (1, 2, 10.0)


def test_wait_is_read_from_the_message_when_there_is_no_header():
    llm, sleeps = llm_with(status_error(429, "Please try again in 1m2.5s."), answer(), max_wait=120)
    llm.chat([])
    assert sleeps == [62.5]


def test_server_and_network_errors_retry_with_growing_waits():
    llm, sleeps = llm_with(status_error(500), openai.APIConnectionError(request=REQUEST),
                           status_error(500), answer())
    llm.chat([])
    assert sleeps == [1, 2, 4]


# --- what stops the run -------------------------------------------------------------

def test_a_request_too_large_is_never_retried():
    llm, sleeps = llm_with(status_error(413), answer())
    with pytest.raises(LLMCallError, match="top_k_per_doc"):
        llm.chat([])
    assert (llm.client.calls, sleeps) == (1, [])


def test_a_daily_limit_stops_instead_of_waiting_minutes():
    llm, sleeps = llm_with(status_error(429, "Please try again in 9m14.688s."), answer())
    with pytest.raises(LLMCallError, match="max_wait_seconds"):
        llm.chat([])
    assert sleeps == []


def test_gives_up_after_max_retries():
    llm, sleeps = llm_with(*[status_error(500)] * 4, answer(), max_retries=2)
    with pytest.raises(LLMCallError, match="3 attempts"):
        llm.chat([])
    assert len(sleeps) == 2


def test_other_client_errors_are_raised_unchanged():
    # e.g. the provider rejecting a JSON answer: the judge turns it into an "error" verdict
    llm, _ = llm_with(status_error(400, "json_validate_failed"))
    with pytest.raises(openai.BadRequestError):
        llm.chat([])


# --- usage accounting ------------------------------------------------------------------

def test_meter_reports_usage_since_the_last_take_and_totals_by_role():
    meter = UsageMeter()
    draft, _ = llm_with(answer(tokens_in=4000, tokens_out=300), meter=meter)
    draft = LLM(**{**draft.__dict__, "role": "draft"})
    judge, _ = llm_with(answer(tokens_in=3000, tokens_out=100), answer(tokens_in=3500, tokens_out=90),
                        meter=meter)

    draft.chat([])
    first = meter.take()
    judge.chat([])
    judge.chat([])
    second = meter.take()

    assert (first.calls, first.tokens_in, first.tokens_out) == (1, 4000, 300)
    assert (second.calls, second.tokens_in, second.tokens_out) == (2, 6500, 190)
    assert meter.take().calls == 0
    totals = meter.totals_by_role()
    assert (totals["draft"].calls, totals["verify"].calls) == (1, 2)


def test_the_meter_is_told_about_each_wait_before_it_starts():
    meter, notices = UsageMeter(), []
    meter.on_wait = notices.append
    llm, sleeps = llm_with(status_error(429, retry_after="7"), status_error(500), answer(), meter=meter)
    llm.chat([])
    assert [(n.role, n.seconds, n.attempt, n.reason) for n in notices] == [
        ("verify", 7.0, 1, "rate_limit"), ("verify", 2, 2, "server_error")]
    assert sleeps == [7.0, 2]
