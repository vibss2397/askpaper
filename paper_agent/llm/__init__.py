from .. import config
from .base import LLMClient, LLMNotConfiguredError
from .gemini import GeminiClient
from .openai_client import OpenAIClient

PROVIDERS: dict[str, type[LLMClient]] = {
    GeminiClient.name: GeminiClient,
    OpenAIClient.name: OpenAIClient,
}


def get_client() -> LLMClient:
    """Build the LLM client from config.

    Plug-and-play: `provider` (optional, inferred from the model name)
    and `model` come from config.yaml; the matching client class is
    initialized with the provider's API key and base_url.
    """
    settings = config.get_llm_settings()

    provider = settings["provider"]
    client_cls = PROVIDERS.get(provider)
    if client_cls is None:
        raise LLMNotConfiguredError(
            f"Unknown LLM provider '{provider}'. "
            f"Available: {', '.join(sorted(PROVIDERS))}"
        )

    if not settings["api_key"]:
        raise LLMNotConfiguredError(settings["key_error"])

    return client_cls(
        model=settings["model"],
        api_key=settings["api_key"],
        base_url=settings["base_url"],
    )


__all__ = [
    "LLMClient",
    "LLMNotConfiguredError",
    "GeminiClient",
    "OpenAIClient",
    "get_client",
    "PROVIDERS",
]
