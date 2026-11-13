"""Step 1: load the test questions."""
import json
import re
from pathlib import Path


def files_in_source(source):
    """The file names in a question's 'source' text, e.g. 'My Contract, Inc.txt, Governing Law' -> {'My Contract, Inc.txt'}.
    Several passages are separated by ';'. File names may contain spaces and commas."""
    found = set()
    for part in source.split(";"):
        match = re.match(r"\s*(.+?\.(?:md|txt))(?=\s*(?:,|$))", part)
        if match:
            found.add(match.group(1))
    return found


def load_questions(path, limit=0):
    """Read a question file. Each question is a dictionary with these keys:
        id, kind ('direct', 'multi-passage' or 'not-found'), question,
        answer (the correct answer written by a person), source (where the answer is),
        files (the file names named in source), answerable (False for 'not-found' questions)
    """
    questions = json.loads(Path(path).read_text(encoding="utf-8"))
    for q in questions:
        q["files"] = files_in_source(q.get("source", ""))
        q["answerable"] = q.get("kind") != "not-found"
    if limit:
        questions = questions[:limit]
    print(f"Loaded {len(questions)} questions from {path}")
    return questions
