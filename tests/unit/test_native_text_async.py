"""Cancellation retains ownership of a native-prose CPU worker until it exits."""

import asyncio
import threading

import pytest

from app.services.native_text_service import NativeTextService


@pytest.mark.asyncio
async def test_cancelled_async_wrapper_waits_for_its_existing_cpu_work():
    started, release = threading.Event(), threading.Event()

    class ControlledService(NativeTextService):
        def apply(self, *args, **kwargs):
            started.set()
            release.wait(3)
            return {"finished": True}

    task = asyncio.create_task(ControlledService().apply_async(None, {}, None))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_repeated_cancellation_cannot_release_a_still_running_native_worker():
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = 0

    class ControlledService(NativeTextService):
        def apply(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            started.set()
            release.wait(3)
            finished.set()
            return {"finished": True}

    task = asyncio.create_task(ControlledService().apply_async(None, {}, None))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        for _ in range(3):
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            assert not finished.is_set()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set() and calls == 1


@pytest.mark.asyncio
async def test_received_native_worker_error_is_preserved_without_retry():
    calls = 0
    failure = ValueError("authored native worker failure")

    class FailedService(NativeTextService):
        def apply(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            raise failure

    with pytest.raises(ValueError) as raised:
        await FailedService().apply_async(None, {}, None)
    assert raised.value is failure and calls == 1


@pytest.mark.asyncio
async def test_cancelled_worker_that_finishes_with_error_is_drained_once():
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = 0

    class ControlledFailure(NativeTextService):
        def apply(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            started.set()
            release.wait(3)
            finished.set()
            raise ValueError("authored received failure after cancellation")

    task = asyncio.create_task(ControlledFailure().apply_async(None, {}, None))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and not finished.is_set()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set() and calls == 1
