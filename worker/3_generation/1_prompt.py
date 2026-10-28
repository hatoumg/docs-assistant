"""Step 1: build the message we send to the answering model."""

PROMPT = """You answer questions using only the numbered passages below.

Rules:
- Use only information in the passages. Do not use outside knowledge.
- Cite the passages you used with their numbers in square brackets, for example [1] or [2][3].
- If the passages do not contain the answer, reply with exactly: NOT_FOUND

Passages:
{passages}

Question: {question}
Answer:"""


def format_passages(chunks):
    """Number the chunks: '[1] (from file.md, part 3)' followed by the text."""
    blocks = []
    for number, chunk in enumerate(chunks, start=1):
        blocks.append(f"[{number}] (from {chunk['name']}, part {chunk['position'] + 1})\n{chunk['text']}")
    return "\n\n".join(blocks)


def build_prompt(question, chunks):
    return PROMPT.replace("{passages}", format_passages(chunks)).replace("{question}", question)
