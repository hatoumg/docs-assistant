import csv
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "prepare_cuad.py"


def load_script():
    spec = importlib.util.spec_from_file_location("prepare_cuad", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_cuad(root, count=8):
    texts = root / "full_contract_txt" / "Part_I"  # the real download nests the files like this
    texts.mkdir(parents=True)
    with (root / "master_clauses.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Filename", "Document Name", "Document Name-Answer", "Parties-Answer", "Agreement Date-Answer", "Expiration Date-Answer", "Governing Law-Answer"])
        for i in range(count):
            writer.writerow([f"Contract{i}.PDF" if i % 2 else f"Contract{i}.pdf", "", "Services Agreement", f"['Acme {i} Inc.', 'Beta {i} LLC']", "1/2/2020", "" if i == 0 else "1/2/2025", "State of Delaware"])
            (texts / f"Contract{i}.txt").write_text(f"Agreement number {i}")
    decoy = root / ".cache" / "huggingface" / "full_contract_txt"  # an empty folder like the one Hugging Face leaves behind
    decoy.mkdir(parents=True)
    return root


def test_cuad_script_splits_by_document_and_writes_labelled_questions(tmp_path):
    module = load_script()
    root = fake_cuad(tmp_path / "cuad")
    csv_path, txt_dir = module.find_files(root)
    rows = module.read_rows(csv_path, txt_dir)
    dev, test = module.build(rows, 3, seed=1)
    module.write_set(dev, "dev", tmp_path / "docs" / "cuad-dev", tmp_path / "evals" / "contracts-dev.json")
    module.write_set(test, "test", tmp_path / "docs" / "cuad-test", tmp_path / "evals" / "contracts-test.json")
    dev_files = {p.name for p in (tmp_path / "docs" / "cuad-dev").iterdir()}
    test_files = {p.name for p in (tmp_path / "docs" / "cuad-test").iterdir()}
    assert len(dev_files) == len(test_files) == 3 and not dev_files & test_files
    questions = json.loads((tmp_path / "evals" / "contracts-dev.json").read_text())
    first = questions[0]
    assert first["question"].startswith("What law governs the Services Agreement between Acme")
    assert "Acme" in first["question"] and " and Beta" in first["question"] and "[" not in first["question"]
    assert first["answer"] == "State of Delaware" and first["source"].split(",")[0] in dev_files
    assert [q["kind"] for q in questions].count("not-found") == 3
    assert [q["id"] for q in questions] == list(range(1, len(questions) + 1))


def test_cuad_script_names_the_missing_columns(tmp_path):
    module = load_script()
    root = tmp_path / "cuad"
    (root / "full_contract_txt").mkdir(parents=True)
    (root / "master_clauses.csv").write_text("Filename,Something Else\nA.pdf,x\n")
    with pytest.raises(SystemExit) as error:
        module.read_rows(root / "master_clauses.csv", root / "full_contract_txt")
    assert "Governing Law-Answer" in str(error.value)
