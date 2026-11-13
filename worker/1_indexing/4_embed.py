"""Step 4: turn every chunk into a vector (a list of 768 numbers that captures its meaning).

Chunks with similar meaning get vectors that point in similar directions, which is what search uses.
This runs on your own computer through Ollama, so there is no key and no daily limit. The first call is
slower because Ollama has to load the model into memory.
"""
from common.config import CHUNK_CONTEXT
from common.models import embed_texts


def text_to_embed(chunk, with_context=CHUNK_CONTEXT):
    """What is embedded for one chunk: its text, with its context line ("Document > Section") in front if asked.
    Only the vector sees the context line; the stored text stays the original passage."""
    context = chunk.get("context", "") if with_context else ""
    return f"{context}\n\n{chunk['text']}" if context else chunk["text"]


def embed_chunks(chunks, with_context=CHUNK_CONTEXT):
    """Returns a list of vectors, in the same order as the chunks."""
    print(f"Embedding {len(chunks)} chunks with the local model{' (with context lines)' if with_context else ''}...")
    vectors = embed_texts([text_to_embed(chunk, with_context) for chunk in chunks])
    print(f"Made {len(vectors)} vectors of {len(vectors[0]) if vectors else 0} numbers each")
    return vectors
