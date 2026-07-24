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
