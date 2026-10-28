import json

import pytest

from common.fallback import FallbackLLM
from common.openai_compatible import LLMRequestError, OpenAICompatibleLLM, is_transient
from common.providers import PRESETS, create_provider_llm, model_for
from common.models import build_llm
from common.settings import Settings, load_settings
from common.usage import UsageMeter
from tests.fakes import ScriptedLLM


def reply(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def adapter(post, retries=3, waits=None):
    return OpenAICompatibleLLM("groq", "https://example.test/v1/", "k", "m", retries, UsageMeter(), post=post, sleep=(waits.append if waits is not None else lambda s: None))


def test_request_is_built_in_the_openai_format():
    seen = {}

    def post(url, headers, payload, timeout):
        seen.update(url=url, headers=headers, payload=payload)
        return reply("hi")

    llm = adapter(post)
    assert llm.complete("question?") == "hi"
    assert seen["url"] == "https://example.test/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer k"
    assert seen["payload"] == {"model": "m", "temperature": 0, "messages": [{"role": "user", "content": "question?"}]}
    assert llm.model_id == "groq:m"


def test_rate_limits_are_retried():
    attempts, waits = [], []

    def post(url, headers, payload, timeout):
        attempts.append(1)
        if len(attempts) < 3:
            raise LLMRequestError("HTTP 429", 429)
        return reply("ok")

    assert adapter(post, waits=waits).complete("p") == "ok"
    assert len(attempts) == 3 and waits == [2.0, 4.0]


def test_a_wrong_key_is_not_retried():
    attempts = []

    def post(url, headers, payload, timeout):
        attempts.append(1)
        raise LLMRequestError("HTTP 401", 401)

    with pytest.raises(LLMRequestError):
        adapter(post).complete("p")
    assert len(attempts) == 1


def test_transient_classification():
    assert is_transient(LLMRequestError("x", 503)) and is_transient(LLMRequestError("x", 429)) and is_transient(LLMRequestError("x"))
    assert not is_transient(LLMRequestError("x", 400)) and not is_transient(LLMRequestError("x", 404))


def test_an_odd_reply_gives_a_clear_error():
    with pytest.raises(LLMRequestError):
        adapter(lambda *a: {"error": "nope"}, retries=1).complete("p")


# ----- fallback -----


class Failing(ScriptedLLM):
    def complete(self, prompt):
        raise RuntimeError("503 busy")


def test_fallback_uses_the_next_model_when_the_first_fails():
    second = ScriptedLLM("from second")
    chain = FallbackLLM([Failing(), second])
    assert chain.complete("p") == "from second"


def test_fallback_skips_later_models_when_the_first_works():
    second = ScriptedLLM("from second")
    assert FallbackLLM([ScriptedLLM("from first"), second]).complete("p") == "from first"
    assert second.prompts == []


def test_fallback_raises_the_last_error_when_all_fail():
    with pytest.raises(RuntimeError):
        FallbackLLM([Failing(), Failing()]).complete("p")


# ----- settings and wiring -----


def test_default_provider_is_gemini():
    settings = load_settings({"GEMINI_API_KEY": "g"})
    assert settings.llm_provider == "gemini" and settings.llm_fallbacks == ()


def test_settings_read_provider_fallback_keys_and_models():
    settings = load_settings(
        {"LLM_PROVIDER": "Groq", "LLM_FALLBACK": "openrouter, gemini", "GROQ_API_KEY": "gk", "GROQ_MODEL": "my-model", "GEMINI_API_KEY": "g"}
    )
    assert settings.llm_provider == "groq"
    assert settings.llm_fallbacks == ("openrouter", "gemini")
    assert settings.provider_keys["groq"] == "gk"
    assert model_for("groq", settings) == "my-model"
    assert model_for("mistral", settings) == PRESETS["mistral"].default_model
    assert model_for("groq", settings, "override") == "override"


def test_missing_key_names_the_variable_to_set():
    with pytest.raises(RuntimeError) as error:
        create_provider_llm("groq", "m", Settings(), UsageMeter())
    assert "GROQ_API_KEY" in str(error.value)


def test_unknown_provider_lists_the_choices():
    with pytest.raises(ValueError) as error:
        create_provider_llm("nope", "m", Settings(), UsageMeter())
    assert "groq" in str(error.value)


def test_build_llm_chains_providers_and_applies_the_judge_override_to_the_first_only(tmp_path):
    settings = Settings(llm_provider="groq", llm_fallbacks=("gemini",), cache_dir=tmp_path)
    built = []

    class Named(ScriptedLLM):
        def __init__(self, provider, model):
            super().__init__(f"{provider} answer")
            self.name = f"{provider}:{model}"

        @property
        def model_id(self):
            return self.name

    def factory(provider, model, settings, usage):
        built.append((provider, model))
        return Named(provider, model)

    chain = build_llm(settings, UsageMeter(), "judge", "big-model", factory=factory)
    assert built == [("groq", "big-model"), ("gemini", settings.llm_model)]
    assert chain.complete("p") == "groq answer"


def test_single_provider_has_no_fallback_wrapper(tmp_path):
    settings = Settings(cache_dir=tmp_path)
    llm = build_llm(settings, UsageMeter(), "llm", factory=lambda *a: ScriptedLLM("x"))
    assert not isinstance(llm, FallbackLLM)


def test_a_used_up_budget_hands_over_to_the_fallback(tmp_path):
    settings = Settings(llm_provider="groq", llm_fallbacks=("gemini",), cache_dir=tmp_path, daily_llm_call_cap=1)
    models = {"groq": ScriptedLLM("groq answer"), "gemini": ScriptedLLM("gemini answer")}
    chain = build_llm(settings, UsageMeter(), "llm", factory=lambda p, m, s, u: models[p])
    assert chain.complete("one") == "groq answer"
    assert chain.complete("two") == "gemini answer"  # groq's cap of 1 is spent


def test_gemini_errors_are_classified_by_code():
    from common.gemini import is_transient as gemini_transient

    class Err(Exception):
        def __init__(self, code):
            self.code = code

    assert gemini_transient(Err(503)) and gemini_transient(Err(429)) and gemini_transient(RuntimeError("network"))
    assert not gemini_transient(Err(404)) and not gemini_transient(Err(400))


# ----- pacing and rate-limit hints -----


def test_wait_time_is_read_from_the_providers_message():
    from common.openai_compatible import suggested_wait

    assert suggested_wait(LLMRequestError("limit. Please try again in 7.2s.", 429)) == 8.2
    assert suggested_wait(LLMRequestError("Please try again in 1m2.5s", 429)) == 63.5
    assert suggested_wait(LLMRequestError("Please try again in 850ms", 429)) < 2
    assert suggested_wait(LLMRequestError("something else", 429)) is None


def test_the_providers_wait_hint_replaces_the_doubling_delay():
    waits, attempts = [], []

    def post(url, headers, payload, timeout):
        attempts.append(1)
        if len(attempts) == 1:
            raise LLMRequestError("Please try again in 20s", 429)
        return reply("ok")

    assert adapter(post, waits=waits).complete("p") == "ok"
    assert waits == [21.0]


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.waits = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


def throttled(limit, inner=None):
    from common.throttle import ThrottledLLM

    c = FakeClock()
    return ThrottledLLM(inner or ScriptedLLM("ok"), limit, reserve_output=100, chars_per_token=1.0, clock=c.clock, sleep=c.sleep), c


def test_calls_under_the_limit_are_not_delayed():
    llm, c = throttled(1000)
    llm.complete("x" * 300)
    llm.complete("x" * 300)  # 400 + 400 = 800 <= 1000
    assert c.waits == []


def test_a_call_that_would_pass_the_limit_waits_for_the_window_to_clear():
    inner = ScriptedLLM("ok")
    llm, c = throttled(1000, inner)
    llm.complete("x" * 500)  # 600 tokens
    llm.complete("x" * 500)  # would be 1200 -> must wait
    assert len(c.waits) == 1 and 59 < c.waits[0] < 62
    assert len(inner.prompts) == 2


def test_an_oversized_single_call_still_goes_through():
    llm, c = throttled(100)
    assert llm.complete("x" * 500) == "ok"
    assert c.waits == []


def test_groq_is_paced_by_default_and_the_limit_can_be_changed():
    from common.providers import tokens_per_minute_for

    assert tokens_per_minute_for("groq", load_settings({})) == 8000
    assert tokens_per_minute_for("groq", load_settings({"GROQ_TOKENS_PER_MINUTE": "6000"})) == 6000
    assert tokens_per_minute_for("groq", load_settings({"GROQ_TOKENS_PER_MINUTE": "0"})) == 0
    assert tokens_per_minute_for("gemini", load_settings({})) == 0


# ----- embedding pacing -----


def test_google_wait_hint_is_read_from_the_error():
    from common.gemini import suggested_wait as google_wait

    assert abs(google_wait(RuntimeError("quota. Please retry in 58.535892576s.")) - 59.535892576) < 1e-6
    assert google_wait(RuntimeError("{'retryDelay': '58s'}")) == 59.0
    assert google_wait(RuntimeError("other")) is None


def make_embedder(tokens_per_minute, batch_size=50):
    from common.gemini import GeminiEmbedder

    embedder = GeminiEmbedder("k", "m", 4, batch_size, 0, 1, UsageMeter(), tokens_per_minute, chars_per_token=1.0)
    batches = []
    embedder._embed = lambda texts, task: (batches.append(len(texts)) or [[0.0] * 4 for _ in texts])
    return embedder, batches


def test_embedding_batches_respect_the_token_budget():
    embedder, batches = make_embedder(1000)  # budget 900 estimated tokens per batch
    from common.throttle import TokenWindow

    clock = FakeClock()
    embedder._window = TokenWindow(1000, clock.clock, clock.sleep)
    vectors = embedder.embed_documents(["x" * 299] * 10)  # 300 estimated tokens each -> 3 per batch
    assert len(vectors) == 10
    assert batches == [3, 3, 3, 1]
    assert len(clock.waits) >= 1  # the second batch had to wait for the minute to pass


def test_no_limit_means_full_batches():
    embedder, batches = make_embedder(0, batch_size=4)
    embedder.embed_documents(["x" * 300] * 10)
    assert batches == [4, 4, 2]
