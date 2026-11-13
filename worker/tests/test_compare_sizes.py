"""Tests for the chunk size answer-quality comparison (4_evaluation/compare_sizes.py). No database or AI calls."""
import subprocess
import sys
from importlib import import_module
from pathlib import Path

compare_sizes = import_module("4_evaluation.compare_sizes")
files_in_source = import_module("4_evaluation.1_questions").files_in_source
WORKER = Path(__file__).resolve().parents[1]


def row(id, passed, answerable=True, correctness=2, faithfulness=2, citation=2, hit=True):
    return {"id": id, "kind": "direct" if answerable else "not-found", "question": f"question {id}", "answerable": answerable,
            "passed": passed, "correctness": correctness, "faithfulness": faithfulness, "citation": citation,
            "hit": hit, "reciprocal_rank": 1.0 if hit else 0.0, "rank": 1 if hit else None, "found": answerable}


def test_file_names_with_spaces_and_commas_are_read_from_the_source():
    assert files_in_source("NETGEAR,INC_04_21_2003-EX-10.16-DISTRIBUTOR AGREEMENT.txt, Governing Law") == {"NETGEAR,INC_04_21_2003-EX-10.16-DISTRIBUTOR AGREEMENT.txt"}
    assert files_in_source("a.md, Wildcards section; b c.md, note") == {"a.md", "b c.md"}
    assert files_in_source("fastapi-response-status-code.md") == {"fastapi-response-status-code.md"}
    assert files_in_source("none") == set()


def test_summary_numbers_for_one_size():
    rows = [row(1, True), row(2, False, correctness=1), row(3, True), row(4, True, answerable=False, correctness=0, faithfulness=0, citation=0, hit=False)]
    summary = compare_sizes.summarise_size(rows)
    assert summary["questions"] == 4
    assert summary["pass_rate"] == 3 / 4
    assert summary["answerable_pass_rate"] == 2 / 3
    assert summary["correct"] == 2 / 3
    assert summary["not_found_ok"] == 1.0
    assert summary["right_file@k"] == 1.0  # not-found questions are left out of the file score


def test_questions_where_sizes_disagree_are_listed():
    results = {300: [row(1, True), row(2, True), row(3, False)], 500: [row(1, True), row(2, False), row(3, False)]}
    found = compare_sizes.differences(results)
    assert [(i, outcomes) for i, _, outcomes in found] == [(2, {300: True, 500: False})]


def test_every_size_is_indexed_before_it_is_scored():
    steps = []
    results = compare_sizes.compare(
        [300, 500],
        index_size=lambda size: steps.append(("index", size)),
        evaluate_size=lambda size: steps.append(("score", size)) or [row(1, True)],
    )
    assert steps == [("index", 300), ("score", 300), ("index", 500), ("score", 500)]
    assert list(results) == [300, 500]


def test_each_size_gets_its_own_index_and_a_fifth_overlap():
    environment = compare_sizes.size_environment(500)
    assert environment["RAG_COLLECTION"] == "size-500w"
    assert environment["RAG_CHUNK_WORDS"] == "500" and environment["RAG_OVERLAP_WORDS"] == "100"


def read_config(**environment):
    """The chunk settings a fresh process sees with the given environment variables."""
    code = "from common.config import COLLECTION, CHUNK_SIZE_WORDS, CHUNK_OVERLAP_WORDS; print(COLLECTION, CHUNK_SIZE_WORDS, CHUNK_OVERLAP_WORDS)"
    import os
    clean = {k: v for k, v in os.environ.items() if not k.startswith("RAG_")}
    return subprocess.run([sys.executable, "-c", code], cwd=WORKER, env={**clean, **environment}, capture_output=True, text=True, check=True).stdout.split()


def test_settings_default_to_the_normal_values_and_can_be_overridden():
    assert read_config() == ["simple-nomic", "200", "40"]
    assert read_config(RAG_COLLECTION="size-300w", RAG_CHUNK_WORDS="300", RAG_OVERLAP_WORDS="60") == ["size-300w", "300", "60"]
    assert read_config(RAG_CHUNK_WORDS="500") == ["simple-nomic", "500", "100"]  # overlap follows the size when not given


def test_summaries_are_appended_to_a_csv(tmp_path):
    summaries = {300: compare_sizes.summarise_size([row(1, True)]), 500: compare_sizes.summarise_size([row(1, False)])}
    path = tmp_path / "out.csv"
    compare_sizes.save_rows(summaries, "contracts-dev.json", path)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3 and lines[0].startswith("time,dataset,size,questions,pass_rate")


def test_failed_questions_are_listed_with_the_judges_reason():
    failed = row(2, False)
    failed.update({"reason": "The answer names the wrong state.", "answer": "Delaware"})
    results = {300: [row(1, True), failed], 500: [row(1, True), row(2, True)]}
    assert compare_sizes.failures(results) == [(300, 2, "question 2", "The answer names the wrong state.", "Delaware")]
