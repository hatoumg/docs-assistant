"""Tests for the plain step-by-step version (1_indexing ... 4_evaluation).

Database and AI calls are replaced by small fakes, so these run without Docker or API keys.
"""
import csv
import json
from importlib import import_module

from common.loader import load

index_main = import_module("1_indexing.main")
retrieval_main = import_module("2_retrieval.main")
generate_step = import_module("3_generation.2_generate")
eval_main = import_module("4_evaluation.main")
load_documents = load("1_indexing.1_load", "load_documents")
clean_text = load("1_indexing.2_clean", "clean_text")
split_documents, split_text = load("1_indexing.3_chunk", "split_documents", "split_text")
transform_query = load("2_retrieval.1_query", "transform_query")
merge_results = load("2_retrieval.3_merge", "merge_results")
rerank = load("2_retrieval.4_rerank", "rerank")
answer_from_chunks = load("3_generation.main", "answer_from_chunks")
build_prompt = load("3_generation.1_prompt", "build_prompt")
check_answer = load("3_generation.3_check", "check_answer")
load_questions = load("4_evaluation.1_questions", "load_questions")
score_retrieval = load("4_evaluation.2_retrieval_scores", "score_retrieval")
did_pass, parse_scores = load("4_evaluation.3_judge", "did_pass", "parse_scores")
save_rows, summarise = load("4_evaluation.4_report", "save_rows", "summarise")


def chunk(id, name="a.md", position=0, text="text", score=0.5):
    return {"id": id, "name": name, "source": "s", "position": position, "text": text, "score": score}


# ----- Phase 1 -----


def test_load_skips_unwanted_files(tmp_path):
    (tmp_path / "a.md").write_text("alpha")
    (tmp_path / "b.txt").write_text("beta")
    (tmp_path / "SOURCE.md").write_text("notes")
    (tmp_path / "LICENSE-MIT.txt").write_text("licence")
    (tmp_path / "c.pdf").write_bytes(b"%PDF")
    docs = load_documents(tmp_path)
    assert [d["name"] for d in docs] == ["a.md", "b.txt"]
    assert docs[0]["source"] == tmp_path.name and len(docs[0]["hash"]) == 64


def test_clean_text_removes_noise():
    raw = "# Title { #title }\n\n{* ../code.py *}\n\n\n\n/// tip\nUse <b>bold</b> words\n///\n<img src='x'>\n"
    cleaned = clean_text(raw)
    assert cleaned == "# Title\n\nUse bold words"


def test_split_text_overlaps_and_ends():
    text = " ".join(f"w{i}" for i in range(100))
    chunks = split_text(text, chunk_size=30, overlap=10)
    assert [len(c.split()) for c in chunks] == [30, 30, 30, 30, 20]
    assert chunks[0].split()[-10:] == chunks[1].split()[:10]  # the overlap
    assert chunks[-1].endswith("w99")


def test_short_text_is_one_chunk_and_empty_is_none():
    assert split_text("just a few words", 30, 10) == ["just a few words"]
    assert split_text("", 30, 10) == []


def test_split_documents_labels_every_chunk():
    docs = [{"name": "a.md", "source": "s", "hash": "h1", "text": " ".join(["w"] * 70)}]
    chunks = split_documents(docs, chunk_size=30, overlap=10)
    assert [c["position"] for c in chunks] == [0, 1, 2]
    assert all(c["name"] == "a.md" and c["hash"] == "h1" for c in chunks)


def test_index_folder_runs_the_steps_in_order(tmp_path, monkeypatch):
    (tmp_path / "a.md").write_text("one two three " * 100)
    calls = []
    monkeypatch.setattr(index_main, "skip_already_stored", lambda docs: calls.append("skip") or docs)
    monkeypatch.setattr(index_main, "embed_chunks", lambda chunks: calls.append("embed") or [[0.0]] * len(chunks))
    monkeypatch.setattr(index_main, "save_chunks", lambda chunks, vectors: calls.append(("save", len(chunks), len(vectors))))
    index_main.index_folder(tmp_path)
    assert calls[0] == "skip" and calls[1] == "embed"
    assert calls[2][0] == "save" and calls[2][1] == calls[2][2] > 1


def test_nothing_new_stops_early(tmp_path, monkeypatch):
    (tmp_path / "a.md").write_text("words")
    monkeypatch.setattr(index_main, "skip_already_stored", lambda docs: [])
    monkeypatch.setattr(index_main, "embed_chunks", lambda chunks: 1 / 0)  # must not be reached
    index_main.index_folder(tmp_path)


# ----- Phase 2 -----


def test_transform_query_trims():
    assert transform_query("  hello?  ") == ["hello?"]


def test_merge_keeps_best_score_without_repeats():
    first = [chunk(1, score=0.9), chunk(2, score=0.5)]
    second = [chunk(2, score=0.8), chunk(3, score=0.7)]
    merged = merge_results([first, second], k=3)
    assert [c["id"] for c in merged] == [1, 2, 3] and merged[1]["score"] == 0.8
    assert len(merge_results([first, second], k=2)) == 2


def test_rerank_changes_nothing():
    chunks = [chunk(1), chunk(2)]
    assert rerank("q", chunks) == chunks


def test_retrieve_runs_search_for_each_query(monkeypatch):
    seen = []
    monkeypatch.setattr(retrieval_main, "transform_query", lambda q: [q, q + " again"])
    monkeypatch.setattr(retrieval_main, "search_chunks", lambda q, k, sources: seen.append((q, sources)) or [chunk(len(seen), score=1 / len(seen))])
    result = retrieval_main.retrieve("cors", sources=["s"], k=5)
    assert seen == [("cors", ["s"]), ("cors again", ["s"])] and len(result) == 2


# ----- Phase 3 -----


def test_prompt_numbers_the_passages():
    prompt = build_prompt("What?", [chunk(1, "cors.md", 0, "first text"), chunk(2, "tasks.md", 3, "second text")])
    assert "[1] (from cors.md, part 1)\nfirst text" in prompt and "[2] (from tasks.md, part 4)" in prompt
    assert prompt.rstrip().endswith("Question: What?\nAnswer:")


def test_check_answer_finds_citations_and_ignores_bad_numbers():
    chunks = [chunk(1, "a.md"), chunk(2, "b.md")]
    result = check_answer("It is 600 [1] and also [2][1][9].", chunks)
    assert result["found"] and [c["name"] for c in result["citations"]] == ["a.md", "b.md"]


def test_check_answer_handles_fullwidth_brackets_and_not_found():
    chunks = [chunk(1)]
    assert len(check_answer("Answer【1】", chunks)["citations"]) == 1
    nothing = check_answer("NOT_FOUND", chunks)
    assert nothing["found"] is False and nothing["text"] == "Not found in the documents."
    assert check_answer("anything", [])["found"] is False


def test_answer_from_chunks_uses_the_model_reply(monkeypatch):
    prompts = []
    monkeypatch.setattr(generate_step, "ask_llm", lambda p: prompts.append(p) or "Done [1]")
    answer = answer_from_chunks("Q?", [chunk(1, "a.md", text="the passage")])
    assert answer["text"] == "Done [1]" and answer["citations"][0]["name"] == "a.md"
    assert "the passage" in prompts[0] and answer["chunks"][0]["name"] == "a.md"


# ----- Phase 4 -----


def write_questions(path):
    path.write_text(json.dumps([
        {"id": 1, "kind": "direct", "question": "Q1?", "answer": "A1", "source": "a.md, Section"},
        {"id": 2, "kind": "not-found", "question": "Q2?", "answer": "none", "source": "none"},
    ]))
    return path


def test_load_questions_reads_files_and_answerable(tmp_path):
    questions = load_questions(write_questions(tmp_path / "q.json"))
    assert questions[0]["files"] == {"a.md"} and questions[0]["answerable"]
    assert questions[1]["files"] == set() and not questions[1]["answerable"]
    assert len(load_questions(tmp_path / "q.json", limit=1)) == 1


def test_retrieval_score():
    question = {"files": {"b.md"}}
    assert score_retrieval(question, [chunk(1, "a.md"), chunk(2, "b.md")]) == {"rank": 2, "hit": True, "reciprocal_rank": 0.5}
    assert score_retrieval(question, [chunk(1, "a.md")])["hit"] is False


def test_judge_reply_parsing_and_pass_rule():
    scores = parse_scores('```json\n{"correctness": 2, "faithfulness": 9, "citation": 1, "reason": "ok"}\n```')
    assert (scores["correctness"], scores["faithfulness"], scores["citation"]) == (2, 2, 1)
    question = {"answerable": True}
    assert did_pass(question, {"found": True}, scores)
    assert not did_pass(question, {"found": True}, {**scores, "correctness": 1})
    assert did_pass({"answerable": False}, {"found": False}, scores)
    assert not did_pass({"answerable": False}, {"found": True}, scores)


def test_run_evaluation_retrieval_only_skips_not_found_and_model_calls(tmp_path, monkeypatch):
    path = write_questions(tmp_path / "q.json")
    monkeypatch.setattr(eval_main, "retrieve", lambda q, sources: [chunk(1, "a.md")])
    monkeypatch.setattr(eval_main, "answer_from_chunks", lambda q, c: 1 / 0)
    rows = eval_main.run_evaluation(str(path), retrieval_only=True, save=False)
    assert len(rows) == 1 and rows[0]["hit"] and rows[0]["passed"] is None


def test_run_evaluation_full_run_and_csv(tmp_path, monkeypatch):
    path = write_questions(tmp_path / "q.json")
    monkeypatch.setattr(eval_main, "retrieve", lambda q, sources: [chunk(1, "a.md")])
    monkeypatch.setattr(eval_main, "answer_from_chunks", lambda q, c: {"text": "T", "found": q == "Q1?", "citations": [], "chunks": c})
    monkeypatch.setattr(eval_main, "judge_answer", lambda q, a: {"correctness": 2, "faithfulness": 2, "citation": 2, "reason": ""})
    monkeypatch.setattr(eval_main, "RESULTS_FILE", tmp_path / "out" / "results.csv")
    rows = eval_main.run_evaluation(str(path))
    assert [r["passed"] for r in rows] == [True, True]  # Q2 is not-found and the system admitted it
    summary = summarise(rows)
    assert summary["hit_at_k"] == 1.0 and summary["pass_rate"] == 1.0
    with (tmp_path / "out" / "results.csv").open() as handle:
        assert len(list(csv.DictReader(handle))) == 2
