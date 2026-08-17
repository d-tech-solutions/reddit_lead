from typing import ClassVar

import pytest

from app.core.constants import EMBEDDING_DIMENSIONS
from app.workers import embedding_source
from app.workers.embedding_source import (
    MAX_INPUT_CHARS,
    build_embedding_provider,
    post_to_text,
)


def test_post_to_text_joins_title_and_body():
    assert post_to_text("Need a logo", "Budget is $200") == "Need a logo\n\nBudget is $200"


def test_post_to_text_omits_empty_body():
    # RSS mode never supplies a body, so title-only must not leave trailing separator noise.
    assert post_to_text("Need a logo", "") == "Need a logo"
    assert post_to_text("Need a logo", "   ") == "Need a logo"


def test_post_to_text_truncates_to_the_input_cap():
    text = post_to_text("t", "x" * (MAX_INPUT_CHARS * 2))
    assert len(text) == MAX_INPUT_CHARS


def test_build_embedding_provider_requires_an_api_key():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_embedding_provider("", "text-embedding-3-small")


def test_build_embedding_provider_returns_a_provider_when_configured():
    provider = build_embedding_provider("sk-test-not-a-real-key", "text-embedding-3-small")
    assert hasattr(provider, "embed")


async def test_fake_provider_is_deterministic_and_correctly_sized(fake_provider):
    first = await fake_provider.embed(["hello"])
    second = await fake_provider.embed(["hello"])
    other = await fake_provider.embed(["goodbye"])

    assert first == second
    assert first != other
    assert len(first[0]) == EMBEDDING_DIMENSIONS


async def test_openai_provider_reorders_results_by_index(monkeypatch):
    # The matcher pairs vectors with rows positionally, so out-of-order API responses must be
    # re-sorted rather than trusted.
    class FakeItem:
        def __init__(self, index, embedding):
            self.index = index
            self.embedding = embedding

    class FakeResponse:
        data: ClassVar[list] = [
            FakeItem(1, [0.2] * EMBEDDING_DIMENSIONS),
            FakeItem(0, [0.1] * EMBEDDING_DIMENSIONS),
        ]
        usage = None

    provider = object.__new__(embedding_source.OpenAIEmbeddingProvider)
    provider._model = "text-embedding-3-small"

    class FakeEmbeddings:
        async def create(self, model, input):
            return FakeResponse()

    provider._client = type("FakeClient", (), {"embeddings": FakeEmbeddings()})()

    vectors = await provider.embed(["first", "second"])

    assert vectors[0][0] == pytest.approx(0.1)
    assert vectors[1][0] == pytest.approx(0.2)


async def test_openai_provider_rejects_wrong_dimensions():
    # A model swap that changes vector width would otherwise fail deep in the database driver.
    class FakeItem:
        index = 0
        embedding = [0.1] * 128

    class FakeResponse:
        data: ClassVar[list] = [FakeItem()]
        usage = None

    provider = object.__new__(embedding_source.OpenAIEmbeddingProvider)
    provider._model = "some-other-model"

    class FakeEmbeddings:
        async def create(self, model, input):
            return FakeResponse()

    provider._client = type("FakeClient", (), {"embeddings": FakeEmbeddings()})()

    with pytest.raises(ValueError, match="dimensions"):
        await provider.embed(["text"])


async def test_openai_provider_short_circuits_on_empty_input():
    provider = object.__new__(embedding_source.OpenAIEmbeddingProvider)
    provider._model = "text-embedding-3-small"
    provider._client = None  # must not be touched

    assert await provider.embed([]) == []
