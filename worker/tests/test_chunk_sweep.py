"""Tests for the chunk size comparison (4_evaluation/chunk_sweep.py). A fake embedder replaces Ollama."""
import zlib
from importlib import import_module

import numpy as np

sweep = import_module("4_evaluation.chunk_sweep")

DIM = 128


def fake_embed(text):
    """A bag-of-words vector: texts that share words point in similar directions. No AI model needed."""
    vector = np.zeros(DIM)
    for word in sweep.normalise(text).split():
        vector[zlib.crc32(word.encode()) % DIM] += 1
    return vector.tolist()


def fake_embed_many(texts):
    return [fake_embed(t) for t in texts]


def document(name, text):
    return {"name": name, "source": "t", "text": text, "hash": name}


def filler(word, count):
    return " ".join(f"{word}{i % 7}" for i in range(count))


def test_normalise_ignores_case_punctuation_and_accents():
    assert sweep.normalise("New-York, N.Y.!") == " new york n y "
    assert sweep.normalise("Café") == sweep.normalise("café")


def test_dates_match_other_ways_of_writing_them():
    variants = sweep.answer_variants("1/22/07")
    assert sweep.normalise("January 22, 2007") in variants
    assert sweep.normalise("22 January 2007") in variants
    assert sweep.normalise("1/22/07") in variants
    assert sweep.answer_variants("New York") == [sweep.normalise("New York")]


def test_file_names_with_spaces_and_commas_are_found_in_the_source():
    names = ["NETGEAR,INC_2003 DISTRIBUTOR AGREEMENT.txt", "other file.txt"]
    source = "NETGEAR,INC_2003 DISTRIBUTOR AGREEMENT.txt, Governing Law"
    assert sweep.files_named_in(source, names) == {"NETGEAR,INC_2003 DISTRIBUTOR AGREEMENT.txt"}


def test_prepare_questions_marks_which_answers_can_be_checked():
    docs = [document("a.txt", "This agreement is governed by the laws of Taiwan. Signed on January 5, 2010.")]
    questions = [
        {"id": 1, "question": "Which law?", "answer": "Taiwan", "source": "a.txt, Governing Law", "answerable": True},
        {"id": 2, "question": "Date?", "answer": "1/5/10", "source": "a.txt, Date", "answerable": True},
        {"id": 3, "question": "Why?", "answer": "Because of the long sentence that is not in the file", "source": "a.txt, X", "answerable": True},
        {"id": 4, "question": "Nothing?", "answer": "none", "source": "none", "answerable": False},
        {"id": 5, "question": "Other file?", "answer": "Taiwan", "source": "missing.txt, X", "answerable": True},
    ]
    prepared = {q["id"]: q for q in sweep.prepare_questions(questions, docs)}
    assert set(prepared) == {1, 2, 3}  # not-found and unknown-file questions are dropped
    assert prepared[1]["variants"] and prepared[2]["variants"]
    assert prepared[3]["variants"] == []  # counts in file hit only


def test_smaller_sizes_make_more_chunks():
    docs = [document("a.txt", filler("w", 1000))]
    small = sweep.build_chunks(docs, 50, 0.2)
    large = sweep.build_chunks(docs, 400, 0.2)
    assert len(small) > len(large)
    assert max(c["words"] for c in small) <= 50 and max(c["words"] for c in large) <= 400


def test_embeddings_are_saved_and_not_computed_twice(tmp_path):
    calls = []

    def embed(texts):
        calls.append(len(texts))
        return fake_embed_many(texts)

    first = sweep.embed_cached(["a b", "c d"], embed, tmp_path, "model")
    second = sweep.embed_cached(["a b", "c d"], embed, tmp_path, "model")
    assert calls == [2]
    assert np.allclose(first, second)
    assert np.allclose(np.linalg.norm(first, axis=1), 1.0)
    sweep.embed_cached(["a b", "c d"], embed, tmp_path, "other-model")
    assert calls == [2, 2]  # a different model never reuses saved vectors


def test_budget_counts_how_many_chunks_collect_enough_words():
    chunks = [{"words": 100}, {"words": 100}, {"words": 100}]
    assert sweep.words_for_budget([0, 1, 2], chunks, 150) == 2
    assert sweep.words_for_budget([0, 1, 2], chunks, 100) == 1
    assert sweep.words_for_budget([0, 1, 2], chunks, 10_000) == 3


def run(docs, questions, sizes, tmp_path, budget=300):
    return sweep.run_sweep(docs, questions, sizes, 0.2, fake_embed_many, fake_embed, tmp_path, "fake", budget)


def test_the_sweep_finds_the_answer_and_reports_every_size(tmp_path):
    needle = "The governing law of this contract is the law of Taiwan and no other place."
    docs = [
        document("target.txt", filler("alpha", 300) + " " + needle + " " + filler("beta", 300)),
        document("other.txt", filler("gamma", 600)),
    ]
    questions = [{"id": 1, "question": "What is the governing law of this contract?", "answer": "Taiwan", "source": "target.txt, Governing Law", "answerable": True}]
    rows = run(docs, questions, [50, 200], tmp_path)
    assert [r["size"] for r in rows] == [50, 200]
    for row in rows:
        assert row["graded"] == 1 and row["questions"] == 1
        assert row["answer_hit@1"] == 1.0 and row["mrr"] == 1.0 and row["file_hit@5"] == 1.0
    assert rows[0]["chunks"] > rows[1]["chunks"]
    assert rows[0]["context_words"] < rows[1]["context_words"]  # small chunks give the model less to read


def test_a_chunk_from_the_wrong_file_does_not_count(tmp_path):
    docs = [
        document("right.txt", filler("alpha", 200)),
        document("wrong.txt", "The governing law of this contract is the law of Taiwan. " + filler("beta", 100)),
    ]
    # the answer is only checked in the named file; right.txt does not contain it, so the question cannot be graded
    questions = [{"id": 1, "question": "What is the governing law of this contract?", "answer": "Taiwan", "source": "right.txt, Governing Law", "answerable": True}]
    row = run(docs, questions, [50], tmp_path)[0]
    assert row["graded"] == 0 and row["answer_hit@5"] is None and row["file_hit@5"] is not None


def test_a_question_about_no_known_document_is_an_error(tmp_path):
    docs = [document("a.txt", filler("x", 100))]
    questions = [{"id": 1, "question": "q", "answer": "a", "source": "zzz.txt, X", "answerable": True}]
    try:
        run(docs, questions, [50], tmp_path)
    except ValueError as error:
        assert "--docs" in str(error)
    else:
        raise AssertionError("expected a ValueError")


def test_results_are_appended_to_a_csv(tmp_path):
    rows = [{"size": 50, "overlap": 10, "chunks": 3, "avg_words": 40.0, "graded": 1, "questions": 1, "file_hit@5": 1.0,
             "hit@budget": 1.0, "mrr": 1.0, "context_words": 200.0, "answer_hit@1": 1.0, "answer_hit@3": 1.0, "answer_hit@5": 1.0}]
    path = tmp_path / "out.csv"
    sweep.save_rows(rows, "contracts-dev.json", path)
    sweep.save_rows(rows, "contracts-dev.json", path)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3 and lines[0].startswith("time,dataset,size")


def test_the_sweep_compares_methods_and_context_lines(tmp_path):
    needle = "2.1. GOVERNING LAW This contract is governed by the law of Taiwan and no other place."
    clauses = "     ".join(f"{i}.1. SECTION{i} " + filler(f"c{i}", 40) for i in range(3, 9))
    docs = [
        document("target.txt", "1.1. INTRO " + filler("alpha", 60) + "     " + needle + "     " + clauses),
        document("other.txt", filler("gamma", 400)),
    ]
    questions = [{"id": 1, "question": "What is the governing law of this contract?", "answer": "Taiwan", "source": "target.txt, Governing Law", "answerable": True}]
    rows = sweep.run_sweep(docs, questions, [60], 0.2, fake_embed_many, fake_embed, tmp_path, "fake", 300,
                           methods=("fixed", "clauses"), contexts=(False, True))
    assert [(r["method"], r["context"]) for r in rows] == [("fixed", "no"), ("fixed", "yes"), ("clauses", "no"), ("clauses", "yes")]
    assert all(r["graded"] == 1 for r in rows)
    assert rows[2]["max_words"] <= 60 * 1.3


def test_context_lines_change_what_is_embedded_but_not_what_is_matched():
    docs = [document("Acme_Agreement.txt", "1.1. TERMS " + filler("a", 30) + "     1.2. MORE " + filler("b", 30) + "     2.1. LAST " + filler("c", 30))]
    plain = sweep.build_chunks(docs, 40, 0.0, "clauses", with_context=False)
    rich = sweep.build_chunks(docs, 40, 0.0, "clauses", with_context=True)
    assert [c["text"] for c in plain] == [c["text"] for c in rich]
    assert all(c["embed"] == c["text"] for c in plain)
    assert all(c["embed"].startswith("Acme Agreement") for c in rich)


def test_an_old_csv_without_the_method_column_is_upgraded(tmp_path):
    path = tmp_path / "old.csv"
    path.write_text("time,dataset,size,chunks\n2026-01-01T00:00:00,old.json,200,10\n", encoding="utf-8")
    sweep.save_rows([{"method": "clauses", "context": "yes", "size": 300, "chunks": 5}], "new.json", path)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "time,dataset,method,context,size,chunks"
    assert lines[1] == "2026-01-01T00:00:00,old.json,fixed,no,200,10"
    assert lines[2].endswith(",new.json,clauses,yes,300,5")
