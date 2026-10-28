"""Download CUAD (contracts as text, plus the answer spreadsheet) from Hugging Face into data/raw/cuad-download/.

    pip install huggingface_hub
    python scripts/fetch_cuad.py
    python scripts/prepare_cuad.py data/raw/cuad-download --dev 25 --test 25

CUAD: The Atticus Project, CC BY 4.0. Only the text contracts and master_clauses.csv are fetched
(the PDFs are skipped), which keeps the download much smaller than the full 159 MB.
"""
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "cuad-download"


def main():
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        sys.exit("Run: pip install huggingface_hub")
    snapshot_download(
        repo_id="theatticusproject/cuad",
        repo_type="dataset",
        allow_patterns=["CUAD_v1/master_clauses.csv", "CUAD_v1/full_contract*txt/*", "CUAD_v1/*README*"],
        local_dir=str(OUT),
    )
    csv_files = list(OUT.rglob("master_clauses.csv"))
    txt_files = list(OUT.rglob("*.txt"))
    print(f"Saved to {OUT}: {len(csv_files)} master_clauses.csv, {len(txt_files)} text files")
    if not csv_files or len(txt_files) < 100:
        sys.exit("The download looks incomplete. Open https://huggingface.co/datasets/theatticusproject/cuad/tree/main/CUAD_v1 to check the folder names.")


if __name__ == "__main__":
    main()
