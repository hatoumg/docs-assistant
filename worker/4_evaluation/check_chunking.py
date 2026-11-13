"""Check that the chunking code works, from quick checks to the full pipeline, and print a summary.

Run from the worker folder:

    python -m 4_evaluation.check_chunking            # steps 1-3 (step 3 is skipped if Ollama is not running)
    python -m 4_evaluation.check_chunking --quick    # steps 1-2 only: no Ollama, no database, under a minute
    python -m 4_evaluation.check_chunking --full     # steps 1-4 (step 4 needs Docker/Postgres and Ollama)

The steps:
    1. tests        the automated tests for chunking (pytest)
    2. real chunks  cuts the CUAD contracts and FastAPI docs and checks the result: sizes stay under the limit,
                    contract chunks start at a clause number, doc chunks start at a heading, and 'auto' picks the
                    right method. Prints a few chunks so you can look at them.
    3. retrieval    chunk_sweep: compares fixed with the new methods, with and without context lines
    4. pipeline     indexes the contracts into a separate index ("check-auto") with method auto and context lines,
                    then scores search on it and on your normal index. Your website's index is not changed.

Nothing is saved to the results files unless you add --save.
"""
import argparse
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from common.config import REPO_DIR, WORKER_DIR

SIZE, OVERLAP = 300, 60
CONTRACTS = REPO_DIR / "data" / "raw" / "cuad-dev"
TECHNICAL = REPO_DIR / "data" / "samples" / "technical"
CONTRACT_QUESTIONS = REPO_DIR / "evals" / "contracts-dev.json"
TECHNICAL_QUESTIONS = REPO_DIR / "evals" / "technical.json"
CLAUSE_AT_START = re.compile(r"^(?:\d{1,2}(?:\.\d{1,3})+\.?|\d{1,2}\.)\s")

results = []  # (step, outcome, note)


def heading(title):
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78, flush=True)


def record(step, outcome, note=""):
    results.append((step, outcome, note))
    print(f"\n>>> {step}: {outcome}" + (f" ({note})" if note else ""), flush=True)


def run(command, env=None):
    """Runs a command in the worker folder, showing its output as it goes. Returns True if it succeeded."""
    print("$ " + " ".join(str(part) for part in command), flush=True)
    return subprocess.run(command, cwd=WORKER_DIR, env=env).returncode == 0


def python(*args):
    return [sys.executable, "-m", *args]


# ----- step 1 -----


def step_tests():
    heading("Step 1: automated tests")
    try:
        import langchain_text_splitters  # noqa: F401
    except ImportError:
        record("1. tests", "FAIL", "langchain-text-splitters is not installed: run  pip install langchain-text-splitters")
        return False
    ok = run(python("pytest", "-q", "tests/test_chunk_methods.py", "tests/test_chunk_sweep.py", "tests/test_simple_steps.py"))
    record("1. tests", "PASS" if ok else "FAIL", "" if ok else "see the pytest output above")
    return ok


# ----- step 2 -----


def load_folder(folder):
    from common.loader import load

    load_documents = load("1_indexing.1_load", "load_documents")
    clean_text = load("1_indexing.2_clean", "clean_text")
    documents = load_documents(folder)
    for document in documents:
        document["text"] = clean_text(document["text"])
    return documents


def check_folder(folder, method, starts_well, label):
    """Cuts every document in the folder and returns a list of problems (empty if all is well)."""
    from common.loader import load

    make_chunks, choose_method, title_from_name = load("1_indexing.3_chunk", "make_chunks", "choose_method", "title_from_name")
    documents = load_folder(folder)
    if not documents:
        return [f"no documents found in {folder}"]
    problems, chunks_total, good_starts, too_big, lost_words = [], 0, 0, 0, 0
    wrong_auto = []
    for document in documents:
        chunks = make_chunks(document["text"], method, SIZE, OVERLAP, title_from_name(document["name"]))
        chunks_total += len(chunks)
        good_starts += sum(1 for c in chunks if starts_well(c["text"]))
        too_big += sum(1 for c in chunks if len(c["text"].split()) > SIZE)
        # every word of the document must appear in some chunk (the overlap may repeat words, never drop them)
        chunk_words = sum(len(c["text"].split()) for c in chunks)
        if chunk_words < len(document["text"].split()):
            lost_words += 1
        if choose_method(document["text"]) != method:
            wrong_auto.append(document["name"])

    share = good_starts / max(chunks_total, 1)
    print(f"\n{label}: {len(documents)} documents, {chunks_total} chunks with '{method}'")
    print(f"  chunks that start at a {'clause number' if method == 'clauses' else 'heading'}: {share:.0%}")
    print(f"  chunks over {SIZE} words: {too_big}")
    print(f"  documents where words went missing: {lost_words}")
    print(f"  documents where 'auto' would not pick '{method}': {len(wrong_auto)}")
    if too_big:
        problems.append(f"{label}: {too_big} chunks are over {SIZE} words")
    if lost_words:
        problems.append(f"{label}: words went missing in {lost_words} documents")
    if share < 0.5:
        problems.append(f"{label}: only {share:.0%} of chunks start at a {'clause' if method == 'clauses' else 'heading'}")
    if len(wrong_auto) > len(documents) // 4:
        problems.append(f"{label}: 'auto' picks another method for {len(wrong_auto)} documents, e.g. {wrong_auto[0]}")

    sample = documents[0]
    print(f"\n  First chunks of {sample['name']}:")
    for chunk in make_chunks(sample["text"], method, SIZE, OVERLAP, title_from_name(sample["name"]))[:5]:
        start = chunk["text"][:70].replace("\n", " ")
        print(f"    {len(chunk['text'].split()):4} words | {chunk['context'][:60]:60} | {start}")
    return problems


def step_real_chunks():
    heading(f"Step 2: cut real documents ({SIZE} words, overlap {OVERLAP})")
    try:
        problems = check_folder(CONTRACTS, "clauses", lambda t: bool(CLAUSE_AT_START.match(t)), "Contracts")
        problems += check_folder(TECHNICAL, "headings", lambda t: t.startswith("#"), "FastAPI docs")
    except Exception as error:  # show the error but carry on with the summary
        record("2. real chunks", "FAIL", f"{type(error).__name__}: {error}")
        return False
    for problem in problems:
        print(f"  problem: {problem}")
    record("2. real chunks", "PASS" if not problems else "WARN", "; ".join(problems))
    return not problems


# ----- step 3 -----


def ollama_running():
    from common.settings import load_settings

    try:
        urllib.request.urlopen(load_settings().ollama_url.rstrip("/") + "/api/tags", timeout=3)
        return True
    except Exception:
        return False


def step_retrieval(save):
    heading("Step 3: retrieval quality (chunk_sweep)")
    if not ollama_running():
        record("3. retrieval", "SKIPPED", "Ollama is not running: start it and run this again")
        return None
    extra = [] if save else ["--no-save"]
    ok = run(python("4_evaluation.chunk_sweep", CONTRACT_QUESTIONS, "--docs", CONTRACTS, "--sizes", str(SIZE),
                    "--methods", "fixed,recursive,clauses", "--context", "both", *extra))
    ok = run(python("4_evaluation.chunk_sweep", TECHNICAL_QUESTIONS, "--docs", TECHNICAL, "--sizes", str(SIZE),
                    "--methods", "fixed,recursive,headings", "--context", "both", *extra)) and ok
    note = "compare MRR and @budget: does clauses/headings beat fixed, and context yes beat no?" if ok else "see the output above"
    record("3. retrieval", "PASS" if ok else "FAIL", note)
    return ok


# ----- step 4 -----


def step_pipeline(save):
    heading("Step 4: full pipeline on a separate index ('check-auto')")
    if not ollama_running():
        record("4. pipeline", "SKIPPED", "Ollama is not running")
        return None
    test_env = {**os.environ, "RAG_COLLECTION": "check-auto", "RAG_CHUNK_METHOD": "auto", "RAG_CHUNK_CONTEXT": "1",
                "RAG_CHUNK_WORDS": str(SIZE), "RAG_OVERLAP_WORDS": str(OVERLAP)}
    normal_env = {k: v for k, v in os.environ.items() if not k.startswith(("RAG_COLLECTION", "RAG_CHUNK", "RAG_OVERLAP"))}
    extra = [] if save else ["--no-save"]
    evaluate = python("4_evaluation.main", CONTRACT_QUESTIONS, "--source", CONTRACTS.name, "--retrieval-only", *extra)

    print("\nIndexing the contracts with method auto and context lines (needs Docker/Postgres)...")
    if not run(python("1_indexing.main", CONTRACTS), env=test_env):
        record("4. pipeline", "FAIL", "indexing failed: is Docker running (docker compose up -d)?")
        return False
    print("\nSearch scores on the NEW index (auto + context):")
    new_ok = run(evaluate, env=test_env)
    print("\nSearch scores on your NORMAL index, for comparison:")
    run(evaluate, env=normal_env)
    record("4. pipeline", "PASS" if new_ok else "FAIL",
           "compare hit@k and MRR of the two runs above" if new_ok else "the evaluation failed, see above")
    return new_ok


def main():
    parser = argparse.ArgumentParser(description="Check that the chunking code works.")
    parser.add_argument("--quick", action="store_true", help="steps 1-2 only (no Ollama, no database)")
    parser.add_argument("--full", action="store_true", help="also step 4: index into a separate collection and score it")
    parser.add_argument("--save", action="store_true", help="save the step 3 and 4 results to the evals CSV files")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # contract text has symbols some Windows consoles cannot print

    step_tests()
    step_real_chunks()
    if not args.quick:
        step_retrieval(args.save)
    if args.full:
        step_pipeline(args.save)

    heading("Summary")
    for step, outcome, note in results:
        print(f"  {step:16} {outcome:8} {note}")
    sys.exit(1 if any(outcome == "FAIL" for _, outcome, _ in results) else 0)


if __name__ == "__main__":
    main()
