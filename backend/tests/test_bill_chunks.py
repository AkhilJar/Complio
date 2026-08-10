from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from database.models import Bill, BillChunk

EMBEDDING_DIMENSIONS = 1536


@pytest.fixture
def bill(db):
    """A parent bill, since every chunk needs one to point at."""
    row = Bill(
        bill_id="89R_TEST1",
        session="89r",
        bill_type="house_bills",
        bill_number="TEST1",
        title="relating to a test.",
        fetched_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def test_table_has_expected_columns(db):
    columns = {c["name"] for c in inspect(db.bind).get_columns("bill_chunks")}
    assert columns == {
        "chunk_id",
        "bill_id",
        "chunk_index",
        "chunk_text",
        "embedding",
        "created_at",
    }


def test_embedding_column_is_a_1536_dimension_vector(db):
    #format_type renders the declared dimension, which the generic sqlalchemy
    #inspector flattens away
    declared = db.execute(
        text(
            "SELECT format_type(a.atttypid, a.atttypmod) "
            "FROM pg_attribute a "
            "WHERE a.attrelid = 'bill_chunks'::regclass AND a.attname = 'embedding'"
        )
    ).scalar()
    assert declared == f"vector({EMBEDDING_DIMENSIONS})"


def test_hnsw_index_exists(db):
    #the index is what makes a similarity search cheap; losing it would not
    #fail any other test, only make production slow
    definition = db.execute(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
        {"name": "ix_bill_chunks_embedding_hnsw"},
    ).scalar()
    assert definition is not None
    assert "hnsw" in definition
    assert "vector_cosine_ops" in definition


def test_insert_chunk_with_real_bill(db, bill):
    chunk = BillChunk(bill_id=bill.bill_id, chunk_index=0, chunk_text="a chunk")
    db.add(chunk)
    db.flush()

    stored = db.query(BillChunk).filter_by(bill_id=bill.bill_id).one()
    assert stored.chunk_index == 0
    assert stored.chunk_text == "a chunk"
    #server_default fires on insert, so this is populated without being set
    assert stored.created_at is not None


def test_embedding_may_be_null(db, bill):
    """The embedding step has not been built yet, so rows arrive without one."""
    chunk = BillChunk(bill_id=bill.bill_id, chunk_index=0, chunk_text="unembedded")
    db.add(chunk)
    db.flush()

    assert db.query(BillChunk).one().embedding is None


def test_foreign_key_rejects_unknown_bill(db):
    db.add(BillChunk(bill_id="89R_DOES_NOT_EXIST", chunk_index=0, chunk_text="orphan"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_unique_constraint_rejects_duplicate_position(db, bill):
    db.add(BillChunk(bill_id=bill.bill_id, chunk_index=0, chunk_text="first"))
    db.flush()

    db.add(BillChunk(bill_id=bill.bill_id, chunk_index=0, chunk_text="second"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_same_index_allowed_for_a_different_bill(db, bill):
    """The constraint is on the pair, not on chunk_index alone."""
    other = Bill(
        bill_id="89R_TEST2",
        session="89r",
        bill_type="house_bills",
        bill_number="TEST2",
        fetched_at=datetime.now(timezone.utc),
    )
    db.add(other)
    db.add(BillChunk(bill_id=bill.bill_id, chunk_index=0, chunk_text="one"))
    db.add(BillChunk(bill_id=other.bill_id, chunk_index=0, chunk_text="two"))
    db.flush()

    assert db.query(BillChunk).count() == 2


def test_cosine_distance_query_returns_nearest_chunk(db, bill):
    """End-to-end proof that pgvector itself works, not just the column type."""
    #two vectors pointing in clearly different directions
    near = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
    far = [0.0, 1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 2)
    db.add(BillChunk(bill_id=bill.bill_id, chunk_index=0, chunk_text="near", embedding=near))
    db.add(BillChunk(bill_id=bill.bill_id, chunk_index=1, chunk_text="far", embedding=far))
    db.flush()

    #query with the 'near' vector: cosine distance to itself is 0
    results = (
        db.query(BillChunk)
        .order_by(BillChunk.embedding.cosine_distance(near))
        .limit(2)
        .all()
    )
    assert [c.chunk_text for c in results] == ["near", "far"]

    distance = db.query(BillChunk.embedding.cosine_distance(near)).order_by(
        BillChunk.embedding.cosine_distance(near)
    ).first()[0]
    assert distance == pytest.approx(0.0, abs=1e-6)
