import json
import re
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

_SCHEMA_INSTRUCTION = (
    "Respond with a single JSON object that conforms exactly to this JSON schema. "
    "No markdown fences, no commentary, only the JSON object:\n{schema}"
)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LLMNotConfiguredError(RuntimeError):
    """Raised when the active provider has no API key configured."""


class LLMClient:
    """Base LLM client — OpenAI-compatible chat-completions transport.

    Every provider is reachable through the same OpenAI-compatible API
    (OpenRouter by default), so the transport lives here once. Subclasses
    are thin wrappers that pin provider identity (name, model naming,
    default base_url); client construction and model selection stay
    plug-and-play via config.yaml.
    """

    name = "base"
    default_base_url = DEFAULT_BASE_URL

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url or self.default_base_url
        self._client = AsyncOpenAI(api_key=api_key, base_url=self.base_url)

    @staticmethod
    def _messages(prompt: str, system: str | None) -> list[dict]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    async def generate(
        self, prompt: str, *, system: str | None = None
    ) -> AsyncIterator[str]:
        """Stream a plain-text response for a prompt."""
        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=self._messages(prompt, system),
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def generate_structured(
        self,
        prompt: str,
        *,
        system: str | None = None,
        response_schema: dict,
    ) -> dict:
        """Return a JSON object conforming to the given JSON schema."""
        full_prompt = prompt + "\n\n" + _SCHEMA_INSTRUCTION.format(
            schema=json.dumps(response_schema, indent=2)
        )
        messages = self._messages(full_prompt, system)

        # Prefer JSON mode; not every endpoint/model supports it, so fall
        # back to a plain completion and parse the JSON out of the text.
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
            )
        except Exception:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
            )

        text = (response.choices[0].message.content or "").strip()
        text = _FENCE_RE.sub("", text).strip()
        return json.loads(text)
