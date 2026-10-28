"""Step 1: prepare the user's question for searching.

Basic method: only trim spaces. The function returns a LIST of questions, because later methods
(for example asking the AI to rephrase the question three ways) produce several.
"""


def transform_query(question):
    """Returns a list of questions to search with."""
    queries = [question.strip()]
    print(f"Searching with {len(queries)} question(s): {queries}")
    return queries
