"""Recheck three-layer evidence before formal publication.

Arithmetic and trace checks do not prove semantic compiler coverage. The
independent validation and real-format diagnosis gates remain separate.
"""

from __future__ import annotations

import copy
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from rapidfuzz.distance import Levenshtein

from .business_correspondence import (
    _family,
    _qualifier_check,
    _record_comparison,
    _value_check,
    assertion_signature,
    identity_checks,
    query_for,
    record_vector,
    requirement_key,
)
from .layer_aggregation import require_validation, summarize_layers
from .packaging import inside, read_json
from .relation_correspondence import (
    logical_roles_decision,
    logical_roles_equal,
    relation_scope_verification,
    unchanged_binding,
)
from .scalar_evidence import validate_scalar_sources
from .three_layer import PROTOCOL, canonical

PIPELINES = tuple(f"P{i:02}" for i in range(1, 9))


def _identity(item: dict[str, Any]) -> tuple[Any, ...]:
    return requirement_key(item, canonical)


def _source(item: dict[str, Any]) -> None:
    if not isinstance(item.get("source"), dict) or not item["source"].get("path"):
        raise ValueError("requirements and selected candidates must retain their actual source")


def _text_source(source: dict[str, Any], *, spans: bool = True) -> dict[str, Any]:
    names = ("path", "cell", "native_path", "lines", "block", "block_lines", "row", "col")
    if spans:
        names += ("text_span", "cell_text_span")
    return {name: source[name] for name in names if name in source}


def _text_source_key(source: dict[str, Any], *, spans: bool = True) -> str:
    return json.dumps(_text_source(source, spans=spans), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _source_identifier(identifier: str, prefix: str, source: dict[str, Any]) -> None:
    if not isinstance(identifier, str) or not identifier.startswith(prefix):
        raise ValueError("a text capacity identifier must name its actual source")
    try:
        decoded = json.loads(identifier[len(prefix):])
    except (TypeError, ValueError) as error:
        raise ValueError("a text capacity source identifier is malformed") from error
    if decoded != _text_source(source):
        raise ValueError("a text capacity identifier differs from its actual source")


def _text_sources(projection: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    cells: dict[str, dict[str, Any]] = {}
    fragments: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell in projection.get("source_cells", []):
        _source(cell)
        if not isinstance(cell.get("text"), str):
            raise ValueError("text cell evidence requires its original literal")
        identity = _text_source_key(cell["source"], spans=False)
        if identity in cells and cells[identity] != cell:
            raise ValueError("one physical text cell has conflicting original evidence")
        cells[identity] = cell
    for fragment in projection.get("source_fragments", []):
        _source(fragment)
        if not isinstance(fragment.get("text"), str):
            raise ValueError("text fragments require their original literal")
        fragments[_text_source_key(fragment["source"], spans=False)].append(fragment)
    return cells, fragments


def _origin_literal(origin: dict[str, Any], cells: dict[str, dict[str, Any]],
                    fragments: dict[str, list[dict[str, Any]]]) -> None:
    _source(origin)
    source = origin["source"]
    candidates = ([cells[_text_source_key(source, spans=False)]] if source.get("cell")
                  and _text_source_key(source, spans=False) in cells else
                  fragments.get(_text_source_key(source, spans=False), []))
    span = source.get("cell_text_span", source.get("text_span"))
    for candidate in candidates:
        raw = candidate["text"]
        offset = (candidate["source"].get("text_span") or [0])[0]
        if span is None:
            if origin["text"] == raw:
                return
        elif (isinstance(span, list) and len(span) == 2 and all(type(value) is int for value in span)
              and 0 <= span[0] - offset < span[1] - offset <= len(raw)
              and raw[span[0] - offset:span[1] - offset] == origin["text"]):
            return
    raise ValueError("text alias origin is absent from its original cell or fragment range")


def _literal_occurrences(atoms: list[dict[str, Any]], cells: dict[str, dict[str, Any]],
                         fragments: dict[str, list[dict[str, Any]]]) -> None:
    used: dict[str, list[tuple[int, int]]] = defaultdict(list)

    def claim(source: dict[str, Any], text: str) -> None:
        identity = _text_source_key(source, spans=False)
        candidates = [cells[identity]] if source.get("cell") and identity in cells else fragments.get(identity, [])
        wanted = source.get("cell_text_span", source.get("text_span"))
        for candidate in candidates:
            raw = candidate["text"]
            offset = (candidate["source"].get("text_span") or [0])[0]
            if wanted is not None and (not isinstance(wanted, list) or len(wanted) != 2
                                       or not all(type(value) is int for value in wanted)):
                raise ValueError("a literal occurrence has no valid source interval")
            for found in re.finditer(re.escape(text), raw):
                a, b = found.start() + offset, found.end() + offset
                if wanted is not None and not (wanted[0] <= a < b <= wanted[1]):
                    continue
                if any(a < stop and start < b for start, stop in used[identity]):
                    continue
                used[identity].append((a, b))
                return
        raise ValueError("literal text is missing or reuses an already consumed actual source occurrence")

    for atom in atoms:
        if atom.get("projection_kind") == "bounded_alias":
            continue
        sources = atom.get("source_fragments")
        if sources:
            texts = atom.get("source_fragment_texts")
            if texts is None:
                texts = atom.get("strict_text", "").split("\n")
            if (not isinstance(texts, list) or len(sources) != len(texts)
                    or canonical("\n".join(texts)) != canonical(atom["text"])):
                raise ValueError("merged prose requires every actual fragment and its original text")
            for source, text in zip(sources, texts, strict=True):
                claim(source, text)
        else:
            claim(atom["source"], atom.get("strict_text", atom["text"]))


def _text_atom_manifest(atoms: list[dict[str, Any]], projection: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(atoms, list) or not isinstance(projection, dict):
        raise ValueError("a complete precomparison text view is required for report verification")
    manifest: dict[str, dict[str, Any]] = {}
    capacity = set()
    cells, fragments = _text_sources(projection)
    origins = {}
    for origin in projection.get("origins", []):
        if not origin.get("id") or origin["id"] in origins and origins[origin["id"]] != origin:
            raise ValueError("text origins require distinct consistent source identities")
        origins[origin["id"]] = origin
    for atom in atoms:
        _source(atom)
        if (not atom.get("id") or atom["id"] in manifest or not isinstance(atom.get("text"), str)
                or not atom["text"].strip()):
            raise ValueError("the complete text view has duplicate or invalid occurrences")
        manifest[atom["id"]] = atom
        if atom.get("projection_kind") != "bounded_alias":
            continue
        obj = atom.get("data_object", {})
        _source(obj)
        _source_identifier(obj.get("id"), "data:", obj["source"])
        if not isinstance(atom.get("role"), str) or not atom["role"]:
            raise ValueError("a text alias requires its explicit source role")
        identity = (obj["id"], atom.get("role"), atom["text"])
        if identity in capacity:
            raise ValueError("one actual data object cannot provide repeated identical text capacity")
        capacity.add(identity)
        if atom.get("alias_key") != ":".join(identity):
            raise ValueError("a text alias key differs from its object, role or printed literal")
        if obj["source"].get("cell"):
            if _text_source_key(obj["source"], spans=False) not in cells:
                raise ValueError("a text alias invented a data object outside the actual cells")
        else:
            bounds = obj["source"].get("text_span")
            candidates = fragments.get(_text_source_key(obj["source"], spans=False), [])
            if not (bounds and any(0 <= bounds[0] < bounds[1] <= len(part["text"]) for part in candidates)):
                raise ValueError("a text alias lacks its independently present value object")
        atom_origins = atom.get("origins")
        if not isinstance(atom_origins, list) or not atom_origins:
            raise ValueError("bounded text capacity requires actual printed origins")
        seen = set()
        for origin in atom_origins:
            if (origin.get("id") in seen or origins.get(origin.get("id")) != origin
                    or origin.get("text") != atom["text"] or origin.get("role") != atom.get("role")):
                raise ValueError("a text alias differs from its complete printed origin evidence")
            seen.add(origin["id"])
            _source_identifier(origin["id"], origin["role"] + ":", origin["source"])
            _origin_literal(origin, cells, fragments)
        if atom["source"] not in [origin["source"] for origin in atom_origins]:
            raise ValueError("a text alias selected a source outside its actual origins")
    _literal_occurrences(atoms, cells, fragments)
    return manifest


def _complete_text_trace(score: dict[str, Any]) -> None:
    evidence = score.get("text_evidence")
    if not isinstance(evidence, dict):
        raise ValueError("formal text decisions require the full precomparison text evidence")
    required = _text_atom_manifest(evidence.get("required_atoms"), evidence.get("required_projection"))
    candidate = _text_atom_manifest(evidence.get("candidate_atoms"), evidence.get("candidate_projection"))
    rows = [row for row in score["outcomes"] if row["layer"] == "T"]
    if Counter(row["expected"]["id"] for row in rows) != Counter(required.keys()):
        raise ValueError("text requirements differ from the complete precomparison view")
    used = set()
    for row in rows:
        if row["expected"] != required[row["expected"]["id"]]:
            raise ValueError("a text requirement differs from its original complete evidence")
        actual = row.get("actual")
        if actual:
            if actual.get("id") in used:
                raise ValueError("one candidate text occurrence cannot satisfy multiple requirements")
            used.add(actual.get("id"))
            if candidate.get(actual.get("id")) != actual:
                raise ValueError("a text match differs from its actual precomparison occurrence")


def _joined_prose_trace(score: dict[str, Any]) -> None:
    """Check B/L fragment claims against the independently retained T sources."""
    evidence = score["text_evidence"]
    views, checked = {}, set()

    def check(source, side):
        token = (side, json.dumps(source, ensure_ascii=False, sort_keys=True))
        if token in checked:
            return
        checked.add(token)
        if side not in views:
            projection = evidence[side + "_projection"]
            views[side] = (*_text_sources(projection), evidence[side + "_atoms"])
        cells, raw_fragments, atoms = views[side]
        fragments = source["joined_fragments"]
        if not isinstance(fragments, list) or len(fragments) < 2:
            raise ValueError("joined prose requires every actual source fragment")
        joined, pieces, sources = "", [], []
        for fragment in fragments:
            if not isinstance(fragment, dict):
                raise ValueError("joined prose has a malformed original fragment")
            _source(fragment)
            text, span = fragment.get("text"), fragment.get("joined_span")
            if not isinstance(text, str) or not text:
                raise ValueError("joined prose requires its unchanged original wording")
            separator = ("" if joined and re.search(r"[\u3400-\u9fff]$", joined)
                         and re.match(r"[\u3400-\u9fff]", text) else " ") if joined else ""
            start = len(joined) + len(separator)
            if (not isinstance(span, list) or len(span) != 2 or not all(type(value) is int for value in span)
                    or span != [start, start + len(text)]):
                raise ValueError("joined prose has an invalid or reordered fragment interval")
            joined += separator + text
            pieces.append(text)
            sources.append(fragment["source"])
        if _text_source_key(source, spans=False) != _text_source_key(sources[0], spans=False):
            raise ValueError("joined prose no longer names its first actual source")
        if not any(atom.get("source_fragments") == sources and atom.get("source_fragment_texts") == pieces
                   and atom.get("text") == joined for atom in atoms):
            raise ValueError("joined prose differs from the actual ordered text fragments")
        try:
            _literal_occurrences([{"source": original, "text": text} for original, text in zip(sources, pieces, strict=True)],
                                 cells, raw_fragments)
        except ValueError as error:
            raise ValueError("joined prose refers to absent or reused original wording") from error
        span = source.get("text_span")
        offset = (sources[0].get("text_span") or [0])[0]
        if span is not None and (not isinstance(span, list) or len(span) != 2
                                 or not all(type(value) is int for value in span)
                                 or not 0 <= span[0] - offset < span[1] - offset <= len(joined)):
            raise ValueError("joined prose assertion range is outside its original fragments")

    def walk(value, side):
        if isinstance(value, dict):
            if "joined_fragments" in value and "path" in value:
                check(value, side)
            for nested in value.values():
                walk(nested, side)
        elif isinstance(value, list):
            for nested in value:
                walk(nested, side)

    for row in score["outcomes"]:
        if row["layer"] == "T":
            continue
        walk(row["expected"], "required")
        for hit in row.get("retrieval", {}).get("candidates", []):
            walk(hit.get("candidate", hit.get("evidence", {})), "candidate")


def _business_trace(row: dict[str, Any], scope_options: dict[str, Any]) -> None:
    expected, trace = row["expected"], row.get("retrieval", {})
    query = query_for(expected)
    if trace.get("query") != query or not isinstance(trace.get("candidates"), list):
        raise ValueError("business retrieval requires an answer-independent complete identity query")
    if not isinstance(trace.get("textual_hits"), list):
        raise ValueError("business retrieval must retain literal hits independently of data-role proof")
    for hit in trace["textual_hits"]:
        _source(hit)
        if not hit.get("text") or not hit.get("reason") or hit.get("decision") != "literal_evidence_only":
            raise ValueError("a raw literal hit cannot supply an unproved business value")
    accepted, seen, exposed = [], set(), {}
    for hit in trace["candidates"]:
        _source(hit)
        if not hit.get("id") or hit["id"] in seen or not hit.get("reason"):
            raise ValueError("retrieval candidates need unique identities and exclusion reasons")
        seen.add(hit["id"])
        candidate = hit.get("candidate")
        if not isinstance(candidate, dict) or candidate.get("id") != hit["id"]:
            raise ValueError("retrieval must retain each candidate's own complete fact before selection")
        _source(candidate)
        if candidate["source"] != hit["source"]:
            raise ValueError("retrieval source differs from the actual recalled candidate")
        checks = identity_checks(query, candidate, canonical, **scope_options)
        if hit.get("identity") != checks:
            raise ValueError("retrieval admitted an inconsistent identity decision")
        context = hit.get("context_evidence", {})
        if (context.get("candidate_scope") != candidate.get("scope", [])
                or context.get("candidate_facets") != candidate.get("identity_facets", {})
                or context.get("source") != candidate["source"]):
            raise ValueError("business context must come from the candidate's own declared evidence")
        eligible = all(check["correct"] for check in checks.values())
        if hit.get("decision") != ("accepted" if eligible else "rejected"):
            raise ValueError("a conflicting retrieval candidate cannot supply a compared value")
        if eligible:
            accepted.append(hit["id"])
            exposed[hit["id"]] = candidate
    if trace.get("accepted") != accepted:
        raise ValueError("retrieval accepted-set differs from its complete trace")
    actual = row.get("actual")
    if not isinstance(actual, list) or Counter(item["id"] for item in actual) != Counter(accepted):
        raise ValueError("business values must come from the complete identity-validated set")
    for item in actual:
        _source(item)
        if item != exposed[item["id"]]:
            raise ValueError("a compared business value differs from its actual recalled candidate")
    comparisons = [{"id": item["id"], "value": _value_check(expected, item, canonical),
                    "qualifiers": {dimension: _qualifier_check(expected, item, dimension, canonical)
                                   for dimension in sorted(set(expected.get("qualifiers", {})) | set(item.get("qualifiers", {})))}}
                   for item in actual]
    if row.get("comparisons") != comparisons:
        raise ValueError("business comparison equivalence differs from the shared final decision")


def _record_trace(row: dict[str, Any], replay: dict[str, Any] | None) -> bool:
    comparison = row.get("record_comparison")
    if comparison is None:
        if replay is not None:
            raise ValueError("a complete required record comparison is absent")
        return True
    if comparison.get("rule") != "complete_record_vector_multiset" or comparison.get("complete") is not True:
        raise ValueError("unsupported duplicate record provenance cannot provide a published business judgment")
    if replay is None or replay.get("complete") is not True:
        raise ValueError("record equivalence cannot be reconstructed from the complete business evidence")
    mappings = comparison.get("field_equivalence")
    expected_mappings = replay.get("field_equivalence", [])
    if (not isinstance(mappings, list) or len({item.get("candidate_id") for item in mappings}) != len(mappings)
            or {item.get("candidate_id"): item for item in mappings} != {item["candidate_id"]: item for item in expected_mappings}):
        raise ValueError("record field equivalence differs from source-bound identity decisions")
    labels = {item["candidate_id"]: item["required_attribute"] for item in expected_mappings}
    collections = []
    for side in ("required_records", "actual_records"):
        records = comparison.get(side)
        if not isinstance(records, list):
            raise ValueError("repeated business assertions require complete record vectors")
        seen = set()
        fields_by_record = {}
        for record in records:
            if not record.get("record_id") or record["record_id"] in seen or not record.get("fields"):
                raise ValueError("repeated record vectors require unique actual record identities")
            seen.add(record["record_id"])
            fields_by_id = {}
            for item in record["fields"]:
                _source(item)
                if (item.get("record_id") or item["source"].get("record_id")) != record["record_id"]:
                    raise ValueError("a vector field is outside its declared actual source record")
                if not item.get("id") or item["id"] in fields_by_id:
                    raise ValueError("record fields require unique actual identities")
                fields_by_id[item["id"]] = item
            fields_by_record[record["record_id"]] = fields_by_id
        expected_fields = {record["record_id"]: {item["id"]: item for item in record["fields"]} for record in replay[side]}
        if fields_by_record != expected_fields:
            raise ValueError("record comparison omitted or changed a field from its complete source-bound collection")
        collections.append(Counter(record_vector(record["fields"], canonical,
                                  attribute_labels=labels if side == "actual_records" else None) for record in records))
    equal = collections[0] == collections[1]
    if comparison.get("equal") != equal:
        raise ValueError("record-vector comparison differs from its complete field collections")
    if comparison.get("equal") != replay["equal"] or comparison.get("reason") != replay["reason"]:
        raise ValueError("record equivalence differs from the shared complete-record decision")
    required = [item for record in comparison["required_records"] for item in record["fields"]]
    if not any(item == row["expected"] for item in required):
        raise ValueError("a scored repeated requirement is absent from its full record comparison")
    return equal


def _relation_trace(row: dict[str, Any], used: set[str], scope_options: dict[str, Any]) -> None:
    trace, actual, expected = row.get("retrieval", {}), row.get("actual"), row["expected"]
    if trace.get("method") not in {"independent_object_anchor", "declared_logical_roles"}:
        raise ValueError("logical relations require their endpoint retrieval method")
    hits = trace.get("candidates")
    if not isinstance(hits, list) or len({hit.get("id") for hit in hits}) != len(hits):
        raise ValueError("logical relation candidates require distinct actual identities")
    for hit in hits:
        _source(hit)
        if not hit.get("id") or type(hit.get("correct")) is not bool or not hit.get("reason"):
            raise ValueError("logical relation candidates require actual sources and decisions")
        edge = hit.get("evidence")
        if not isinstance(edge, dict) or edge.get("id") != hit["id"] or edge.get("source") != hit["source"]:
            raise ValueError("logical relation candidates must retain their actual complete endpoint evidence")
        proof = relation_scope_verification(expected, edge, canonical, **scope_options)
        equivalence = logical_roles_decision(expected, edge, canonical, **scope_options)
        if hit.get("equivalence") != equivalence:
            raise ValueError("logical endpoint equivalence differs from the shared final decision")
        correct = ((unchanged_binding(expected, edge, canonical) and (proof is None or proof["correct"]))
                   or equivalence["equivalent"])
        if hit["correct"] != correct or hit.get("scope_verification") != proof:
            raise ValueError("logical relation retrieval contradicts its actual scope and endpoint proof")
    selected = trace.get("selected")
    eligible = [hit for hit in hits if hit["correct"]]
    if selected != (eligible[0]["id"] if eligible else None):
        raise ValueError("a logical relation selected a conflicting or different endpoint")
    if actual is None:
        if selected is not None or row["outcome"] != "incorrect" or (hits and trace["method"] == "independent_object_anchor"):
            raise ValueError("logical relation decision contradicts its endpoint retrieval")
        return
    _source(actual)
    if actual["id"] in used:
        raise ValueError("one candidate relation cannot satisfy multiple requirements")
    used.add(actual["id"])
    matched = [hit for hit in hits if hit["id"] == actual["id"] and hit["source"] == actual["source"]]
    if len(matched) != 1:
        raise ValueError("the compared logical endpoint is outside the recalled candidate set")
    if matched[0]["evidence"] != actual:
        raise ValueError("relation decision has different endpoints or differs from its actually recalled evidence")
    proof = relation_scope_verification(expected, actual, canonical, **scope_options)
    correct = ((unchanged_binding(expected, actual, canonical) and (proof is None or proof["correct"]))
               or logical_roles_equal(expected, actual, canonical, **scope_options))
    if matched[0]["correct"] != correct or row["outcome"] != ("correct" if correct else "incorrect"):
                raise ValueError("relation decision has different endpoints or contradicts its complete binding evidence")
    if correct and selected != actual["id"]:
        raise ValueError("the logical relation selected a different actual endpoint")
    if not correct and (selected is not None or trace["method"] != "independent_object_anchor"
                        or not expected.get("object_anchor") or expected.get("object_anchor") != actual.get("object_anchor")):
        raise ValueError("an incorrect located binding requires the same independent data object")


def _validate_flat_evidence(score: dict[str, Any]) -> None:
    """Independently read back edits, occurrences, relation endpoints and traces."""
    if score.get("protocol") != PROTOCOL:
        raise ValueError("mixed scoring protocols cannot be published")
    _complete_text_trace(score)
    _joined_prose_trace(score)
    evidence = score["text_evidence"]
    business_rows = [row for row in score["outcomes"] if row["layer"] == "B"]
    validate_scalar_sources((row["expected"] for row in business_rows), evidence["required_projection"], canonicalize=canonical)
    # Annual comparison ownership needs the complete candidate bank. A
    # correctly rejected metric can be absent from retrieval hits while its
    # own source still proves the candidate's local year binding.
    candidate_bank = score.get('semantic_comparison', {}).get('inputs', {}).get('actual', {}).get('business')
    if not isinstance(candidate_bank, list):
        raise ValueError('scalar source replay lacks its complete candidate business bank')
    validate_scalar_sources(candidate_bank, evidence["candidate_projection"], canonicalize=canonical)
    summarize_layers([score])
    scope_options = {key: score.get("scope_evidence", {}).get(key, None if key == "contexts" else ())
                     for key in ("contexts", "declared_paths", "context_labels")}
    actual_facts = {}
    families = defaultdict(list)
    for row in business_rows:
        family = _family(row["expected"], canonical)
        families[family].append(row["expected"])
        for hit in row.get("retrieval", {}).get("candidates", []):
            item = hit["candidate"]
            if item["id"] in actual_facts and actual_facts[item["id"]] != item:
                raise ValueError("one actual business identity has inconsistent complete evidence")
            actual_facts[item["id"]] = item
    record_replays = {family: _record_comparison(members, list(actual_facts.values()), canonical, **scope_options)
                      for family, members in families.items()}
    text = [row for row in score["outcomes"] if row["layer"] == "T"]
    totals, strict_totals = Counter(), Counter()
    denominator, located_chars, located, used = 0, 0, 0, set()
    relation_used, business = set(), defaultdict(list)
    for row in score["outcomes"]:
        _source(row["expected"])
        if not row.get("root_cause"):
            raise ValueError("each decision must retain its common-cause trace")
        if row["layer"] == "T":
            expected = row["expected"]["text"]
            actual = row["actual"]["text"] if row.get("actual") else ""
            a, b = canonical(expected), canonical(actual)
            denominator += len(a)
            strict_expected = row["expected"].get("strict_text", expected)
            strict_actual = row["actual"].get("strict_text", actual) if row.get("actual") else ""
            for wanted, observed, field, counts in ((a, b, "edits", totals),
                                                   (strict_expected, strict_actual, "strict_edits", strict_totals)):
                operations = Counter(op.tag for op in Levenshtein.editops(wanted, observed))
                edits = {"S": operations["replace"], "D": operations["delete"], "I": operations["insert"]}
                if row.get(field) != edits:
                    raise ValueError("text S/D/I differs from its actual paired literals")
                counts.update(edits)
            if row["outcome"] != ("correct" if a == b else "incorrect"):
                raise ValueError("text decision contradicts its paired literals")
            if row.get("actual"):
                _source(row["actual"])
                identity = row["actual"]["id"]
                if identity in used:
                    raise ValueError("one candidate text occurrence cannot satisfy multiple requirements")
                used.add(identity)
                located += 1
                located_chars += len(a)
        elif row["layer"] == "B":
            _business_trace(row, scope_options)
            business[_identity(row["expected"])].append(row)
        else:
            _relation_trace(row, relation_used, scope_options)
    counts = score["layers"]["T"]
    expected_counts = {"numerator": denominator - sum(totals.values()), "denominator": denominator,
                       "required_units": len(text), "located_units": located,
                       "located_characters": located_chars, **dict(totals)}
    if any(counts.get(key, 0) != value for key, value in expected_counts.items()):
        raise ValueError("text full-range aggregate differs from its character decisions")
    for members in business.values():
        expected_set = Counter(assertion_signature(row["expected"], canonical) for row in members)
        actual_set = Counter(assertion_signature(item, canonical) for item in members[0]["actual"])
        record_equal = [_record_trace(row, record_replays.get(_family(row["expected"], canonical))) for row in members]
        correct = expected_set == actual_set and all(record_equal)
        if any(row["actual"] != members[0]["actual"] or row["outcome"] != ("correct" if correct else "incorrect") for row in members):
            raise ValueError("business judgment contradicts the complete repeated assertion set")


def validate_evidence(score: dict[str, Any]) -> None:
    """Replay both flat evidence and any compositional decision that changed it."""
    semantic = score.get("semantic_comparison")
    if semantic is None:
        raise ValueError("semantic comparison evidence is required by the current scoring contract")
    from .semantic_layer_comparison import compare_semantic_layers

    inputs = semantic.get("inputs", {})
    if set(inputs) != {"required", "actual"}:
        raise ValueError("semantic comparison lacks its independently retained inputs")
    text = score.get("text_evidence", {})
    if any(inputs[side].get("text_projection") != text.get(key) for side, key in
           (("required", "required_projection"), ("actual", "candidate_projection"))):
        raise ValueError("semantic sources differ from actual retained text evidence")
    flat = copy.deepcopy(score)
    for row in flat["outcomes"]:
        if "flat_outcome" in row:
            row["outcome"] = row.pop("flat_outcome")
        row.pop("ast_comparisons", None)
        row.pop("semantic_comparison_status", None)
        row.pop("semantic_responsibility", None)
    for layer in ("B", "L"):
        own = flat["layers"][layer]
        own["numerator"] = sum(row["outcome"] == "correct" for row in flat["outcomes"] if row["layer"] == layer)
        own["score"] = 100 * own["numerator"] / own["denominator"] if own["denominator"] else None
    flat["score"] = sum(layer["score"] for layer in flat["layers"].values()) / 3 if all(
        layer["score"] is not None for layer in flat["layers"].values()) else None
    _validate_flat_evidence(flat)
    business_rows = [row for row in score["outcomes"] if row["layer"] == "B"]
    required_owners = {fact["id"]: fact for fact in inputs["required"].get("business", [])}
    if (len(required_owners) != len(business_rows)
            or required_owners != {row["expected"]["id"]: row["expected"] for row in business_rows}):
        raise ValueError("semantic target owners differ from the complete business requirements")
    actual_owners = {fact["id"]: fact for fact in inputs["actual"].get("business", [])}
    if len(actual_owners) != len(inputs["actual"].get("business", [])) or any(
            actual_owners.get(hit["candidate"]["id"]) != hit["candidate"]
            for row in business_rows for hit in row.get("retrieval", {}).get("candidates", [])):
        raise ValueError("semantic candidate owners differ from actual retrieved business evidence")
    scope_options = {key: score.get("scope_evidence", {}).get(key, None if key == "contexts" else ())
                     for key in ("contexts", "declared_paths", "context_labels")}
    replay = compare_semantic_layers(inputs["required"], inputs["actual"], flat["outcomes"], flat["layers"],
                                     canonicalize=canonical, scope_options=scope_options)
    if replay != semantic or flat["outcomes"] != score["outcomes"]:
        raise ValueError("semantic comparison differs from its source-bound recursive replay")
    if any(blocker not in score.get("blockers", []) for blocker in replay["blockers"]):
        raise ValueError("semantic comparison blockers were omitted from the publication decision")
    for layer in ("B", "L"):
        if flat["layers"][layer]["numerator"] != score["layers"][layer]["numerator"]:
            raise ValueError("semantic layer aggregate differs from its unchanged target votes")
    summarize_layers([score])


def text_layer_diagnostics(scores: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep full-range and strict edits visible without redefining the T score."""
    edits, strict_edits = Counter(), Counter()
    units = located_units = denominator = located_chars = extras = 0
    for score in scores:
        for row in score["outcomes"]:
            if row["layer"] != "T":
                continue
            units += 1
            chars = len(canonical(row["expected"]["text"]))
            denominator += chars
            edits.update(row["edits"])
            strict_edits.update(row["strict_edits"])
            if row.get("actual"):
                located_units += 1
                located_chars += chars
        extras += len(score["layers"]["T"].get("unadjudicated_extra_units", []))
        if score["outcomes"]:
            del row
        del score
    return {"required_units": units, "located_units": located_units, "required_characters": denominator,
            "located_characters": located_chars, "edits": dict(edits), "strict_edits": dict(strict_edits),
            "unadjudicated_extra_units": extras,
            "meaning": "full_expected_scope_text_consistency_not_original_pdf_ocr_accuracy"}


class SavedScoreGroup:
    """A reusable file-backed view; iteration never caches complete scores."""

    def __init__(self, root: Path, records: list[dict[str, Any]]):
        self.root, self.records = root, records

    def __len__(self):
        return len(self.records)

    def __iter__(self):
        from .trace_storage import read_score

        for record in self.records:
            yield read_score(inside(self.root, record["path"]))


def load_complete(index_path: Path) -> tuple[dict[str, Any], dict[str, SavedScoreGroup]]:
    from .streaming_aggregation import aggregate_score_files
    from .trace_storage import read_score

    index = read_json(index_path)
    if (index.get("state") != "completed" or index.get("expected_comparison_complete") is not True
            or index.get("protocol") != PROTOCOL or index.get("blockers")):
        raise ValueError("complete validated three-layer comparison is required before publication")
    require_validation(index.get("validation", {}))
    software_id = index.get("software", {}).get("software_id")
    if not software_id:
        raise ValueError("formal results require a frozen software identity")
    records_by_path, groups, seen = {}, defaultdict(list), set()
    for record in index["records"]:
        key = record["group"], record["sample_id"]
        path = inside(index_path.parent, record["path"])
        if key in seen or path in records_by_path:
            raise ValueError("duplicate evaluated sample/group or scoring file")
        seen.add(key)
        records_by_path[path] = record
        groups[record["group"]].append(record)
    if not groups or set(groups) != set(index["groups"]) or len(index["groups"]) != len(groups):
        raise ValueError("declared comparison groups are missing or duplicated")
    coverage = {row["sample_id"]: row for row in index["coverage"]}
    if len(coverage) != len(index["coverage"]):
        raise ValueError("declared expected scope contains duplicate samples")

    def validated_read(path):
        record = records_by_path[path.resolve()]
        score = read_score(path)
        if (score.get("sample_id") != record["sample_id"]
                or score.get("pipeline") != record["group"].split("-", 1)[0]):
            raise ValueError("mismatched evaluated sample/group")
        if score.get("scoring_software_id") != software_id:
            raise ValueError("mixed scoring software cannot be published")
        validate_evidence(score)
        return score

    # This also proves common targets and all layer denominators while only
    # retaining one complete score and one sample's compact comparisons.
    pooled = aggregate_score_files(index["records"], groups=index["groups"], base_dir=index_path.parent,
                                   reader=validated_read, expected_sample_ids=coverage)
    if pooled["summary"] != index.get("summary"):
        raise ValueError("group summary differs from its actual layer decisions")
    if not pooled["publishable"]:
        raise ValueError("global quality requires three legal nonzero layer denominators")
    for row in pooled["coverage"]:
        if row["layers"] != coverage[row["sample_id"]]["layers"]:
            raise ValueError("a layer differs from the frozen expected denominator")
    if index.get("paired", {}) != pooled["paired"]:
        raise ValueError("paired layer summary differs from its actual same-target decisions")
    return index, {name: SavedScoreGroup(index_path.parent, records) for name, records in groups.items()}
