"""Step 3: cut each document into chunks.

The cutting itself is done by LangChain's RecursiveCharacterTextSplitter: it cuts at the first separator in its list
that appears in the text, cuts again with the next separator only the pieces that are still too long, then joins
neighbouring pieces back together up to chunk_size words. The methods differ only in that list of separators:

    fixed      N words, then move forward by (N - overlap) words. Ignores structure. Kept as the baseline.
    recursive  paragraphs, then lines, then sentences, then words. For general text.
    headings   Markdown headings (# ## ###) and code blocks first, then as recursive. For technical docs, reports,
               papers, and every PDF and Word upload (common/convert.py turns them into Markdown).
    clauses    numbered clauses (1. / 2.2 / 2.2.1.) first, then as recursive. For contracts and policies.
               If a text has no clause numbers, this is the same as recursive.
    auto       headings if the text has Markdown headings, clauses if it has numbered clauses, else recursive.

Every chunk also gets a "context" line: the document title and the heading path or clause it falls under, for example
"Acme Distributor Agreement > 14. GOVERNING LAW". 4_embed.py can put it in front of the chunk before embedding
(CHUNK_CONTEXT in common/config.py). The stored text stays the original passage.
"""
import re
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from common.config import CHUNK_METHOD, CHUNK_OVERLAP_WORDS, CHUNK_SIZE_WORDS

# The separators are regular expressions, tried in order. They must not contain capturing groups: use (?:...).
SENTENCE = r"(?<=[a-z)\]\"'”%][.!?])\s+"  # after a full stop that follows a letter, so "2.2." is not a sentence end
CLAUSE = r"\s+(?=(?:\d{1,2}(?:\.\d{1,3})+\.?|\d{1,2}\.)\s+[\"“(]?[A-Z])"  # before "2.2.1. Term", "3.0 GOVERNING", "4. Price"
PLAIN = [r"\n\n", r"\n", SENTENCE, " ", ""]
SEPARATORS = {
    "recursive": PLAIN,
    "headings": [r"\n(?=#{1,6} )", r"\n(?=```)", *PLAIN],
    "clauses": [CLAUSE, *PLAIN],
}
METHODS = ("fixed", *SEPARATORS)

# The kinds of document a user can pick, and the method each one uses.
DOC_TYPES = {"general": "recursive", "technical": "headings", "report": "headings", "paper": "headings",
             "contract": "clauses", "legal": "clauses", "policy": "clauses"}

HEADING_LINE = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")
CLAUSE_START = re.compile(r"(?:^|(?<=\s))(?:\d{1,2}(?:\.\d{1,3})+\.?|\d{1,2}\.)\s+(?=[\"“(]?[A-Z])")


def count_words(text):
    return len(text.split())


def title_from_name(name):
    """A readable title from a file name: 'Acme_Distributor Agreement.txt' -> 'Acme Distributor Agreement'."""
    return re.sub(r"\s+", " ", Path(name).stem.replace("_", " ")).strip()


def choose_method(text):
    """For 'auto': look at the text."""
    if len(HEADING_LINE.findall(text)) >= 2:
        return "headings"
    if len(CLAUSE_START.findall(text)) >= 5:
        return "clauses"
    return "recursive"


def split_fixed(text, chunk_size, overlap):
    """Take chunk_size words, then move forward by (chunk_size - overlap) words and repeat."""
    words = text.split()
    chunks, start = [], 0
    while start < len(words):
        chunks.append(" ".join(words[start : start + chunk_size]))
        if start + chunk_size >= len(words):
            break  # that chunk reached the end of the text
        start += chunk_size - overlap
    return chunks


def clause_label(text):
    """'2.2. Term. This Agreement lasts...' -> '2.2. Term'; '14. GOVERNING LAW This...' -> '14. GOVERNING LAW'."""
    number, _, rest = text.strip().partition(" ")
    caps = re.match(r"(?:[A-Z][A-Z&,;'/-]+\s+)*[A-Z][A-Z&,;'/-]+\b", rest)
    if caps:
        return f"{number} {caps.group(0).rstrip(',;')}"
    short = re.match(r"([A-Z][^.]{0,50})\.", rest)
    if short and count_words(short.group(1)) <= 6:
        return f"{number} {short.group(1)}"
    return number


def context_at(text, position, method, title):
    """The context line for a chunk starting at `position`: title > headings above it, or title > its clause."""
    if method == "headings":
        path = {}
        for match in HEADING_LINE.finditer(text):
            if match.start() > position:
                break
            level = len(match.group(1))
            path = {lvl: name for lvl, name in path.items() if lvl < level}
            path[level] = match.group(2)
        return " > ".join([title, *path.values()])
    if method == "clauses":
        starts = [m.start() for m in CLAUSE_START.finditer(text) if m.start() <= position]
        if starts:
            return f"{title} > {clause_label(text[starts[-1] : starts[-1] + 120])}"
    return title


def make_chunks(text, method="recursive", chunk_size=CHUNK_SIZE_WORDS, overlap=CHUNK_OVERLAP_WORDS, title=""):
    """Cut one text with one method. Returns a list of {"text": ..., "context": ...}."""
    if method == "auto":
        method = choose_method(text)
    if method not in METHODS:
        raise ValueError(f"Unknown chunking method '{method}'. Choose one of: {', '.join(METHODS)}, auto")
    if method == "fixed":
        return [{"text": piece, "context": title} for piece in split_fixed(text, chunk_size, overlap)]

    splitter = RecursiveCharacterTextSplitter(
        separators=SEPARATORS[method],
        is_separator_regex=True,
        keep_separator="start",  # a heading or clause number starts the next piece instead of ending the last one
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        length_function=count_words,  # sizes in words, like CHUNK_SIZE_WORDS
    )
    chunks, search_from = [], 0
    for piece in splitter.split_text(text):
        position = text.find(piece, search_from)
        position = position if position >= 0 else search_from
        search_from = position + 1
        chunks.append({"text": piece, "context": context_at(text, position, method, title)})
    return chunks


def split_text(text, chunk_size=CHUNK_SIZE_WORDS, overlap=CHUNK_OVERLAP_WORDS, method="fixed", title=""):
    """Cut one text into a list of chunk strings (without the context lines)."""
    return [chunk["text"] for chunk in make_chunks(text, method, chunk_size, overlap, title)]


def method_for(document, default=None):
    """The method for one document: its own "method", else the one for its "doc_type", else CHUNK_METHOD."""
    method = document.get("method") or DOC_TYPES.get((document.get("doc_type") or "").lower()) or default or CHUNK_METHOD
    return choose_method(document["text"]) if method == "auto" else method


def split_documents(documents, chunk_size=CHUNK_SIZE_WORDS, overlap=CHUNK_OVERLAP_WORDS, method=None):
    """Cut every document into chunks. Returns one flat list of chunks.

    Each chunk is a dictionary: name, source, hash (of its document), position (0, 1, 2...), text, context and method.
    `method` applies to every document; leave it out to choose per document (see method_for).
    """
    print(f"Splitting documents into chunks of about {chunk_size} words (overlap {overlap})...")
    chunks = []
    for document in documents:
        chosen = method_for({**document, "method": method} if method else document)
        pieces = make_chunks(document["text"], chosen, chunk_size, overlap, title_from_name(document["name"]))
        for position, piece in enumerate(pieces):
            chunks.append({"name": document["name"], "source": document["source"], "hash": document["hash"],
                           "position": position, "method": chosen, **piece})

    for chunk in chunks[:3]:
        print(f"\n--- {chunk['name']} #{chunk['position']} ({chunk['method']}, {count_words(chunk['text'])} words) ---")
        print(f"Context: {chunk['context']}")
        print(chunk["text"][:300] + ("..." if len(chunk["text"]) > 300 else ""))
    print(f"\nCreated {len(chunks)} chunks from {len(documents)} documents")
    return chunks
