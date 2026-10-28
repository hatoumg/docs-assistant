"""Step 1: read the files in a folder into memory."""
import hashlib
from pathlib import Path

FILE_TYPES = (".md", ".txt")
SKIP_NAMES = ("SOURCE.md", "README.md")


def load_documents(folder):
    """Read every .md and .txt file in the folder. Returns a list of documents.

    Each document is a dictionary:
        name    the file name
        source  the folder name (used later to search one dataset at a time)
        text    the full text
        hash    a fingerprint of the file, so we can tell if it was already stored
    """
    print(f"Loading documents from {folder}...")
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")

    documents = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in FILE_TYPES:
            continue
        if path.name in SKIP_NAMES or path.name.upper().startswith(("LICENSE", "LICENCE")):
            continue
        raw = path.read_bytes()
        documents.append(
            {
                "name": path.name,
                "source": folder.name,
                "text": raw.decode("utf-8", errors="replace"),
                "hash": hashlib.sha256(raw).hexdigest(),
            }
        )

    print(f"Loaded {len(documents)} documents")
    return documents
