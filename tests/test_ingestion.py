"""CP-12 — ingestion: node + embedding + explicit-ref edges + no-orphan flag."""
from sqlalchemy import select

from edos.db.models import DocumentChunk, GraphEdge, ProjectItem
from edos.engines import ingestion


def test_first_item_flagged_needs_linking(session):
    item = ingestion.ingest_item(session, id="REQ-1", project_id="p1", item_type="requirement",
                                 content="Battery powered water quality monitor")
    assert item.needs_linking is True   # nothing to link to yet — soft flag, not a silent orphan


def test_item_is_embedded(session):
    ingestion.ingest_item(session, id="REQ-1", project_id="p1", item_type="requirement",
                          content="pH TDS temperature DO")
    chunk = session.scalars(select(DocumentChunk).where(DocumentChunk.document_id == "REQ-1")).first()
    assert chunk is not None
    assert chunk.embedding is not None


def test_reference_creates_edge_and_clears_needs_linking(session):
    ingestion.ingest_item(session, id="REQ-1", project_id="p1", item_type="requirement",
                          content="Read pH sensor")
    dec = ingestion.ingest_item(session, id="DEC-1", project_id="p1", item_type="decision",
                                content="This decision depends on REQ-1 for the sensor interface")
    assert dec.needs_linking is False
    edge = session.scalars(
        select(GraphEdge).where(GraphEdge.source_id == "DEC-1", GraphEdge.target_id == "REQ-1")
    ).first()
    assert edge is not None
    assert edge.relation_type == "depends_on"


def test_supersede_reference_marks_prior_superseded(session):
    ingestion.ingest_item(session, id="DEC-1", project_id="p1", item_type="decision", content="Use ESP32")
    ingestion.ingest_item(session, id="DEC-2", project_id="p1", item_type="decision",
                          content="This supersedes DEC-1 with nRF52")
    assert session.get(ProjectItem, "DEC-1").validity == "superseded"


def test_ingest_survives_embedder_quota_failure(session):
    """A provider/quota outage on the embedding API must NOT 500 the ingest or lose the engineer's item.
    The item is the data; the embedding is a best-effort enhancement. On failure the item persists WITHOUT a
    semantic chunk (retrieval degrades for it until re-embedded) — it is never rolled back."""
    class _BrokenEmbedder:
        name, dim = "broken", 8
        def embed(self, text):
            raise RuntimeError("429 RESOURCE_EXHAUSTED (simulated quota outage)")

    item = ingestion.ingest_item(
        session, id="REQ-Q", project_id="pq", item_type="requirement",
        content="IP68 sealed enclosure requirement", embedder=_BrokenEmbedder(),
    )
    # the item survived
    assert session.get(ProjectItem, "REQ-Q") is not None
    assert item.content == "IP68 sealed enclosure requirement"
    # but no semantic chunk was stored (skipped, not crashed)
    chunk = session.scalars(select(DocumentChunk).where(DocumentChunk.document_id == "REQ-Q")).first()
    assert chunk is None


def test_ingest_stamps_embedding_provenance(session):
    """A4: every embedded chunk records WHICH embedder produced it (and the dim), so a stub-space vs
    Gemini-space mismatch is detectable and the backfill can be resumable/idempotent."""
    from edos.db.models import EMBED_DIM
    ingestion.ingest_item(session, id="REQ-PROV", project_id="pprov", item_type="requirement",
                          content="pH sensor calibration over temperature")
    chunk = session.scalars(select(DocumentChunk).where(DocumentChunk.document_id == "REQ-PROV")).first()
    assert chunk is not None
    assert chunk.embedding_model == "stub"        # tests run on the stub embedder
    assert chunk.embedding_dim == EMBED_DIM
