"""End-to-end scoring: the checks of each category, read from recorded events (no LLM)."""

from claimverify.contracts import Claim, Draft, Passage, Verdict
from claimverify.e2e_eval import near_duplicates, read_question, report, review_sheet, score_question
from claimverify.evaluation import GoldQuestion
from claimverify.events import (
    ClaimsExtracted,
    ClaimVerified,
    DraftWritten,
    QuestionFinished,
    QuestionStarted,
    Usage,
)

PRO = "LumberChunker consistently outperforms every other baseline"
CON = "costs associated with semantic chunking are not justified by consistent performance gains"
L, V = "lumber.pdf", "vectara.pdf"


def passage(filename, text, i=0) -> Passage:
    return Passage(filename=filename, source_type="pdf", chunk_index=i, text=text, score=1.0)


def verdict(label, pro=(), con=(), evidence=(), claim="A claim about chunking.") -> Verdict:
    return Verdict(claim_id="c1", claim=claim, verdict=label, justification="because",
                   supporting_sources=list(pro), contradicting_sources=list(con),
                   verifier="fake", evidence=list(evidence))


def events(verdicts, claims=None, index=1, finished=True):
    common = {"run_id": "r", "pipeline": "answering", "question_index": index}
    draft = Draft(question="q?", text="An answer.", passages=[passage(L, "Intro. " + PRO)])
    claims = claims or [Claim(id=f"c{i}", claim=v.claim) for i, v in enumerate(verdicts)]
    out = [QuestionStarted(question="q?", **common),
           DraftWritten(draft=draft, seconds=1, usage=Usage(calls=1, tokens_in=100), **common),
           ClaimsExtracted(claims=claims, seconds=1, **common)]
    out += [ClaimVerified(position=i, total=len(verdicts), verdict=v, usage=Usage(calls=1, tokens_in=10), **common)
            for i, v in enumerate(verdicts, 1)]
    if finished:
        out.append(QuestionFinished(verdict_counts={}, seconds=5, **common))
    return out


def conflict_question() -> GoldQuestion:
    return GoldQuestion(id="q05", category="conflict", question="Does semantic chunking help?",
                        statement="Content-based chunking consistently improves retrieval.",
                        evidence=[{"filename": L, "stance": "supports", "quote": PRO},
                                  {"filename": V, "stance": "contradicts", "quote": CON}])


def test_a_question_is_read_from_its_own_events_and_only_once_finished():
    mixed = events([verdict("supported", [L])], index=1) + events([verdict("contested", [L], [V])] * 2, index=2)
    run = read_question(mixed, 2)
    assert len(run.verdicts) == 2 and run.usage.tokens_in == 120 and run.seconds == 5
    assert read_question(events([verdict("supported", [L])], finished=False), 1) is None


def test_a_conflict_is_found_whichever_way_the_claim_is_phrased():
    q = conflict_question()
    for pro, con in (([L], [V]), ([V], [L])):
        s = score_question(q, read_question(events([verdict("contested", pro, con)]), 1))
        assert s.passed, s.checks
    one_side = score_question(q, read_question(events([verdict("supported", [L, V])]), 1))
    assert one_side.checks == {"sources used": True, "conflict found": False}


def test_a_false_conflict_and_a_missing_source_fail_a_single_source_question():
    q = GoldQuestion(id="q01", category="single_source", question="How does LumberChunker work?",
                     evidence=[{"filename": L, "stance": "supports", "quote": PRO}])
    assert score_question(q, read_question(events([verdict("supported", [L])]), 1)).passed
    s = score_question(q, read_question(events([verdict("contested", [V], [V, "x.pdf"])]), 1))
    assert s.checks == {"sources used": False, "no false conflict": False, "no contradiction": True}


def test_a_false_premise_is_caught_when_contradicted_or_when_its_correction_is_supported_by_the_proof():
    q = GoldQuestion(id="q07", category="false_premise", question="Why does semantic chunking always pay off?",
                     statement="Semantic chunking always pays off.",
                     evidence=[{"filename": V, "stance": "contradicts", "quote": CON}])
    caught = verdict("contradicted", con=[V])
    corrected = verdict("supported", pro=[V], evidence=[passage(V, "Results. The " + CON + ".")])
    unrelated = verdict("supported", pro=[V], evidence=[passage(V, "Another passage.")])
    for v, ok in ((caught, True), (corrected, True), (unrelated, False)):
        assert score_question(q, read_question(events([v]), 1)).checks["premise caught"] is ok


def test_an_out_of_corpus_question_passes_only_if_nothing_is_supported():
    q = GoldQuestion(id="q09", category="out_of_corpus", question="How does RAPTOR build its tree?")
    assert score_question(q, read_question(events([verdict("unverifiable")]), 1)).passed
    assert not score_question(q, read_question(events([verdict("supported", [L])]), 1)).passed


def test_proofs_are_counted_in_the_drafters_and_the_judges_passages():
    v = verdict("contested", [L], [V], evidence=[passage(V, CON)])
    s = score_question(conflict_question(), read_question(events([v]), 1))
    assert (s.proofs_drafted, s.proofs_read) == (1, 1)


def test_near_identical_claims_are_counted_as_pairs():
    claims = [Claim(id="a", claim="Chunking strongly affects retrieval quality."),
              Claim(id="b", claim="Chunking strongly affects the retrieval quality."),
              Claim(id="c", claim="RAG uses BART as its generator.")]
    assert near_duplicates(claims) == 1


def test_meta_claims_are_counted_and_listed_for_review_but_have_no_verdict():
    claims = [Claim(id="c0", claim="A claim about chunking."),
              Claim(id="c1", claim="The passages do not mention RAPTOR.", kind="meta")]
    q = GoldQuestion(id="q09", category="out_of_corpus", question="How does RAPTOR build its tree?")
    s = score_question(q, read_question(events([verdict("unverifiable")], claims=claims), 1))
    assert s.passed
    assert "| q09 | out_of_corpus | ✓ pass | – | – | 1 + 1 | 1 unverifiable |" in report([s], [q], "Judge `fake`")
    assert "of which 1 about the answer itself" in report([s], [q], "Judge `fake`")
    assert "- The passages do not mention RAPTOR." in review_sheet([s])


def test_the_report_and_the_review_sheet_list_every_scored_question():
    q = conflict_question()
    s = score_question(q, read_question(events([verdict("contested", [L], [V])]), 1))
    other = GoldQuestion(id="q09", category="out_of_corpus", question="How does RAPTOR build its tree?")
    text = report([s], [q, other], "Judge `fake`")
    assert "**Questions passed: 1/1.**" in text and "Not run yet: q09." in text
    assert "| q05 | conflict | ✓ pass |" in text
    assert "## q05 (conflict)" in review_sheet([s])
