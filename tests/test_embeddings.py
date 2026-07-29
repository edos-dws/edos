"""CP-12 ticket 12.2 — stub embedding provider is deterministic and dimension-correct."""
from edos.db.models import EMBED_DIM
from edos.engines.embeddings import StubEmbeddingProvider


def test_deterministic_and_dim():
    e = StubEmbeddingProvider()
    v1 = e.embed("battery powered water quality monitor")
    v2 = e.embed("battery powered water quality monitor")
    assert v1 == v2                      # deterministic
    assert len(v1) == EMBED_DIM          # right dimension


def test_similar_text_closer_than_unrelated():
    e = StubEmbeddingProvider()

    def dot(a, b):
        return sum(x * y for x, y in zip(a, b, strict=True))

    base = e.embed("pH TDS temperature dissolved oxygen sensor")
    similar = e.embed("pH TDS temperature dissolved oxygen probe")
    unrelated = e.embed("quarterly financial revenue report")
    assert dot(base, similar) > dot(base, unrelated)


def test_empty_text_is_zero_vector():
    assert StubEmbeddingProvider().embed("") == [0.0] * EMBED_DIM


def test_gemini_embed_dimension_guard_raises_not_silently_stores():
    """A4: a provider returning the wrong dimension must raise (never silently store a mismatched vector into
    the fixed-dim pgvector column). Mocked client — no network."""
    import pytest

    from edos.engines.embeddings import GeminiEmbeddingProvider

    p = GeminiEmbeddingProvider(model="m", api_key="k", dim=EMBED_DIM)

    class _Emb:
        values = [0.1] * 10          # wrong dimension (10, not EMBED_DIM)

    class _Resp:
        embeddings = [_Emb()]  # noqa: RUF012 — throwaway test fake, not a real mutable-default footgun

    class _Models:
        def embed_content(self, **kw):
            return _Resp()

    class _Client:
        models = _Models()

    p._client = _Client()
    with pytest.raises(ValueError):
        p.embed("x")


def test_stub_always_correct_dimension():
    # the stub constructs its own dim, so it can never mismatch (guard is for the API path)
    assert len(StubEmbeddingProvider().embed("anything")) == EMBED_DIM
