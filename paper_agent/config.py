import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

DEFAULT_VAULT_PATH = Path.home() / ".paper-vault"
DEFAULT_MODEL = "openai/gpt-5.6-luna"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

CONFIG_DIR = ".paper-agent"
CONFIG_FILE = "config.yaml"

API_KEY_ENV = "OPENROUTER_API_KEY"
BASE_URL_ENV = "OPENROUTER_BASE_URL"


def _get_vault_path() -> Path:
    env_path = os.environ.get("PAPER_AGENT_VAULT")
    if env_path:
        return Path(env_path).expanduser()
    return DEFAULT_VAULT_PATH


def _get_config_path() -> Path:
    return _get_vault_path() / CONFIG_DIR / CONFIG_FILE


def _load_env():
    vault = _get_vault_path()
    env_files = [
        Path.cwd() / ".env",
        vault / CONFIG_DIR / ".env",
    ]
    for env_file in env_files:
        if env_file.exists():
            load_dotenv(env_file)


def load_config() -> dict:
    _load_env()
    config_path = _get_config_path()
    if not config_path.exists():
        return {
            "vault_path": str(_get_vault_path()),
            "model": DEFAULT_MODEL,
        }
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def save_config(config: dict) -> None:
    config_path = _get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(config, f)


def ensure_config_exists() -> dict:
    config = load_config()
    config.setdefault("vault_path", str(_get_vault_path()))
    config.setdefault("model", DEFAULT_MODEL)
    save_config(config)
    return config


def _infer_provider(model: str) -> str:
    org = model.split("/", 1)[0] if "/" in model else ""
    if org == "google" or model.startswith("gemini"):
        return "gemini"
    return "openai"


def resolve_provider(model: str, cfg: dict) -> str:
    """Explicit `provider` in config wins; otherwise infer from the model name."""
    provider = cfg.get("provider")
    if provider:
        return str(provider)
    return _infer_provider(model)


def _resolve_settings(cfg: dict, model: str, provider: str | None) -> dict:
    if provider == "gemini":
        from .llm.gemini import normalize_gemini_model

        model = normalize_gemini_model(model)

    api_key = os.environ.get(API_KEY_ENV)
    base_url = cfg.get("base_url") or os.environ.get(BASE_URL_ENV)

    if not api_key:
        key_error = f"{API_KEY_ENV} is not set. Add it to your .env file."
    else:
        key_error = ""

    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "key_env": API_KEY_ENV,
        "key_error": key_error,
    }


def get_llm_settings() -> dict:
    """Resolve the active provider, model, API key, and base_url.

    All traffic goes through OpenRouter (or any OpenAI-compatible
    endpoint via `base_url`), authenticated with a single
    OPENROUTER_API_KEY. Returns a dict with keys: provider, model,
    api_key, base_url, key_env, key_error, reasoning_effort.
    """
    _load_env()
    cfg = load_config()
    model = cfg.get("model", DEFAULT_MODEL)
    provider = resolve_provider(model, cfg)
    settings = _resolve_settings(cfg, model, provider)
    settings["reasoning_effort"] = cfg.get("reasoning_effort")
    return settings


def get_structured_llm_settings() -> dict:
    """Settings for structured (JSON) calls: summarize, synthesize, knowledge.

    Uses `structured_model` from config.yaml when set (falling back to the
    main `model`), plus an optional `structured_reasoning_effort`
    (falling back to the main `reasoning_effort`). Determinism for these
    tasks comes from forced per-item verdicts in the schemas plus a
    reasoning model — not temperature.
    Returns the same keys as get_llm_settings() plus `reasoning_effort`.
    """
    _load_env()
    cfg = load_config()
    model = cfg.get("structured_model") or cfg.get("model", DEFAULT_MODEL)
    provider = cfg.get("structured_provider") or _infer_provider(model)
    settings = _resolve_settings(cfg, model, provider)
    settings["reasoning_effort"] = (
        cfg.get("structured_reasoning_effort") or cfg.get("reasoning_effort")
    )
    return settings


def get_api_key() -> str | None:
    """API key for the active provider (provider-aware)."""
    return get_llm_settings()["api_key"]


def get_secret_key() -> str | None:
    _load_env()
    return os.environ.get("PAPER_AGENT_SECRET")
