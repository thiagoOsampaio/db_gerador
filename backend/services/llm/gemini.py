"""Google Gemini service via ``langchain-google-genai``.

This is the *only* LLM integration in the system. There is intentionally
no provider abstraction layer — adding more providers would be a future
project, not a speculative interface.

Key guarantees:
- API key is loaded from environment via ``Settings`` only.
- API key never appears in logs, traces, prompts, or returned data.
- Structured outputs are mandatory: callers pass a Pydantic schema and
  receive a typed instance back, never raw JSON.
"""

from __future__ import annotations

import asyncio
from typing import TypeVar

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.config import Settings
from backend.observability.logging import get_logger

T = TypeVar("T", bound=BaseModel)

_logger = get_logger(__name__)


class GeminiService:
    """Thin wrapper around ``ChatGoogleGenerativeAI`` with structured output."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model_name = settings.GEMINI_MODEL
        self._chat = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY.get_secret_value(),
            temperature=settings.GEMINI_TEMPERATURE,
            timeout=settings.GEMINI_REQUEST_TIMEOUT,
        )
        self._max_retries = settings.GEMINI_MAX_RETRIES
        # Soft concurrency cap to avoid hitting provider rate limits.
        self._semaphore = asyncio.Semaphore(8)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def invoke_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[T],
    ) -> T:
        """Invoke Gemini and parse the response into ``output_schema``.

        The Gemini API key never enters the prompt. The user prompt is
        the caller's responsibility — agents must build prompts from
        sanitized, structured domain models only.
        """
        structured = self._chat.with_structured_output(output_schema)
        # Compose a reusable LangChain pipeline: prompt template -> LLM.
        # ``{system}`` / ``{user}`` are injected as raw strings (no
        # f-string formatting on the template itself) so curly braces in
        # the prompt body are preserved.
        prompt = ChatPromptTemplate.from_messages(
            [("system", "{system}"), ("human", "{user}")]
        )
        chain = prompt | structured

        async def _call() -> T:
            async with self._semaphore:
                _logger.debug(
                    "gemini.invoke_structured",
                    model=self._model_name,
                    schema=output_schema.__name__,
                )
                result = await chain.ainvoke(
                    {"system": system_prompt, "user": user_prompt}
                )
            if not isinstance(result, output_schema):
                # ``with_structured_output`` may return a dict in some
                # versions — coerce defensively.
                return output_schema.model_validate(result)
            return result

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=2, min=2, max=8),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                return await _call()
        raise RuntimeError("unreachable")  # pragma: no cover

    async def invoke_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Free-form text invocation. Avoid for primary data flows."""
        prompt = ChatPromptTemplate.from_messages(
            [("system", "{system}"), ("human", "{user}")]
        )
        chain = prompt | self._chat
        async with self._semaphore:
            response = await chain.ainvoke(
                {"system": system_prompt, "user": user_prompt}
            )
        content = response.content
        if isinstance(content, list):
            return "".join(str(p) for p in content)
        return str(content)
