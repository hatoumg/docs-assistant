"""Tests for the chunking methods in 1_indexing/3_chunk.py (fixed, recursive, headings, clauses, auto)."""
from common.loader import load

make_chunks, split_text, split_documents, choose_method, method_for, clause_label, title_from_name, count_words = load(
    "1_indexing.3_chunk", "make_chunks", "split_text", "split_documents", "choose_method", "method_for",
    "clause_label", "title_from_name", "count_words")
text_to_embed = load("1_indexing.4_embed", "text_to_embed")


def sentences(word, count, length=10):
    """`count` sentences of `length` words each, all starting with a capital."""
    return " ".join(f"{word.capitalize()} " + " ".join(f"{word}{i}x{j}" for j in range(length - 1)) + "." for i in range(count))


def paragraphs(word, count, sentences_each=3):
    return "\n\n".join(sentences(f"{word}{p}", sentences_each) for p in range(count))


MARKDOWN = "# Guide\n\nIntro text here.\n\n## Install\n\n" + sentences("install", 8) + \
    "\n\n```bash\n\npip install thing\n\n```\n\n## Use\n\n### Options\n\n" + sentences("option", 8)

CONTRACT = (
    "DISTRIBUTOR AGREEMENT This agreement is made between Acme and Beta.     "
    "1. DEFINITIONS 1.1. \"Product\" means the goods sold by Acme.     1.2. \"Territory\" means Canada.     "
    "2. APPOINTMENT 2.1. Appointment. Acme appoints Beta as its distributor.     "
    "2.2. Term. " + sentences("term", 12) + "     "
    "3.0 GOVERNING LAW This Agreement is governed by the laws of New York. It lasts 30 Days after notice."
)


def test_fixed_is_the_old_behaviour():
    text = " ".join(f"w{i}" for i in range(100))
    chunks = split_text(text, 30, 10)
    assert [count_words(c) for c in chunks] == [30, 30, 30, 30, 20]
    assert chunks[0].split()[-10:] == chunks[1].split()[:10]
    assert split_text("", 30, 10) == [] and split_text("a few words", 30, 10) == ["a few words"]


def test_recursive_keeps_paragraphs_whole_when_they_fit():
    text = paragraphs("p", 6)  # six paragraphs of 30 words
    for chunk in split_text(text, 70, 0, method="recursive"):
        assert count_words(chunk) <= 70
        assert all(part in text.split("\n\n") for part in chunk.split("\n\n"))  # never cut inside a paragraph


def test_recursive_cuts_a_long_paragraph_at_sentence_ends():
    chunks = split_text(sentences("long", 20), 50, 0, method="recursive")  # one paragraph of 200 words
    assert len(chunks) >= 4
    assert all(c.endswith(".") and count_words(c) <= 50 for c in chunks)


def test_every_word_ends_up_in_a_chunk():
    text = paragraphs("p", 7) + "\n\n" + " ".join(["word"] * 120)  # the last paragraph has no sentence ends
    assert sum(count_words(c) for c in split_text(text, 50, 0, method="recursive")) == count_words(text)


def test_headings_start_new_chunks_and_give_the_section_path():
    chunks = make_chunks(MARKDOWN, "headings", chunk_size=60, overlap=0, title="Thing docs")
    starts = {c["text"].split("\n")[0]: c["context"] for c in chunks}
    assert starts["### Options"] == "Thing docs > Guide > Use > Options"
    assert any(text.startswith("## Install") for text in starts)


def test_headings_keep_a_small_code_block_whole():
    holding = [c for c in split_text(MARKDOWN, 60, 0, method="headings") if "pip install thing" in c]
    assert len(holding) == 1 and holding[0].count("```") == 2


def test_clauses_start_new_chunks_and_name_their_clause():
    chunks = make_chunks(CONTRACT, "clauses", chunk_size=40, overlap=0, title="Acme Agreement")
    law = [c for c in chunks if "New York" in c["text"]][0]
    assert law["text"].startswith("3.0 GOVERNING LAW")
    assert law["context"] == "Acme Agreement > 3.0 GOVERNING LAW"
    assert "30 Days" in law["text"]  # "30" has no dot, so it is not a clause number


def test_clause_labels():
    assert clause_label("14. GOVERNING LAW This Agreement is governed") == "14. GOVERNING LAW"
    assert clause_label("2.2. Term. This Agreement lasts three years.") == "2.2. Term"
    assert clause_label('1.1. "Product" means the goods sold by Acme.') == "1.1."


def test_text_without_clause_numbers_is_cut_like_recursive():
    text = paragraphs("plain", 5)
    assert split_text(text, 40, 0, method="clauses") == split_text(text, 40, 0, method="recursive")


def test_auto_chooses_by_looking_at_the_text():
    assert choose_method(MARKDOWN) == "headings"
    assert choose_method(CONTRACT * 2) == "clauses"
    assert choose_method(paragraphs("plain", 3)) == "recursive"


def test_the_document_type_chooses_the_method():
    doc = {"text": paragraphs("plain", 3)}
    assert method_for({**doc, "doc_type": "contract"}) == "clauses"
    assert method_for({**doc, "doc_type": "Technical"}) == "headings"
    assert method_for({**doc, "doc_type": "unknown"}, default="recursive") == "recursive"
    assert method_for({**doc, "method": "auto"}) == "recursive"


def test_unknown_method_is_an_error():
    try:
        make_chunks("some text", "magic")
    except ValueError as error:
        assert "magic" in str(error)
    else:
        raise AssertionError("expected a ValueError")


def test_split_documents_adds_context_and_method():
    docs = [{"name": "Acme_Distributor Agreement.txt", "source": "s", "hash": "h", "text": CONTRACT, "doc_type": "contract"}]
    chunks = split_documents(docs, chunk_size=40, overlap=0)
    assert all(c["method"] == "clauses" for c in chunks)
    assert all(c["context"].startswith("Acme Distributor Agreement") for c in chunks)
    assert [c["position"] for c in chunks] == list(range(len(chunks)))


def test_the_context_line_is_only_embedded_when_asked():
    chunk = {"text": "body", "context": "Doc > Section"}
    assert text_to_embed(chunk, with_context=False) == "body"
    assert text_to_embed(chunk, with_context=True) == "Doc > Section\n\nbody"
    assert text_to_embed({"text": "body", "context": ""}, with_context=True) == "body"


def test_title_from_file_name():
    assert title_from_name("Acme_Inc_Distributor Agreement.txt") == "Acme Inc Distributor Agreement"


def test_an_upload_is_cut_with_the_method_for_the_type_the_user_picked(tmp_path, monkeypatch):
    from importlib import import_module

    index_main = import_module("1_indexing.main")
    path = tmp_path / "deal.txt"
    path.write_text(CONTRACT, encoding="utf-8")
    saved = []
    monkeypatch.setattr(index_main, "embed_chunks", lambda chunks: [[0.0]] * len(chunks))
    monkeypatch.setattr(index_main, "save_document_chunks", lambda document_id, chunks, vectors: saved.extend(chunks))
    index_main.index_upload(7, path, "deal.txt", "h", "contract")
    assert saved and all(c["method"] == "clauses" for c in saved)
