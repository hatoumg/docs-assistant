"""Download the full FastAPI documentation (English) into data/raw/fastapi-full/.

    python scripts/fetch_fastapi_docs.py

Source: https://github.com/fastapi/fastapi (MIT license, Copyright (c) 2018 Sebastian Ramirez).
Uses only the standard library. Files are flattened ("tutorial/cors.md" becomes "tutorial-cors.md")
so every file name is unique. data/raw/ is git-ignored.
"""
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://github.com/fastapi/fastapi/archive/refs/heads/master.zip"
PREFIX = "docs/en/docs/"
# Pages about the project itself rather than how to use FastAPI. They would only add noise.
SKIP = {
    "release-notes.md", "fastapi-people.md", "contributing.md", "help-fastapi.md", "external-links.md",
    "newsletter.md", "management.md", "management-tasks.md", "translation-banner.md", "about/index.md",
    "benchmarks.md", "history-design-future.md", "editor-support.md",
}
OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "fastapi-full"


def flat_name(relative: str) -> str:
    return relative[:-3].replace("/", "-") + ".md"


def main():
    print(f"Downloading {URL} (about 20 to 60 MB)...")
    request = urllib.request.Request(URL, headers={"User-Agent": "docs-assistant"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    OUT.mkdir(parents=True, exist_ok=True)
    kept = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.namelist():
            marker = member.find(PREFIX)
            if marker == -1 or not member.endswith(".md"):
                continue
            relative = member[marker + len(PREFIX):]
            if relative in SKIP or relative.startswith(("img/", "css/", "js/")) or Path(relative).name.startswith("_"):
                continue
            (OUT / flat_name(relative)).write_bytes(archive.read(member))
            kept += 1
    print(f"Saved {kept} Markdown files to {OUT}")
    if kept < 50:
        sys.exit("Fewer files than expected. The repository layout may have changed.")


if __name__ == "__main__":
    main()
