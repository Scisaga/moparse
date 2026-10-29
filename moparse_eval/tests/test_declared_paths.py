"""Explicit author-file path bases, using synthetic declarations only."""

import json

from moparse_eval.packaging import read_selection


def test_declared_author_base_is_lexical_and_does_not_probe_files(tmp_path):
    (tmp_path / "author-a.json").write_text(json.dumps({
        "authoring_base": "authored/a",
        "documents": [{"authoring_file": "document/document.json"}],
        "samples": [{"authoring_file": "document/sample.json"}],
        "suites": {"lite": ["sample"]},
    }))
    (tmp_path / "author-b.json").write_text(json.dumps({
        "documents": [{"authoring_file": "authored/b/document.json"}],
        "samples": [{"authoring_file": "authored/b/sample.json"}],
    }))
    declaration = tmp_path / "selection.json"
    declaration.write_text(json.dumps({"includes": ["author-a.json", "author-b.json"]}))
    result = read_selection(declaration, tmp_path)
    assert result["documents"] == [{"authoring_file": "authored/a/document/document.json"},
                                    {"authoring_file": "authored/b/document.json"}]
    assert result["samples"] == [{"authoring_file": "authored/a/document/sample.json"},
                                  {"authoring_file": "authored/b/sample.json"}]
    assert result["suites"]["lite"] == ["sample"]
