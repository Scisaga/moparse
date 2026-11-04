"""Expected-only, independent text, relation and business measurements.

This module has no PDF, model, service or reference-writing interface. The
syntax reader is shared; requirements and candidate evidence are separate
objects. Unsupported semantics are publication blockers, never candidate
errors. No legacy scorer is called.
"""

from __future__ import annotations

import copy
import re
from collections import Counter, defaultdict
from typing import Any

from rapidfuzz.distance import Levenshtein

from app.utils.measurement import unit_applicable

from .expected_readback import elements
from .metrics import normalize_text
from .representations import visible_text

PROTOCOL = {
    "id": "mo-parse-three-layer",
    "weights": {"T": 1 / 3, "L": 1 / 3, "B": 1 / 3},
    "reference": "canonical_expected_read_only_selected_ranges",
    "text": "capacity_one_literal_units_width_equivalence_full_denominator_edit_distance",
    "relations": "explicit_semantic_edges_independent_of_value_spelling",
    "business": "identity_metric_description_one_assertion_one_vote_qualifiers_not_questions",
    "software_failure": "block_publication",
    "insertion": "inside_paired_comparable_literal_only_other_extras_unadjudicated",
}

IDENTITY = re.compile(r"(?:Name|Entity|Company|Subject|Identifier|ID|Code|Ticker|Role|Type|Market|Region|名称|姓名|主体|公司名称|证券代码|证券简称|类型|职务|市场|地区)", re.I)
PRIMARY = re.compile(r"Name|Entity|Company|Subject|名称|姓名|主体|公司名称", re.I)
QUALIFIER = re.compile(r"(?:Units?|Currency|Period|Year|Scope|Note|Condition|Exception|单位|币种|期间|年度|口径|附注|条件|例外)", re.I)
LOGICAL = re.compile(r"\b(?:must|shall|unless|except|if|not|no|only|obligation)\b|不得|必须|应当|除外|除非|仅限|条件|不适用|不包括|否认|禁止", re.I)
NUMERIC = re.compile(r"[+\-−]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)\s*(?:[%‰]|万元|亿元|元|万元人民币|人民币|美元|人|股|万股|吨|件)?$")
PAIR = re.compile(r"^([^:：=\n]{1,100}?)\s*[:：=]\s*(.*)$", re.S)
UNIT = re.compile(r"^(.*?)\s*(万元人民币|万元|亿元|人民币|美元|元|万股|股|吨|件|%|‰)$")


def canonical(text: str) -> str:
    """Preserve internal words, signs and digits, including numeric spaces."""
    text = re.sub(r"(?<=[\u3400-\u9fff])[^\S\n]*\n\s*(?=[\u3400-\u9fff])", "", text)
    text = normalize_text(text, collapse_whitespace=True).strip()
    # Only full Latin-containing terms at CJK boundaries have display spaces.
    text = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[A-Za-z]|\d+[A-Za-z])", "", text)
    text = re.sub(r"([A-Za-z0-9]*[A-Za-z][A-Za-z0-9]*)\s+(?=[\u3400-\u9fff])", r"\1", text)
    return text


def _source(path: str, lines: list[int] | tuple[int, int], **extra: Any) -> dict[str, Any]:
    return {"path": path, "lines": list(lines), **extra}


def _qualifier_key(label: str) -> str:
    value = canonical(label).lower()
    for key, pattern in {
        "unit": r"units?|单位", "currency": r"currency|币种", "period": r"period|year|期间|年度",
        "scope": r"scope|口径", "note": r"note|附注", "condition": r"condition|条件", "exception": r"exception|例外",
    }.items():
        if re.fullmatch(pattern, value):
            return key
    raise ValueError("unclassified qualifier")


def _pairs(text: str) -> list[tuple[str, str]]:
    """Only the first explicit delimiter in a clause binds its value.

    Times, URLs, negatives and ordinary terminal numbers remain literal.
    Semicolons split only if every clause is independently labelled.
    """
    pieces = re.split(r"[;；]\s*", text.strip())
    if pieces and not pieces[-1]:
        pieces.pop()
    matches = [PAIR.fullmatch(piece) for piece in pieces]
    if matches and all(matches):
        return [(match[1].strip(), match[2].strip()) for match in matches if match]
    match = PAIR.fullmatch(text.strip())
    return [(match[1].strip(), match[2].strip())] if match else []


class _Graph:
    def __init__(self, sample_id: str) -> None:
        self.data: dict[str, Any] = {"sample_id": sample_id, "text": [], "business": [],
                                     "relations": [], "blockers": [], "syntax": []}
        self.qualifiers: dict[str, str] = {}
        self.subject = ""
        self.headings: list[str] = []
        self.continuity_segment = 0
        self.identity_facets: dict[str, str] = {}
        self.record_start = 0

    def identity_attribute(self, attribute: str, value: str) -> None:
        if PRIMARY.fullmatch(attribute):
            self.subject = value
            self.identity_facets = {}
            self.record_start = len(self.data["business"])
        elif IDENTITY.fullmatch(attribute):
            self.identity_facets[attribute] = value
            for fact in self.data["business"][self.record_start:]:
                if fact["role"] != "identity":
                    fact["identity_facets"][attribute] = value

    def block(self, reason: str, source: dict[str, Any], **detail: Any) -> None:
        self.data["blockers"].append({"reason": reason, "source": source, **detail})

    def literal(self, text: str, source: dict[str, Any], role: str = "literal") -> str | None:
        if not text.strip():
            return None
        identifier = f"T:{len(self.data['text'])}"
        self.data["text"].append({"id": identifier, "text": text.strip(), "role": role, "source": source,
                                  "continuity_segment": self.continuity_segment, "scope": list(self.headings)})
        return identifier

    def relation(self, kind: str, left: Any, right: Any, source: dict[str, Any]) -> None:
        edge = {"id": f"L:{len(self.data['relations'])}", "type": kind, "left": left, "right": right, "source": source}
        self.data["relations"].append(edge)

    def fact(self, attribute: str, value: str, source: dict[str, Any], *,
             subject: str | None = None, qualifiers: dict[str, str] | None = None,
             identity: bool | None = None, role: str | None = None,
             identity_facets: dict[str, str] | None = None) -> dict[str, Any]:
        identity = bool(IDENTITY.fullmatch(attribute)) if identity is None else identity
        q = {**self.qualifiers, **(qualifiers or {})}
        if identity or (q.get("unit") and not unit_applicable(q["unit"], [attribute])):
            q.pop("unit", None)
        header_unit = re.fullmatch(r"(.*?)\s*[（(]([^()（）]+)[)）]", attribute)
        if header_unit and UNIT.fullmatch("1" + header_unit[2]):
            attribute = header_unit[1].strip()
            q["unit"] = header_unit[2]
        match = UNIT.fullmatch(value)
        if match and match[1] and NUMERIC.fullmatch(match[1].strip()):
            value = match[1].strip()
            q["unit"] = match[2]
        item = {"id": f"B:{len(self.data['business'])}", "subject": self.subject if subject is None else subject,
                "attribute": attribute, "value": value, "role": role or ("identity" if identity else "metric"),
                "qualifiers": q, "scope": list(self.headings), "source": source,
                "identity_facets": {} if identity else dict(self.identity_facets if identity_facets is None else identity_facets)}
        self.data["business"].append(item)
        endpoint = {"subject": item["subject"], "attribute": attribute, "scope": list(self.headings),
                    "occurrence": sum(f["subject"] == item["subject"] and f["attribute"] == attribute
                                      for f in self.data["business"][:-1])}
        self.relation("field_binding", {"subject": item["subject"], "attribute": attribute}, endpoint, source)
        for key, literal in q.items():
            self.relation("qualifier_scope", {"type": key, "text": literal}, endpoint, source)
        return item

    def prose(self, text: str, source: dict[str, Any], kind: str = "text", parents: list[str] | None = None) -> None:
        if kind in {"heading", "table", "image", "picture", "figure", "unknown", "table_caption"}:
            self.continuity_segment += 1
        self.data["syntax"].append({"kind": kind, "text": text, "source": source})
        if re.search(r"续表|續表|\btable\s+continued\b|\bcontinued\s+table\b", text, re.I):
            self.block("cross_page_relation_interpretation_unsupported", source, text=text)
        for parent in parents or []:
            parent_pairs = _pairs(parent)
            if not parent_pairs or any(not (IDENTITY.fullmatch(key) or QUALIFIER.fullmatch(key))
                                       for key, _ in parent_pairs):
                self.block("list_group_scope_interpretation_unsupported", source, parent=parent)
        pairs = _pairs(text)
        if pairs and (re.search(r"(?:19|20)\d{2}年[^;；]*[、][^;；]*[;；]", text)
                      or re.search(r"[:：]\s*(?:19|20)\d{2}\s*[:：]", text)):
            self.block("compact_multi_metric_requirement_unsupported", source, text=text)
        if pairs:
            # Identity is independent of formatting and never a numeric parent.
            for key, value in pairs:
                if PRIMARY.fullmatch(key) and value:
                    self.identity_attribute(key, value)
            for key, value in pairs:
                if IDENTITY.fullmatch(key) and not PRIMARY.fullmatch(key):
                    self.identity_attribute(key, value)
            for parent in parents or []:
                for key, value in _pairs(parent):
                    if PRIMARY.fullmatch(key) and value and self.subject != value:
                        self.identity_attribute(key, value)
                    elif IDENTITY.fullmatch(key) and not PRIMARY.fullmatch(key):
                        self.identity_attribute(key, value)
                    if QUALIFIER.fullmatch(key):
                        self.qualifiers[_qualifier_key(key)] = value
            # Qualifiers in a record apply to its independent sibling facts,
            # regardless of serialization order.
            for key, value in pairs:
                if QUALIFIER.fullmatch(key):
                    self.qualifiers[_qualifier_key(key)] = value
            for key, value in pairs:
                self.literal(key, source, "label")
                match = UNIT.fullmatch(value)
                if match and match[1] and NUMERIC.fullmatch(match[1].strip()):
                    self.literal(match[1].strip(), source, "value")
                    self.literal(match[2], source, "unit")
                elif value:
                    self.literal(value, source, "value")
                if QUALIFIER.fullmatch(key):
                    self.qualifiers[_qualifier_key(key)] = value
                elif value:
                    self.fact(key, value, source)
                elif kind != "parent_label":
                    # A colon alone is a scope label, not an empty fact.
                    pass
            return
        self.literal(text, source, "heading" if kind == "heading" else "literal")
        if kind == "heading" and len(self.headings) > 1:
            self.relation("heading_parent", self.headings[-2], self.headings[-1], source)
        if LOGICAL.search(text):
            # This exact statement is an important description. Its logical
            # constituents still need a supported semantic grammar; exact
            # matching cannot certify equivalent paraphrases.
            self.fact("statement", text, source, role="description")
        elif kind == "text" and re.search(r"\d|金额|收入|利润|比例|数量|主体|期间|附注", text):
            self.block("unclassified_business_prose", source, text=text)
        if self.headings and kind != "heading":
            self.relation("heading_membership", self.headings[-1], {"text": text}, source)
            self.block("prose_relation_endpoint_alignment_unsupported", source, text=text)
        if parents:
            # Numeric sibling properties never become parent properties.
            labels = [p for p in parents if not _pairs(p) or any(IDENTITY.fullmatch(k) for k, _ in _pairs(p))]
            if labels:
                self.relation("list_membership", labels[-1], {"text": text}, source)

    def table(self, cells: list[dict[str, Any]], source: dict[str, Any]) -> None:
        self.continuity_segment += 1
        if not cells:
            self.block("table_without_readable_cells", source)
            return
        ordered = sorted(cells, key=lambda c: (c.get("row", 0), c.get("col", 0)))
        for cell in ordered:
            self.literal(cell.get("text", ""), {**source, "cell": cell.get("native_path", cell.get("id")),
                                               "row": cell.get("row"), "col": cell.get("col")}, "cell")
            if cell.get("native_header_role_conflict"):
                self.block("conflicting_explicit_header_roles", source, cell=cell.get("id"))
        if any(c.get("row_span", 1) > 1 or c.get("col_span", 1) > 1 for c in ordered):
            self.block("spanning_header_or_group_semantics_unsupported", source)
        if any("row" not in c or "col" not in c for c in ordered):
            self.block("table_cells_without_source_grid", source)
            return
        by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for cell in ordered:
            if cell.get("native_id"):
                by_id[str(cell["native_id"])].append(cell)
        if any(len(group) > 1 for group in by_id.values()):
            self.block("conflicting_native_header_id", source)
        # Thead/explicit scope/GFM roles declare column headers. A top td row
        # and the mere existence of a neighboring cell never prove a value.
        headers = [c for c in ordered if c.get("is_column_header") or
                   (c.get("native_header_tag") and not c.get("is_row_header") and c["row"] == min(x["row"] for x in ordered))]
        row_headers = [c for c in ordered if c.get("is_row_header")]
        values = [c for c in ordered if c not in headers and c not in row_headers]
        if not headers and not row_headers:
            self.block("untyped_grid_semantics", source, cells=[c.get("id") for c in ordered])
            return
        header_rows = {c["row"] for c in headers}
        if any(QUALIFIER.fullmatch(c["text"]) for c in headers):
            self.block("text_restatement_policy_unvalidated", source, layers=["T"])
        # Property/value table: schema explicitly names both data roles.
        property_headers = [c for c in headers if re.fullmatch(r"Attribute|Metric|Property|Field|指标|项目|属性|字段", c["text"], re.I)]
        value_headers = [c for c in headers if re.fullmatch(r"Value|Amount|值|数值|金额", c["text"], re.I)]
        vertical = len(property_headers) == len(value_headers) == 1
        if vertical:
            for cell in values:
                if cell["col"] != value_headers[0]["col"]:
                    continue
                labels = [c for c in ordered if c["row"] == cell["row"] and c["col"] == property_headers[0]["col"]]
                if len(labels) != 1:
                    self.block("property_value_role_ambiguous", source)
                    continue
                key, value = labels[0]["text"], cell["text"]
                if QUALIFIER.fullmatch(key):
                    self.qualifiers[_qualifier_key(key)] = value
                else:
                    self.identity_attribute(key, value)
                    self.fact(key, value, {**source, "cell": cell.get("native_path", cell.get("id"))})
            return
        # A complete horizontal record uses column roles, including column 0.
        # A single data row never turns the second column header into a value.
        rows = sorted({c["row"] for c in values if c["row"] not in header_rows})
        identity_columns = {c["col"] for c in headers if PRIMARY.fullmatch(c["text"])}
        for row in rows:
            band = [c for c in ordered if c["row"] <= row < c["row"] + c.get("row_span", 1) and c not in headers]
            identities = [c for c in band if c["col"] in identity_columns]
            own_rows = [c for c in row_headers if c["row"] <= row < c["row"] + c.get("row_span", 1)]
            subject = " / ".join(c["text"] for c in identities or own_rows) or self.subject
            facets = {h["text"]: c["text"] for h in headers for c in band if h["col"] == c["col"]
                      and IDENTITY.fullmatch(h["text"]) and not PRIMARY.fullmatch(h["text"])}
            for cell in band:
                if cell in row_headers:
                    continue
                attrs = cell.get("native_attributes", {})
                explicit = str(attrs.get("headers", "")).split()
                if explicit and any(len(by_id.get(h, [])) != 1 for h in explicit):
                    self.block("unresolved_or_ambiguous_explicit_header_reference", {**source, "cell": cell.get("id")}, references=explicit)
                    continue
                column = ([by_id[h][0] for h in explicit if by_id[h][0] not in row_headers]
                          if explicit else [h for h in headers if h["col"] <= cell["col"] < h["col"] + h.get("col_span", 1)])
                if len(column) != 1:
                    self.block("compound_header_semantics_unsupported", {**source, "cell": cell.get("id")},
                               headers=[c["text"] for c in column])
                    continue
                attribute = column[0]["text"]
                if explicit:
                    # A relation endpoint must have an identity independent
                    # of the value being tested. Visible numbers cannot name
                    # their own objects, nor can expected choose a data cell.
                    self.relation("explicit_header_reference", column[0].get("native_id"),
                                  cell.get("native_id", cell.get("native_path", cell.get("id"))),
                                  {**source, "cell": cell.get("id")})
                    self.data["relations"][-1]["independent_endpoint"] = bool(cell.get("native_id"))
                if QUALIFIER.fullmatch(attribute):
                    continue
                # An unlabeled first column is a row subject only when a
                # producer explicitly supplied its row-header role.
                if not attribute.strip():
                    self.block("untyped_record_name", {**source, "cell": cell.get("id")})
                    continue
                qualifiers = {}
                for qcell in band:
                    qheaders = [h for h in headers if h["col"] == qcell["col"] and QUALIFIER.fullmatch(h["text"])]
                    if len(qheaders) == 1:
                        qualifiers[_qualifier_key(qheaders[0]["text"])] = qcell["text"]
                self.fact(attribute, cell["text"], {**source, "cell": cell.get("native_path", cell.get("id"))},
                          subject=subject, qualifiers=qualifiers, identity_facets=facets)


def _finish(graph: _Graph) -> dict[str, Any]:
    # Stable semantic requirements; never inferred from candidate availability.
    # Delimiter labels for qualifiers are relational syntax, while their actual
    # literals remain text. A table's schema role labels are also syntax.
    graph.data["text"] = [x for x in graph.data["text"] if not
                          (x["role"] == "label" and QUALIFIER.fullmatch(x["text"]))]
    repeated_labels = Counter(canonical(item["text"]) for item in graph.data["text"] if item["role"] == "label")
    if any(count > 1 for count in repeated_labels.values()):
        graph.block("shared_header_text_restatement_unsupported", {"path": "<text-schema>"}, layers=["T"])
    # Read consecutive fragments of the same prose sentence in their printed
    # order. Preserve an actual word boundary. Never join numeric or field
    # atoms, and never skip intervening material.
    sentence_units = []
    for item in graph.data["text"]:
        parts = re.split(r"(?<=[。！？])\s*|(?<=[.!?])\s+(?=[A-Z])", item["text"]) if item["role"] == "literal" else [item["text"]]
        sentence_units.extend({**item, "text": text, "id": f"{item['id']}:sentence:{i}"}
                              for i, text in enumerate(parts) if text.strip())
    merged = []
    for item in sentence_units:
        if (merged and merged[-1]["role"] == item["role"] == "literal"
                and merged[-1]["continuity_segment"] == item["continuity_segment"]
                and not re.search(r"[。.!?！？;；:]$", merged[-1]["text"])
                and not NUMERIC.fullmatch(merged[-1]["text"])
                and not NUMERIC.fullmatch(item["text"])):
            previous = merged[-1]
            separator = "" if re.search(r"[\u3400-\u9fff]$", previous["text"]) and re.match(r"[\u3400-\u9fff]", item["text"]) else " "
            previous["strict_text"] = previous.get("strict_text", previous["text"]) + "\n" + item.get("strict_text", item["text"])
            previous["text"] += separator + item["text"]
            previous.setdefault("source_fragments", [previous["source"]]).append(item["source"])
        else:
            merged.append(item)
    graph.data["text"] = merged
    # Identity values are independently tested; they are not their own subject.
    for item in graph.data["business"]:
        if item["role"] == "identity" and canonical(item["value"]) == canonical(item["subject"]):
            item["subject"] = ""
    # This transient ledger detects mutation/omission between compilation and
    # grading. It is bookkeeping, not independent semantic validation.
    graph.data["requirement_ledger"] = copy.deepcopy(graph.data["business"])
    return graph.data


def compile_markdown(markdown: str, *, sample_id: str = "synthetic",
                     selected_lines: list[tuple[int, int]] | None = None, path: str = "<markdown>") -> dict[str, Any]:
    graph = _Graph(sample_id)
    skipped_context: list[dict[str, Any]] = []
    for element in elements(markdown):
        source = _source(path, element.lines)
        included = selected_lines is None or any(a <= element.lines[0] and element.lines[1] <= b for a, b in selected_lines)
        if not included:
            if element.kind == "heading" or any(QUALIFIER.fullmatch(k) for k, _ in _pairs(element.text)):
                skipped_context.append({"text": element.text, "source": source})
            continue
        if skipped_context and (element.headings or any(QUALIFIER.fullmatch(k) for c in skipped_context for k, _ in _pairs(c["text"]))):
            graph.block("input_scope_context", source, outside_selection=copy.deepcopy(skipped_context))
            skipped_context.clear()
        if element.kind == "heading":
            level = element.native_heading_level or 1
            graph.headings = graph.headings[:level - 1]
            graph.headings.append(element.text)
            graph.subject = ""
            graph.identity_facets = {}
            graph.record_start = len(graph.data["business"])
            graph.qualifiers = {}
            graph.prose(element.text, source, "heading")
        elif element.cells:
            graph.table(element.cells, source)
        else:
            graph.prose(element.text, source, "parent_label" if element.has_children else element.kind, list(element.parents))
    return _finish(graph)


def compile_expected(expected: dict[str, Any]) -> dict[str, Any]:
    """Compile raw selected syntax, deliberately ignoring legacy record fields."""
    if "business" in expected and "relations" in expected:
        return copy.deepcopy(expected)
    graph = _Graph(expected["sample_id"])
    selected_headings = {t["text"] for t in expected["targets"] if t["kind"] == "heading"}
    for target in expected["targets"]:
        source = target["reference"]
        if target.get("outside_selection_context"):
            graph.block("input_scope_context", source, outside_selection=target["outside_selection_context"])
        external = [name for name in target.get("context", []) if name not in selected_headings]
        if external:
            graph.block("input_scope_context", source, outside_selection=external)
        # Only selected, actually expressed headings may become obligations.
        graph.headings = [name for name in target.get("context", []) if name in selected_headings]
        if target.get("cells"):
            graph.table(target["cells"], source)
        else:
            graph.prose(target.get("raw_text", target["text"]), source,
                        "parent_label" if target.get("has_children") else target["kind"], target.get("parents", []))
    graph.data.update({key: expected.get(key) for key in ("document_id", "family_id", "development_exposure", "source_pages")})
    return _finish(graph)


def read_candidate_markdown(markdown: str, *, sample_id: str = "synthetic", pipeline: str = "test") -> dict[str, Any]:
    result = compile_markdown(markdown, sample_id=sample_id, path="<candidate-markdown>")
    result["pipeline"] = pipeline
    return result


def read_candidate(observation: dict[str, Any]) -> dict[str, Any]:
    if "business" in observation and "relations" in observation:
        return copy.deepcopy(observation)
    graph = _Graph(observation["sample_id"])
    graph.data["native_links"] = copy.deepcopy(observation.get("relations", []))
    if any(link.get("type") in {"continues", "footnote", "caption", "references"}
           for link in graph.data["native_links"]):
        graph.block("native_link_semantic_alignment_unsupported", {"path": "#/relations"})
    for page in observation.get("pages", []):
        for block in page.get("blocks", []):
            source = {"path": block.get("native_path", block.get("id")), "page": page.get("page"),
                      "lines": block.get("public_lines", []), "block": block.get("id")}
            if block.get("read_error_category") == "engineering_failure":
                graph.block("candidate_reader_failure", source, detail=block.get("read_error"))
            if block.get("notes") or any(cell.get("inline_annotations") for cell in block.get("cells", [])):
                graph.block("native_note_binding_interpretation_unsupported", source)
            if block.get("cells"):
                graph.table(block["cells"], source)
            else:
                representation = block.get("text_format", "plain")
                text = block.get("text", "")
                kind = block.get("kind", "text")
                if representation == "markdown":
                    declared_heading = kind in {"heading", "section_header", "title", "doc_title"}
                    if declared_heading:
                        level = block.get("heading_level", block.get("level", 1)) or 1
                        graph.headings = graph.headings[:max(0, int(level) - 1)]
                        graph.headings.append(visible_text(text, representation))
                    for element in elements(text):
                        element_source = {**source, "block_lines": list(element.lines)}
                        if element.cells:
                            graph.table(element.cells, element_source)
                        else:
                            if element.kind == "heading" and not declared_heading:
                                level = element.native_heading_level or 1
                                graph.headings = graph.headings[:level - 1] + [element.text]
                            graph.prose(element.text, element_source,
                                        "heading" if declared_heading else "parent_label" if element.has_children else element.kind,
                                        list(element.parents))
                else:
                    if kind in {"heading", "section_header", "title", "doc_title"}:
                        level = block.get("heading_level", block.get("level", 1)) or 1
                        graph.headings = graph.headings[:max(0, int(level) - 1)]
                        graph.headings.append(visible_text(text, representation))
                    graph.prose(visible_text(text, representation), source,
                                "parent_label" if block.get("public_has_children") else kind,
                                block.get("public_list_parents", []))
    result = _finish(graph)
    result.update(pipeline=observation.get("pipeline"), status=observation.get("status"),
                  timing=observation.get("timing", {}), resources=observation.get("resources", {}))
    return result


def _edit(reference: str, actual: str) -> dict[str, int]:
    counts = Counter(op.tag for op in Levenshtein.editops(reference, actual))
    return {"S": counts["replace"], "D": counts["delete"], "I": counts["insert"]}


def _text_layer(reference: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    available = set(range(len(candidate)))
    matches: dict[int, int] = {}
    # Literal-unit capacity one, not a global character bag. Complete units
    # can move; no permutation inside any word, number or paragraph is allowed.
    for i, item in enumerate(reference):
        hits = [j for j in sorted(available) if canonical(candidate[j]["text"]) == canonical(item["text"])]
        if hits:
            matches[i] = hits[0]
            available.remove(hits[0])
    possibilities = []
    for i, item in enumerate(reference):
        if i in matches:
            continue
        for j in available:
            a, b = canonical(item["text"]), canonical(candidate[j]["text"])
            similarity = Levenshtein.normalized_similarity(a, b)
            if similarity >= 0.35:
                possibilities.append((-similarity, i, j))
    for _, i, j in sorted(possibilities):
        if i not in matches and j in available:
            matches[i] = j
            available.remove(j)
    rows, totals = [], Counter()
    located_characters = 0
    for i, item in enumerate(reference):
        actual = candidate[matches[i]] if i in matches else None
        a, b = canonical(item["text"]), canonical(actual["text"]) if actual else ""
        edit = _edit(a, b)
        strict = _edit(item.get("strict_text", item["text"]), actual.get("strict_text", actual["text"]) if actual else "")
        totals.update(edit)
        located_characters += len(a) if actual else 0
        rows.append({"id": item["id"], "layer": "T", "role": "literal", "expected": item,
                     "actual": actual, "outcome": "correct" if a == b else "incorrect",
                     "edits": edit, "strict_edits": strict, "source": item["source"],
                     "root_cause": f"literal:{item['id']}"})
    denominator = sum(len(canonical(item["text"])) for item in reference)
    numerator = denominator - sum(totals.values())
    return {"numerator": numerator, "denominator": denominator,
            "score": 100 * max(0, numerator) / denominator if denominator else None,
            "complete": True, **{key: totals[key] for key in ("S", "D", "I")},
            "located_units": len(matches), "required_units": len(reference),
            "located_characters": located_characters, "unadjudicated_extra_units": [candidate[j] for j in sorted(available)],
            "full_scope_edit_rate": sum(totals.values()) / denominator if denominator else None}, rows


def _key(fact: dict[str, Any]) -> tuple[Any, ...]:
    return (canonical(fact["subject"]), canonical(fact["attribute"]), tuple(canonical(x) for x in fact.get("scope", [])),
            tuple(sorted((canonical(key), canonical(value)) for key, value in fact.get("identity_facets", {}).items())))


def _retrieve(wanted: dict[str, Any], candidates: list[dict[str, Any]], literals: list[dict[str, Any]]) -> dict[str, Any]:
    query = {"subject": wanted["subject"], "attribute": wanted["attribute"], "scope": wanted.get("scope", []),
             "identity_facets": wanted.get("identity_facets", {})}
    hits = []
    for item in candidates:
        # Recall is deliberately broader than identity validation. Even a
        # unique hit must pass every independent identity/context check.
        if canonical(item["attribute"]) != canonical(wanted["attribute"]):
            continue
        checks = {key: {"required": query[key], "actual": item.get(key, [] if key == "scope" else {} if key == "identity_facets" else ""),
                        "correct": (not query[key] if key == "scope" else False)
                        or (_key(wanted)[index] == _key(item)[index])}
                  for index, key in enumerate(("subject", "attribute", "scope", "identity_facets"))}
        accepted = all(check["correct"] for check in checks.values())
        hits.append({"id": item["id"], "source": item["source"], "identity": checks,
                     "decision": "accepted" if accepted else "rejected",
                     "reason": "identity_and_context_verified" if accepted else "explicit_identity_or_context_conflict"})
    literal_hits = [{"id": item["id"], "source": item["source"], "text": item["text"],
                     "scope": item.get("scope", []), "role": item["role"],
                     "decision": "literal_evidence_only", "reason": "literal_alone_does_not_prove_a_value_binding"}
                    for item in literals if canonical(wanted["attribute"]) in canonical(item["text"])]
    return {"query": query, "candidates": hits, "textual_hits": literal_hits,
            "accepted": [hit["id"] for hit in hits if hit["decision"] == "accepted"]}


def _business_layer(reference: list[dict[str, Any]], candidate: list[dict[str, Any]], *,
                    literals: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in reference:
        groups[_key(item)].append(item)
    rows = []
    for members in groups.values():
        retrieval = _retrieve(members[0], candidate, literals)
        actual = [item for item in candidate if item["id"] in retrieval["accepted"]]
        # Establish the complete identity set before observing any answer.
        # Compare repeated records as a multiset, never cherry-pick a value.
        def sig(item):
            return canonical(item["value"]), tuple(sorted((key, canonical(value)) for key, value in item["qualifiers"].items()))
        agree = Counter(map(sig, members)) == Counter(map(sig, actual))
        for item in members:
            rows.append({"id": item["id"], "layer": "B", "role": item["role"], "expected": item,
                         "actual": actual, "outcome": "correct" if agree else "incorrect", "retrieval": retrieval,
                         "reason": "complete_assertion_set_equal" if agree else "missing_conflicting_or_different_assertion_set",
                         "root_cause": "binding:" + repr(_key(item))})
    numerator, denominator = sum(row["outcome"] == "correct" for row in rows), len(rows)
    return {"numerator": numerator, "denominator": denominator, "score": 100 * numerator / denominator if denominator else None,
            "complete": True}, rows


def _relation_signature(edge: dict[str, Any]) -> Any:
    def freeze(value: Any) -> Any:
        if isinstance(value, dict):
            return tuple(sorted((k, freeze(v)) for k, v in value.items()))
        if isinstance(value, list):
            return tuple(map(freeze, value))
        return canonical(value) if isinstance(value, str) else value
    return edge["type"], freeze(edge["left"]), freeze(edge["right"])


def _relation_layer(reference: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    available = list(candidate)
    rows = []
    for item in reference:
        hits = [edge for edge in available if _relation_signature(edge) == _relation_signature(item)]
        actual = hits[0] if hits else None
        if actual:
            available.remove(actual)
        rows.append({"id": item["id"], "layer": "L", "role": item["type"], "expected": item,
                     "actual": actual, "outcome": "correct" if actual else "incorrect",
                     "root_cause": "relation:" + repr(_relation_signature(item))})
    numerator, denominator = sum(row["outcome"] == "correct" for row in rows), len(rows)
    return {"numerator": numerator, "denominator": denominator, "score": 100 * numerator / denominator if denominator else None,
            "complete": True}, rows


def grade_layers(requirements: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    if requirements["sample_id"] != evidence["sample_id"]:
        raise ValueError("expected and candidate sample identities differ")
    if requirements.get("requirement_ledger") != requirements["business"]:
        raise ValueError("compiled requirements changed or were omitted before grading")
    layers, rows = {}, []
    for key, reference_key, function in (("T", "text", _text_layer), ("L", "relations", _relation_layer), ("B", "business", _business_layer)):
        arguments = {"literals": evidence["text"]} if key == "B" else {}
        layers[key], outcomes = function(requirements[reference_key], evidence[reference_key], **arguments)
        rows.extend(outcomes)
    requires_explicit_object_ids = any(edge["type"] == "explicit_header_reference" for edge in requirements["relations"])
    blockers = [{"side": side, **blocker} for side, graph in (("expected", requirements), ("candidate", evidence))
                for blocker in graph.get("blockers", [])
                if not (side == "candidate" and not requires_explicit_object_ids and
                        blocker["reason"] == "explicit_reference_endpoint_without_independent_identity")]
    if requires_explicit_object_ids:
        blockers.extend({"side": side, "reason": "explicit_reference_endpoint_without_independent_identity", "source": edge["source"]}
                        for side, graph in (("expected", requirements), ("candidate", evidence))
                        for edge in graph["relations"] if edge["type"] == "explicit_header_reference" and not edge.get("independent_endpoint"))
    for key, layer in layers.items():
        affected = any(key in blocker.get("layers", ["L", "B"]) for blocker in blockers)
        layer["complete"] = not affected
        if affected:
            layer["score"] = None
    return {"sample_id": requirements["sample_id"], "pipeline": evidence.get("pipeline"), "protocol": PROTOCOL,
            "layers": layers, "score": sum(layer["score"] for layer in layers.values()) / 3
            if not blockers and all(layer["denominator"] for layer in layers.values()) else None,
            "publishable": not blockers, "blockers": blockers, "outcomes": rows,
            "status": evidence.get("status"), "timing": evidence.get("timing", {}),
            **{key: requirements.get(key) for key in ("document_id", "family_id", "development_exposure")}}


def grade_expected(expected: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    return grade_layers(compile_expected(expected), read_candidate(observation))
