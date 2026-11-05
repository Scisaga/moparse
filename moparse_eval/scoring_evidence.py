"""Grade-local snapshots for read-only evidence in JSON scoring traces.

Only completed evidence and trace payloads belong here. Mutable working
copies, queries being rewritten and temporary endpoints use ordinary deepcopy.
"""

from __future__ import annotations

import copy
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any


class _SnapshotMemo(dict):
    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        # A completed trace can contain an earlier snapshot. Re-copying that
        # snapshot would rebuild its entire context tree yet again. Snapshot
        # containers are read-only within this session, including when they
        # appear below a newly completed trace wrapper.
        if isinstance(value, (dict, list, tuple, set)):
            super().setdefault(id(value), value)


_ACTIVE: ContextVar[_SnapshotMemo | None] = ContextVar("scoring_evidence_snapshot_memo", default=None)


@contextmanager
def evidence_session():
    """Bound snapshot reuse to one grade; nested use shares its outer scope."""
    if _ACTIVE.get() is not None:
        yield
        return
    memo = _SnapshotMemo()
    token = _ACTIVE.set(memo)
    try:
        yield
    finally:
        _ACTIVE.reset(token)
        memo.clear()


def snapshot_copy(value: Any) -> Any:
    """Copy immutable-in-this-grade evidence, sharing only its isolated snapshot.

    The returned dictionaries/lists remain normal JSON values. Callers treat
    them as read-only, and never use this helper to create a mutable working
    copy. Outside a session every call remains an independent deepcopy.
    """
    memo = _ACTIVE.get()
    return copy.deepcopy(value) if memo is None else copy.deepcopy(value, memo)
