"""Admission checks use invented software metadata, without reading datasets."""

import pytest

from moparse_eval.cli import require_frozen_execution


def test_formal_execution_requires_new_authored_execution_freeze():
    for lock in ({}, {"frozen": False}, {"frozen": True}):
        with pytest.raises(ValueError, match="post-preflight execution lock"):
            require_frozen_execution(lock, {"software_id": "synthetic"})


@pytest.mark.parametrize("identity", [{}, {"software_id": "different"}])
def test_formal_execution_rejects_missing_or_changed_software_identity(identity):
    lock = {"frozen": True, "freeze_record": {"preflight": "invented"}, "software_identity": identity}
    with pytest.raises(ValueError, match="changed after the execution freeze"):
        require_frozen_execution(lock, {"software_id": "synthetic"})


def test_matching_frozen_software_is_admitted():
    require_frozen_execution({"frozen": True, "freeze_record": {"preflight": "invented"},
        "software_identity": {"software_id": "synthetic"}}, {"software_id": "synthetic"})
