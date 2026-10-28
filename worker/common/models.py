"""The four things we ask the AI services to do.

    embed_texts(texts)   turn many texts into vectors (for storing documents)
    embed_query(text)    turn one question into a vector (for searching)
    ask_llm(prompt)      get an answer from the answering model
    ask_judge(prompt)    get a grade from the judging model

Behind them, the other files in this folder do the unglamorous work: wait when a free-tier limit is hit (throttle.py),
retry (retry.py), remember answers on disk (cache.py), and switch between providers (providers.py, fallback.py).
Which service answers is chosen in .env (LLM_PROVIDER). Embeddings always use Gemini.
"""
from common.cache import BudgetedLLM, CachedEmbedder, CachedLLM
from common.fallback import FallbackLLM
from common.gemini import GeminiEmbedder
from common.providers import create_provider_llm, model_for, tokens_per_minute_for
from common.settings import load_settings
from common.throttle import ThrottledLLM
from common.usage import UsageMeter


def build_embedder(settings, usage):
    """Gemini embeddings, remembered on disk so a repeated text is never embedded twice."""
    gemini = GeminiEmbedder(
        settings.require_api_key(),
        settings.embed_model,
        settings.embed_dim,
        settings.embed_batch_size,
        settings.embed_pause_seconds,
        settings.max_retries,
        usage,
        settings.embed_tokens_per_minute,
    )
    return CachedEmbedder(gemini, settings.cache_dir / "embeddings")


def build_llm(settings, usage, folder, model_override="", factory=create_provider_llm):
    """The answering model: the chosen provider, then any fallbacks.

    Each one is wrapped so that it waits under free-tier token limits (ThrottledLLM), stops at a daily call cap
    (BudgetedLLM), and remembers answers on disk (CachedLLM). model_override applies to the first provider only.
    """
    models = []
    for position, provider in enumerate([settings.llm_provider, *settings.llm_fallbacks]):
        model = model_for(provider, settings, model_override if position == 0 else "")
        raw = factory(provider, model, settings, usage)
        limit = tokens_per_minute_for(provider, settings)
        if limit:
            raw = ThrottledLLM(raw, limit)
        counter = settings.cache_dir / f"llm_usage_{provider}.json"
        budgeted = BudgetedLLM(raw, settings.daily_llm_call_cap, counter)
        models.append(CachedLLM(budgeted, settings.cache_dir / folder))
    return models[0] if len(models) == 1 else FallbackLLM(models)


_clients = None


def _get_clients():
    """Build the clients the first time they are needed."""
    global _clients
    if _clients is None:
        settings = load_settings()
        usage = UsageMeter()
        _clients = {
            "embedder": build_embedder(settings, usage),
            "llm": build_llm(settings, usage, "llm"),
            "judge": build_llm(settings, usage, "judge", settings.judge_model),
        }
    return _clients


def embed_texts(texts):
    return _get_clients()["embedder"].embed_documents(texts)


def embed_query(text):
    return _get_clients()["embedder"].embed_query(text)


def ask_llm(prompt):
    return _get_clients()["llm"].complete(prompt)


def ask_judge(prompt):
    return _get_clients()["judge"].complete(prompt)
