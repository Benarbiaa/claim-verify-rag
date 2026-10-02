"""Stage interfaces: each implementation satisfies its Protocol and does its job.

Fakes everywhere: no network, no model download, no database.
"""

import json

import pytest

from claimverify.answering.decomposition import Decomposer, LLMDecomposer
from claimverify.answering.drafting import Drafter, LLMDrafter
from claimverify.answering.retrieval import PgvectorRetriever, Retriever
from claimverify.answering.verification import Judge, LangGraphVerifier, LLMJudge, Verifier
from claimverify.components.embedding import BgeEmbedder, Embedder
from claimverify.contracts import Claim, Document, Draft, Passage, Verdict
from claimverify.indexing.chunking import Chunker, FixedSizeChunker
from claimverify.indexing.loading import FileLoader, Loader
from fakes import WordTokenizer, fake_llm

PASSAGE = Passage(filename="a.pdf", source_type="peer_reviewed_paper", chunk_index=0,
                  text="Evidence.", score=0.9)
VERDICT_JSON = json.dumps({"verdict": "supported", "justification": "a.pdf says so"})


# --- fakes for the stages themselves ------------------------------------------

class FakeEmbedder:
    def embed_texts(self, texts):
        return [[0.0, 1.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0]


class FakeRetriever:
    def __init__(self):
        self.queries = []

    def retrieve(self, query):
        self.queries.append(query)
        return [PASSAGE]


class FakeJudge:
    def __init__(self):
        self.seen = []

    def judge(self, claim, passages):
        self.seen.append((claim.id, passages))
        return Verdict(claim_id=claim.id, claim=claim.claim, verdict="supported",
                       justification="fake", verifier="fake")


class FakeConnection:
    """Answers the two queries of search_per_document and records their parameters."""

    def __init__(self):
        self.params = []

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.params.append(params)
        self._rows = ([("a.pdf",)] if "DISTINCT" in sql
                      else [("a.pdf", "peer_reviewed_paper", 0, "Evidence.", 0.9)])

    def fetchall(self):
        return self._rows


def claims(n):
    return [Claim(id=f"c{i}", claim=f"claim {i}") for i in range(1, n + 1)]


# --- every implementation satisfies its interface -------------------------------

def test_implementations_satisfy_their_interfaces():
    assert isinstance(FileLoader(), Loader)
    assert isinstance(FixedSizeChunker(WordTokenizer()), Chunker)
    assert isinstance(BgeEmbedder(), Embedder)  # lazy: no model is loaded here
    assert isinstance(PgvectorRetriever(FakeEmbedder(), conn=None), Retriever)
    assert isinstance(LLMDrafter(fake_llm("x")), Drafter)
    assert isinstance(LLMDecomposer(fake_llm("x")), Decomposer)
    assert isinstance(LLMJudge(fake_llm("x")), Judge)
    assert isinstance(LangGraphVerifier(FakeRetriever(), FakeJudge()), Verifier)


def test_an_object_without_the_method_is_not_a_stage():
    class NotAJudge:
        def evaluate(self, claim, passages): ...

    assert not isinstance(NotAJudge(), Judge)


# --- each implementation does its job --------------------------------------------

def test_file_loader_reads_markdown(tmp_path):
    (tmp_path / "post.md").write_text("Some text.", encoding="utf-8")
    [doc] = FileLoader().load(tmp_path)
    assert (doc.filename, doc.source_type, doc.text) == ("post.md", "blog_post", "Some text.")


def test_fixed_size_chunker_uses_its_settings():
    doc = Document(doc_id="d", filename="a.pdf", source_type="peer_reviewed_paper",
                   text=" ".join(f"w{i}" for i in range(100)))
    chunks = FixedSizeChunker(WordTokenizer(), chunk_size=50, overlap_ratio=0.0).chunk([doc])
    assert [c.tokens for c in chunks] == [50, 50]


def test_pgvector_retriever_searches_with_the_embedders_query_vector():
    conn = FakeConnection()
    passages = PgvectorRetriever(FakeEmbedder(), conn, top_k_per_doc=3).retrieve("question")
    assert passages == [PASSAGE]
    # the per-document query received the embedder's vector and the configured k
    assert conn.params[-1] == ([1.0, 0.0], "a.pdf", [1.0, 0.0], 3)


@pytest.mark.parametrize(("extra_args", "k"), [([], 2), (["--top_k_per_doc", "4"], 4)])
def test_query_check_shows_what_the_drafter_retrieves(monkeypatch, capsys, extra_args, k):
    from claimverify.answering import query_check

    class ClosableConnection(FakeConnection):
        def close(self):
            pass

    conn = ClosableConnection()
    monkeypatch.setattr(query_check.psycopg2, "connect", lambda url: conn)
    monkeypatch.setattr(query_check, "build_embedder", lambda settings: FakeEmbedder())
    monkeypatch.setattr("sys.argv", ["query_check", "--db_url", "fake", "--query", "Q?", "--per_document",
                                     *extra_args])
    query_check.main()

    # k comes from config.yaml (answering.retriever: 2) unless overridden for this run
    assert conn.params[-1][-1] == k
    assert "source=a.pdf" in capsys.readouterr().out


def test_llm_drafter_returns_a_draft_with_its_passages():
    draft = LLMDrafter(fake_llm("Answer [a.pdf].")).draft("Q?", [PASSAGE])
    assert draft == Draft(question="Q?", text="Answer [a.pdf].", passages=[PASSAGE])


def test_llm_decomposer_returns_claims():
    payload = json.dumps({"claims": [{"id": "c1", "claim": "X"}]})
    assert LLMDecomposer(fake_llm(payload)).decompose(Draft(question="Q?", text="X", passages=[])) \
        == [Claim(id="c1", claim="X")]


def test_llm_judge_sends_the_passages_and_returns_a_verdict():
    llm = fake_llm(VERDICT_JSON, model="judge-model")
    verdict = LLMJudge(llm).judge(Claim(id="c1", claim="X"), [PASSAGE])
    assert (verdict.verdict, verdict.verifier) == ("supported", "llm_judge:judge-model")
    assert "[Source: a.pdf" in llm.client.calls[0]["messages"][1]["content"]


def test_verifier_retrieves_then_judges_each_claim_in_order():
    retriever, judge = FakeRetriever(), FakeJudge()
    verdicts = list(LangGraphVerifier(retriever, judge).verify(claims(3)))
    assert retriever.queries == ["claim 1", "claim 2", "claim 3"]
    assert judge.seen == [("c1", [PASSAGE]), ("c2", [PASSAGE]), ("c3", [PASSAGE])]
    assert [v.claim_id for v in verdicts] == ["c1", "c2", "c3"]


def test_verifier_handles_more_than_twelve_claims():
    # LangGraph's default limit is 25 steps, i.e. 12 claims at 2 steps each
    assert len(list(LangGraphVerifier(FakeRetriever(), FakeJudge()).verify(claims(15)))) == 15


def test_verifier_with_no_claims_returns_no_verdicts():
    assert list(LangGraphVerifier(FakeRetriever(), FakeJudge()).verify([])) == []


def test_verifier_yields_each_verdict_as_soon_as_it_is_ready():
    judge = FakeJudge()
    verdicts = LangGraphVerifier(FakeRetriever(), judge).verify(claims(3))
    first = next(verdicts)
    # the first verdict arrives before the other claims are even judged
    assert first.claim_id == "c1"
    assert [claim_id for claim_id, _ in judge.seen] == ["c1"]
    assert [v.claim_id for v in verdicts] == ["c2", "c3"]
