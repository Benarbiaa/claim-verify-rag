"""
Client LLM — un modèle prêt à l'emploi, derrière une API compatible OpenAI
============================================================================

Tous les fournisseurs visés exposent une API compatible OpenAI (Groq, Gemini,
Cerebras, Mistral, OpenRouter, Ollama/vLLM en local...) : un LLM, c'est donc
un nom de modèle + l'URL du fournisseur + une clé.

QUEL modèle et QUEL fournisseur chaque étape utilise se choisit dans
config.yaml ; la clé API se met dans .env. C'est factory.build_llm qui
assemble les trois et appelle make_llm.

Nouvelles tentatives : faites ici (celles du SDK sont désactivées), pour les
voir et les compter, et pour traiter à part les erreurs qu'il est inutile de
retenter :
    429 limite par minute, 5xx, délai, réseau  -> attendre puis réessayer
    429 dont l'attente dépasse max_wait_seconds (ex. limite par jour) -> LLMCallError
    413 requête plus grosse que la limite par minute -> LLMCallError (jamais retentée)
    autres 4xx (ex. 400 JSON rejeté)           -> remontées telles quelles
Chaque appel est enregistré dans un UsageMeter (tokens, tentatives, attente).
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache

import openai
from openai import OpenAI

from claimverify.events import Usage


class LLMCallError(RuntimeError):
    """Un appel qu'il est inutile (ou impossible) de retenter : le run s'arrête."""


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 6          # nouvelles tentatives après le premier échec
    max_wait_seconds: float = 60  # une attente plus longue arrête le run
    timeout_seconds: float = 120  # durée maximale d'une requête


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
    """Une attente sur le point de commencer, avant une nouvelle tentative."""
    role: str
    model: str
    seconds: float
    attempt: int   # la tentative qui vient d'échouer (1 = le premier appel)
    reason: str    # "rate_limit", "server_error" ou "connection"


class UsageMeter:
    """Enregistre chaque appel ; partagé par tous les LLM d'un pipeline (voir factory).

    on_wait, si défini, est prévenu avant chaque attente : une attente de 30 s
    due à une limite par minute se voit pendant l'étape, pas seulement après.
    """

    def __init__(self):
        self.records: list[CallRecord] = []
        self._cursor = 0
        self.on_wait: Callable[[WaitNotice], None] | None = None

    def record(self, call: CallRecord) -> None:
        self.records.append(call)

    def take(self) -> Usage:
        """Usage depuis le dernier take() : l'orchestrateur l'appelle après chaque étape."""
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
    """Attente demandée par le fournisseur : en-tête retry-after, sinon "try again in 9m14.6s"."""
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


@lru_cache(maxsize=None)
def _client(base_url: str, api_key: str, timeout: float) -> OpenAI:
    # Un client par (fournisseur, clé) : si deux rôles partagent le même
    # fournisseur, ils partagent le même client. max_retries=0 : c'est LLM.chat
    # qui gère les nouvelles tentatives.
    return OpenAI(api_key=api_key, base_url=base_url, max_retries=0, timeout=timeout)


@dataclass(frozen=True)
class LLM:
    """Un modèle prêt à l'emploi pour un rôle donné."""
    role: str
    model: str
    base_url: str
    client: OpenAI
    retry: RetryPolicy = RetryPolicy()
    meter: UsageMeter = field(default_factory=UsageMeter)
    sleep: Callable[[float], None] = time.sleep  # remplaçable dans les tests

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
                        f"{self.role} ({self.model}) : requête plus grosse que la limite du "
                        f"fournisseur par minute. Réduire top_k_per_doc dans la config."
                    ) from e
                if e.status_code != 429 and e.status_code < 500:
                    raise  # ex. 400 : pas une erreur temporaire
                wait = _retry_after(e)
                error, reason = e, "rate_limit" if e.status_code == 429 else "server_error"
            except openai.APIConnectionError as e:  # inclut les délais dépassés
                wait, error, reason = None, e, "connection"
            if wait is None:
                wait = min(2 ** (attempts - 1), self.retry.max_wait_seconds)
            if attempts > self.retry.max_retries:
                raise LLMCallError(
                    f"{self.role} ({self.model}) : échec après {attempts} tentatives ({error})"
                ) from error
            if wait > self.retry.max_wait_seconds:
                raise LLMCallError(
                    f"{self.role} ({self.model}) : le fournisseur demande d'attendre {wait:.0f}s "
                    f"(> max_wait_seconds={self.retry.max_wait_seconds:.0f}), probablement une "
                    f"limite par jour. Réessayer plus tard ou changer de fournisseur."
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
    """Construit un LLM à partir de valeurs déjà résolues (utilisé par la factory)."""
    retry = retry or RetryPolicy()
    return LLM(role=role, model=model, base_url=base_url,
               client=_client(base_url, api_key, retry.timeout_seconds),
               retry=retry, meter=meter if meter is not None else UsageMeter())
