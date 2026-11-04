"""Step 5: save the chunks and their vectors in the database."""
import numpy as np

from common.config import COLLECTION
from common.database import connect


def skip_already_stored(documents):
    """Drop documents that are already in the database (same file contents), so reruns are quick."""
    connection = connect()
    new_documents = []
    for document in documents:
        row = connection.execute(
            "SELECT 1 FROM documents WHERE collection = %s AND file_hash = %s", (COLLECTION, document["hash"])
        ).fetchone()
        if row is None:
            new_documents.append(document)
    connection.close()
    print(f"{len(documents) - len(new_documents)} documents already stored, {len(new_documents)} new")
    return new_documents


def save_chunks(chunks, vectors):
    """Save each document, then its chunks with their vectors."""
    print("Saving to the database...")
    connection = connect()

    # Group the chunks by the document they came from.
    by_document = {}
    for chunk, vector in zip(chunks, vectors):
        by_document.setdefault(chunk["hash"], []).append((chunk, vector))

    for file_hash, items in by_document.items():
        first = items[0][0]
        with connection.transaction():  # all of a document's rows are saved together, or not at all
            document_id = connection.execute(
                "INSERT INTO documents (name, source, file_hash, collection) VALUES (%s, %s, %s, %s) RETURNING id",
                (first["name"], first["source"], file_hash, COLLECTION),
            ).fetchone()[0]
            rows = [
                (document_id, chunk["position"], chunk["text"], np.array(vector, dtype=np.float32))
                for chunk, vector in items
            ]
            connection.cursor().executemany(
                "INSERT INTO chunks (document_id, position, text, embedding) VALUES (%s, %s, %s, %s)", rows
            )
        print(f"  saved {first['name']}: {len(items)} chunks")

    total_docs = connection.execute("SELECT count(*) FROM documents WHERE collection = %s", (COLLECTION,)).fetchone()[0]
    total_chunks = connection.execute(
        "SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.document_id WHERE d.collection = %s", (COLLECTION,)
    ).fetchone()[0]
    connection.close()
    print(f"The '{COLLECTION}' index now holds {total_docs} documents and {total_chunks} chunks")


def save_document_chunks(document_id, chunks, vectors):
    """Web app: save the chunks of a document whose row already exists, then mark it ready.

    The document becomes searchable only when all its chunks are saved (one transaction).
    """
    connection = connect()
    rows = [
        (document_id, chunk["position"], chunk["text"], np.array(vector, dtype=np.float32))
        for chunk, vector in zip(chunks, vectors)
    ]
    with connection.transaction():
        connection.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))  # safe to run again
        connection.cursor().executemany(
            "INSERT INTO chunks (document_id, position, text, embedding) VALUES (%s, %s, %s, %s)", rows
        )
        connection.execute(
            "UPDATE documents SET status = 'ready', error = NULL, collection = %s WHERE id = %s", (COLLECTION, document_id)
        )
    connection.close()
    print(f"  saved document {document_id}: {len(rows)} chunks")


def mark_failed(document_id, message):
    """Web app: record why a document could not be indexed, so the user can see it."""
    connection = connect()
    connection.execute("UPDATE documents SET status = 'failed', error = %s WHERE id = %s", (message[:300], document_id))
    connection.close()
