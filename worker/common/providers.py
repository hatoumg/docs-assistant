"""The list of answer-writing services this project knows about, and how to build one.

To add a provider that speaks the OpenAI format, add one line to PRESETS and one pair of names
to KEY_VARIABLES in settings.py. Gemini has its own adapter because it uses a different SDK.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    base_url: str
    default_model: str
    tokens_per_minute: int = 0  # 0 means: do not pace calls


# Default model names are starting points. Providers rename models often, so override with
# <PROVIDER>_MODEL in .env (for example GROQ_MODEL) if one is rejected.
PRESETS = {
    "groq": Preset("https://api.groq.com/openai/v1", "openai/gpt-oss-120b", tokens_per_minute=8000),
    "openrouter": Preset("https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free"),
    "mistral": Preset("https://api.mistral.ai/v1", "mistral-small-latest"),
}
PROVIDERS = ("gemini",) + tuple(PRESETS)


def model_for(provider, settings, override=""):
    """The model to use: an explicit override, then <PROVIDER>_MODEL from .env, then the default."""
    if override:
        return override
    if provider == "gemini":
        return settings.provider_models.get("gemini", settings.llm_model)
    return settings.provider_models.get(provider) or PRESETS[provider].default_model


def create_provider_llm(provider, model, settings):
    """Build the raw (not yet cached or budgeted) model for one provider."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Choose from: {', '.join(PROVIDERS)}")
    key = settings.provider_keys.get(provider, "")
    if not key or key == "your-key-here":
        variable = provider.upper() + "_API_KEY"
        raise RuntimeError(f"Provider '{provider}' needs {variable} in the .env file in the repo root.")
    if provider == "gemini":
        from common.gemini import GeminiLLM

        return GeminiLLM(key, model, settings.max_retries)
    from common.openai_compatible import OpenAICompatibleLLM

    return OpenAICompatibleLLM(provider, PRESETS[provider].base_url, key, model, settings.max_retries)


def tokens_per_minute_for(provider, settings):
    """<PROVIDER>_TOKENS_PER_MINUTE in .env wins (0 turns pacing off); otherwise the preset's value."""
    if provider in settings.provider_limits:
        return settings.provider_limits[provider]
    return PRESETS[provider].tokens_per_minute if provider in PRESETS else 0
