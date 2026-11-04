"""Phase 1: read documents and store them so they can be searched.

Run from the worker folder:

    python -m 1_indexing.main ../data/raw/cuad-dev

Running it again is safe: documents that are already stored are skipped.
"""
import argparse
from pathlib import Path

from common.convert import CONVERTED_SUFFIX, CONVERTIBLE
from common.loader import load

# The step files start with a number, so they are imported with load() instead of 'from ... import'.
load_documents, load_file = load("1_indexing.1_load", "load_documents", "load_file")
clean_documents = load("1_indexing.2_clean", "clean_documents")
split_documents = load("1_indexing.3_chunk", "split_documents")
embed_chunks = load("1_indexing.4_embed", "embed_chunks")
save_chunks, skip_already_stored, save_document_chunks = load(
    "1_indexing.5_store", "save_chunks", "skip_already_stored", "save_document_chunks"
)


def index_folder(folder):
    # Step 1: Load documents
    documents = load_documents(folder)

    # Skip the ones we stored on an earlier run
    documents = skip_already_stored(documents)
    if not documents:
        print("Nothing new to index.")
        return

    # Step 2: Clean the text
    documents = clean_documents(documents)

    # Step 3: Split into chunks
    chunks = split_documents(documents)

    # Step 4: Turn the chunks into vectors
    vectors = embed_chunks(chunks)

    # Step 5: Save everything in the database
    save_chunks(chunks, vectors)


def index_upload(document_id, path, name, file_hash):
    """Index one file uploaded through the web app. Same steps as above; the database row already exists."""
    document = load_file(path, name, file_hash)
    if Path(path).suffix.lower() in CONVERTIBLE:
        # Keep the converted text next to the original, so the website can show "the text version" of a PDF or Word file.
        # The API reads (and deletes) this same name: keep CONVERTED_SUFFIX in api/src/storage.ts the same.
        Path(str(path) + CONVERTED_SUFFIX).write_text(document["text"], encoding="utf-8")
    documents = clean_documents([document])
    chunks = split_documents(documents)
    if not chunks:
        raise ValueError("The file has no text to index.")
    vectors = embed_chunks(chunks)
    save_document_chunks(document_id, chunks, vectors)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index a folder of documents.")
    parser.add_argument("folder", help="folder with .md or .txt files")
    index_folder(parser.parse_args().folder)
