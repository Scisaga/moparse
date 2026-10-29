"""Typed-renderer fault injection; no PDF, SDK inference or service lifecycle."""

import asyncio
import sys
from copy import deepcopy
from types import ModuleType, SimpleNamespace

import pytest

from native_worker.server import export_source_blocks


class Block:
    type = "text"

    def __init__(self, text: str) -> None:
        self.raw = {"type": "text", "content": [{"type": "text", "content": text}]}

    def to_dict(self, **_kwargs):
        return deepcopy(self.raw)


def stub_renderer(monkeypatch, renderer) -> None:
    options = ModuleType("docvortex.options")
    options.LatexDelimitersConfig = lambda: None
    markdown = ModuleType("docvortex.render.markdown")
    markdown.render_single_block = renderer
    monkeypatch.setitem(sys.modules, "docvortex.options", options)
    monkeypatch.setitem(sys.modules, "docvortex.render.markdown", markdown)


@pytest.mark.parametrize("error_type", [ValueError, TypeError, KeyError])
def test_local_typed_export_failure_preserves_raw_block_and_valid_neighbors(
    monkeypatch, error_type
) -> None:
    before, broken, after = Block("before"), Block("unrendered"), Block("after")

    def render(block, **_kwargs):
        if block is broken:
            raise error_type("malformed region")
        return block.raw["content"][0]["content"]

    stub_renderer(monkeypatch, render)
    exported = export_source_blocks(SimpleNamespace(blocks=[before, broken, after]))

    assert exported[0]["markdown"] == "before"
    assert exported[2]["markdown"] == "after"
    assert exported[1]["content"] == broken.raw["content"]
    assert "markdown" not in exported[1]
    assert exported[1]["export_error"] == {
        "code": "native_block_export_invalid",
        "exception_type": error_type.__name__,
    }
    assert all("export_error" not in block.raw for block in (before, broken, after))


@pytest.mark.parametrize(
    "error_type", [MemoryError, TimeoutError, asyncio.CancelledError, RuntimeError]
)
def test_resource_deadline_and_unknown_failures_are_not_local_content_errors(
    monkeypatch, error_type
) -> None:
    def render(_block, **_kwargs):
        raise error_type("not a content-format error")

    stub_renderer(monkeypatch, render)
    with pytest.raises(error_type):
        export_source_blocks(SimpleNamespace(blocks=[Block("before")]))
