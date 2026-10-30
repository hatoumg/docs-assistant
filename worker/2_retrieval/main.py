"""Phase 2: find the chunks that can answer a question.

Run from the worker folder:

    python -m 2_retrieval.main "What is the default max_age for CORS?"
    python -m 2_retrieval.main "What law governs the agreement?" --source cuad-dev
"""
import argparse

from common.config import TOP_K
from common.loader import load

# The step files start with a number, so they are imported with load() instead of 'from ... import'.
transform_query = load("2_retrieval.1_query", "transform_query")
search_chunks = load("2_retrieval.2_search", "search_chunks")
merge_results = load("2_retrieval.3_merge", "merge_results")
rerank = load("2_retrieval.4_rerank", "rerank")


def retrieve(question, sources=None, k=TOP_K, scope=None):
    """Returns the best chunks for the question. scope limits the search to one user's documents (see 2_search.py)."""
    # Step 1: Prepare the question (one or more versions)
    queries = transform_query(question)

    # Step 2: Search the database with each version
    result_lists = [search_chunks(query, k, sources, scope) for query in queries]

    # Step 3: Combine the result lists into one
    chunks = merge_results(result_lists, k)

    # Step 4: Put the chunks in the best order
    chunks = rerank(question, chunks)

    return chunks


def show_chunks(chunks):
    for number, chunk in enumerate(chunks, start=1):
        preview = " ".join(chunk["text"].split())[:200]
        print(f"[{number}] score {chunk['score']:.3f}  {chunk['name']} (part {chunk['position'] + 1})\n    {preview}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show the chunks found for a question.")
    parser.add_argument("question")
    parser.add_argument("--source", nargs="+", default=None, help="only search these datasets")
    args = parser.parse_args()
    show_chunks(retrieve(args.question, args.source))
