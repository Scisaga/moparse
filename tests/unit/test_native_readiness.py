"""Readiness follows the selected primary parser without a secondary parser."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.health import router
from app.lifespan import Runtime
from app.models import BackendState, BackendStatus


@pytest.mark.parametrize("native", ["mineru", "docling"])
@pytest.mark.parametrize("native_ready", [False, True])
@pytest.mark.parametrize("other_ready", [False, True])
def test_http_readiness_follows_only_the_selected_native_parser(native, native_ready, other_ready):
    expected = native_ready
    settings = SimpleNamespace(
        native_parser_backend=native,
        app_id="moparse",
        version="0.5.1",
        max_queued_jobs=5,
        public_config=lambda: {},
    )
    selected = "mineru-advanced-txt" if native == "mineru" else "docling-standard"
    other = "docling-standard" if native == "mineru" else "mineru-advanced-txt"
    backends = [
        BackendStatus(
            name=selected,
            state=BackendState.READY if native_ready else BackendState.UNAVAILABLE,
        ),
        BackendStatus(
            name=other,
            state=BackendState.READY if other_ready else BackendState.UNAVAILABLE,
        ),
    ]
    runtime = SimpleNamespace(
        settings=settings,
        parser_service=SimpleNamespace(probe_backends=AsyncMock(return_value=backends)),
        storage_service=SimpleNamespace(is_writable=AsyncMock(return_value=True)),
        repository=SimpleNamespace(ping=AsyncMock(return_value=True)),
        job_service=SimpleNamespace(queue_depth=0),
        uptime_seconds=1.0,
    )

    async def ready_checks():
        return await Runtime.ready_checks(runtime)

    runtime.ready_checks = ready_checks
    app = FastAPI()
    app.include_router(router)
    app.state.runtime = runtime
    with TestClient(app) as client:
        health = client.get("/health")
        ready = client.get("/ready")
        assert health.status_code == 200
        assert health.json()["service"] == "mosaicparse"
        assert health.json()["display_name"] == "MO-Parse"
        assert "moparse" in health.json()["aliases"]
        assert health.json()["status"] == ("ok" if expected else "degraded")
        assert ready.status_code == (200 if expected else 503)
        assert ready.json()["ready"] is expected
        assert ready.json()["checks"]["docling"] is expected
