import base64
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.models import BackendState
from app.parsers.base import ParserError
from app.parsers.glm_ocr_remote import GlmOcrRemoteAdapter


def async_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_glm_probe_reports_real_model_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"data": [{"id": "zai-org/GLM-OCR"}]})

    client = async_client(handler)
    adapter = GlmOcrRemoteAdapter(
        SimpleNamespace(
            glm_ocr_enabled=True,
            glm_ocr_api_url="http://glm.test/v1/chat/completions",
            glm_ocr_model="zai-org/GLM-OCR",
            backend_health_ttl_seconds=0,
        ), client,
    )
    status = await adapter.probe()
    assert status.state == BackendState.READY
    assert status.model == "zai-org/GLM-OCR"
    assert status.latency_ms is not None
    await client.aclose()


async def test_glm_probe_distinguishes_disabled_and_unavailable() -> None:
    disabled_client = async_client(lambda _: httpx.Response(500))
    disabled = GlmOcrRemoteAdapter(SimpleNamespace(glm_ocr_enabled=False), disabled_client)
    assert (await disabled.probe()).state == BackendState.DISABLED
    await disabled_client.aclose()

    unavailable_client = async_client(lambda _: httpx.Response(503))
    unavailable = GlmOcrRemoteAdapter(
        SimpleNamespace(
            glm_ocr_enabled=True,
            glm_ocr_api_url="http://glm.test/v1/chat/completions",
            backend_health_ttl_seconds=0,
        ), unavailable_client,
    )
    assert (await unavailable.probe()).state == BackendState.UNAVAILABLE
    await unavailable_client.aclose()


async def test_glm_media_ocr_uses_original_image_and_official_fixed_prompt() -> None:
    image = Path("tests/fixtures/sample-image.png").read_bytes()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert request.url.host == "glm.test"
        payload = json.loads(request.content)
        assert payload["model"] == "zai-org/GLM-OCR"
        assert payload["temperature"] == 0
        assert payload["max_tokens"] == 4096
        content = payload["messages"][0]["content"]
        assert len(content) == 2
        assert content[0]["type"] == "image_url"
        assert base64.b64decode(content[0]["image_url"]["url"].partition(",")[2]) == image
        assert content[1] == {"type": "text", "text": "Text Recognition:"}
        assert "response_format" not in payload
        assert "reasoning_effort" not in payload
        return httpx.Response(200, json={"choices": [
            {"finish_reason": "stop", "message": {"content": "原件文字 0.2907 元／股"}}
        ]})

    client = async_client(handler)
    adapter = GlmOcrRemoteAdapter(
        SimpleNamespace(glm_ocr_enabled=True, glm_ocr_model="zai-org/GLM-OCR",
                        glm_ocr_api_url="http://glm.test/v1/chat/completions"), client,
    )

    assert await adapter.recognize_image(image) == "原件文字 0.2907 元／股"
    assert calls == ["http://glm.test/v1/chat/completions"]
    await client.aclose()


@pytest.mark.parametrize("response", [
    {"choices": [{"finish_reason": "length", "message": {"content": "截断的不完整文字"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": None}}]},
    {"choices": []},
])
async def test_glm_media_ocr_rejects_incomplete_or_invalid_recognition(response: dict) -> None:
    client = async_client(lambda _: httpx.Response(200, json=response))
    adapter = GlmOcrRemoteAdapter(
        SimpleNamespace(glm_ocr_enabled=True, glm_ocr_api_url="http://glm.test/v1/chat/completions",
                        glm_ocr_max_retries=0), client,
    )

    with pytest.raises(ParserError):
        await adapter.recognize_image(Path("tests/fixtures/sample-image.png").read_bytes())
    await client.aclose()
