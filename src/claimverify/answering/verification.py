"""
Claim verification — Step D (the heart of the project)
======================================================

For each atomic claim (the output of step C):
    1. TARGETED, PER-DOCUMENT retrieval (the claim's cited_source is not
       reused: where the draft claimed it came from is deliberately ignored,
       and the WHOLE corpus is searched independently).
    2. A judge (by default an LLM from ANOTHER family than the one that wrote
       the draft: answering.verifier.judge in config.yaml) gives a verdict,
       with a justification and its sources.

The Verifier receives its Retriever and its Judge (see the Interfaces
section); the current implementation loops with LangGraph: retrieve -> judge
-> next claim, until there are none left.

Usage:
    # 1) Split an answer into claims (step C) and save them as JSON:
    python -m claimverify.answering.decomposition --draft_file draft.json --save_json claims.json

    # 2) Verify these claims (--db_url is optional when DB_URL is in .env, see config.py):
    python -m claimverify.answering.verification --claims_file claims.json
"""

import argparse
import json
from collections.abc import Iterator
from typing import Protocol, TypedDict, runtime_checkable

import psycopg2
from langgraph.graph import END, StateGraph
from openai import BadRequestError

from claimverify.answering.retrieval import Retriever, format_evidence
from claimverify.config import add_db_url_argument
from claimverify.contracts import JUDGE_LABELS, VERDICT_ICONS, VERDICT_LABELS, Claim, Passage, Verdict
from claimverify.llm import LLM
from claimverify.settings import add_config_argument, load_settings

VERDICT_SYSTEM_PROMPT = """You are a rigorous claim verifier (fact-checker). You are given a claim
and a set of source passages, potentially from MULTIPLE different documents. Judge the claim using
ONLY these passages: a claim you believe is true but that no passage addresses is "unverifiable".

IMPORTANT: Always respond in English, matching the language of the claim and evidence.

Verdict definitions (pick exactly one):
- "supported": at least one source clearly states or strongly implies the claim, and no source
  states something incompatible with it.
- "contradicted": the sources state something incompatible with the claim (a different number,
  name, date, direction of effect...), and no source supports it.
- "contested": the sources disagree with EACH OTHER on this claim: at least one supports it and at
  least one states something incompatible with it. Name the documents on each side.
- "unverifiable": no passage addresses the claim's subject, for or against. Absence of evidence
  is not contradiction.

A source that discusses a different technique, dataset or setting does NOT contradict the claim:
contradiction requires incompatible statements about the same thing. For example, a paper that
proposes a complementary method is not evidence against another paper's result.

The source lists must match the verdict: "contradicted" needs at least one contradicting source,
"contested" needs at least one source on each side.

Respond ONLY with a valid JSON object, no text before or after, in this format:

{
  "verdict": "supported" | "contradicted" | "contested" | "unverifiable",
  "justification": "concise explanation, citing source documents by filename",
  "supporting_sources": ["filename.pdf", ...],
  "contradicting_sources": ["filename.pdf", ...]
}
"""


def debug_single_claim(claim_text: str, retriever: Retriever):
    """Prints in detail (full text + scores) the chunks retrieved for ONE
    claim, with no LLM call. Used to diagnose whether an "unverifiable"
    verdict comes from retrieval (the right chunk was not retrieved) or from
    the LLM's judgment (the chunk was there but misjudged)."""
    passages = retriever.retrieve(claim_text)

    print("=" * 100)
    print(f"CLAIM: {claim_text}")
    print("=" * 100)
    for p in passages:
        print(f"\n[score={p.score:.4f}] {p.filename} (#{p.chunk_index}, {p.source_type})")
        print(f"{'-' * 80}")
        print(p.text)
    print("\n" + "=" * 100)
    print(f"Total: {len(passages)} chunks from {len({p.filename for p in passages})} document(s)")


# ---------------------------------------------------------------------------
# Judging a claim with an LLM
# ---------------------------------------------------------------------------

def judge_with_llm(llm: LLM, claim: Claim, passages: list[Passage]) -> Verdict:
    """Asks the LLM for a verdict on a claim, given the passages.

    An unusable answer gives the verdict "error" (never "unverifiable", which
    is a conclusion about the sources): invalid or truncated JSON, unknown
    verdict, missing field, sources inconsistent with the verdict, or JSON
    rejected by the provider itself. The raw answer is kept.
    """
    user_message = f"""Claim to verify:
"{claim.claim}"

Source passages (from multiple documents, evaluated independently of the source originally
cited by the claim):

{format_evidence(passages)}
"""
    identity = {
        "claim_id": claim.id,
        "claim": claim.claim,
        "original_cited_source": claim.cited_source,
        "verifier": f"llm_judge:{llm.model}",
        "evidence": passages,
    }
    raw_text = ""
    try:
        raw_text = llm.chat(
            [
                {"role": "system", "content": VERDICT_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            json_mode=True,
        ) or ""
        data = json.loads(raw_text)
        if not isinstance(data, dict) or data.get("verdict") not in JUDGE_LABELS:
            raise ValueError(f"verdict missing or not one of the judge's {len(JUDGE_LABELS)} verdicts")
        return Verdict(**identity, **data)
    except BadRequestError as e:
        # In JSON mode, Groq can itself reject an answer that is not valid JSON
        # (often truncated). Other 400 errors remain errors.
        if "json_validate_failed" not in str(e):
            raise
        reason, raw_text = "JSON rejected by the provider", str(e)
    except (json.JSONDecodeError, TypeError, ValueError) as e:  # ValidationError inherits from it
        reason = f"{type(e).__name__}: {str(e).splitlines()[0]}"
    return Verdict(
        **identity,
        verdict="error",
        justification=f"Unusable judge answer ({reason}). Raw answer: {raw_text[:300]}",
    )


# ---------------------------------------------------------------------------
# The Judge and Verifier interfaces, and their implementations
# ---------------------------------------------------------------------------
# The Verifier does "for each claim: find passages, then judge". It RECEIVES a
# Retriever and a Judge: either one, or the whole Verifier, can be replaced.
# The graph's state holds only data.

@runtime_checkable
class Judge(Protocol):
    """Interface: gives a verdict on a claim, given passages."""

    def judge(self, claim: Claim, passages: list[Passage]) -> Verdict: ...


class LLMJudge:
    """Implementation: an LLM (role "verify" of llm.py) with VERDICT_SYSTEM_PROMPT."""

    def __init__(self, llm: LLM):
        self.llm = llm

    def judge(self, claim: Claim, passages: list[Passage]) -> Verdict:
        return judge_with_llm(self.llm, claim, passages)


@runtime_checkable
class Verifier(Protocol):
    """Interface: gives a verdict for each claim."""

    def verify(self, claims: list[Claim]) -> Iterator[Verdict]:
        """Yields the verdicts one by one, as soon as each is ready (same order as the claims)."""
        ...


class VerifierState(TypedDict):
    claims: list[Claim]
    current_index: int
    passages: list[Passage]      # passages of the current claim
    verdicts: list[Verdict]


def should_continue(state: VerifierState) -> str:
    return "retrieve" if state["current_index"] < len(state["claims"]) else "end"


class LangGraphVerifier:
    """Implementation: a LangGraph loop retrieve -> judge over the claims."""

    def __init__(self, retriever: Retriever, judge: Judge):
        self.retriever = retriever
        self.judge = judge
        self.graph = self._build_graph()

    def _build_graph(self):
        def retrieve(state: VerifierState) -> dict:
            claim = state["claims"][state["current_index"]]
            return {"passages": self.retriever.retrieve(claim.claim)}

        def judge(state: VerifierState) -> dict:
            claim = state["claims"][state["current_index"]]
            verdict = self.judge.judge(claim, state["passages"])
            return {"verdicts": state["verdicts"] + [verdict],
                    "current_index": state["current_index"] + 1}

        graph = StateGraph(VerifierState)
        graph.add_node("retrieve", retrieve)
        graph.add_node("judge", judge)
        graph.set_entry_point("retrieve")
        graph.add_edge("retrieve", "judge")
        graph.add_conditional_edges("judge", should_continue, {"retrieve": "retrieve", "end": END})
        return graph.compile()

    def verify(self, claims: list[Claim]) -> Iterator[Verdict]:
        if not claims:
            return
        initial: VerifierState = {"claims": claims, "current_index": 0,
                                  "passages": [], "verdicts": []}
        # 2 steps per claim (retrieve + judge): LangGraph's default limit (25
        # steps) would crash an answer with more than 12 claims.
        config = {"recursion_limit": 2 * len(claims) + 5}
        # stream() yields each node's output as soon as it finishes: after each
        # pass through "judge", the last verdict added is ready.
        for update in self.graph.stream(initial, config, stream_mode="updates"):
            if "judge" in update:
                yield update["judge"]["verdicts"][-1]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def read_claims_file(path: str) -> list[Claim]:
    """Reads the claims of a JSON file: the output of decomposition.py
    ({"claims": [...]}) or a plain list of claims."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw = data["claims"] if isinstance(data, dict) else data
    return [Claim.model_validate(c) for c in raw]


def print_summary(verdicts: list[Verdict]):
    counts = dict.fromkeys(VERDICT_LABELS, 0)
    for v in verdicts:
        counts[v.verdict] += 1

    print("\n" + "=" * 100)
    print("VERIFICATION SUMMARY")
    print("=" * 100)
    detail = ", ".join(f"{n} {label}" for label, n in counts.items() if n)
    print(f"Total: {len(verdicts)} claims — {detail}\n")

    for v in verdicts:
        print(f"[{VERDICT_ICONS[v.verdict]}] {v.claim_id} — {v.verdict.upper()}")
        print(f"    Claim: {v.claim}")
        print(f"    Justification: {v.justification}")
        if v.contradicting_sources:
            print(f"    Contradicting sources: {v.contradicting_sources}")
        print()


def main():
    # Local import: factory imports this module, importing it at the top would be circular.
    from claimverify.factory import build_embedder, build_retriever, build_verifier

    parser = argparse.ArgumentParser()
    parser.add_argument("--claims_file", type=str, default=None,
                         help="JSON file holding the claims (output of decomposition.py).")
    add_db_url_argument(parser)
    add_config_argument(parser)
    parser.add_argument("--save_json", type=str, default=None,
                         help="Optional path to save the verdicts as JSON.")
    parser.add_argument("--debug_claim", type=str, default=None,
                         help="Debug mode: prints the raw chunks retrieved for THIS claim text "
                              "(no LLM call), instead of running the full verification.")
    args = parser.parse_args()

    settings = load_settings(args.config)
    conn = psycopg2.connect(args.db_url)

    if args.debug_claim:
        retriever = build_retriever(settings.answering.verifier.retriever, build_embedder(settings),
                                    conn, "answering.verifier.retriever")
        debug_single_claim(args.debug_claim, retriever)
        conn.close()
        return

    if not args.claims_file:
        raise RuntimeError("--claims_file is required outside --debug_claim mode.")

    claims = read_claims_file(args.claims_file)

    verifier = build_verifier(settings, build_embedder(settings), conn)
    print(f"\nVerifying {len(claims)} claims ({settings.answering.verifier.judge.model})...\n")
    verdicts = list(verifier.verify(claims))
    conn.close()

    print_summary(verdicts)

    if args.save_json:
        with open(args.save_json, "w", encoding="utf-8") as f:
            json.dump([v.model_dump() for v in verdicts], f, ensure_ascii=False, indent=2)
        print(f"Verdicts saved to {args.save_json}")


if __name__ == "__main__":
    main()