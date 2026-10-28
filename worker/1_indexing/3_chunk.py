"""Step 3: cut each document into chunks.

Method: fixed size. Take N words, then move forward by (N - overlap) words and repeat.
The overlap repeats a few words, so a sentence cut at the edge still appears whole in one chunk.
"""
from common.config import CHUNK_OVERLAP_WORDS, CHUNK_SIZE_WORDS


def split_text(text, chunk_size=CHUNK_SIZE_WORDS, overlap=CHUNK_OVERLAP_WORDS):
    """Cut one text into a list of chunk strings."""
    words = text.split()
    step = chunk_size - overlap
    chunks = []
    start = 0
    while start < len(words):
        chunks.append(" ".join(words[start : start + chunk_size]))
        if start + chunk_size >= len(words):
            break  # that chunk reached the end of the text
        start += step
    return chunks


def split_documents(documents, chunk_size=CHUNK_SIZE_WORDS, overlap=CHUNK_OVERLAP_WORDS):
    """Cut every document into chunks. Returns one flat list of chunks.

    Each chunk is a dictionary: name, source, hash (of its document), position (0, 1, 2...) and text.
    """
    print(f"Splitting documents into chunks of {chunk_size} words (overlap {overlap})...")
    chunks = []
    for document in documents:
        for position, text in enumerate(split_text(document["text"], chunk_size, overlap)):
            chunks.append(
                {
                    "name": document["name"],
                    "source": document["source"],
                    "hash": document["hash"],
                    "position": position,
                    "text": text,
                }
            )

    for i, chunk in enumerate(chunks[:3]):
        print(f"\n--- Chunk {i + 1} ---")
        print(f"File: {chunk['name']}   Words: {len(chunk['text'].split())}")
        print(chunk["text"][:300] + ("..." if len(chunk["text"]) > 300 else ""))
        print("-" * 50)
    if len(chunks) > 3:
        print(f"\n... and {len(chunks) - 3} more chunks")

    print(f"Created {len(chunks)} chunks from {len(documents)} documents")
    return chunks
