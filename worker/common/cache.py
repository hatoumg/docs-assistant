"""Wrappers that add behaviour around an embedder or an LLM without changing it.

CachedEmbedder / CachedLLM  remember results on disk, so repeat runs cost nothing.
BudgetedLLM                 refuses to call the model after a daily limit.
Each wraps another object that has the same methods, so they can be stacked in any order.
"""
import hashlib
import json
from datetime import date
from pathlib import Path


DOCUMENT_TASK = "RETRIEVAL_DOCUMENT"
QUERY_TASK = "RETRIEVAL_QUERY"


class BudgetExceeded(RuntimeError):
    pass


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CachedEmbedder:
    def __init__(self, inner, cache_dir):
        self._inner = inner
        self._dir = Path(cache_dir)

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    def _path(self, task: str, text: str) -> Path:
        return self._dir / f"{_digest(f'{self._inner.model_id}|{task}|{text}')}.json"

    def _embed_cached(self, texts, task, embed_missing):
        self._dir.mkdir(parents=True, exist_ok=True)
        vectors = [None] * len(texts)
        missing = []
        for i, text in enumerate(texts):
            path = self._path(task, text)
            if path.exists():
                vectors[i] = json.loads(path.read_text())
            else:
                missing.append(i)
        if missing:
            fresh = embed_missing([texts[i] for i in missing])
            for i, vector in zip(missing, fresh):
                vectors[i] = vector
                self._path(task, texts[i]).write_text(json.dumps(vector))
        return vectors

    def embed_documents(self, texts: list) -> list:
        return self._embed_cached(texts, DOCUMENT_TASK, self._inner.embed_documents)

    def embed_query(self, text: str) -> list:
        return self._embed_cached([text], QUERY_TASK, lambda items: [self._inner.embed_query(items[0])])[0]


class CachedLLM:
    def __init__(self, inner, cache_dir):
        self._inner = inner
        self._dir = Path(cache_dir)

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    def complete(self, prompt: str) -> str:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{_digest(f'{self._inner.model_id}|{prompt}')}.txt"
        if path.exists():
            return path.read_text(encoding="utf-8")
        text = self._inner.complete(prompt)
        path.write_text(text, encoding="utf-8")
        return text


class BudgetedLLM:
    def __init__(self, inner, daily_cap: int, counter_path, today=date.today):
        self._inner = inner
        self._cap = daily_cap
        self._path = Path(counter_path)
        self._today = today

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    def _read(self) -> dict:
        try:
            return json.loads(self._path.read_text())
        except (FileNotFoundError, ValueError):
            return {}

    def calls_today(self) -> int:
        return self._read().get(self._today().isoformat(), 0)

    def complete(self, prompt: str) -> str:
        counts = self._read()
        key = self._today().isoformat()
        if counts.get(key, 0) >= self._cap:
            raise BudgetExceeded(
                f"Daily limit of {self._cap} model calls reached. Raise MAX_REQUESTS_PER_DAY in .env or wait until tomorrow."
            )
        counts = {key: counts.get(key, 0) + 1}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(counts))
        return self._inner.complete(prompt)
