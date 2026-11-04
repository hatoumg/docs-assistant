"""Step 1: read the files in a folder into memory."""
import hashlib
from pathlib import Path

from common.convert import CONVERTIBLE, convert

FILE_TYPES = (".md", ".txt") + CONVERTIBLE
SKIP_NAMES = ("SOURCE.md", "README.md")


def read_text(path, raw=None):
    """The text inside one file. Text files are decoded as they are; PDF and Word files are converted to clean standard text
    (headings, paragraphs, lists and tables) by common/convert.py. Raises ValueError with a message if a file cannot be read."""
    path = Path(path)
    if path.suffix.lower() in CONVERTIBLE:
        return convert(path).text
    return (raw if raw is not None else path.read_bytes()).decode("utf-8", errors="replace")


def load_documents(folder):
    """Read every .md, .txt, .pdf and .docx file in the folder. Returns a list of documents.

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
        try:
            text = read_text(path, raw)
        except ValueError as error:
            print(f"Skipping {path.name}: {error}")
            continue
        documents.append(
            {
                "name": path.name,
                "source": folder.name,
                "text": text,
                "hash": hashlib.sha256(raw).hexdigest(),
            }
        )

    print(f"Loaded {len(documents)} documents")
    return documents


def load_file(path, name, file_hash, source="uploads"):
    """Read one file that the web app stored, as a document (same shape as load_documents returns)."""
    # A PDF with no readable text raises ValueError; the service saves that message on the file so the user can see it.
    return {"name": name, "source": source, "text": read_text(path), "hash": file_hash}
