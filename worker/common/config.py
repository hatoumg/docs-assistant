"""The numbers you will change while experimenting. Everything is in one place on purpose."""
from pathlib import Path

WORKER_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = WORKER_DIR.parent

# Phase 1: indexing
COLLECTION = "simple"        # name of this index inside the database (a different name = a separate index)
CHUNK_SIZE_WORDS = 200       # how many words go in one chunk
CHUNK_OVERLAP_WORDS = 40     # how many words are repeated between neighbouring chunks

# Phase 2: retrieval
TOP_K = 5                    # how many chunks are given to the answering model

# Phase 4: evaluation
JUDGE_PROMPT_FILE = REPO_DIR / "evals" / "judge_prompt.md"
RESULTS_FILE = REPO_DIR / "evals" / "results-simple.csv"
