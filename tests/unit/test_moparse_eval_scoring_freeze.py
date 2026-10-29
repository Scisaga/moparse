"""Scoring software locks use synthetic metadata only."""

from __future__ import annotations

import json

import pytest

from moparse_eval.cli import SCORING_PROTOCOL, parser, read_scoring_freeze


def _record():
    return {
        "software_id": "synthetic-software",
        "protocol_id": SCORING_PROTOCOL["id"],
        "validation": {"status": "passed", "scope": "synthetic software tests only"},
    }


def test_scoring_freeze_records_software_and_protocol_without_rewriting_it(tmp_path):
    record = _record()
    path = tmp_path / "freeze.json"
    payload = json.dumps(record)
    path.write_text(payload)
    assert read_scoring_freeze(path, {"software_id": "synthetic-software"}) == record
    assert path.read_text() == payload
    args = parser().parse_args(["score", "--run", str(tmp_path), "--freeze", str(path)])
    assert args.freeze == path


@pytest.mark.parametrize("change, message", [
    ({"software_id": "different"}, "software differs"),
    ({"protocol_id": "different"}, "protocol differs"),
    ({"validation": {"status": "failed"}}, "passed engineering validation"),
])
def test_scoring_freeze_rejects_unvalidated_or_changed_software(tmp_path, change, message):
    path = tmp_path / "freeze.json"
    path.write_text(json.dumps({**_record(), **change}))
    with pytest.raises(ValueError, match=message):
        read_scoring_freeze(path, {"software_id": "synthetic-software"})
