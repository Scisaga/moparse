"""A copied stage option must consume the original request's monotonic budget."""

import pytest

from app.models.parse_options import ContentParseOptions
from app.parsers.base import ParserTimeoutError
from app.utils.deadline import attach_deadline, remaining_timeout


def test_stage_copies_share_remaining_budget_without_serializing_host_clock(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.utils.deadline.time.monotonic", lambda: clock[0])
    caller = ContentParseOptions(timeout_seconds=7200)
    running = attach_deadline(caller, 600)
    assert caller._deadline_monotonic is None
    assert running._deadline_monotonic == 700
    assert "_deadline_monotonic" not in running.model_dump()
    assert "_deadline_monotonic" not in running.model_json_schema()["properties"]
    stage = running.model_copy(update={"unit_range": "3-4"})
    clock[0] = 650
    assert remaining_timeout(stage, cap=120) == 50
    assert remaining_timeout(stage, cap=30) == 30
    assert attach_deadline(stage, 600)._deadline_monotonic == 700
    clock[0] = 700
    with pytest.raises(ParserTimeoutError, match="shared deadline"):
        remaining_timeout(stage, cap=120)


def test_standalone_adapter_keeps_its_cap_and_invalid_budget_fails():
    options = ContentParseOptions(timeout_seconds=7200)
    assert remaining_timeout(options, cap=120) == 120
    for invalid in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ParserTimeoutError):
            attach_deadline(options, invalid)
        with pytest.raises(ParserTimeoutError):
            remaining_timeout(options, cap=invalid)
