"""Wrappers that add behaviour around an answering model without changing it.

CachedLLM    remembers answers on disk, so repeat runs cost nothing.
BudgetedLLM  refuses to call the model after a daily limit.
Each wraps another object that has the same methods, so they can be stacked in any order.
"""
import hashlib
import json
from datetime import date
from pathlib import Path


class BudgetExceeded(RuntimeError):
    pass


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
