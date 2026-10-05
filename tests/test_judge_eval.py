"""Judge evaluation: verdicts against the gold set, and why a wrong verdict is wrong. No LLM."""

from claimverify.contracts import Passage, Verdict
from claimverify.evaluation import GoldClaim
from claimverify.judge_eval import cause, proof_seen, report, score, sources_ok

QUOTE = "The threshold of 1000 tokens performs the worst."


def gold(expected="contradicted", category="perturbed_fact", gid="g01"):
    evidence = [] if expected == "unverifiable" else [
        {"filename": "a.pdf", "stance": "contradicts" if expected == "contradicted" else "supports", "quote": QUOTE}]
    return GoldClaim.model_validate({"id": gid, "category": category, "claim": "1000 tokens is the best.",
                                     "expected": expected, "evidence": evidence})


def verdict(label, read=QUOTE, pro=(), con=(), gid="g01"):
    passage = Passage(filename="a.pdf", source_type="peer_reviewed_paper", chunk_index=0,
                      text=f"Some context. {read} More.", score=0.8)
    return Verdict(claim_id=gid, claim="1000 tokens is the best.", verdict=label, justification="because",
                   supporting_sources=list(pro), contradicting_sources=list(con), verifier="fake",
                   evidence=[passage])


def test_the_proof_counts_as_read_only_if_its_quote_is_in_a_passage():
    assert proof_seen(gold(), verdict("contradicted", con=["a.pdf"])) is True
    assert proof_seen(gold(), verdict("unverifiable", read="Something else entirely.")) is False
    assert proof_seen(gold("unverifiable", "out_of_corpus"), verdict("unverifiable")) is None


def test_the_judge_must_cite_the_gold_sources_on_the_right_side():
    assert sources_ok(gold(), verdict("contradicted", con=["a.pdf"]))
    assert not sources_ok(gold(), verdict("contradicted", con=["b.pdf"]))
    assert sources_ok(gold("unverifiable", "out_of_corpus"), verdict("unverifiable"))
    assert not sources_ok(gold("unverifiable", "out_of_corpus"), verdict("supported", pro=["a.pdf"]))


def test_a_wrong_verdict_is_blamed_on_retrieval_only_when_the_proof_was_not_read():
    [missed] = score([gold()], {"g01": verdict("unverifiable", read="Unrelated text here.")})
    [misjudged] = score([gold()], {"g01": verdict("supported", pro=["a.pdf"])})
    [broken] = score([gold()], {"g01": verdict("error")})
    assert (cause(missed), cause(misjudged), cause(broken)) == (
        "retrieval: proof not read", "judge", "judge answer unusable")


def test_a_stopped_run_is_scored_on_the_claims_that_have_a_verdict():
    golds = [gold(gid="g01"), gold(gid="g02")]
    assert [s.gold.id for s in score(golds, {"g02": verdict("contradicted", con=["a.pdf"], gid="g02")})] == ["g02"]


def test_the_report_counts_false_contradictions_on_complementary_claims():
    golds = [gold("supported", "complementary", "g07"), gold(gid="g03")]
    verdicts = {"g07": verdict("contradicted", con=["a.pdf"], gid="g07"),
                "g03": verdict("contradicted", con=["a.pdf"], gid="g03")}
    text = report(score(golds, verdicts), "fake-judge", "")
    assert "**Correct verdicts: 1/2.**" in text
    assert "False contradictions on complementary claims: 1/1." in text
    assert "| supported | · | 1 |" in text  # confusion row: expected supported, judged contradicted
