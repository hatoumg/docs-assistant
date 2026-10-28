"""Step 4: turn every chunk into a vector (a list of 768 numbers that captures its meaning).

Chunks with similar meaning get vectors that point in similar directions, which is what search uses.
The free Gemini plan limits how fast we can send text, so this step can pause; that is normal.
"""
from common.models import embed_texts


def embed_chunks(chunks):
    """Returns a list of vectors, in the same order as the chunks."""
    print(f"Embedding {len(chunks)} chunks (this can take several minutes on the free plan)...")
    vectors = embed_texts([chunk["text"] for chunk in chunks])
    print(f"Made {len(vectors)} vectors of {len(vectors[0]) if vectors else 0} numbers each")
    return vectors
