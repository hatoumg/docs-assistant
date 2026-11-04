"""Step 2: find the chunks whose meaning is closest to the question.

The question becomes a vector, and the database returns the chunks with the nearest vectors.
In the SQL, '<=>' is the cosine distance (small = similar), so the score is 1 minus that distance.
"""
import numpy as np

from common.config import COLLECTION
from common.database import connect
from common.models import embed_query

# Who can see what:
#   - the evaluation data has no owner, and is searched when no owner is given
#   - a web-app user's files are searched only for that user, and only the document ids the API allows
SEARCH_SQL = """
    SELECT c.id, d.name, d.source, c.position, c.text, 1 - (c.embedding <=> %s) AS score, d.id AS document_id
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE d.collection = %s
      AND d.status = 'ready'
      AND (%s::text[] IS NULL OR d.source = ANY(%s::text[]))
      AND d.owner_id IS NOT DISTINCT FROM %s::uuid
      AND (%s::int[] IS NULL OR d.id = ANY(%s::int[]))
    ORDER BY c.embedding <=> %s
    LIMIT %s
"""


def search_chunks(query, k, sources=None, scope=None):
    """Returns the k closest chunks.

    sources  a list of dataset names to search (evaluation data), or None for all of it
    scope    for the web app: {"owner_id": "<user id>", "document_ids": [1, 2, 3]}. Only that user's documents
             in that list are searched. document_ids=None means all of the user's documents; an empty list means none.
             With no scope, only evaluation documents (which have no owner) are searched, never a user's files.
    """
    owner_id = scope["owner_id"] if scope else None
    document_ids = scope.get("document_ids") if scope else None
    if scope and not owner_id:
        raise ValueError("scope needs an owner_id")
    vector = np.array(embed_query(query), dtype=np.float32)
    connection = connect()
    params = (vector, COLLECTION, sources, sources, owner_id, document_ids, document_ids, vector, k)
    rows = connection.execute(SEARCH_SQL, params).fetchall()
    connection.close()
    return [
        {"id": r[0], "name": r[1], "source": r[2], "position": r[3], "text": r[4], "score": float(r[5]), "document_id": r[6]}
        for r in rows
    ]
