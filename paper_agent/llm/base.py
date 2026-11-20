import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

logger = logging.getLogger(__name__)

_SCHEMA_INSTRUCTION = (
    "Respond with a single JSON object that conforms exactly to this JSON schema. "
    "No markdown fences, no commentary, only the JSON object:\n{schema}"
)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

_ASYNCGEN_FILTER_ATTR = "_paper_agent_asyncgen_teardown_filter"


def install_asyncgen_teardown_filter() -> None:
    """Downgrade httpcore2 asyncgen finalization noise on the running loop.

    Root cause (verified against openai 3.8 / httpx2 2.12 / httpcore2 2.12):
    openai's SSE streams `break` on the [DONE] event without exhausting
    httpcore2's response-body generator chain (PoolByteStream.__aiter__ ->
    HTTP11ConnectionByteStream.__aiter__ -> _receive_response_body). When GC
    later finalizes the orphaned generators, asyncio athrows GeneratorExit
    into them and httpcore2's `except BaseException: await self.aclose();
    raise exc` pattern inside nested async-context managers fails the
    asyncgen close protocol: RuntimeError("generator didn't stop after
    athrow()").

    The connection itself was already released (openai's
    `finally: await response.aclose()` runs the object-level cleanup, and
    httpcore2's later aclose is a no-op guarded by _closed), so this
    failure is pure teardown noise — no leak. Log it at debug instead of
    letting asyncio dump tracebacks. Revisit when openai/httpcore2 fix
    the interaction.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    if getattr(loop, _ASYNCGEN_FILTER_ATTR, False):
        return

    previous = loop.get_exception_handler()

    def handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
        exc = context.get("exception")
        if (
            isinstance(exc, RuntimeError)
            and "generator didn't stop after athrow" in str(exc)
        ):
            logger.debug(
                "suppressed httpcore2 asyncgen teardown noise: %s",
                context.get("message", ""),
            )
            return
        if previous is not None:
            previous(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(handler)
    setattr(loop, _ASYNCGEN_FILTER_ATTR, True)


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
        reasoning_effort: str | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url or self.default_base_url
        self.reasoning_effort = reasoning_effort
        self._client = AsyncOpenAI(api_key=api_key, base_url=self.base_url)
        # Streaming through the openai SDK orphans httpcore2 generators that
        # fail noisily at finalization (see install_asyncgen_teardown_filter).
        install_asyncgen_teardown_filter()

    def _completion_kwargs(self) -> dict:
        """Extra OpenRouter params: reasoning effort for reasoning models."""
        if self.reasoning_effort:
            return {
                "extra_body": {
                    "reasoning": {"enabled": True, "effort": self.reasoning_effort}
                }
            }
        return {}

    async def aclose(self) -> None:
        """Close the underlying HTTP client.

        Call when done with the client — unclosed httpx connections are
        GC'd at event-loop shutdown and produce noisy teardown errors.
        """
        await self._client.close()

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
            **self._completion_kwargs(),
        )
        async with stream:
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
                **self._completion_kwargs(),
            )
        except Exception:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                **self._completion_kwargs(),
            )

        text = (response.choices[0].message.content or "").strip()
        text = _FENCE_RE.sub("", text).strip()
        return json.loads(text)
