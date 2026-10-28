"""Step 2: did the search find the right file?

Hit: the right file is among the retrieved chunks.
Rank: the position of the first chunk from the right file (1 = best).
Reciprocal rank: 1 / rank, or 0 if the file was not found. The average over all questions is called MRR.
"""


def score_retrieval(question, chunks):
    """Returns a dictionary: rank, hit and reciprocal_rank."""
    rank = None
    for position, chunk in enumerate(chunks, start=1):
        if chunk["name"] in question["files"]:
            rank = position
            break
    return {"rank": rank, "hit": rank is not None, "reciprocal_rank": 1 / rank if rank else 0.0}
