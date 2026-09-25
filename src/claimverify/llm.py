"""
Configuration LLM par rôle — un modèle (et un fournisseur) différent par étape
===============================================================================

Trois rôles :
    draft      -> génération de la réponse brouillon (étape B)
    decompose  -> décomposition en claims atomiques  (étape C)
    verify     -> verdict par claim                   (étape D)

Pourquoi : un modèle qui vérifie sa propre réponse fait des erreurs corrélées
(il relit mal ce qu'il a mal lu). Le vérifieur doit donc pouvoir être un modèle
d'une autre famille, éventuellement chez un autre fournisseur ou en local.

Tous les fournisseurs visés exposent une API compatible OpenAI (Groq, Cerebras,
Mistral, OpenRouter, Ollama/vLLM en local...), donc changer de modèle = éditer
le .env, pas le code.

Résolution de chaque paramètre, du plus spécifique au plus général :
    <ROLE>_MODEL     -> défaut du rôle (DEFAULT_MODELS)
    <ROLE>_BASE_URL  -> LLM_BASE_URL  -> Groq
    <ROLE>_API_KEY   -> LLM_API_KEY   -> GROQ_API_KEY (seulement si l'URL est Groq)
(<ROLE> = DRAFT, DECOMPOSE ou VERIFY)

Il n'y a volontairement PAS de LLM_MODEL global : il écraserait le modèle du
vérifieur et remettrait silencieusement le même modèle partout. L'ancienne
variable LLM_MODEL est ignorée (avec un avertissement).

Un .env qui ne contient que GROQ_API_KEY fonctionne donc tel quel.
"""

import os
import warnings
from dataclasses import dataclass
from functools import lru_cache

from openai import OpenAI

import claimverify.config  # noqa: F401  (charge le .env)

if os.getenv("LLM_MODEL"):
    warnings.warn(
        "LLM_MODEL est ignoré depuis le passage à la config par rôle. "
        "Utiliser DRAFT_MODEL, DECOMPOSE_MODEL et VERIFY_MODEL dans .env.",
        stacklevel=2,
    )

ROLES = ("draft", "decompose", "verify")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Défauts : rédaction et décomposition sur gpt-oss-120b, vérification sur une
# autre famille de modèles (Meta Llama) pour décorréler juge et rédacteur.
# Les deux sont servis par Groq -> une seule clé API suffit.
DEFAULT_MODELS = {
    "draft": "openai/gpt-oss-120b",
    "decompose": "openai/gpt-oss-120b",
    "verify": "llama-3.3-70b-versatile",
}


def _env(role: str, key: str, fallback_to_global: bool = True) -> str | None:
    """Lit <ROLE>_<KEY>, sinon LLM_<KEY>. Les valeurs vides comptent comme absentes."""
    names = [f"{role.upper()}_{key}"] + ([f"LLM_{key}"] if fallback_to_global else [])
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


@dataclass(frozen=True)
class LLMConfig:
    role: str
    model: str
    base_url: str
    api_key: str

    def describe(self) -> str:
        """Pour les logs et les rapports — ne contient jamais la clé."""
        return f"{self.model} @ {self.base_url}"


def get_config(role: str) -> LLMConfig:
    if role not in ROLES:
        raise ValueError(f"Rôle inconnu : {role!r} (attendu : {ROLES})")

    model = _env(role, "MODEL", fallback_to_global=False) or DEFAULT_MODELS[role]
    base_url = _env(role, "BASE_URL") or GROQ_BASE_URL
    api_key = _env(role, "API_KEY")
    # GROQ_API_KEY n'est utilisée qu'avec Groq : ne jamais envoyer la clé Groq
    # à un autre fournisseur parce qu'on a oublié <ROLE>_API_KEY.
    if not api_key and base_url == GROQ_BASE_URL:
        api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            f"Aucune clé API pour le rôle '{role}'. Définir {role.upper()}_API_KEY, "
            f"LLM_API_KEY ou GROQ_API_KEY dans .env (pour un serveur local type "
            f"Ollama, n'importe quelle valeur non vide convient)."
        )
    return LLMConfig(role=role, model=model, base_url=base_url, api_key=api_key)


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


def get_llm(role: str) -> LLM:
    cfg = get_config(role)
    return make_llm(cfg.role, cfg.model, cfg.base_url, cfg.api_key)
