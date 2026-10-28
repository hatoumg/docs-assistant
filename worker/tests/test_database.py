"""Checks on the real database. They replace smoke_check.py.

They need Docker running and `python migrate.py` applied. If the database cannot be reached, every test here is skipped.
The data checks also need some documents to be indexed first (python -m 1_indexing.main ../data/raw/cuad-dev).
"""
import pytest

from common.database import connect
from common.settings import load_settings


@pytest.fixture
def conn():
    try:
        connection = connect()
    except Exception as error:
        pytest.skip(f"database not reachable: {error}")
    yield connection
    connection.close()


def stored_chunks(conn):
    count = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
    if count == 0:
        pytest.skip("no chunks stored yet; index some documents first")
    return count


# ----- setup checks (no documents needed) -----


def test_pgvector_extension_is_installed(conn):
    assert conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").fetchone() is not None


def test_tables_exist(conn):
    tables = {r[0] for r in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    assert {"documents", "chunks"} <= tables


def test_migration_002_added_the_collection_column(conn):
    column = conn.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = 'documents' AND column_name = 'collection'"
    ).fetchone()
    assert column is not None, "run: python migrate.py"


def test_embedding_index_exists(conn):
    assert conn.execute("SELECT 1 FROM pg_indexes WHERE indexname = 'chunks_embedding_idx'").fetchone() is not None


# ----- data checks (need indexed documents) -----


def test_every_document_has_chunks(conn):
    stored_chunks(conn)
    empty = conn.execute(
        "SELECT count(*) FROM documents d WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.document_id = d.id)"
    ).fetchone()[0]
    assert empty == 0, f"{empty} documents have no chunks"


def test_every_chunk_has_an_embedding(conn):
    stored_chunks(conn)
    assert conn.execute("SELECT count(*) FROM chunks WHERE embedding IS NULL").fetchone()[0] == 0


def test_embeddings_have_the_expected_size(conn):
    stored_chunks(conn)
    sizes = [r[0] for r in conn.execute("SELECT DISTINCT vector_dims(embedding) FROM chunks")]
    assert sizes == [load_settings().embed_dim]


def test_search_finds_a_chunk_at_distance_zero_from_itself(conn):
    """Search with a stored chunk's own vector: the closest result must be at distance 0.

    (We do not compare ids, because the same text can be stored twice, for example in two collections.
    Identical vectors tie at distance 0, and the database may return either one.)
    """
    stored_chunks(conn)
    closest = conn.execute(
        "SELECT embedding <=> (SELECT embedding FROM chunks ORDER BY id LIMIT 1) AS distance "
        "FROM chunks ORDER BY distance LIMIT 1"
    ).fetchone()[0]
    assert closest == pytest.approx(0, abs=1e-6)


def test_chunks_per_collection_are_listed(conn):
    """Not a pass/fail check: prints what is stored (run pytest with -s to see it)."""
    stored_chunks(conn)
    for collection, docs, chunks in conn.execute(
        "SELECT d.collection, count(DISTINCT d.id), count(c.id) FROM documents d "
        "LEFT JOIN chunks c ON c.document_id = d.id GROUP BY d.collection ORDER BY d.collection"
    ):
        print(f"collection '{collection}': {docs} documents, {chunks} chunks")
