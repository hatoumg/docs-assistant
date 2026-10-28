"""Step 3: combine the results when there was more than one search.

With one question there is only one list, so this changes nothing. With several questions, the same
chunk may be found twice; we keep it once, with its best score.
"""


def merge_results(result_lists, k):
    """Returns at most k chunks, best score first, with no repeats."""
    best = {}
    for results in result_lists:
        for chunk in results:
            if chunk["id"] not in best or chunk["score"] > best[chunk["id"]]["score"]:
                best[chunk["id"]] = chunk
    merged = sorted(best.values(), key=lambda chunk: chunk["score"], reverse=True)
    return merged[:k]
