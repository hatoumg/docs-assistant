"""Step 3: check the reply and work out which passages it cites."""
import re

NOT_FOUND_TEXT = "Not found in the documents."


def check_answer(reply, chunks):
    """Returns a dictionary:
        text       the answer to show
        found      False when the model said NOT_FOUND (or had nothing to work from)
        citations  the chunks the answer cites, for example [1] points to the first chunk
    """
    if not chunks or not reply or reply.upper().startswith("NOT_FOUND"):
        return {"text": NOT_FOUND_TEXT, "found": False, "citations": []}

    # Some models write 【1】 instead of [1]. Make them the same.
    reply = re.sub(r"[【［]\s*(\d+)\s*[】］]", r"[\1]", reply)

    citations = []
    for number in re.findall(r"\[(\d+)\]", reply):
        number = int(number)
        if 1 <= number <= len(chunks) and chunks[number - 1] not in citations:
            citations.append(chunks[number - 1])  # ignore numbers that point past the last passage

    return {"text": reply, "found": True, "citations": citations}
