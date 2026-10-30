"""Step 1: read the files in a folder into memory."""
import hashlib
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

FILE_TYPES = (".md", ".txt", ".pdf")
SKIP_NAMES = ("SOURCE.md", "README.md")


def read_text(path, raw=None):
    """The text inside one file. Text files are decoded; for a PDF the text of every page is joined together."""
    path = Path(path)
    if path.suffix.lower() != ".pdf":
        return (raw if raw is not None else path.read_bytes()).decode("utf-8", errors="replace")
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("This PDF is password protected.")
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except PyPdfError as error:
        raise ValueError(f"This PDF could not be read ({error}).") from None
    text = "\n\n".join(page for page in pages if page)
    if not text.strip():
        raise ValueError("This PDF has no selectable text (it may be a scan). Scanned pages need OCR, which is not supported yet.")
    return text


def load_documents(folder):
    """Read every .md, .txt and .pdf file in the folder. Returns a list of documents.

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
