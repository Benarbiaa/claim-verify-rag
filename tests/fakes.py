"""Test doubles shared by the test files: no network, no GPU, no database."""

from types import SimpleNamespace

from claimverify.llm import LLM


class FakeClient:
    """Mimics openai.OpenAI().chat.completions.create and returns a fixed string."""

    def __init__(self, content: str, tokens_in: int = 100, tokens_out: int = 20):
        message = SimpleNamespace(content=content)
        usage = SimpleNamespace(prompt_tokens=tokens_in, completion_tokens=tokens_out)
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)
        self.calls = []

        def create(**kwargs):
            self.calls.append(kwargs)
            return response

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def fake_llm(content: str, model: str = "fake-model") -> LLM:
    return LLM(role="test", model=model, base_url="http://fake", client=FakeClient(content))


def provider_error(code: str) -> Exception:
    """An openai.BadRequestError like the one Groq returns, e.g. code 'json_validate_failed'."""
    import httpx
    from openai import BadRequestError

    request = httpx.Request("POST", "http://fake/chat/completions")
    return BadRequestError(f"Error code: 400 - {code}", response=httpx.Response(400, request=request),
                           body={"error": {"code": code}})


def failing_llm(error: Exception, model: str = "fake-model") -> LLM:
    """An LLM whose every call raises `error`."""
    def create(**kwargs):
        raise error

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return LLM(role="test", model=model, base_url="http://fake", client=client)


class WordTokenizer:
    """One token per whitespace-separated word, with its character positions."""

    def token_spans(self, text: str) -> list[tuple[int, int]]:
        import re
        return [m.span() for m in re.finditer(r"\S+", text)]


class PieceTokenizer:
    """Cuts words into pieces of at most 3 characters, like WordPiece cuts rare words."""

    def token_spans(self, text: str) -> list[tuple[int, int]]:
        import re
        return [(s, min(s + 3, m.end())) for m in re.finditer(r"\S+", text)
                for s in range(m.start(), m.end(), 3)]
