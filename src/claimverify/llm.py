"""
LLM client — a ready-to-use model, behind an OpenAI-compatible API
==================================================================

Every targeted provider exposes an OpenAI-compatible API (Groq, Gemini,
Cerebras, Mistral, OpenRouter, Ollama/vLLM locally...): an LLM is therefore a
model name + the provider's URL + a key.

WHICH model and WHICH provider each stage uses is chosen in config.yaml; the
API key goes in .env. factory.build_llm puts the three together and calls
make_llm.

Retries: done here (the SDK's are disabled), to see and count them, and to
handle separately the errors that are pointless to retry:
    429 per-minute limit, 5xx, timeout, network -> wait, then retry
    429 whose wait exceeds max_wait_seconds (e.g. daily limit) -> LLMCallError
    413 request larger than the per-minute limit -> LLMCallError (never retried)
    other 4xx (e.g. 400 JSON rejected)          -> raised unchanged
Every call is recorded in a UsageMeter (tokens, attempts, waiting).
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache

import openai
from openai import OpenAI

from claimverify.events import Usage


class LLMCallError(RuntimeError):
    """A call that is pointless (or impossible) to retry: the run stops."""


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 6          # new attempts after the first failure
    max_wait_seconds: float = 60  # a longer wait stops the run
    timeout_seconds: float = 120  # maximum duration of one request


@dataclass(frozen=True)
class CallRecord:
    role: str
    tokens_in: int
    tokens_out: int
    attempts: int
    waited_seconds: float
    seconds: float


@dataclass(frozen=True)
class WaitNotice:
    """A wait about to start, before a new attempt."""
    role: str
    model: str
    seconds: float
    attempt: int   # the attempt that just failed (1 = the first call)
    reason: str    # "rate_limit", "server_error" or "connection"


class UsageMeter:
    """Records every call; shared by all the LLMs of a pipeline (see factory).

    on_wait, when set, is told before each wait: a 30 s wait caused by a
    per-minute limit shows during the stage, not only afterwards.
    """

    def __init__(self):
        self.records: list[CallRecord] = []
        self._cursor = 0
        self.on_wait: Callable[[WaitNotice], None] | None = None

    def record(self, call: CallRecord) -> None:
        self.records.append(call)

    def take(self) -> Usage:
        """Usage since the last take(): the orchestrator calls it after each stage."""
        new, self._cursor = self.records[self._cursor:], len(self.records)
        return _sum(new)

    def totals_by_role(self) -> dict[str, Usage]:
        roles = dict.fromkeys(r.role for r in self.records)
        return {role: _sum([r for r in self.records if r.role == role]) for role in roles}


def _sum(records: list[CallRecord]) -> Usage:
    return Usage(
        calls=len(records),
        tokens_in=sum(r.tokens_in for r in records),
        tokens_out=sum(r.tokens_out for r in records),
        retries=sum(r.attempts - 1 for r in records),
        waited_seconds=round(sum(r.waited_seconds for r in records), 2),
        seconds=round(sum(r.seconds for r in records), 2),
    )


def _retry_after(error: openai.APIStatusError) -> float | None:
    """The wait the provider asks for: the retry-after header, else "try again in 9m14.6s"."""
    header = error.response.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    match = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", str(error))
    if match:
        return int(match.group(1) or 0) * 60 + float(match.group(2))
    return None


@cache
def _client(base_url: str, api_key: str, timeout: float) -> OpenAI:
    # One client per (provider, key): two roles sharing a provider share a
    # client. max_retries=0: LLM.chat handles the retries.
    return OpenAI(api_key=api_key, base_url=base_url, max_retries=0, timeout=timeout)


@dataclass(frozen=True)
class LLM:
    """A ready-to-use model for a given role."""
    role: str
    model: str
    base_url: str
    client: OpenAI
    retry: RetryPolicy = RetryPolicy()
    meter: UsageMeter = field(default_factory=UsageMeter)
    sleep: Callable[[float], None] = time.sleep  # replaceable in tests

    def chat(self, messages: list[dict], json_mode: bool = False) -> str:
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        start, attempts, waited = time.perf_counter(), 0, 0.0
        while True:
            attempts += 1
            try:
                response = self.client.chat.completions.create(
                    model=self.model, messages=messages, **kwargs
                )
                break
            except openai.APIStatusError as e:
                if e.status_code == 413:
                    raise LLMCallError(
                        f"{self.role} ({self.model}): request larger than the provider's "
                        f"per-minute limit. Lower top_k_per_doc in the config."
                    ) from e
                if e.status_code != 429 and e.status_code < 500:
                    raise  # e.g. 400: not a temporary error
                wait = _retry_after(e)
                error, reason = e, "rate_limit" if e.status_code == 429 else "server_error"
            except openai.APIConnectionError as e:  # includes timeouts
                wait, error, reason = None, e, "connection"
            if wait is None:
                wait = min(2 ** (attempts - 1), self.retry.max_wait_seconds)
            if attempts > self.retry.max_retries:
                raise LLMCallError(
                    f"{self.role} ({self.model}): failed after {attempts} attempts ({error})"
                ) from error
            if wait > self.retry.max_wait_seconds:
                raise LLMCallError(
                    f"{self.role} ({self.model}): the provider asks to wait {wait:.0f}s "
                    f"(> max_wait_seconds={self.retry.max_wait_seconds:.0f}), probably a "
                    f"daily limit. Try again later or switch provider."
                ) from error
            if self.meter.on_wait:
                self.meter.on_wait(WaitNotice(self.role, self.model, wait, attempts, reason))
            self.sleep(wait)
            waited += wait

        usage = getattr(response, "usage", None)  # absent chez certains serveurs locaux
        self.meter.record(CallRecord(
            role=self.role,
            tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
            tokens_out=getattr(usage, "completion_tokens", 0) or 0,
            attempts=attempts,
            waited_seconds=waited,
            seconds=time.perf_counter() - start,
        ))
        return response.choices[0].message.content

    def describe(self) -> str:
        return f"{self.model} @ {self.base_url}"


def make_llm(role: str, model: str, base_url: str, api_key: str,
             retry: RetryPolicy | None = None, meter: UsageMeter | None = None) -> LLM:
    """Builds an LLM from already-resolved values (used by the factory)."""
    retry = retry or RetryPolicy()
    return LLM(role=role, model=model, base_url=base_url,
               client=_client(base_url, api_key, retry.timeout_seconds),
               retry=retry, meter=meter if meter is not None else UsageMeter())
