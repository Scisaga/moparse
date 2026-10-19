"""Cancellation acknowledges actual parse cleanup, not only an HTTP disconnect."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from native_worker import server


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setattr(server, "_ready", True)
    monkeypatch.setattr(server, "_requests", {})
    monkeypatch.setattr(server, "_tasks", {})
    monkeypatch.setattr(server, "_document_lock", asyncio.Lock())
    return server


async def submit(client, identifier, timeout=60):
    return await client.post(
        "/parse",
        files={"file": ("original.pdf", b"%PDF-test")},
        data={"request_id": identifier, "timeout_seconds": str(timeout)},
    )


async def test_cancel_retains_lock_and_nonterminal_state_until_dependency_drains(
    worker, monkeypatch
):
    entered, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def parse(path, page_range):
        assert path.read_bytes() == b"%PDF-test"
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cleaning.set()
            await release.wait()
            assert path.is_file()
            raise

    monkeypatch.setattr(worker, "_parse", parse)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=worker.app), base_url="http://worker"
    ) as client:
        work = asyncio.create_task(submit(client, "owned"))
        await entered.wait()
        response = await client.post("/requests/owned/cancel")
        assert response.json()["state"] == "stopping"
        await cleaning.wait()
        assert worker._document_lock.locked() and not work.done()
        assert (await client.get("/requests/owned")).json()["state"] == "stopping"
        release.set()
        assert (await work).status_code == 409
        assert (await client.get("/requests/owned")).json()["state"] == "cancelled"
        assert not worker._document_lock.locked() and not worker._tasks


async def test_deadline_waits_cleanup_then_reports_timed_out(worker, monkeypatch):
    cleaning, release = asyncio.Event(), asyncio.Event()

    async def parse(path, page_range):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cleaning.set()
            await release.wait()
            raise

    monkeypatch.setattr(worker, "_parse", parse)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=worker.app), base_url="http://worker"
    ) as client:
        work = asyncio.create_task(submit(client, "deadline", 0.02))
        await cleaning.wait()
        assert not work.done() and worker._document_lock.locked()
        release.set()
        assert (await work).status_code == 408
        assert (await client.get("/requests/deadline")).json()["state"] == "timed_out"
        assert not worker._document_lock.locked()


async def test_cancel_before_upload_prevents_late_parse_and_duplicate_id_never_replays(
    worker, monkeypatch
):
    calls = []

    async def parse(path, page_range):
        calls.append(path)
        return {"schema": "mineru-native/1"}

    monkeypatch.setattr(worker, "_parse", parse)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=worker.app), base_url="http://worker"
    ) as client:
        assert (await client.post("/requests/early/cancel")).json()["state"] == "cancelled"
        assert (await submit(client, "early")).status_code == 409
        assert not calls
        assert (await submit(client, "once")).status_code == 200
        assert (await submit(client, "once")).status_code == 409
        assert len(calls) == 1
