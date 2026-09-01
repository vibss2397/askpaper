from .base import LLMClient

GEMINI_MODEL_PREFIX = "google/"


def normalize_gemini_model(model: str) -> str:
    """Bare gemini model names get the OpenRouter org prefix."""
    if "/" not in model:
        return f"{GEMINI_MODEL_PREFIX}{model}"
    return model


class GeminiClient(LLMClient):
    """Thin wrapper — Gemini models served through OpenRouter."""

    name = "gemini"
