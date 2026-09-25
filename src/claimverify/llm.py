"""
Client LLM — un modèle prêt à l'emploi, derrière une API compatible OpenAI
============================================================================

Tous les fournisseurs visés exposent une API compatible OpenAI (Groq, Gemini,
Cerebras, Mistral, OpenRouter, Ollama/vLLM en local...) : un LLM, c'est donc
un nom de modèle + l'URL du fournisseur + une clé.

QUEL modèle et QUEL fournisseur chaque étape utilise se choisit dans
config.yaml ; la clé API se met dans .env. C'est factory.build_llm qui
assemble les trois et appelle make_llm.
"""

from dataclasses import dataclass
from functools import lru_cache

from openai import OpenAI


@lru_cache(maxsize=None)
def _client(base_url: str, api_key: str) -> OpenAI:
    # Un client par (fournisseur, clé) : si deux rôles partagent le même
    # fournisseur, ils partagent le même client.
    return OpenAI(api_key=api_key, base_url=base_url)


@dataclass(frozen=True)
class LLM:
    """Un modèle prêt à l'emploi pour un rôle donné."""
    role: str
    model: str
    base_url: str
    client: OpenAI

    def chat(self, messages: list[dict], json_mode: bool = False) -> str:
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        response = self.client.chat.completions.create(
            model=self.model, messages=messages, **kwargs
        )
        return response.choices[0].message.content

    def describe(self) -> str:
        return f"{self.model} @ {self.base_url}"


def make_llm(role: str, model: str, base_url: str, api_key: str) -> LLM:
    """Construit un LLM à partir de valeurs déjà résolues (utilisé par la factory)."""
    return LLM(role=role, model=model, base_url=base_url, client=_client(base_url, api_key))
