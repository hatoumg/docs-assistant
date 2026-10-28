import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parent / ".env")


def main():
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for f in sorted((ROOT / "migrations").glob("*.sql")):
            print("Applying", f.name)
            conn.execute(f.read_text())


if __name__ == "__main__":
    main()
