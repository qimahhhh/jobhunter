"""Model access for the extraction stage.

Everything that talks to a provider lives here, so the rest of the app can take
an :class:`LLMClient` and stay testable without a network call. The default
provider is DeepSeek through its OpenAI-compatible endpoint, which means the
only thing that differs from OpenAI is the ``base_url``.

Configuration comes from the environment, never from source:

    DEEPSEEK_API_KEY   required
    DEEPSEEK_MODEL     optional, defaults to ``deepseek-chat``
    DEEPSEEK_BASE_URL  optional, defaults to ``https://api.deepseek.com``
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Protocol

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TIMEOUT = 60.0

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


class LLMError(RuntimeError):
    """The model was unreachable, or its reply was not usable JSON."""


class LLMClient(Protocol):
    """What the extraction stage needs. Tests pass a fake implementation."""

    def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        ...


def _load_env() -> None:
    """Load ``.env`` when python-dotenv is available; carry on if it is not."""

    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - optional convenience only
        return
    load_dotenv()


def _parse_json(content: str) -> dict[str, Any]:
    """Accept a bare object or one wrapped in a markdown fence."""

    text = _FENCE_RE.sub("", content.strip()).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"model reply was not JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise LLMError("model reply was JSON but not an object")
    return value


class DeepSeekClient:
    """Thin wrapper around the OpenAI SDK pointed at DeepSeek."""

    name = "deepseek"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        _load_env()

        key = (api_key or os.getenv("DEEPSEEK_API_KEY", "")).strip()
        if not key:
            raise LLMError(
                "DEEPSEEK_API_KEY is not set; put it in .env or the environment"
            )

        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise LLMError(
                "the DeepSeek client needs the openai package: pip install openai"
            ) from exc

        self.model = model or os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)
        self._client = OpenAI(
            api_key=key,
            base_url=base_url or os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
            timeout=timeout,
        )

    def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        """One non-streaming turn, constrained to a JSON object reply."""

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=2000,
            )
        except Exception as exc:  # provider errors share no useful base class
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc

        content = response.choices[0].message.content if response.choices else ""
        if not content or not content.strip():
            raise LLMError("model returned an empty reply")
        return _parse_json(content)
