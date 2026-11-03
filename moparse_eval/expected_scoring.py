"""Common binary output grading against a transient read-only expected view."""

from __future__ import annotations

import copy
import re
from bisect import bisect_left, bisect_right
from collections import Counter
from functools import lru_cache
from typing import Any

from .context_matching import (
    consecutive_title_pairs,
    flat_display_levels,
    flat_level_in_scope,
    heading_context_keys,
    literal_context_members,
    repeated_ancestor_evidence,
)
from .expected_readback import (
    ExpectedReadError,
    _field,
    _pairs,
    list_scope,
    qualify_reference_record,
)
from .information import business_scope_text, row_path_locates
from .information_reading import (
    _PRINTED_REPORT_TITLE,
    read_information_observation,
    report_title_transition,
)
from .matching import (
    _approximate_spans,
    _normalized_positions,
    _text_streams,
    _whole_numeric_span,
    in_page_scope,
    match_units,
    observation_candidates,
)
from .metrics import normalize_text, text_metrics
from .prose_metrics import changed_spans, summarize_text
from .score_contract import require_retrieval_evidence
from .scoring import _locate_record_field, _required_qualifiers, _score_records
from .target_coverage import partition_record, require_complete_ranges

PROTOCOL = {
    "id": "mo-parse-expected-only-v2", "reference": "canonical_expected_read_only",
    "scope": "existing_authored_source_map_selected_content",
    "grades": ["correct", "incorrect"], "legacy_adjudications": "not_consumed",
    "field_locator": "text_recall_required_identity_and_bounded_candidate_context_before_values",
    "retrieval_evidence": "identity_query_all_hits_context_checks_rejections_selected_origin",
    "text_policy": "mo-parse-eval-text-v1", "reader_failure": "repair_before_publication",
    "field_content_equivalence": "declared_width_spacing_comma_separator_spacing_cjk_latin_term_edges_scoped_scalar_units_year_range_dash_terminal_prose_punctuation_label_quote_parenthesis_operator_typography_checkbox_label_edges",
    "qualifier_reading": "candidate_only_explicit_table_record_caption_and_note_scopes",
    "output_reading": "native_fields_or_actual_public_markdown_without_private_ir_credit",
    "reader_revision": "identity_retrieval_and_bounded_candidate_context",
    "repeated_records": "complete_record_multiset_comparison_after_complete_identity_collection_localization",
}


def _checkbox_sequence(text: str) -> tuple[tuple[str, str], ...] | None:
    """Read only whitespace at the edges of two or more explicit check labels.

    Markers, negations and whitespace inside each label remain literal. Raw
    character diagnostics continue to use the unchanged original strings.
    """
    marks = list(re.finditer(r"[□☐☑☒√✓✔✗✘]", text))
    if len(marks) < 2 or text[:marks[0].start()].strip():
        return None
    result = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        label = text[mark.end():end].strip()
        if not label:
            return None
        result.append((mark.group(), label))
    return tuple(result)


def _table_records(target: dict[str, Any]) -> list[dict[str, Any]]:
    """Read explicit authored table headers, never manufacturing a first row."""
    cells = target["cells"]
    leading = set()
    for row in sorted({c["row"] for c in cells}):
        band = [c for c in cells if c["row"] == row]
        if not all(c.get("native_header_tag") and not c.get("is_row_header") for c in band):
            break
        leading.add(row)
    headers = [c for c in cells if (c.get("is_column_header") is True or c["row"] in leading) and c["text"].strip()]
    if not headers:
        return []
    header_rows = {row for c in headers for row in range(c["row"], c["row"] + c.get("row_span", 1))}
    rows = sorted({c["row"] for c in cells} - header_rows)
    result = []
    for row in rows:
        band = [c for c in cells if c["row"] <= row < c["row"] + c.get("row_span", 1)
                and c["row"] not in header_rows]
        explicit_subjects = [c for c in band if c.get("is_row_header") and c["text"].strip()]
        subjects = sorted(explicit_subjects or [c for c in band if c["col"] == 0 and c["text"].strip()],
                          key=lambda cell: cell["col"])
        if not subjects:
            continue
        fields = []
        for cell in band:
            if cell in subjects:
                continue
            labels = [c["text"] for c in sorted(headers, key=lambda c: (c["row"], c["col"]))
                      if c["col"] <= cell["col"] < c["col"] + c.get("col_span", 1)]
            if not labels:
                raise ExpectedReadError("expected table field has no explicitly expressed column label")
            explicit = _pairs(cell["text"])
            if explicit and len(explicit) > 1:
                fields.extend({**_field(" / ".join([*labels, key]), value), "source_cell_index": cells.index(cell)}
                              for key, value in explicit)
            else:
                fields.append({**_field(" / ".join(labels), cell["text"]), "source_cell_index": cells.index(cell)})
        if fields:
            parsed = {"id": target["id"], "row_header_path": [c["text"] for c in subjects], "fields": fields}
            context = target.get("reference_context", {})
            qualify_reference_record(parsed, context.get("units", []), context.get("periods", []), context.get("currencies", []))
            result.append({**target, "id": f"{target['id']}:row:{row}", "record": parsed})
    return result


def _prepared(expected: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    texts, records = [], []
    for target in expected["targets"]:
        source = {"id": target["id"], "kind": "image" if target["kind"] == "image_alt_text" else "text", "pages": target["pages"],
                  "source_element_id": target["id"],
                  "reference_text": target["text"], "reference": target["reference"],
                  "expected_context": target["context"], "expected_kind": target["kind"]}
        source.update(list_parents=target.get("parents", []), has_children=target.get("has_children", False))
        if target.get("record"):
            table = copy.deepcopy(target["record"])
            if not table["fields"]:
                raise ExpectedReadError("an expected record was read without its required fields")
            table.setdefault("id", f"expected:list:{target['list_span']}" if target.get("list_span")
                             else " / ".join(target["context"]) or "expected-records")
            if target.get("has_children") and len(table["fields"]) == 1:
                field = table["fields"][0]
                if field.get("named_value") and field.get("unit") is None and not re.fullmatch(r"[\d\s,.+\-−()%‰]+", field["value"]):
                    parents = list_scope(target.get("parents", [])) or {"rows": []}
                    field["subject_identity"] = {"row_header_path": [*parents["rows"], field["value"]],
                                                 "column_header_path": table["row_header_path"][-1:]}
            records.append({**source, "kind": "table_record", "table": table,
                            "reference_text": table["row_header_path"][-1]})
            if target.get("also_prose"):
                texts.append({**source, "id": source["id"] + ":prose"})
        elif target.get("cells"):
            table_rows = _table_records(target)
            for row in table_rows:
                records.append({**source, "id": row["id"], "kind": "table_record", "table": row["record"],
                                "reference_text": row["record"]["row_header_path"][-1]})
            # Values already have business-field targets. Keep table labels
            # and unbound prose as visible-content targets without inventing
            # header semantics for a first row with no declared header role.
            for i, cell in enumerate(target["cells"]):
                if any(field.get("source_cell_index") == i for row in table_rows for field in row["record"]["fields"]):
                    continue
                if cell["text"].strip():
                    texts.append({**source, "id": f"{source['id']}:cell:{i}", "reference_text": cell["text"],
                                  "expected_kind": "table_cell_text"})
        elif source["reference_text"]:
            texts.append(source)
    # An explicitly authored scope identifies a field even when the selected
    # reference contains no second homonymous record. Candidate multiplicity
    # must never determine which reference requirements are enforced.
    selected_headings={target['text'] for target in expected['targets'] if target['kind']=='heading'}
    for record in records:
        heading = record["expected_context"][-1] if record["expected_context"] else ""
        for field in record["table"]["fields"]:
            if heading and not re.fullmatch(r"(?:19|20)\d{2}\s*(?:年(?:度|末)?)?", heading):
                field["business_scope"] = heading
                parents=[label for label in record['expected_context'][:-1] if label in selected_headings
                         and not re.fullmatch(r'(?:19|20)\d{2}\s*(?:年(?:度|末)?)?',label)]
                if parents:
                    field['parent_scopes']=parents
    for target in expected["targets"]:
        if not target.get("record") or target.get("also_prose"):
            continue
        members = [row for row in records if row["source_element_id"] == target["id"]]
        _, residual = partition_record(target, members)
        base = members[0]
        texts.extend({**base, **part, "kind": "text"} for part in residual)
    return texts, records


def grade_expected(expected: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    """Grade every target using one shared policy, with no pipeline branches."""
    if expected["sample_id"] != observation.get("sample_id"):
        raise ValueError("expected and candidate sample identities differ")
    if observation.get("scoring_readback", {}).get("native_status") == "readback_error":
        raise ValueError("candidate reader failed; repair it before grading")
    texts, records = _prepared(expected)
    matching = match_units(records, observation, threshold=0.8, collapse_whitespace=True)
    matching['heading_targets']=[target for target in expected['targets'] if target['kind']=='heading']
    matching['context_members']=literal_context_members(expected['targets'])
    text_matching = match_units(texts, observation, threshold=0.8, collapse_whitespace=True)
    candidates = observation_candidates(observation)
    visible = [(item, *_normalized_positions(item["text"], True)) for item in candidates]
    streams_by_pages: dict[tuple[int, ...], list[tuple[Any, ...]]] = {}
    candidate_map = {item["id"]: item for item in candidates}
    record_rows, record_metrics = _score_records(records, observation, True, matching)
    outcomes = []
    used_heading_literals = set()
    for target in texts:
        match = text_matching["matches"].get(target["id"])
        wanted = normalize_text(target["reference_text"], collapse_whitespace=True)
        if target["expected_kind"] == "heading":
            standalone = [(item, positions) for item, text, positions in visible if text == wanted
                          and positions and in_page_scope(item, set(target["pages"]))]
            primary = [pair for pair in standalone if pair[0]["kind"] == "text"] or standalone
            available = [pair for pair in primary if pair[0]["id"] not in used_heading_literals]
            if available:
                item, positions = min(available, key=lambda pair: pair[0]["order"])
                used_heading_literals.add(item["id"])
                a, b = positions[0][0], positions[-1][1]
                match = {"candidate_id": item["id"], "native_path": item.get("native_path"),
                         "hypothesis": item["text"][a:b], "span": [a, b],
                         "claims": [{"candidate_id": item["id"], "span": [a, b]}],
                         "method": "standalone_literal_before_infix_mentions"}
            elif primary:
                match = None
        # Repeated headings/labels still preserve their literal content. Their
        # business ownership is graded independently by complete record paths.
        if not match and wanted and not (target["expected_kind"] == "heading" and standalone):
            scope = tuple(sorted(target["pages"]))
            if scope not in streams_by_pages:
                streams_by_pages[scope] = [(item, *_normalized_positions(item["text"], True))
                                          for item in _text_streams(candidates, set(scope))]
            exact = [(item, text.index(wanted), positions) for item, text, positions in [*visible, *streams_by_pages[scope]] if wanted in text
                     and in_page_scope(item, set(target["pages"]))
                     and (not wanted.replace(",", "").replace(".", "").isdigit()
                          or _whole_numeric_span(text, text.index(wanted), text.index(wanted) + len(wanted)))]
            if exact:
                item, start, positions = exact[0]
                raw_start, raw_end = positions[start][0], positions[start + len(wanted) - 1][1]
                match = {"candidate_id": item["id"], "native_path": item.get("native_path"),
                         "hypothesis": item["text"][raw_start:raw_end], "span": [raw_start, raw_end],
                         "normalized_span": [start, start + len(wanted)],
                         "method": "complete_visible_literal_presence", "matching_occurrences": len(exact)}
                if item.get("components"):
                    match["claims"] = [{"candidate_id": part["candidate_id"],
                        "native_path": candidate_map[part["candidate_id"]].get("native_path"),
                        "span": [max(raw_start, part["start"]) - part["start"],
                                 min(raw_end, part["end"]) - part["start"]]}
                        for part in item["components"] if part["start"] < raw_end and part["end"] > raw_start]
        actual = match["hypothesis"] if match else ""
        scope = tuple(sorted(target["pages"]))
        if scope not in streams_by_pages:
            streams_by_pages[scope] = [(item, *_normalized_positions(item["text"], True))
                                      for item in _text_streams(candidates, set(scope))]
        occurrences = max(sum(text.count(wanted) for item, text, _ in visible if wanted and in_page_scope(item, set(scope))),
                          sum(text.count(wanted) for _item, text, _ in streams_by_pages[scope] if wanted))
        correct = bool(match and normalize_text(target["reference_text"], collapse_whitespace=True)
                       == normalize_text(actual, collapse_whitespace=True))
        outcomes.append({"id": target["id"], "kind": target["expected_kind"],
                         "source_element_id": target["source_element_id"],
                         "reference": target["reference"], "expected": target["reference_text"],
                         "context": target["expected_context"], "outcome": "correct" if correct else "incorrect",
                         "list_context": target["list_parents"],
                         "reason": "complete_visible_text" if correct else "text_missing_or_different",
                         "candidate": match, "actual": actual,
                         "distinct_occurrences": occurrences,
                         "text": text_metrics(target["reference_text"], actual, collapse_whitespace=True),
                         "differences": changed_spans(target["reference_text"], actual)})
    by_id = {record["id"]: record for record in records}
    # Verify explicit expected heading ownership using printed anchors and
    # candidate order. This accepts plain text headings and different blocks;
    # no private heading tree or candidate-specific relation fields are needed.
    headings = [target for target in expected["targets"] if target["kind"] == "heading"]
    list_headings = [{**target,'id':target['id']+':list_scope','kind':'heading',
                      'heading_level':len(target['context'])+len(target.get('parents',[]))+1,
                      'context':[*target['context'],*target.get('parents',[]),target['text']]}
                     for target in expected['targets'] if target.get('has_children') and not target.get('record')
                     and target['kind']=='item']
    headings = [*headings,*list_headings]

    def position(match):
        if not match:
            return None
        claims = match.get("claims") or [match]
        claim = claims[0]
        item = text_matching["candidate_map"].get(claim["candidate_id"], candidate_map.get(claim["candidate_id"]))
        return (*item["order"], (claim.get("span") or [0])[0]) if item else None

    def end_position(match):
        if not match:
            return None
        claim = (match.get("claims") or [match])[-1]
        item = candidate_map.get(claim["candidate_id"], text_matching["candidate_map"].get(claim["candidate_id"]))
        return (*item["order"], claim["span"][1]) if item else None

    def view_range(item, start, stop):
        """Clip a literal stream at actual heading positions before searching."""
        left, right = 0, len(item["text"])
        parts = item.get("components") or [{"candidate_id": item["id"], "start": 0, "end": right}]
        for part in parts:
            order = tuple(candidate_map[part["candidate_id"]]["order"])
            if start is not None:
                if order < start[:-1]:
                    left = max(left, part["end"])
                elif order == start[:-1]:
                    left = max(left, part["start"] + start[-1])
            if stop is not None:
                if order > stop[:-1]:
                    right = min(right, part["start"])
                elif order == stop[:-1]:
                    right = min(right, part["start"] + stop[-1])
        return left, right

    def literal_matches(target):
        wanted = normalize_text(target.get("reference_text", target.get("text", "")), collapse_whitespace=True)
        full_literal = wanted
        if target.get("expected_kind", target.get("kind")) in {"text", "item", "record_residual_text"}:
            wanted = wanted.removesuffix("。").removesuffix(".")
        scope = tuple(sorted(target["pages"]))
        views = [*visible, *streams_by_pages.get(scope, [])]
        found = {}
        for item, text, positions in views:
            if not wanted or not in_page_scope(item, set(scope)):
                continue
            for occurrence in re.finditer(re.escape(wanted), text):
                a, b = positions[occurrence.start()][0], positions[occurrence.end() - 1][1]
                if wanted != full_literal and item["text"][b:b + 1] in {".", "。"}:
                    b += 1
                claims = [{"candidate_id": item["id"], "span": [a, b]}]
                if item.get("components"):
                    claims = [{"candidate_id": part["candidate_id"],
                        "span": [max(a, part["start"]) - part["start"], min(b, part["end"]) - part["start"]]}
                        for part in item["components"] if part["start"] < b and part["end"] > a]
                key = tuple((claim["candidate_id"], *claim["span"]) for claim in claims)
                found.setdefault(key, {"candidate_id": item["id"], "native_path": item.get("native_path"),
                    "span": [a, b], "hypothesis": item["text"][a:b], "claims": claims,
                    "method": "complete_literal_inside_explicit_scope"})
        return list(found.values())

    consumed = {}

    def overlaps_consumed(match):
        for claim in match.get("claims") or [match]:
            a, b = claim["span"]
            if any(a < end and start < b for start, end in consumed.get(claim["candidate_id"], [])):
                return True
        return False

    def retain_boundary_tokens(match, reference):
        if not match:
            return None
        result = copy.deepcopy(match)
        claims = result.get("claims") or [{"candidate_id": result["candidate_id"], "span": list(result["span"])}]
        first, last = claims[0], claims[-1]
        left = candidate_map[first["candidate_id"]]["text"]
        right = candidate_map[last["candidate_id"]]["text"]
        a, b = first["span"][0], last["span"][1]
        old_a, old_b = a, b
        prefix = re.search(r"(?:\b(?:no|not|without)\s+|[不未无無非])$", left[:a], re.I)
        if prefix:
            a = prefix.start()
        if reference and reference[0].isdigit():
            while a and left[a - 1] in "0123456789.,+−-":
                a -= 1
        last_token = reference.removesuffix("。").removesuffix(".")[-1:]
        if last_token and last_token in "0123456789%‰":
            while b < len(right) and right[b] in "0123456789.,%‰":
                b += 1
        if a == old_a and b == old_b:
            return match
        first["span"][0], last["span"][1] = a, b
        result["claims"] = claims
        result["span"] = [result["span"][0] - (old_a - a), result["span"][1] + (b - old_b)]
        result["hypothesis"] = "\n".join(candidate_map[claim["candidate_id"]]["text"][slice(*claim["span"])] for claim in claims)
        result.pop("normalized_span", None)
        return result

    heading_options = {}

    @lru_cache(maxsize=8192)
    def heading_identity(text):
        text = normalize_text(text, collapse_whitespace=True).translate(str.maketrans("‘’“”", "''\"\""))
        text = re.sub(r"^[•·\uf06e]\s+", "", text)
        text = re.sub(r"\\?\(\s*\^\{([^{}]+)\}\s*\\?\)", lambda match: "^" + match[1], text)
        text = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", lambda match: "^" + match[0].translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")), text)
        # Title wrapping and enumerator spacing can locate the same printed
        # title; this key never replaces strict text/character comparison.
        text = re.sub(r"(?<=[\u3400-\u9fff、，:])\s+(?=\S)|(?<=\d)\s+(?=[\u3400-\u9fff])|\s+(?=\^)", "", text)
        caption = re.search(r"\b(Graph|Figure|Table|Box)\s+((?:[A-Z]+[.-]?)?\d+(?:[.-][A-Z0-9]+)*|[A-Z](?:[.-][A-Z0-9]+)*)(?:[.:：]\s*|\s+|$)", text, re.I)
        if caption:
            return caption[1].casefold(), caption[2], (text[:caption.start()] + text[caption.end():]).strip()
        return text

    title_roles = {"heading", "title", "doc_title", "paragraph_title", "section_header"}
    title_views = []
    ordered = sorted(candidates, key=lambda item: item["order"])
    for index, item in enumerate(ordered):
        if item["kind"] != "text" or not item["text"].strip():
            continue
        offset = 0
        for line in item["text"].splitlines(keepends=True):
            literal = line.strip()
            if literal:
                start = offset + len(line) - len(line.lstrip())
                end = start + len(literal)
                title_views.append({"candidate_id": item["id"], "native_path": item.get("native_path"),
                    "hypothesis": literal, "span": [start, end],
                    "claims": [{"candidate_id": item["id"], "span": [start, end]}],
                    "declared_title_role": item.get("block", {}).get("kind") in title_roles,
                    "method": "complete_printed_line"})
            offset += len(line)
        run = []
        for following in ordered[index:index + 4]:
            if following["kind"] != "text" or not following["text"].strip() or len(following["text"]) > 512 or following.get("page") != item.get("page"):
                break
            run.append(following)
            title_views.append({"candidate_id": item["id"], "native_path": item.get("native_path"),
                "hypothesis": "\n".join(part["text"] for part in run), "span": [0, len(item["text"])],
                "claims": [{"candidate_id": part["id"], "span": [0, len(part["text"])]} for part in run],
                "declared_title_role": item.get("block", {}).get("kind") in title_roles,
                "method": "printed_title_typography_and_adjacent_blocks"})
    unique_titles = {}
    for view in title_views:
        key = tuple((claim["candidate_id"], *claim["span"]) for claim in view["claims"])
        unique_titles.setdefault(key, view)
    title_views = list(unique_titles.values())

    def heading_matches(heading):
        if heading["id"] not in heading_options:
            matches = literal_matches(heading)
            titles = [match for match in title_views if (heading_identity(match["hypothesis"]) == heading_identity(heading["text"])
                      or match.get('method')=='complete_printed_line'
                      and business_scope_text(heading['text'])==business_scope_text(match['hypothesis'])
                      or match.get("method") == "complete_printed_line" and match.get("declared_title_role")
                      and business_scope_text(heading["text"]) in heading_context_keys(match["hypothesis"]))
                      and in_page_scope(candidate_map[match["candidate_id"]], set(heading["pages"]))]
            def complete_printed_span(match):
                claims = match.get('claims') or [match]
                if len(claims) != 1:
                    return False
                claim = claims[0]
                raw = candidate_map.get(claim['candidate_id'],{}).get('text','')
                a,b = claim['span']
                return not raw[:a].rsplit('\n',1)[-1].strip() and raw[b:].split('\n',1)[0].strip() in {'',':','：'}
            standalone = [match for match in matches if complete_printed_span(match)]
            paths = [match for match in matches if candidate_map.get(match["candidate_id"], {}).get("cell", {}).get("public_record_literal")
                and any(heading_identity(label) == heading_identity(heading["text"])
                        for cell in candidate_map[match["candidate_id"]]["block"].get("cells", [])
                        for label in cell.get("row_header_path", []))]
            options = titles or standalone or paths
            declared = any(match.get("declared_title_role") for match in options)
            if not declared:
                references = [target for target in expected["targets"] if target["kind"] != "heading"
                    and target["reference"]["lines"][0] < heading["reference"]["lines"][0]
                    and heading_identity(target["text"]) == heading_identity(heading["text"])]
                remaining = list(references)
                kept = []
                for match in sorted(options, key=position):
                    source = candidate_map[match["candidate_id"]]
                    prior = next((target for target in remaining if in_page_scope(source, set(target["pages"]))), None)
                    if prior is not None:
                        remaining.remove(prior)
                    else:
                        kept.append(match)
                options = kept
            heading_options[heading["id"]] = options
        return heading_options[heading["id"]]

    declared_titles = [view for view in title_views if (view.get("declared_title_role")
                       or _PRINTED_REPORT_TITLE.fullmatch(view['hypothesis']))
                       and view.get("method") == "complete_printed_line"]
    report_counts = Counter(business_scope_text(view['hypothesis']) for view in declared_titles
                            if _PRINTED_REPORT_TITLE.fullmatch(view['hypothesis']))
    repeated_reports = {key for key, count in report_counts.items() if count >= 2} if len(report_counts) == 1 else set()
    report_markers = [{'text':view['hypothesis'],'position':position(view)} for view in declared_titles
                      if _PRINTED_REPORT_TITLE.fullmatch(view['hypothesis'])]
    actual_titles = [{'text':view['hypothesis'],'position':position(view),
                      'declared_title':view.get('declared_title_role') and view.get('method')=='complete_printed_line',
                      'kind':candidate_map[view['candidate_id']].get('block',{}).get('kind'),
                      'native_ids':[part['candidate_id'] for part in view.get('claims',[view])]}
                     for view in title_views if position(view) is not None]
    actual_title_pairs = consecutive_title_pairs(actual_titles)
    component_cache={}
    display_levels=None
    heading_anchor_cache=None
    boundary_cache={}
    repeated_titles={}

    def actual_heading_anchors():
        nonlocal heading_anchor_cache
        if heading_anchor_cache is None:
            actual={}
            for heading in headings:
                actual[heading['id']]=[]
                for match in heading_matches(heading):
                    for claim in match.get('claims',[match]):
                        block=candidate_map[claim['candidate_id']].get('block',{})
                        level=block.get('heading_level') or block.get('level')
                        if block.get('kind') in title_roles and position(match) is not None:
                            actual[heading['id']].append({'level':level,'position':position(match),
                                'native_ids':[part['candidate_id'] for part in match.get('claims',[match])]})
            heading_anchor_cache=actual
        return heading_anchor_cache

    def title_display_levels():
        nonlocal display_levels
        if display_levels is None:
            display_levels=flat_display_levels(headings,actual_heading_anchors())
        return display_levels

    def explicit_child_component(view, owner_key, level):
        signature=(owner_key,level,tuple((claim['candidate_id'],*claim['span']) for claim in view['claims']))
        if signature not in component_cache:
            owners=[heading['text'] for heading in headings if heading_identity(heading['text'])==owner_key
                    or isinstance(owner_key,str)
                    and business_scope_text(heading['text']) in heading_context_keys(owner_key)]
            children=[heading for heading in headings if (heading.get('heading_level') or 1)>level
                      and any(owner in heading['context'] for owner in owners)]
            component_cache[signature]=any(all(any(claim['candidate_id']==part['candidate_id']
                and part['span'][0]<=claim['span'][0] and claim['span'][1]<=part['span'][1]
                for part in match.get('claims',[match])) for claim in view['claims'])
                for child in children for match in heading_matches(child))
        return component_cache[signature]

    def actual_boundaries(anchor, start):
        if anchor is None or start is None:
            return []
        key = heading_identity(anchor["hypothesis"])
        cache_key = (key, tuple(start))
        if cache_key in boundary_cache:
            return boundary_cache[cache_key]
        owners = [heading for heading in headings if heading_identity(heading['text']) == key
                  or business_scope_text(heading['text']) in heading_context_keys(anchor['hypothesis'])]
        owner_levels = [heading.get("heading_level") for heading in owners if heading.get("heading_level")]
        expected_level = min(owner_levels) if owner_levels else None
        anchor_claims = anchor.get("claims") or [anchor]
        owner_block = candidate_map[anchor_claims[0]["candidate_id"]].get("block", {})
        native_level = owner_block.get("heading_level") or owner_block.get("level")
        result = []
        for view in declared_titles:
            where = position(view)
            if where is None or where <= start or heading_identity(view["hypothesis"]) == key:
                continue
            if all(any(claim["candidate_id"] == owned["candidate_id"]
                       and owned["span"][0] <= claim["span"][0] and claim["span"][1] <= owned["span"][1]
                       for owned in anchor_claims) for claim in view.get("claims", [view])):
                continue
            block = candidate_map[view["candidate_id"]].get("block", {})
            if block.get('kind') != 'doc_title' and business_scope_text(view['hypothesis']) in repeated_reports:
                continue
            repeat = repeated_ancestor_evidence(view['hypothesis'],owners,actual_titles,start,block.get('kind'),where,actual_title_pairs)
            if repeat:
                repeated_titles[(key,tuple(where))]={**repeat,'position':where,'native_path':view['native_path']}
                continue
            depth = block.get("heading_level") or block.get("level")
            known_depths = [heading.get("heading_level") for heading in headings
                            if (heading_identity(heading["text"]) == heading_identity(view["hypothesis"])
                                or business_scope_text(heading['text']) in heading_context_keys(view['hypothesis']))
                            and heading.get("heading_level")]
            if not known_depths and any(business_scope_text(anchor['hypothesis']) in matching['context_members'].get(
                    literal,set()) for literal in heading_context_keys(view['hypothesis'])):
                continue
            if expected_level is not None and explicit_child_component(view,key,expected_level):
                continue
            if known_depths and expected_level is not None and min(known_depths) > expected_level:
                continue
            if _PRINTED_REPORT_TITLE.fullmatch(view['hypothesis']):
                if known_depths or report_title_transition(view['hypothesis'],block.get('kind'),where,report_markers):
                    result.append(where)
                continue
            if not known_depths:
                if (not isinstance(depth,int) or not isinstance(native_level,int) or depth>native_level
                        or any(flat_level_in_scope(title_display_levels(),heading['context'],depth,start)
                               for heading in owners)):
                    continue
            result.append(where)
        boundary_cache[cache_key]=result
        return result

    # Complete long statements own their spans before a shorter prefix can
    # claim them. Identical repeated paragraphs retain expected order.
    relation_candidates = None
    relation_cache = {}
    for target, row in sorted(zip(texts, outcomes, strict=True), key=lambda pair: -len(pair[0]["reference_text"])):
        if target["expected_kind"] in {"heading", "image_alt_text"}:
            continue
        owning = [heading for heading in headings if heading["text"] in target["expected_context"]
                  and heading["reference"]["lines"][0] < target["reference"]["lines"][0]]
        owner = owning[-1] if owning else None
        next_headings = [heading for heading in headings if owner
            and heading["reference"]["lines"][0] > owner["reference"]["lines"][0]
            and (heading.get("heading_level") or 1) <= (owner.get("heading_level") or 1)]

        anchors = heading_matches(owner) if owner else []
        following = heading_matches(next_headings[0]) if next_headings else []
        ancestors = {heading["text"]: heading for heading in owning if not owner or heading["text"] != owner["text"]}
        constraints = []
        for ancestor in ancestors.values():
            siblings = [heading for heading in headings if heading["reference"]["lines"][0] > ancestor["reference"]["lines"][0]
                        and (heading.get("heading_level") or 1) <= (ancestor.get("heading_level") or 1)]
            constraints.append((ancestor,heading_matches(ancestor), heading_matches(siblings[0]) if siblings else []))

        def bounds_for(match, anchors, following):
            body = position(match)
            preceding = [anchor for anchor in anchors if position(anchor) is not None
                         and body is not None and position(anchor) < body]
            anchor = max(preceding, key=position) if preceding else next(iter(anchors), None)
            start = position(anchor)
            boundaries = [position(item) for item in following if position(item) is not None
                          and start is not None and position(item) > start and position(item) != body]
            boundaries.extend(actual_boundaries(anchor, start))
            boundary = min(boundaries) if boundaries else None
            end = end_position(match)
            correct = (start is not None and body is not None and start < body
                       and (boundary is None or end is not None and end <= boundary))
            if not correct and start is not None and body is not None and body < start and anchor:
                roots = [heading for heading in headings if heading.get('heading_level')==1
                         and any(position(option)==start for option in heading_matches(heading))]
                initial = [item for item in ordered if item['order'] < tuple(start[:-1])]
                if roots and initial and all(item.get('block',{}).get('kind') in title_roles-{'doc_title'}
                    and not any(heading.get('heading_level')==1 and heading not in roots
                        and heading_identity(item['text'])==heading_identity(heading['text']) for heading in headings)
                    for item in initial):
                    correct = all(candidate_map[claim['candidate_id']].get('block',{}).get('kind') in title_roles-{'doc_title'}
                                  for claim in match.get('claims',[match]))
            return correct, anchor, start, boundary

        def context_for(match, anchors=anchors, following=following, owner=owner, constraints=constraints, bounds_for=bounds_for):
            result = bounds_for(match, anchors, following)
            correct = (not owner or result[0]) and all(bounds_for(match, starts, ends)[0] for _ancestor,starts, ends in constraints)
            return correct, *result[1:]

        def context_requirements(match,owner=owner,anchors=anchors,following=following,
                                 constraints=constraints,bounds_for=bounds_for):
            requirements=[(owner,anchors,following)] if owner else []
            requirements.extend(constraints)
            evidence=[]
            for heading,starts,ends in requirements:
                valid,anchor,start,stop=bounds_for(match,starts,ends)
                evidence.append({'scope':heading['text'],'correct':valid,'start':start,'stop':stop,
                    'anchor':{'native_path':anchor.get('native_path'),'claims':anchor.get('claims')} if anchor else None})
            return evidence

        required_list_scope = list_scope(target["list_parents"])
        list_constraints = []
        for label in target['list_parents']:
            parents = [heading for heading in list_headings if business_scope_text(heading['text'])==business_scope_text(label)
                       and heading['reference']['lines'][0]<target['reference']['lines'][0]]
            if parents:
                parent=max(parents,key=lambda heading:heading['reference']['lines'][0])
                ends=[heading for heading in list_headings if heading['reference']['lines'][0]>parent['reference']['lines'][0]
                      and heading['heading_level']<=parent['heading_level']]
                starts = [match for match in heading_matches(parent)
                          if 'cell' not in candidate_map.get(match['candidate_id'],{})]
                list_constraints.append((starts,heading_matches(ends[0]) if ends else []))
        shared_label = bool(required_list_scope and target["has_children"])
        resolution = None
        if required_list_scope:
            columns = required_list_scope["columns"] + ([target["reference_text"]] if shared_label else [])
            if relation_candidates is None:
                relation_candidates = [item for item in observation_candidates(read_information_observation(observation)) if "cell" in item]
            key = tuple(required_list_scope["rows"]), tuple(columns), tuple(target["pages"])
            if key not in relation_cache:
                relation_cache[key] = _locate_record_field(required_list_scope["rows"], columns,
                    [item for item in relation_candidates if in_page_scope(item, set(target["pages"]))], True)
            resolution = relation_cache[key]

        parent_count=len(target['list_parents'])
        def list_context_correct(match, required=required_list_scope, shared=shared_label, resolution=resolution,
                                 list_constraints=list_constraints,bounds_for=bounds_for,
                                 parent_count=parent_count):
            if not required:
                return True
            if not match:
                return False
            claims = match.get("claims") or [match]
            for claim in claims:
                item = candidate_map.get(claim["candidate_id"], {})
                actual = list_scope(item.get("block", {}).get("public_list_parents", []))
                if actual and row_path_locates(required["rows"], actual["rows"], True) and (
                    not required["columns"] or row_path_locates(required["columns"], actual["columns"], True)):
                    return True
            if resolution and not resolution.get("reason"):
                allowed = {item["id"] for item in resolution["columns" if shared else "selected"]}
                if allowed and all(claim["candidate_id"] in allowed for claim in claims):
                    return True
            if list_constraints and len(list_constraints)==parent_count:
                return all(bounds_for(match,starts,ends)[0] for starts,ends in list_constraints)
            return False

        original = row.get("candidate")
        exact = [match for match in literal_matches(target) if normalize_text(
            retain_boundary_tokens(match, target["reference_text"])["hypothesis"], collapse_whitespace=True).rstrip("。.")
            == normalize_text(target["reference_text"], collapse_whitespace=True).rstrip("。.")]
        choices = exact + ([original] if original else [])
        if target['has_children']:
            choices.extend(match for parent in list_headings if parent['id']==target['id']+':list_scope'
                           for match in heading_matches(parent))
        available = [match for match in choices if context_for(match)[0] and list_context_correct(match)
                     and (shared_label or not overlaps_consumed(match))]
        if not available and target["expected_kind"] in {"text", "item", "record_residual_text"}:
            # Search within each actual owner range first. A global exact or
            # closer match in another chapter must not suppress the imperfect
            # paragraph actually printed in the requested chapter.
            windows = []
            for anchor in anchors if owner else [None]:
                start = end_position(anchor)
                boundaries = [position(item) for item in following if position(item) is not None
                              and start is not None and position(item) >= start]
                boundaries.extend(actual_boundaries(anchor, start))
                windows.append((start, min(boundaries) if boundaries else None))
            scope = tuple(sorted(target["pages"]))
            wanted = normalize_text(target["reference_text"], collapse_whitespace=True)
            approximate = {}
            for item, text, positions in [*visible, *streams_by_pages.get(scope, [])]:
                if not in_page_scope(item, set(scope)) or not positions or len(wanted) < 5:
                    continue
                for start, stop in windows:
                    left, right = view_range(item, start, stop)
                    offset = bisect_left(positions, (left,))
                    limit = bisect_right(positions, (right, right))
                    while limit > offset and positions[limit - 1][1] > right:
                        limit -= 1
                    if limit - offset < len(wanted) * .8:
                        continue
                    for a, b, similarity in _approximate_spans(wanted, text[offset:limit], .8):
                        raw_start, raw_end = positions[offset+a][0], positions[offset+b-1][1]
                        claims = [{"candidate_id": item["id"], "span": [raw_start, raw_end]}]
                        if item.get("components"):
                            claims = [{"candidate_id": part["candidate_id"],
                                "span": [max(raw_start, part["start"]) - part["start"],
                                         min(raw_end, part["end"]) - part["start"]]}
                                for part in item["components"] if part["start"] < raw_end and part["end"] > raw_start]
                        match = {"candidate_id": item["id"], "native_path": item.get("native_path"),
                            "span": [raw_start, raw_end], "claims": claims,
                            "hypothesis": item["text"][raw_start:raw_end], "locator_similarity": similarity,
                            "method": "approximate_inside_verified_heading_range"}
                        key = tuple((claim["candidate_id"], *claim["span"]) for claim in claims)
                        approximate.setdefault(key, retain_boundary_tokens(match, target["reference_text"]))
            choices.extend(approximate.values())
            available = sorted([match for match in approximate.values()
                if context_for(match)[0] and list_context_correct(match) and not overlaps_consumed(match)],
                key=lambda match: (-match["locator_similarity"], position(match)))
        row["localization"] = {"query": {"text": target["reference_text"], "context": target["expected_context"]},
            "candidates": [{"native_path": match.get("native_path"), "claims": match.get("claims"),
                "method": match.get("method"), "hypothesis": match.get("hypothesis"),
                'context_requirements':context_requirements(match),
                "decision": "accepted" if context_for(match)[0] and list_context_correct(match)
                    and (shared_label or not overlaps_consumed(match)) else "rejected",
                "reasons": ([] if context_for(match)[0] else ["heading_scope_conflict"])
                    + ([] if list_context_correct(match) else ["list_scope_conflict"])
                    + (["span_already_used"] if not shared_label and overlaps_consumed(match) else [])}
                for match in choices]}
        selected = available[0] if available else None
        selected = retain_boundary_tokens(selected, target["reference_text"])
        if selected and not shared_label and overlaps_consumed(selected):
            selected = None
        actual = selected["hypothesis"] if selected else ""
        row.update(candidate=selected, actual=actual,
                   text=text_metrics(target["reference_text"], actual, collapse_whitespace=True),
                   differences=changed_spans(target["reference_text"], actual))
        reference_literal = normalize_text(target["reference_text"], collapse_whitespace=True)
        actual_literal = normalize_text(actual, collapse_whitespace=True)
        if target["expected_kind"] in {"text", "item", "record_residual_text"}:
            reference_literal = reference_literal.removesuffix("。").removesuffix(".")
            actual_literal = actual_literal.removesuffix("。").removesuffix(".")
        checkbox = _checkbox_sequence(reference_literal)
        literal_correct = bool(selected and (actual_literal == reference_literal or target['has_children']
            and business_scope_text(actual_literal)==business_scope_text(reference_literal)
            or checkbox is not None and checkbox == _checkbox_sequence(actual_literal)))
        correct_context, anchor, start, boundary = context_for(selected)
        heading_correct = bool(selected and correct_context)
        correct_context = bool(heading_correct and list_context_correct(selected))
        row.update(outcome="correct" if literal_correct and correct_context else "incorrect",
                   reason="complete_visible_text" if literal_correct and correct_context else
                          "explicit_list_ownership_incorrect" if literal_correct and not list_context_correct(selected) else
                          "explicit_heading_ownership_incorrect" if literal_correct else "text_missing_or_different")
        if owner:
            row["context_evidence"] = {"correct": heading_correct, "heading": owner["text"],
                "anchor": anchor, "heading_position": start, "content_position": position(selected),
                "following_heading": next_headings[0]["text"] if next_headings else None,
                "following_position": boundary, "method": "printed_anchor_order_within_explicit_expected_scope"}
        if required_list_scope:
            row["list_context_evidence"] = {"required": required_list_scope, "correct": list_context_correct(selected),
                "shared_column_label": shared_label, "method": "printed_list_paths_or_native_row_column_scope",
                "native_scope_reason": resolution.get("reason") if resolution else None}
        if selected and literal_correct and correct_context and not shared_label:
            for claim in selected.get("claims") or [selected]:
                consumed.setdefault(claim["candidate_id"], []).append(tuple(claim["span"]))
    for row in record_rows:
        target = by_id[row["id"]]
        for field in row["fields"]:
            if field.get("outcome") not in {"correct", "incorrect"}:
                raise ValueError("shared business reader has not produced a binary decision")
            index = field["index"]
            expected_field = target["table"]["fields"][index]
            outcomes.append({"id": f"{row['id']}:field:{index}", "kind": "business_field",
                             "source_element_id": target["source_element_id"],
                             "reference": target["reference"],
                             "expected": {**expected_field, "required": _required_qualifiers(target["table"], expected_field)},
                             "row_header_path": target["table"]["row_header_path"],
                             "context": target["expected_context"], "outcome": field["outcome"],
                             "reason": field.get("information", {}).get("reason") or field.get("reason"),
                             "actual": field.get("native_text"),
                             "value_and_labels_correct": bool(field.get("content_exact")),
                             "raw_value_text": None if expected_field.get("reference_blank") or field.get("status") != "compared" else text_metrics(
                                 expected_field["value"], field.get("native_text") or "", collapse_whitespace=True),
                             "candidate": field})
    counts = Counter(item["outcome"] for item in outcomes)
    content_elements = {t["id"] for t in expected["targets"] if t["text"].strip()
                        or any(cell["text"].strip() for cell in t.get("cells", []))}
    represented = {row["source_element_id"] for row in outcomes}
    if content_elements - represented:
        raise ExpectedReadError("expected content was omitted by the scoring compiler; repair before publication")
    content_ranges = []
    for target in expected["targets"]:
        members = [row for row in outcomes if row["source_element_id"] == target["id"]]
        if target.get("record") and not target.get("also_prose"):
            requirements = [row for row in records if row["source_element_id"] == target["id"]]
            ranges, _ = partition_record(target, requirements)
            content_ranges.append({"source_element_id": target["id"], "reference": target["reference"],
                                   "text": target["text"], "ranges": ranges})
        elif target.get("cells"):
            # Every original cell contributes text or complete field targets;
            # per-cell text is also required when no explicit record exists.
            for index, cell in enumerate(target["cells"]):
                if cell["text"]:
                    owned = [row["id"] for row in members if row["id"] == f"{target['id']}:cell:{index}"]
                    if not owned:
                        owned = [row["id"] for row in members if row["kind"] == "business_field"
                                 and row["expected"].get("source_cell_index") == index]
                    content_ranges.append({"source_element_id": target["id"], "reference": target["reference"],
                        "text": cell["text"], "ranges": [{"span": [0, len(cell["text"])], "literal": cell["text"],
                        "role": "table_cell_requirement", "target_ids": owned}]})
        elif target["text"]:
            owned = [row["id"] for row in members if row["kind"] != "business_field"]
            content_ranges.append({"source_element_id": target["id"], "reference": target["reference"],
                "text": target["text"], "ranges": [{"span": [0, len(target["text"])], "literal": target["text"],
                "role": "complete_prose", "target_ids": owned}]})
    require_complete_ranges(content_ranges, outcomes)
    require_retrieval_evidence(outcomes)
    by_kind = {}
    for kind in sorted({item["kind"] for item in outcomes}):
        members = [item for item in outcomes if item["kind"] == kind]
        by_kind[kind] = {"targets": len(members), "correct": sum(x["outcome"] == "correct" for x in members),
                         "incorrect": sum(x["outcome"] == "incorrect" for x in members)}
    if len({item["id"] for item in outcomes}) != len(outcomes):
        raise ValueError("duplicate expected target identities")
    return {"sample_id": expected["sample_id"], "document_id": expected["document_id"],
            "family_id": expected.get("family_id"), "pipeline": observation.get("pipeline"),
            "tags": expected.get("tags", []), "development_exposure": expected.get("development_exposure"),
            "source_category": expected.get("source_category"), "status": observation.get("status"),
            "timing": copy.deepcopy(observation.get("timing", {})),
            "runtime": copy.deepcopy(observation.get("runtime", {})),
            "resources": copy.deepcopy(observation.get("resources", {})),
            'heading_display_reading':title_display_levels(),
            'repeated_ancestor_reading':sorted(repeated_titles.values(), key=lambda item:(item['owner'],item['position'])),
            "asset_delivery": copy.deepcopy(observation.get("asset_delivery", {})),
            "input_page_count": observation.get("input_page_count", len(expected["source_pages"])),
            "protocol": PROTOCOL, "scope": expected["scope"], "source_pages": expected["source_pages"],
            "expected_elements": len(expected["targets"]), "targets": len(outcomes),
            "content_coverage": {"expected_elements": len(content_elements),
                                 "compared_elements": len(content_elements & represented), "omitted_elements": 0,
                                 "literal_ranges": len(content_ranges),
                                 "method": "complete_literal_partition_plus_explicit_business_requirements",
                                 "ranges": content_ranges},
            "correct": counts["correct"], "incorrect": counts["incorrect"], "by_kind": by_kind,
            "business_metrics": record_metrics, "text_metrics": summarize_text(outcomes), "outcomes": outcomes}


def require_paired_targets(scores: list[dict[str, Any]]) -> None:
    """Compare evaluation outputs only; never inspect corpus truth here."""
    signatures = [{(row["id"], row["kind"], repr(row["expected"]), repr(row.get("row_header_path")),
                   repr(row.get("context")), repr(row.get("list_context")), repr(row.get("reference"))) for row in score["outcomes"]}
                  for score in scores]
    if not signatures or any(items != signatures[0] for items in signatures[1:]):
        raise ValueError("compared candidates did not receive identical expected targets")
    for score in scores:
        if score["targets"] != score["correct"] + score["incorrect"]:
            raise ValueError("every expected target must have a binary decision")
        if any(row["outcome"] not in {"correct", "incorrect"} for row in score["outcomes"]):
            raise ValueError("score contains an unfinished target")
