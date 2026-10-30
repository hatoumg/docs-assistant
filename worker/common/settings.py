"""All configuration in one place, read from environment variables (and .env)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

WORKER_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_DIR.parent

DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/docs_assistant"


@dataclass(frozen=True)
class Settings:
    database_url: str = DEFAULT_DATABASE_URL
    ollama_url: str = "http://localhost:11434"  # where the Ollama program is listening
    embed_model: str = "nomic-embed-text"  # downloaded once with: ollama pull nomic-embed-text
    embed_dim: int = 768  # must match vector(768) in the database
    rag_service_secret: str = ""  # the TypeScript API sends this to prove it is allowed to call the service
    upload_dir: Path = REPO_ROOT / "storage" / "uploads"  # where the API saves uploaded files
    llm_model: str = "gemini-3.8-flash"
    judge_model: str = ""  # empty means: use the main provider's model
    llm_provider: str = "gemini"  # which service writes answers: gemini, groq, openrouter or mistral
    llm_fallbacks: tuple = ()  # providers to try, in order, if the main one fails
    provider_keys: dict = field(default_factory=dict)  # provider name -> API key
    provider_models: dict = field(default_factory=dict)  # provider name -> model override
    provider_limits: dict = field(default_factory=dict)  # provider name -> tokens per minute
    max_retries: int = 5
    daily_llm_call_cap: int = 200
    cache_dir: Path = WORKER_DIR / ".cache"


KEY_VARIABLES = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}
MODEL_VARIABLES = {name: name.upper() + "_MODEL" for name in KEY_VARIABLES}
LIMIT_VARIABLES = {name: name.upper() + "_TOKENS_PER_MINUTE" for name in KEY_VARIABLES}


def load_settings(env=None) -> Settings:
    """Build Settings from the environment, loading REPO_ROOT/.env first if python-dotenv is installed.

    Passing env (a plain dict) skips both and reads only that dict, which is how tests use it.
    """
    if env is None:
        try:
            from dotenv import load_dotenv

            load_dotenv(REPO_ROOT / ".env")
        except ImportError:
            pass
        env = os.environ
    defaults = Settings()
    keys = {name: env.get(var, "") for name, var in KEY_VARIABLES.items()}
    models = {name: env[var] for name, var in MODEL_VARIABLES.items() if env.get(var)}
    limits = {name: int(env[var]) for name, var in LIMIT_VARIABLES.items() if env.get(var)}
    return Settings(
        database_url=env.get("DATABASE_URL", defaults.database_url),
        ollama_url=env.get("OLLAMA_URL", defaults.ollama_url),
        embed_model=env.get("EMBED_MODEL", defaults.embed_model),
        rag_service_secret=env.get("RAG_SERVICE_SECRET", ""),
        upload_dir=Path(env["UPLOAD_DIR"]).resolve() if env.get("UPLOAD_DIR") else defaults.upload_dir,
        llm_model=env.get("GEMINI_MODEL", defaults.llm_model),
        judge_model=env.get("JUDGE_MODEL", ""),
        llm_provider=env.get("LLM_PROVIDER", defaults.llm_provider).strip().lower(),
        llm_fallbacks=tuple(p.strip().lower() for p in env.get("LLM_FALLBACK", "").split(",") if p.strip()),
        provider_keys=keys,
        provider_models=models,
        provider_limits=limits,
        daily_llm_call_cap=int(env.get("MAX_REQUESTS_PER_DAY", defaults.daily_llm_call_cap)),
    )
