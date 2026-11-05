"""Invented complete retrieval traces verify lossless shared storage."""

import copy

import pytest

from moparse_eval.trace_storage import FORMAT, expand_evidence, share_evidence


def test_distinct_but_equal_sources_share_storage_without_removing_any_hit():
    source = {"path": "native:汉字", "text": "完整证据" * 2048, "lines": [7, 9]}
    hits = [{"id": f"hit:{n}", "source": copy.deepcopy(source),
             "decision": "accepted" if n == 19 else "explicit_scope_conflict",
             "context": {"subject": "Delta", "scope": ["North" if n == 19 else "South"]}}
            for n in range(100)]
    original = {"outcomes": [{"id": "B:0", "retrieval": {"candidates": hits}}]}
    snapshot = copy.deepcopy(original)
    encoded = share_evidence(original)
    assert encoded["trace_format"] == FORMAT
    assert expand_evidence(encoded) == original == snapshot
    assert len(expand_evidence(encoded)["outcomes"][0]["retrieval"]["candidates"]) == 100
    assert len([v for v in encoded["evidence"].values() if v == source["text"]]) <= 1


def test_source_reference_like_original_objects_are_not_misread_as_references():
    literal = {"$trace_ref": "an original candidate literal" * 50}
    wrapper = {"$trace_object": [["$trace_ref", "original input"]]}
    original = {"source": [literal, literal, wrapper, wrapper]}
    assert expand_evidence(share_evidence(original)) == original


@pytest.mark.parametrize("catalog,root,message", [
    ({}, {"$trace_ref": "missing"}, "missing"),
    ({"loop": {"$trace_ref": "loop"}}, {"$trace_ref": "loop"}, "cyclic"),
])
def test_invalid_catalogs_fail_instead_of_silently_dropping_retrieval_evidence(catalog, root, message):
    with pytest.raises(ValueError, match=message):
        expand_evidence({"trace_format": FORMAT, "score": root, "evidence": catalog})
