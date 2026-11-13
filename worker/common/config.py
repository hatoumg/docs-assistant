"""The numbers you will change while experimenting. Everything is in one place on purpose."""
import os
from pathlib import Path

WORKER_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = WORKER_DIR.parent

# Phase 1: indexing
# The environment variables let 4_evaluation/compare_sizes.py try other values without editing this file. Leave them unset normally.
COLLECTION = os.getenv("RAG_COLLECTION", "simple-nomic")  # name of this index in the database. Use a new name whenever chunking or the embedding model changes
CHUNK_SIZE_WORDS = int(os.getenv("RAG_CHUNK_WORDS", "200"))  # how many words go in one chunk
CHUNK_OVERLAP_WORDS = int(os.getenv("RAG_OVERLAP_WORDS", str(CHUNK_SIZE_WORDS // 5)))  # how many words are repeated between neighbouring chunks (a fifth of the size)
# How documents are cut when they do not say their own type: fixed, recursive, headings, clauses, or auto (look at the text).
# "fixed" keeps today's index unchanged. See 1_indexing/3_chunk.py for what each method does.
CHUNK_METHOD = os.getenv("RAG_CHUNK_METHOD", "fixed")
# Put each chunk's context line ("Document title > Section") in front of its text before embedding. 1 = yes, 0 = no.
CHUNK_CONTEXT = os.getenv("RAG_CHUNK_CONTEXT", "0") == "1"

# Phase 2: retrieval
TOP_K = 5                    # how many chunks are given to the answering model

# Phase 4: evaluation
JUDGE_PROMPT_FILE = REPO_DIR / "evals" / "judge_prompt.md"
RESULTS_FILE = REPO_DIR / "evals" / "results-simple.csv"
