"""Step 2: remove text that is useless for searching."""
import re


def clean_text(text):
    """Clean one text.

    Removes: lines that point to code files ({* ... *}), '///' markers, image lines,
    HTML tags (the words inside them stay), heading ids like '{ #name }', and extra blank lines.
    """
    kept_lines = []
    for line in text.replace("\r\n", "\n").split("\n"):
        start = line.strip()
        if start.startswith(("{*", "///", "<img")):
            continue
        line = re.sub(r"\s*\{\s*#[^}]*\}\s*$", "", line)  # '# Title { #title }' becomes '# Title'
        line = re.sub(r"<[^>]+>", "", line)                 # drop HTML tags
        kept_lines.append(line.rstrip())

    cleaned = "\n".join(kept_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)            # at most one blank line in a row
    return cleaned.strip()


def clean_documents(documents):
    """Clean the text of every document."""
    print("Cleaning documents...")
    for document in documents:
        document["text"] = clean_text(document["text"])
    return documents
