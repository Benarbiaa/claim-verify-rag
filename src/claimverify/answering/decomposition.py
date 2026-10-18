"""
Decomposition into atomic claims — Step C
=========================================

Takes a draft answer (the text written in step B) and splits it into a list
of atomic claims, independent and verifiable one by one.

No retrieval here: it is a pure text transformation, through a second LLM
call dedicated to this single task (separate from drafting, so each step can
be tested on its own).

Each claim is labelled "topic" (about the subject, verified next) or "meta"
(about the answer or its passages, kept in the run but not verified): the LLM
decides, the code only acts on the label, so the decision stays visible.

Input: a Draft. Output: a list of Claim (see contracts.py). Every claim the
LLM returns is validated here: a malformed claim stops the run at this step,
with a clear message, instead of crashing the verification.

Usage (importing the function from another script):
    from claimverify.answering.decomposition import decompose_into_claims
    claims = decompose_into_claims(llm, draft)   # llm: see factory.build_llm

Usage (standalone, on a draft saved by drafting --save_to):
    python -m claimverify.answering.decomposition --draft_file draft.json --save_json claims.json
"""

import argparse
import json
from typing import Protocol, runtime_checkable

from pydantic import ValidationError

from claimverify.contracts import Claim, Draft
from claimverify.llm import LLM
from claimverify.settings import add_config_argument, load_settings


@runtime_checkable
class Decomposer(Protocol):
    """Interface: splits a draft into atomic claims."""

    def decompose(self, draft: Draft) -> list[Claim]: ...


class LLMDecomposer:
    """Implementation: an LLM (role "decompose" of llm.py) in JSON mode."""

    def __init__(self, llm: LLM):
        self.llm = llm

    def decompose(self, draft: Draft) -> list[Claim]:
        return decompose_into_claims(self.llm, draft)

DECOMPOSITION_SYSTEM_PROMPT = """You are a factual claim extractor. Your only task is to decompose
a text into a list of atomic claims (individual factual assertions).

IMPORTANT: Always output claims in English, regardless of the language of the input text. The
source corpus is in English, and the embedding model used for retrieval is English-optimized —
claims in another language will retrieve poorly. If the input text is not in English, translate
each extracted claim into English as you extract it.

Strict rules:
1. Each claim must be a SINGLE verifiable factual assertion — no compound sentences joined by
   "and", "but", "while", etc. If a sentence contains multiple facts, split it into multiple claims.
2. Each claim must be self-contained: resolve pronouns and references ("this method", "it") to the
   actual subject they refer to, based on the surrounding context.
3. Ignore what asserts nothing: transitions ("In summary..."), introductory phrases ("According
   to the provided passages, X" gives the claim X), or vague uncertainty with no content of its own.
4. Label each claim with its "kind":
   - "topic": an assertion about the subject of the text, including what a paper, study or
     source reports about it. "The Vectara study found fixed-size chunking best on 3 of 5
     datasets." and "RAG uses Wikipedia as its non-parametric memory." are "topic".
   - "meta": an assertion about the text itself, the passages or sources it was given, or its
     author. "The provided passages contain no information about X.", "No contradictory evidence
     was found in the passages." and "The question cannot be answered from the given sources."
     are "meta".
   Extract both kinds; when unsure, use "topic". A text that only says its sources do not cover
   the question has no "topic" claim. If the text asserts nothing at all, return an empty list.
5. If the source text cites a source in brackets (e.g. [filename.pdf | chunk #N]) for a claim,
   carry that citation into the claim's "cited_source" field. If several claims come from the same
   source sentence, they all inherit the same citation.
6. If a claim has no explicit citation in the text, set "cited_source" to null.

Respond ONLY with a valid JSON object, no text before or after, in this format:

{
  "claims": [
    {"id": "c1", "claim": "...", "cited_source": "... or null", "kind": "topic"},
    {"id": "c2", "claim": "...", "cited_source": "... or null", "kind": "meta"}
  ]
}
"""


def decompose_into_claims(llm: LLM, draft: Draft) -> list[Claim]:
    """Sends the draft to the LLM and returns the validated list of claims."""
    raw_text = llm.chat(
        [
            {"role": "system", "content": DECOMPOSITION_SYSTEM_PROMPT},
            {"role": "user", "content": f"Text to decompose:\n\n{draft.text}"},
        ],
        json_mode=True,
    )

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"The model did not return valid JSON.\nRaw answer:\n{raw_text}"
        ) from e

    # An empty list is a valid answer (a draft that only says its sources do not
    # cover the question); a missing list is not.
    claims = parsed.get("claims") if isinstance(parsed, dict) else None
    if not isinstance(claims, list):
        raise RuntimeError(f"No \"claims\" list in the answer. Raw answer:\n{raw_text}")  # noqa: TRY004 (same error as the other unusable answers)

    try:
        return [Claim.model_validate(c) for c in claims]
    except ValidationError as e:
        raise RuntimeError(
            f"The model returned a malformed claim:\n{e}\nRaw answer:\n{raw_text}"
        ) from e


def print_claims(claims: list[Claim]):
    print(f"\n{len(claims)} claims extracted:\n")
    for c in claims:
        source = c.cited_source or "(no source cited)"
        label = "" if c.kind == "topic" else " (meta: not verified)"
        print(f"  [{c.id}] {c.claim}{label}")
        print(f"        source: {source}\n")


def main():
    # Local import: factory imports this module, importing it at the top would be circular.
    from claimverify.factory import build_decomposer

    parser = argparse.ArgumentParser()
    add_config_argument(parser)
    parser.add_argument("--draft_file", type=str, required=True,
                         help="Draft as JSON (output of drafting --save_to).")
    parser.add_argument("--save_json", type=str, default=None,
                         help="Optional path to save the claims as JSON "
                              "(to use next as the input of verification.py).")
    args = parser.parse_args()

    settings = load_settings(args.config)
    decomposer = build_decomposer(settings)

    with open(args.draft_file, "r", encoding="utf-8") as f:
        draft = Draft.model_validate_json(f.read())

    print(f"Decomposing into atomic claims ({settings.answering.decomposer.model})...")
    claims = decomposer.decompose(draft)
    print_claims(claims)

    if args.save_json:
        with open(args.save_json, "w", encoding="utf-8") as f:
            json.dump({"claims": [c.model_dump() for c in claims]}, f, ensure_ascii=False, indent=2)
        print(f"Claims saved to {args.save_json}")


if __name__ == "__main__":
    main()  