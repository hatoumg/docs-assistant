"""Phase 1: read documents and store them so they can be searched.

Run from the worker folder:

    python -m 1_indexing.main ../data/raw/cuad-dev

Running it again is safe: documents that are already stored are skipped.
"""
import argparse

from common.loader import load

# The step files start with a number, so they are imported with load() instead of 'from ... import'.
load_documents = load("1_indexing.1_load", "load_documents")
clean_documents = load("1_indexing.2_clean", "clean_documents")
split_documents = load("1_indexing.3_chunk", "split_documents")
embed_chunks = load("1_indexing.4_embed", "embed_chunks")
save_chunks, skip_already_stored = load("1_indexing.5_store", "save_chunks", "skip_already_stored")


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index a folder of documents.")
    parser.add_argument("folder", help="folder with .md or .txt files")
    index_folder(parser.parse_args().folder)
