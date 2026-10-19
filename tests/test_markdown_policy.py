from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.check_markdown_policy import assert_markdown_text, check_paths, maintained_paths


def test_generated_markdown_is_rejected_with_exact_location_in_table_or_code():
    assert_markdown_text("# Document\n\n| Value / period |\n")
    with pytest.raises(ValueError, match=r"new.md:3:9: U\+FF0F"):
        assert_markdown_text("# Document\n\n| Value \uff0f period |", "new.md")
    with pytest.raises(ValueError, match=r"U\+FF0F"):
        assert_markdown_text("```text\nvalue\uff0fperiod\n```\n")


def test_new_document_is_checked_and_ignored_source_requires_explicit_path(tmp_path):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("captured/\n")
    document = tmp_path / "docs/new.md"
    document.parent.mkdir(parents=True)
    document.write_text("New document\uff0fvalue\n")
    captured = tmp_path / "captured/result.md"
    captured.parent.mkdir()
    captured.write_text("Source\uff0fglyph\n")
    paths = maintained_paths(tmp_path)
    assert Path("docs/new.md") in paths
    assert Path("captured/result.md") not in paths
    assert len(check_paths(paths, tmp_path)) == 1
    assert check_paths([captured], tmp_path)[0].path == "captured/result.md"


def test_generator_source_is_checked_before_markdown_is_written(tmp_path):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    generator = tmp_path / "scripts/render_documentation.py"
    generator.parent.mkdir(parents=True)
    generator.write_text('label = "Count\uff0ftotal"\n')
    paths = maintained_paths(tmp_path)
    assert paths == [Path("scripts/render_documentation.py")]
    assert len(check_paths(paths, tmp_path)) == 1
