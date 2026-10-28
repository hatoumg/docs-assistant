"""Step 2: find the chunks whose meaning is closest to the question.

The question becomes a vector, and the database returns the chunks with the nearest vectors.
In the SQL, '<=>' is the cosine distance (small = similar), so the score is 1 minus that distance.
"""
import numpy as np

from common.config import COLLECTION
from common.database import connect
from common.models import embed_query

SEARCH_SQL = """
    SELECT c.id, d.name, d.source, c.position, c.text, 1 - (c.embedding <=> %s) AS score
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE d.collection = %s
      AND (%s::text[] IS NULL OR d.source = ANY(%s::text[]))
    ORDER BY c.embedding <=> %s
    LIMIT %s
"""


def search_chunks(query, k, sources=None):
    """Returns the k closest chunks. If sources is a list of names, only those datasets are searched."""
    vector = np.array(embed_query(query), dtype=np.float32)
    connection = connect()
    rows = connection.execute(SEARCH_SQL, (vector, COLLECTION, sources, sources, vector, k)).fetchall()
    connection.close()
    return [
        {"id": r[0], "name": r[1], "source": r[2], "position": r[3], "text": r[4], "score": float(r[5])}
        for r in rows
    ]
