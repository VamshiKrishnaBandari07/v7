"""Server-side Meta Model API client. Responses are text to be parsed, never executed."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from app.core.config import Settings


class MetaClientError(RuntimeError):
    pass


def extract_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
        return str(payload["output_text"])
    chunks: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("text"), str):
            chunks.append(item["text"])
        for part in item.get("content") or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    text = "\n".join(chunk for chunk in chunks if chunk.strip())
    if not text:
        raise MetaClientError("model response did not contain text")
    return text


class MetaClient:
    """Small retrying wrapper around POST {base}/responses."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] | None = None,
        max_requests: int = 6,
    ) -> None:
        self.settings = settings
        self.usage = {"requests": 0, "input_tokens": 0, "output_tokens": 0, "errors": 0}
        self._max_requests = max_requests
        self._sleeper = sleeper or time.sleep
        self._client = client or httpx.Client(timeout=httpx.Timeout(30.0))
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def complete(self, prompt: str) -> str:
        if not self.settings.model_api_key.strip():
            raise MetaClientError("MODEL_API_KEY is empty")
        if self.usage["requests"] >= self._max_requests:
            raise MetaClientError("model call budget exhausted")
        url = self.settings.meta_base_url.rstrip("/") + "/responses"
        headers = {
            "Authorization": f"Bearer {self.settings.model_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.settings.meta_model,
            "input": prompt,
            "max_output_tokens": 800,
        }
        last_error = "no attempt"
        for attempt in range(3):
            try:
                response = self._client.post(url, headers=headers, json=body)
            except httpx.TimeoutException:
                self.usage["errors"] += 1
                last_error = "timeout"
                self._sleeper(0.2 * (2**attempt))
                continue
            except httpx.HTTPError as exc:
                self.usage["errors"] += 1
                last_error = exc.__class__.__name__
                self._sleeper(0.2 * (2**attempt))
                continue
            self.usage["requests"] += 1
            if response.status_code == 429 or response.status_code >= 500:
                self.usage["errors"] += 1
                last_error = f"HTTP {response.status_code}"
                self._sleeper(0.2 * (2**attempt))
                continue
            if response.status_code >= 400:
                self.usage["errors"] += 1
                raise MetaClientError(f"HTTP {response.status_code}")
            try:
                payload = response.json()
            except ValueError as exc:
                raise MetaClientError("model response was not JSON") from exc
            self._record_tokens(payload)
            return extract_output_text(payload)
        raise MetaClientError(last_error)

    def _record_tokens(self, payload: dict[str, Any]) -> None:
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if not isinstance(usage, dict):
            return
        self.usage["input_tokens"] += int(
            usage.get("input_tokens") or usage.get("prompt_tokens") or 0
        )
        self.usage["output_tokens"] += int(
            usage.get("output_tokens") or usage.get("completion_tokens") or 0
        )
