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


@pytest.mark.parametrize(
    "relative",
    [
        "pdf_sample/parsing/expected/synthetic/expected.md",
        "datasets/synthetic/references/expected.md",
        "benchmark/reports/synthetic/native/faithful.md",
        "benchmark/reference-decisions/synthetic/decision.md",
    ],
)
def test_corpus_paths_are_never_opened_even_when_explicit(tmp_path, relative, monkeypatch):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text("Synthetic fixture\uff0fglyph\n")
    original = Path.read_text

    def guarded_read(candidate, *args, **kwargs):
        if candidate == path:
            raise AssertionError("generic policy opened corpus material")
        return original(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)
    assert Path(relative) not in maintained_paths(tmp_path)
    assert check_paths([path], tmp_path) == []
