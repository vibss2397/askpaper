from .base import LLMClient


class OpenAIClient(LLMClient):
    """Thin wrapper — generic OpenAI-compatible models via OpenRouter.

    The transport (streaming, structured JSON, connection handling)
    lives entirely in LLMClient; this class only pins the provider name.
    Any model slug the endpoint serves (e.g. `someorg/luna`) works
    without code changes.
    """

    name = "openai"
