"""Request-scoped progress at reviewed MinerU async window boundaries."""

from __future__ import annotations

import hashlib
import importlib.metadata
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class NativeRequest:
    request_id: str
    state: str = "queued"
    phase: str = "queued"
    current: int = 0
    total: int = 0
    cancel_requested: bool = False
    updated: float = field(default_factory=time.monotonic)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, **values: Any) -> None:
        with self._lock:
            for name, value in values.items():
                setattr(self, name, value)
            self.updated = time.monotonic()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                name: getattr(self, name)
                for name in ("request_id", "state", "phase", "current", "total", "cancel_requested")
            }


active_request: ContextVar[NativeRequest | None] = ContextVar("native_request", default=None)
WINDOW_SOURCE_SHA256 = "655e823dd4002173e7740775d6f67296e24f6520d6b9e7b8c23e795baf4ac535"


def install_window_progress() -> dict[str, str]:
    """Observe completed windows without changing inference or source bytes.

    MinerU's native async entry point owns cancellation/draining of CPU work,
    PDF render sessions and outstanding async VLM calls. These wrappers only
    expose its existing real preparation/completion boundaries.
    """
    from mineru.backend.analysis.pdf import window

    if importlib.metadata.version("mineru") != "4.0.12":
        raise RuntimeError("window observer requires the reviewed MinerU 4.0.12")
    digest = hashlib.sha256(Path(window.__file__).read_bytes()).hexdigest()
    if digest != WINDOW_SOURCE_SHA256:
        raise RuntimeError("MinerU window lifecycle source differs from reviewed source")
    if not getattr(window._prepare_locked_window, "_moparse_observer", False):
        prepare = window._prepare_locked_window
        finish = window._finish_locked_window

        def observed_prepare(*args: Any, **kwargs: Any) -> Any:
            request = active_request.get()
            if request is not None:
                request.update(phase="window.preparing", total=kwargs["page_count"])
            result = prepare(*args, **kwargs)
            if request is not None:
                request.update(phase="window.inference")
            return result

        def observed_finish(*args: Any, **kwargs: Any) -> Any:
            request = active_request.get()
            if request is not None:
                request.update(phase="window.finishing")
            result = finish(*args, **kwargs)
            if request is not None:
                request.update(current=args[0].window.end + 1, phase="window.processed")
            return result

        observed_prepare._moparse_observer = True
        window._prepare_locked_window = observed_prepare
        window._finish_locked_window = observed_finish
    return {
        "protocol": "native-request/1",
        "window_source_sha256": digest,
        "entrypoint": "mineru.parser.parse_async",
    }
