"""Step 4: turn every chunk into a vector (a list of 768 numbers that captures its meaning).

Chunks with similar meaning get vectors that point in similar directions, which is what search uses.
This runs on your own computer through Ollama, so there is no key and no daily limit. The first call is
slower because Ollama has to load the model into memory.
"""
from common.models import embed_texts


def embed_chunks(chunks):
    """Returns a list of vectors, in the same order as the chunks."""
    print(f"Embedding {len(chunks)} chunks with the local model...")
    vectors = embed_texts([chunk["text"] for chunk in chunks])
    print(f"Made {len(vectors)} vectors of {len(vectors[0]) if vectors else 0} numbers each")
    return vectors
