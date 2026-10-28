import json
from datetime import date

import pytest

from common.cache import BudgetedLLM, BudgetExceeded, CachedEmbedder, CachedLLM
from common.retry import call_with_retries
from tests.fakes import FakeEmbedder, ScriptedLLM


def test_embedding_cache_avoids_repeat_calls(tmp_path):
    inner = FakeEmbedder()
    cached = CachedEmbedder(inner, tmp_path)
    first = cached.embed_documents(["alpha", "beta"])
    second = cached.embed_documents(["alpha", "beta"])
    assert first == second
    assert inner.document_calls == 1


def test_embedding_cache_only_embeds_the_missing_texts(tmp_path):
    inner = FakeEmbedder()
    cached = CachedEmbedder(inner, tmp_path)
    cached.embed_documents(["alpha"])
    cached.embed_documents(["alpha", "beta"])
    assert inner.document_calls == 2


def test_query_and_document_embeddings_are_cached_separately(tmp_path):
    cached = CachedEmbedder(FakeEmbedder(), tmp_path)
    cached.embed_documents(["alpha"])
    cached.embed_query("alpha")
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_llm_cache(tmp_path):
    inner = ScriptedLLM("hello")
    cached = CachedLLM(inner, tmp_path)
    assert cached.complete("p") == cached.complete("p") == "hello"
    assert len(inner.prompts) == 1


def test_daily_budget_stops_calls_and_resets_next_day(tmp_path):
    inner = ScriptedLLM("ok")
    day = {"value": date(2026, 10, 23)}
    budgeted = BudgetedLLM(inner, 2, tmp_path / "usage.json", today=lambda: day["value"])
    budgeted.complete("a")
    budgeted.complete("b")
    with pytest.raises(BudgetExceeded):
        budgeted.complete("c")
    assert len(inner.prompts) == 2
    day["value"] = date(2026, 10, 24)
    assert budgeted.complete("d") == "ok"


def test_decorators_can_be_stacked(tmp_path):
    inner = ScriptedLLM("ok")
    stacked = CachedLLM(BudgetedLLM(inner, 1, tmp_path / "usage.json"), tmp_path / "llm")
    assert stacked.complete("same") == "ok"
    assert stacked.complete("same") == "ok"  # served from cache, so the budget of 1 is not exceeded
    assert len(inner.prompts) == 1


def test_retry_waits_then_succeeds():
    attempts = {"n": 0}
    waits = []

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("rate limit")
        return "done"

    assert call_with_retries(flaky, tries=5, sleep=waits.append) == "done"
    assert waits == [2.0, 4.0]


def test_retry_gives_up_after_the_last_try():
    def always_fails():
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        call_with_retries(always_fails, tries=2, sleep=lambda s: None)
