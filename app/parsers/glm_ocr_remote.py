"""Remote GLM-OCR capability probe and fixed-prompt image text recognition."""

from __future__ import annotations

import asyncio
import base64
import time
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.models.backend import BackendState, BackendStatus
from app.parsers.base import ParserError, ParserUnavailableError
from app.utils.settings import setting


class GlmOcrRemoteAdapter:
    name = "glm-ocr-remote"

    def __init__(
        self, settings: object | None, http_client: httpx.AsyncClient | None = None
    ) -> None:
        self.settings = settings
        self.enabled = bool(setting(settings, "glm_ocr_enabled", False))
        self.api_url = str(
            setting(settings, "glm_ocr_api_url", "http://localhost:8001/v1/chat/completions")
        )
        self.api_key = setting(settings, "glm_ocr_api_key", None)
        self.model = str(setting(settings, "glm_ocr_model", "zai-org/GLM-OCR"))
        self.health_ttl = float(setting(settings, "backend_health_ttl_seconds", 15.0))
        probe_timeout = min(5.0, float(setting(settings, "glm_ocr_timeout_seconds", 120.0)))
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(probe_timeout), trust_env=False
        )
        self._request_semaphore = asyncio.Semaphore(
            int(setting(settings, "glm_ocr_max_concurrency", 4))
        )
        self._last_status: BackendStatus | None = None
        self._last_probe_monotonic = 0.0

    def _models_url(self) -> str:
        parsed = urlsplit(self.api_url)
        path = parsed.path
        marker = path.find("/v1/")
        base_path = f"{path[:marker]}/v1/models" if marker >= 0 else "/v1/models"
        return urlunsplit((parsed.scheme, parsed.netloc, base_path, "", ""))

    async def probe(self, *, force: bool = False) -> BackendStatus:
        if not self.enabled:
            return BackendStatus(
                name=self.name,
                state=BackendState.DISABLED,
                enabled=False,
                detail="GLM-OCR is disabled by configuration",
                model=self.model,
            )
        now = time.monotonic()
        if (
            not force
            and self._last_status is not None
            and now - self._last_probe_monotonic <= self.health_ttl
        ):
            return self._last_status
        headers: dict[str, str] = (
            {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        )
        started = time.perf_counter()
        try:
            response = await self._client.get(self._models_url(), headers=headers)
            response.raise_for_status()
            payload = response.json()
            model_items = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(model_items, list):
                raise ValueError("models response has no data list")
            identifiers = {
                item.get("id")
                for item in model_items
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
            model_missing = self.model not in identifiers
            detail = (
                "backend is reachable; configured model was not listed"
                if model_missing
                else "OpenAI-compatible models endpoint responded"
            )
            status = BackendStatus(
                name=self.name,
                state=BackendState.UNAVAILABLE if model_missing else BackendState.READY,
                detail=detail,
                model=self.model,
                latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            status = BackendStatus(
                name=self.name,
                state=BackendState.UNAVAILABLE,
                detail=f"health probe failed: {type(exc).__name__}",
                model=self.model,
                latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
            )
        self._last_status = status
        self._last_probe_monotonic = now
        return status

    async def recognize_image(self, image: bytes) -> str:
        """Read visible text with GLM-OCR's fixed prompt, without scene inference."""

        if not self.enabled:
            raise ParserUnavailableError("GLM-OCR is disabled")
        headers: dict[str, str] = (
            {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        )
        payload = {
            "model": self.model,
            "max_tokens": int(setting(self.settings, "glm_ocr_max_tokens", 4096)),
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64,"
                                + base64.b64encode(image).decode("ascii")
                            },
                        },
                        {"type": "text", "text": "Text Recognition:"},
                    ],
                }
            ],
        }
        retries = int(setting(self.settings, "glm_ocr_max_retries", 3))
        timeout = float(setting(self.settings, "glm_ocr_timeout_seconds", 120.0))
        async with self._request_semaphore:
            for attempt in range(retries + 1):
                try:
                    response = await self._client.post(
                        self.api_url, json=payload, headers=headers, timeout=timeout
                    )
                    response.raise_for_status()
                    choices = response.json().get("choices", [])
                    choice = choices[0] if choices else {}
                    content = choice.get("message", {}).get("content")
                    if not isinstance(content, str):
                        raise ParserError("GLM-OCR returned no text content")
                    if choice.get("finish_reason") == "length":
                        raise ParserError(
                            "GLM-OCR text recognition exceeded its output-token budget"
                        )
                    return content.strip()
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code < 500 and exc.response.status_code != 429:
                        raise ParserError(
                            f"GLM-OCR returned HTTP {exc.response.status_code}"
                        ) from exc
                    if attempt == retries:
                        raise ParserError("GLM-OCR text recognition failed") from exc
                except httpx.RequestError as exc:
                    if attempt == retries:
                        raise ParserError("GLM-OCR text recognition request failed") from exc
                except (ValueError, TypeError, AttributeError) as exc:
                    raise ParserError("GLM-OCR returned invalid recognition data") from exc
        raise ParserError("GLM-OCR text recognition failed")

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
