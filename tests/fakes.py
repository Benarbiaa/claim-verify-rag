"""Test doubles shared by the test files: no network, no GPU, no database."""

from types import SimpleNamespace

from claimverify.llm import LLM


class FakeClient:
    """Mimics openai.OpenAI().chat.completions.create and returns a fixed string."""

    def __init__(self, content: str):
        message = SimpleNamespace(content=content)
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        self.calls = []

        def create(**kwargs):
            self.calls.append(kwargs)
            return response

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def fake_llm(content: str, model: str = "fake-model") -> LLM:
    return LLM(role="test", model=model, base_url="http://fake", client=FakeClient(content))
