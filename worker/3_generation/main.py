"""Phase 3: write an answer from the retrieved chunks, with citations.

Run from the worker folder:

    python -m 3_generation.main "What is the default max_age for CORS?"
    python -m 3_generation.main "What law governs the agreement?" --source cuad-dev
"""
import argparse

from common.loader import load

# The step files start with a number, so they are imported with load() instead of 'from ... import'.
retrieve, show_chunks = load("2_retrieval.main", "retrieve", "show_chunks")
build_prompt = load("3_generation.1_prompt", "build_prompt")
generate_answer = load("3_generation.2_generate", "generate_answer")
check_answer = load("3_generation.3_check", "check_answer")


def answer_from_chunks(question, chunks):
    """Writes the answer when you already have the chunks."""
    # Step 1: Build the prompt (question + numbered passages)
    prompt = build_prompt(question, chunks)

    # Step 2: Ask the model
    reply = generate_answer(prompt)

    # Step 3: Check the reply and find its citations
    answer = check_answer(reply, chunks)
    answer["chunks"] = chunks
    return answer


def answer_question(question, sources=None):
    """Finds the chunks (phase 2), then writes the answer."""
    chunks = retrieve(question, sources)
    return answer_from_chunks(question, chunks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Answer a question with citations.")
    parser.add_argument("question")
    parser.add_argument("--source", nargs="+", default=None, help="only search these datasets")
    args = parser.parse_args()

    result = answer_question(args.question, args.source)
    print("\nAnswer:\n" + result["text"])
    if result["citations"]:
        print("\nSources:")
        for chunk in result["citations"]:
            print(f"  {chunk['name']} (part {chunk['position'] + 1})")
    print("\nPassages given to the model:")
    show_chunks(result["chunks"])
