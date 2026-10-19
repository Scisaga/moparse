"""One request-local monotonic deadline, preserved by internal option copies."""

from __future__ import annotations

import math
import time

from app.models.parse_options import ContentParseOptions


def attach_deadline(options: ContentParseOptions, timeout: float) -> ContentParseOptions:
    """Clone caller options and attach a deadline without extending an existing one."""
    from app.parsers.base import ParserTimeoutError

    if not math.isfinite(timeout) or timeout <= 0:
        raise ParserTimeoutError("content parsing has no remaining time budget")
    result = options.model_copy()
    deadline = time.monotonic() + timeout
    if result._deadline_monotonic is not None:
        deadline = min(deadline, result._deadline_monotonic)
    result._deadline_monotonic = deadline
    return result


def remaining_timeout(options: ContentParseOptions, cap: float | None = None) -> float:
    """Return the remaining shared budget, bounded by a backend's own cap."""
    from app.parsers.base import ParserTimeoutError

    deadline = options._deadline_monotonic
    if cap is not None and (not math.isfinite(cap) or cap <= 0):
        raise ParserTimeoutError("parser stage has no remaining time budget")
    if deadline is None:
        return float(cap if cap is not None else options.timeout_seconds or 7200)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ParserTimeoutError("content parsing exceeded its shared deadline")
    return min(remaining, cap) if cap is not None else remaining
