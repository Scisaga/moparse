"""Expected-only, independent text, relation and business measurements.

This module has no PDF, model, service or reference-writing interface. The
syntax reader is shared; requirements and candidate evidence are separate
objects. Unsupported semantics are publication blockers, never candidate
errors. No legacy scorer is called.
"""

from __future__ import annotations

import copy
import re
from collections import Counter
from typing import Any

from rapidfuzz.distance import Levenshtein

from app.utils.measurement import unit_applicable, unit_kind

from .business_correspondence import grade_business
from .business_labels import is_amount_role
from .cjk_narrative_requirements import read_cjk_narrative
from .compact_requirements import read_compact_requirements, read_compact_schema
from .context_evidence import read_contexts
from .entity_requirements import read_entity_requirements
from .enumeration_binding import (
    bind_interpreted_members,
    inherit_omitted_subject,
    member_for_source,
    plan_from_syntax,
)
from .enumeration_context import read_enumeration_intro
from .expected_readback import _context_continues, elements
from .explicit_reference_requirements import read_explicit_references
from .field_sequence_requirements import read_field_sequence_requirements, read_labelled_record
from .financial_group_context import (
    bind_financial_group_facts,
    bind_financial_notes,
    bind_financial_summaries,
    financial_statement_kind,
    read_financial_attribution_context,
    read_financial_group_context,
    read_financial_summary_intro,
)
from .header_path_requirements import read_header_path_requirements
from .matrix_evidence import read_matrix
from .measurement_evidence import read_measurement_label, read_measurement_literal, read_unit_token
from .metrics import normalize_text
from .narrative_requirements import read_narrative
from .proposition_requirements import read_propositions
from .prose_requirements import _sentence_spans, read_prose_requirements, read_prose_sequence
from .relation_correspondence import grade_relations
from .representations import visible_text
from .scalar_evidence import validate_scalar_sources
from .scoring_evidence import evidence_session, snapshot_copy
from .series_requirements import (
    is_ordinary_scalar_field,
    read_series_context,
    read_series_requirements,
)
from .source_requirements import plan_field_body, plan_mixed_source
from .text_projection import (
    combine_text_projections,
    project_compact_text,
    project_header_path_text,
    project_metric_declaration,
    project_table_text,
)
from .toc_evidence import project_toc_text, read_toc

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
LOGICAL = re.compile(r"\b(?:must|shall|unless|except|if|not|no|only|obligation)\b|不能|不可|不得|必须|应当|不应|只有|如果|除外|除非|仅限|条件|不适用|不包括|否认|禁止", re.I)
IMPORTANT_RELATION = re.compile(
    r"\b(?:owns?|owned|acquir(?:e[sd]?|ing)|sold|merg(?:e[sd]?|ing)|issued?|issuance|"
    r"approv(?:e[sd]?|al)|declar(?:e[sd]?|ation)|dividends?|repay(?:s|ment|ments)?|guarantee[sd]?|"
    r"borrow(?:s|ed|ing)?|lend(?:s|ing)?|vot(?:e[sd]?|ing)|obligations?|entitl(?:ed|ement)|"
    r"invest(?:s|ed|ing)?|report(?:s|ed|ing)?)\b"
    r"|持有|持股|收[购購]|[发發]行|批准|[审審]批|派[发發]|[偿償][还還]|[担擔]保|表[决決]", re.I)
NUMERIC = re.compile(r"[+\-−]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)\s*(?:[%‰]|万元|亿元|元|万元人民币|人民币|美元|人|股|万股|吨|件)?$")
UNBOUND_NUMBERS = re.compile(r"\s*[+\-−]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)[%‰]?(?:\s+[+\-−]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)[%‰]?)*\s*")
PAIR = re.compile(r"^([^:：=\n]{1,100}?)\s*[:：=]\s*(.*)$", re.S)
CLAUSAL_LABEL = re.compile(
    r"\b(?:am|is|are|was|were|have|has|had|will|shall|must|should|cannot|owns?|owned|acquired|approved)\b"
    r"|[。！？!?]|(?:我们|本公司|本集团|管理层|董事会)(?:正在|已经|将|拟|计划|决定|宣布)", re.I)


def canonical(text: str) -> str:
    """Preserve internal words, signs and digits, including numeric spaces."""
    text = re.sub(r"(?<=[\u3400-\u9fff])[^\S\n]*\n\s*(?=[\u3400-\u9fff])", "", text)
    text = normalize_text(text, collapse_whitespace=True).strip()
    # Only full Latin-containing terms at CJK boundaries have display spaces.
    text = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[A-Za-z]|\d+[A-Za-z])", "", text)
    text = re.sub(r"([A-Za-z0-9]*[A-Za-z][A-Za-z0-9]*)\s+(?=[\u3400-\u9fff])", r"\1", text)
    return text


def _read_narrative(text, source, *, scope=()):
    from .cjk_narrative_requirements import join_following_explanations

    sentences = join_following_explanations(text, _sentence_spans(text), source=source)
    if len(sentences) > 1 and re.search(r"[\u3400-\u9fff]", text):
        # Language dispatch belongs to an independent statement. Selecting
        # the reader with the most leaves over a whole bilingual paragraph
        # silently discarded valid statements read by the other language.
        parts = []
        offset = source.get("text_span", [0])[0]
        for ordinal, (start, end) in enumerate(sentences):
            origin = {**copy.deepcopy(source), "text_span": [offset + start, offset + end]}
            part = _read_narrative(text[start:end], origin, scope=scope)
            identifiers = {fact["id"]: f"statement:{ordinal}:{fact['id']}"
                           for key in ("facts", "semantic_operands") for fact in part.get(key, []) if fact.get("id")}

            def rebind(value, local_ids=identifiers):
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key in {"id", "fact_id"} and isinstance(child, str) and child in local_ids:
                            value[key] = local_ids[child]
                        else:
                            rebind(child)
                elif isinstance(value, list):
                    for child in value:
                        rebind(child)

            rebind(part)
            parts.append(part)
        result = copy.deepcopy(parts[0])
        for key in ("facts", "relations", "logic", "semantic_operands", "semantic_operand_relations",
                    "unresolved", "blockers", "pending_requirements", "issues", "controls"):
            result[key] = [copy.deepcopy(item) for part in parts for item in part.get(key, [])]
        result["required_matcher_features"] = sorted({feature for part in parts for feature in part.get("required_matcher_features", [])})
        origin = {**copy.deepcopy(source), "text_span": [offset, offset + len(text)]}
        result.update(source=copy.deepcopy(source), raw_text=text, syntax_language="mixed",
                      matched=any(part["matched"] for part in parts),
                      complete=all(part["complete"] for part in parts),
                      semantic_complete=all(part["complete"] for part in parts),
                      text_atoms=[{"text": text, "role": "literal", "source": origin}],
                      consumed_spans=[{"text": text, "role": "literal", "span": [0, len(text)], "source": origin}])
        return result
    english = read_narrative(text, source, scope=scope)
    english["syntax_language"] = "en"
    if english["complete"]:
        return english
    cjk = read_cjk_narrative(text, source, scope=scope)
    cjk["syntax_language"] = "zh"
    if cjk["matched"] and (cjk["complete"] or len(cjk["logic"]) > len(english["logic"])):
        return cjk
    return english


def _bind_field_body(result, label, label_source):
    """Retain a printed body owner without replacing the asserted actors."""
    if not label or not label_source:
        return result
    proof = {"text": label, "source": copy.deepcopy(label_source), "role": "printed_field_label"}

    def bind(value):
        if isinstance(value, dict):
            if isinstance(value.get("scope"), list) and (not value["scope"] or value["scope"][-1] != label):
                value["scope"].append(label)
            if value.get("kind") == "proposition":
                value["field_label_evidence"] = copy.deepcopy(proof)
            for child in value.values():
                bind(child)
        elif isinstance(value, list):
            for child in value:
                bind(child)

    # Sources contain no scope labels. Every semantic endpoint belongs to the
    # same explicitly printed field, including its conditional operands.
    bind(result)
    for fact in [*result.get("facts", []), *result.get("semantic_operands", [])]:
        fact.update(printed_label=label, label_source=copy.deepcopy(label_source),
                    field_label_evidence=copy.deepcopy(proof))
    for edge in [*result.get("relations", []), *result.get("semantic_operand_relations", [])]:
        edge["field_label_evidence"] = copy.deepcopy(proof)
    return result


def _adopt_comparison_tree(result, narrative):
    """Add a complete AST only when independently read role sources agree."""
    if not narrative["complete"] or result.get("blockers"):
        return result
    roles = ("attribute", "object", "subject_source", "predicate_source", "object_source")

    def signature(fact):
        return repr([str(fact.get("subject", "")).casefold(), *[fact.get(key) for key in roles]])

    facts = result.get("facts", [])
    if Counter(map(signature, facts)) != Counter(map(signature, narrative["facts"])):
        return result
    for key in ("logic", "semantic_operands", "semantic_operand_relations"):
        result[key] = copy.deepcopy(narrative.get(key, []))

    def bind(node):
        if isinstance(node, dict):
            if node.get("kind") == "proposition":
                matching = [fact for fact in facts if signature(fact) == signature(node)]
                if len(matching) == 1:
                    fact = matching[0]
                    node["identity_facets"] = copy.deepcopy(fact.get("identity_facets", {}))
                    if fact.get("record_evidence"):
                        node["record_evidence"] = copy.deepcopy(fact["record_evidence"])
            for value in node.values():
                bind(value)
        elif isinstance(node, list):
            for value in node:
                bind(value)

    bind(result["logic"])
    result["required_matcher_features"] = sorted(set(result.get("required_matcher_features", []))
        | set(narrative.get("required_matcher_features", [])))
    return result


def _discharge_superseded_clause_pending(data, text, source):
    """Close only the exact clause a later complete source reading explained."""
    def superseded(issue):
        if issue.get("reason") != "prose_clause_semantics_unsupported":
            return False
        own = issue.get("source", {})
        if any(own.get(key) != source.get(key) for key in ("path", "lines", "cell", "block")):
            return False
        outer, inner = source.get("text_span"), own.get("text_span")
        return bool(outer and inner and outer[0] <= inner[0] <= inner[1] <= outer[1]
                    and canonical(issue.get("text", "")).rstrip(".!?。！？") == canonical(text).rstrip(".!?。！？"))

    for key in ("blockers", "pending_requirements"):
        data[key] = [issue for issue in data.get(key, []) if not superseded(issue)]


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


def _pair_sources(text: str, source: dict[str, Any]) -> list[tuple[str, str, dict[str, Any], dict[str, Any]]]:
    """Record each printed label and value span before interpreting its role."""
    pairs = _pairs(text)
    cursor = 0
    result = []
    for key, value in pairs:
        start = text.find(key, cursor)
        delimiter = re.search(r"[:：=]", text[start + len(key):])
        if start < 0 or delimiter is None:
            raise ValueError("explicit pair has no source span")
        after = start + len(key) + delimiter.end()
        value_start = text.find(value, after) if value else after
        if value_start < 0:
            raise ValueError("explicit pair value has no source span")
        offset = source.get("text_span", [0])[0]
        key_source = {**source, "text_span": [offset + start, offset + start + len(key)]}
        value_source = {**source, "text_span": [offset + value_start, offset + value_start + len(value)],
                        "attribute_source": copy.deepcopy(key_source)}
        result.append((key, value, key_source, value_source))
        cursor = value_start + len(value)
    return result


def _printed_unit_declaration(value: str, source: dict[str, Any]) -> dict[str, Any]:
    """A terminal sentence mark is control only after a whole unit token."""
    result = read_unit_token(value, source)
    if not result["matched"] and value.endswith(("。", ".")):
        result = read_unit_token(value[:-1], source)
        if result["matched"]:
            parent_span = source.get("text_span")
            offset = parent_span[0] if isinstance(parent_span, (list, tuple)) and len(parent_span) == 2 and type(parent_span[0]) is int else 0
            result["controls"].append({"text": value[-1], "source": {**copy.deepcopy(source),
                "text_span": [offset + len(value) - 1, offset + len(value)]},
                "reason": "explicit_unit_declaration_terminator"})
    return result


def _compound_metric_series(text: str, source: dict[str, Any]) -> dict[str, Any] | None:
    """Retain a plain prefix and field slots whose joint roles are unresolved."""
    bounds, cursor = [], 0
    for separator in re.finditer(r"[;；]", text):
        bounds.append((cursor, separator.start()))
        cursor = separator.end()
    bounds.append((cursor, len(text)))
    parts = []
    for start, end in bounds:
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            parts.append((start, end))
    if len(parts) < 2 or PAIR.fullmatch(text[slice(*parts[0])]):
        return None
    parent_span = source.get("text_span")
    offset = parent_span[0] if isinstance(parent_span, (list, tuple)) and len(parent_span) == 2 and type(parent_span[0]) is int else 0

    def span(start: int, end: int) -> dict[str, Any]:
        return {**copy.deepcopy(source), "text_span": [offset + start, offset + end]}

    segments, periods = [], 0
    for start, end in parts[1:]:
        match = PAIR.fullmatch(text[start:end])
        if match is None:
            return None
        label, value = match[1].strip(), match[2].strip()
        label_start = start + match.start(1) + len(match[1]) - len(match[1].lstrip())
        value_start = start + match.start(2) + len(match[2]) - len(match[2].lstrip())
        segments.append({"label": label, "value": value,
                         "label_source": span(label_start, label_start + len(label)),
                         "value_source": span(value_start, value_start + len(value))})
        year = re.search(r"(?<!\d)(?:19|20)\d{2}(?!\d)", label)
        period_role = re.search(r"\b(?:year|period|quarter|months?|as\s+of)\b|截至|年度|期間|期间|期末|年", label, re.I)
        if year and (period_role or re.fullmatch(r"(?:19|20)\d{2}年?", label)):
            periods += 1
    if not periods and len(segments) < 2:
        return None
    prefix = {"text": text[slice(*parts[0])], "source": span(*parts[0])}
    if periods:
        return {"kind": "compound_metric_series", "reason": "compound_metric_series_interpretation_unsupported",
                "text": text, "source": span(0, len(text)), "metric": prefix,
                "segments": segments, "layers": ["B", "L"]}
    return {"kind": "prefixed_field_sequence", "reason": "prefixed_field_sequence_interpretation_unsupported",
            "text": text, "source": span(0, len(text)), "prefix": prefix,
            "segments": segments, "layers": ["B", "L"]}


def _toc_syntax_blocks(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate already-read syntax and its own parent references, not answers."""
    blocks, seen = [], []
    for target in targets:
        source = {**copy.deepcopy(target["reference"]), "block": target["id"]}
        block = {"id": target["id"], "text": target["text"], "text_format": "plain", "source": source,
                 "kind": "heading" if target["kind"] == "heading" else "toc_group" if target.get("has_children") else "text"}
        if target.get("heading_level"):
            block["heading_level"] = target["heading_level"]
        if target.get("cells"):
            block.update(kind="table", cells=copy.deepcopy(target["cells"]))
        external = {item.get("text") for item in target.get("outside_selection_context", []) if item.get("kind") == "list_parent"}
        for parent in reversed(target.get("parents", [])):
            match = next((old for old in reversed(seen) if old["text"] == parent and old.get("list_span") == target.get("list_span")), None)
            if parent not in external and match is not None:
                block["parent_id"] = match["id"]
                break
        blocks.append(block)
        seen.append(target)
    return blocks


class _Graph:
    def __init__(self, sample_id: str) -> None:
        self.data: dict[str, Any] = {"sample_id": sample_id, "text": [], "business": [],
                                     "relations": [], "blockers": [], "syntax": [], "scope_context": []}
        self.qualifiers: dict[str, str] = {}
        self.subject = ""
        self.headings: list[str] = []
        self.heading_stack: list[tuple[int, str]] = []
        self.continuity_segment = 0
        self.identity_facets: dict[str, str] = {}
        self.record_start = 0
        self.fact_serial = 0
        self.compact_schema: dict[str, Any] | None = None
        self.series_context: dict[str, Any] | None = None
        self.qualifier_evidence: dict[str, dict[str, Any]] = {}
        self.qualifier_levels: dict[str, str] = {}
        self.record_id: str | None = None
        self.record_sources: dict[str, str] = {}
        self.text_projections: list[dict[str, Any]] = []

    @staticmethod
    def source_key(source: dict[str, Any]) -> str:
        return repr((source.get("path"), source.get("lines"), source.get("block"), source.get("block_lines"), source.get("cell")))

    def enter_heading(self, text: str, level: int) -> None:
        self.heading_stack = [(depth, label) for depth, label in self.heading_stack if depth < level]
        self.heading_stack.append((level, text))
        self.headings = [label for _, label in self.heading_stack]
        self.clear_heading_state()

    def clear_heading_state(self) -> None:
        self.subject = ""
        self.identity_facets = {}
        self.record_id = None
        self.qualifiers = {}
        self.qualifier_levels = {}
        self.qualifier_evidence = {}
        self.compact_schema = None
        self.series_context = None

    def open_record(self, source: dict[str, Any]) -> str:
        key = self.source_key(source)
        if key not in self.record_sources:
            self.record_sources[key] = f"record:{len(self.record_sources)}:{key}"
        self.record_id = self.record_sources[key]
        return self.record_id

    def identity_attribute(self, attribute: str, value: str) -> None:
        if PRIMARY.fullmatch(attribute):
            for key in list(self.qualifiers):
                if self.qualifier_levels.get(key) == "record_explicit":
                    self.qualifiers.pop(key, None)
                    self.qualifier_levels.pop(key, None)
                    self.qualifier_evidence.pop(key, None)
            self.subject = value
            self.identity_facets = {}
            self.record_start = len(self.data["business"])
            if self.data["syntax"]:
                self.open_record(self.data["syntax"][-1]["source"])
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
                                  "syntax_kind": self.data["syntax"][-1]["kind"] if self.data["syntax"] else None,
                                  "continuity_segment": self.continuity_segment, "scope": list(self.headings)})
        if self.data["syntax"]:
            item_source = self.data["syntax"][-1].get("syntax_evidence", {}).get("item_source")
            if item_source:
                self.data["text"][-1]["list_item_source"] = copy.deepcopy(item_source)
            if self.data["syntax"][-1].get("enumeration_declaration"):
                self.data["text"][-1]["enumeration_declaration"] = True
        return identifier

    def relation(self, kind: str, left: Any, right: Any, source: dict[str, Any]) -> None:
        edge = {"id": f"L:{len(self.data['relations'])}", "type": kind, "left": left, "right": right, "source": source}
        self.data["relations"].append(edge)

    def declare_qualifier(self, key: str, value: str, source: dict[str, Any], *, record: bool) -> None:
        if key == "unit":
            printed = _printed_unit_declaration(value, source)
            if printed["matched"]:
                value, source = printed["unit"], printed["sources"]["unit"]
        self.qualifiers[key] = value
        level = "record_explicit" if record else "caption_shared"
        proof = {"text": value, "source": copy.deepcopy(source), "level": level}
        self.qualifier_levels[key] = level
        self.qualifier_evidence[key] = proof
        if not record or not self.record_id:
            return
        for item in self.data["business"]:
            if item["record_id"] != self.record_id or item["role"] == "identity":
                continue
            if item.get("qualifier_provenance", {}).get(key, {}).get("level") in {"field_inline", "header_explicit"}:
                continue
            item["qualifiers"][key] = value
            item.setdefault("qualifier_provenance", {})[key] = copy.deepcopy(proof)
            edges = [edge for edge in self.data["relations"] if edge.get("fact_id") == item["id"]]
            for edge in edges:
                edge["right"]["qualifiers"][key] = value
                if edge["type"] == "qualifier_scope" and edge["left"]["type"] == key:
                    edge["left"]["text"] = value
            if not any(edge["type"] == "qualifier_scope" and edge["left"]["type"] == key for edge in edges):
                self.relation("qualifier_scope", {"type": key, "text": value}, copy.deepcopy(edges[0]["right"]), source)
                self.data["relations"][-1]["fact_id"] = item["id"]

    def unresolved_unit_boundary(self, text: str, source: dict[str, Any], kind: str, parents: list[str]) -> None:
        proof = self.qualifier_evidence.get("unit")
        if not proof:
            return
        if kind == 'image_caption':
            self.data.setdefault('unit_scope_terminations', []).append({'declaration': copy.deepcopy(proof),
                'boundary': {'kind': kind, 'text': text, 'source': copy.deepcopy(source)},
                'rule_id': 'declared_media_caption_ends_prior_record_unit_default'})
            return
        reading = _read_narrative(text, source, scope=self.headings) if not parents and kind in {"text", "field_body"} else None
        offset = source.get('text_span', [0])[0]
        dated_numbers = [origin['text_span'] for fact in (reading or {}).get('facts', [])
                         for key, origin in fact.get('qualifier_sources', {}).items()
                         if key in {'period', 'from_period', 'to_period'} and isinstance(origin, dict)
                         and all(origin.get(k) == source.get(k) for k in ('path', 'lines', 'cell', 'block', 'native_path'))
                         and 'text_span' in origin]
        only_dates = all(any(a <= offset + m.start() < offset + m.end() <= b for a, b in dated_numbers)
                         for m in re.finditer(r'\d+', text))
        explicit = bool(reading and reading.get("facts") and (reading['complete'] and only_dates or all(fact.get("qualifier_sources", {}).get("unit")
            for fact in reading["facts"]) and (reading["complete"] or all(
                not re.search(r"\d", fragment.get("text", "")) for issue in reading.get("unresolved", [])
                for fragment in issue.get("fragments", [issue])))))
        if explicit:
            self.data.setdefault("unit_scope_terminations", []).append({"declaration": copy.deepcopy(proof),
                "boundary": {"kind": kind, "text": text, "source": copy.deepcopy(source)},
                "rule_id": "independent_prose_inline_units_end_the_table_default"})
            return
        original = next((item for item in reversed(self.data["syntax"][:-1])
                         if self.source_key(item["source"]) == self.source_key(proof["source"])), None)
        printed = read_unit_token(proof["text"], proof["source"])
        pending = {"kind": "unit_scope", "reason": "unit_scope_boundary_unresolved",
                   "text": original["text"] if original else proof["text"],
                   "source": copy.deepcopy(original["source"] if original else proof["source"]),
                   "unit": proof["text"], "currency": printed["currency"],
                   "unit_source": copy.deepcopy(proof["source"]),
                   "currency_source": copy.deepcopy(printed["sources"].get("currency")),
                   "scope": copy.deepcopy(original["scope"] if original else self.headings),
                   "boundary": {"kind": kind, "text": text, "source": copy.deepcopy(source)},
                   "affected": {"role": "unit_application_to_following_fields", "scope": list(self.headings),
                                "parent_context": list(parents), "boundary_text": text},
                   "layers": ["B", "L"]}
        self.data["blockers"].append(copy.deepcopy(pending))
        self.data.setdefault("pending_requirements", []).append(pending)

    def financial_heading(self) -> dict[str, Any] | None:
        actual = next((item for item in reversed(self.data["syntax"])
                       if item["kind"] == "heading" and item["scope"] == self.headings
                       and self.headings and item["text"] == self.headings[-1]), None)
        return {"text": actual["text"], "source": copy.deepcopy(actual["source"])} if actual else None

    def end_financial_unit_scope(self, text: str, source: dict[str, Any], kind: str, parents: list[str]) -> None:
        if not financial_statement_kind(self.financial_heading()) or not self.qualifier_evidence.get("unit"):
            return
        self.unresolved_unit_boundary(text, source, kind, parents)
        self.qualifiers = {}
        self.qualifier_levels = {}
        self.qualifier_evidence = {}
        self.series_context = None

    def fact(self, attribute: str, value: str, source: dict[str, Any], *,
             subject: str | None = None, qualifiers: dict[str, str] | None = None,
             identity: bool | None = None, role: str | None = None,
             identity_facets: dict[str, str] | None = None, inherit_qualifiers: bool = True,
             scope: list[str] | None = None, record_id: str | None = None,
             attribute_source: dict[str, Any] | None = None,
             measurement_source: dict[str, Any] | None = None,
             qualifier_sources: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        identity = bool(IDENTITY.fullmatch(attribute)) if identity is None else identity
        q = {**(self.qualifiers if inherit_qualifiers else {}), **(qualifiers or {})}
        provenance = copy.deepcopy(self.qualifier_evidence) if inherit_qualifiers else {}
        for key, origin in (qualifier_sources or {}).items():
            if (key in {"unit", "currency", "period", "period_basis", "from_period", "to_period", "column_currency"}
                    and key in q and isinstance(origin, dict) and origin.get("path")):
                provenance[key] = {"text": q[key], "source": copy.deepcopy(origin), "level": "source_explicit"}
        if inherit_qualifiers and (identity or (q.get("unit") and self.qualifier_levels.get("unit") != "record_explicit"
                                               and not unit_applicable(q["unit"], [attribute]))):
            q.pop("unit", None)
            provenance.pop("unit", None)
        header = read_measurement_label(attribute, attribute_source or source)
        if not identity and header["matched"]:
            attribute = header["label"]
            for key in ("unit", "currency"):
                if header[key]:
                    q[key] = header[key]
                    provenance[key] = {"text": header[key], "source": header["sources"][key], "level": "header_explicit"}
        original_value = value
        measured_source = measurement_source or source
        measurement = read_measurement_literal(value, measured_source)
        if not identity and measurement["matched"]:
            value = measurement["value"]
            for key in ("unit", "currency"):
                if measurement[key]:
                    q[key] = measurement[key]
                    provenance[key] = {"text": measurement[key], "source": measurement["sources"][key], "level": "field_inline"}
        # An explicitly printed currency name inside the actual unit is its
        # currency proof. Symbols such as $ never select a default currency.
        unit = read_unit_token(q.get("unit", ""), provenance.get("unit", {}).get("source", source))
        if not identity and unit["matched"] and unit["currency"] and "currency" not in q:
            q["currency"] = unit["currency"]
            provenance["currency"] = {"text": unit["currency"], "source": unit["sources"]["currency"],
                                      "level": provenance.get("unit", {}).get("level", "explicit_unit"), "derived_from": "unit"}
        item = {"id": f"B:{self.fact_serial}", "subject": self.subject if subject is None else subject,
                "attribute": attribute, "value": value, "role": role or ("identity" if identity else "metric"),
                "qualifiers": q, "scope": list(self.headings if scope is None else scope), "source": source,
                "identity_facets": {} if identity else dict(self.identity_facets if identity_facets is None else identity_facets),
                "qualifier_provenance": {key: proof for key, proof in provenance.items() if key in q},
                "record_id": record_id or self.record_id or self.open_record(source)}
        self.fact_serial += 1
        if not identity and measurement["matched"]:
            item["raw_value"] = original_value
            item["value_source"] = copy.deepcopy(measurement["sources"]["value"])
            item["source"] = copy.deepcopy(measured_source)
            if measured_source != source:
                item["statement_source"] = copy.deepcopy(source)
        if identity and canonical(item["value"]) == canonical(item["subject"]):
            item["subject"] = ""
        self.data["business"].append(item)
        logical_scope = list(item["scope"])
        group = item["identity_facets"].get("group")
        group_path = group if isinstance(group, list) else [group] if group else []
        if group_path and logical_scope[-len(group_path):] != group_path:
            logical_scope.extend(group_path)
        endpoint = {"subject": item["subject"], "attribute": attribute, "scope": logical_scope,
                    "qualifiers": dict(q), "identity_facets": dict(item["identity_facets"])}
        self.relation("field_binding", {"subject": item["subject"], "attribute": attribute}, endpoint, source)
        self.data["relations"][-1]["fact_id"] = item["id"]
        for key, literal in q.items():
            origin = provenance.get(key, {}).get("source", source)
            self.relation("qualifier_scope", {"type": key, "text": literal}, endpoint, origin)
            self.data["relations"][-1]["fact_id"] = item["id"]
            self.data["relations"][-1]["binding_evidence"] = {
                "statement_source": copy.deepcopy(source), "qualifier_source": copy.deepcopy(origin)}
        return item

    def ingest(self, result: dict[str, Any], *, compact: bool = False, logical_prose: bool = False, toc: bool = False,
               series: bool = False,
               record_source: dict[str, Any] | None = None) -> None:
        imported_facts = []
        fact_ids = {}
        self.data.setdefault("pending_requirements", []).extend(copy.deepcopy(result.get("pending_requirements", [])))
        for blocker in result.get("blockers", []):
            self.data["blockers"].append(copy.deepcopy(blocker))
        for original_fact in result.get("facts", []):
            fact = copy.deepcopy(original_fact) if series else original_fact
            if series:
                proof = self.qualifier_evidence.get("unit", {})
                sources = fact.get("source", {}).get("qualifier_sources", {})
                unit = fact.get("qualifiers", {}).get("unit")
                if (unit and proof.get("level") == "caption_shared" and unit == proof.get("text")
                        and sources.get("unit") == proof.get("source")
                        and not unit_applicable(unit, [fact["attribute"]])):
                    application = "shared_amount_role_does_not_qualify_this_non_amount_field"
                    rejected = {**copy.deepcopy(proof), "application": application, "status": "not_applied"}
                    fact["qualifiers"].pop("unit")
                    fact.setdefault("qualifier_provenance", {})["unit"] = rejected
                    printed = read_unit_token(unit, proof["source"])
                    if (printed["currency"] and fact["qualifiers"].get("currency") == printed["currency"]
                            and sources.get("currency") == printed["sources"].get("currency")):
                        fact["qualifiers"].pop("currency")
                        fact["qualifier_provenance"]["currency"] = {
                            "text": printed["currency"], "source": copy.deepcopy(sources["currency"]),
                            "level": "caption_shared", "derived_from": "unit", "application": application,
                            "status": "not_applied"}
            facets = copy.deepcopy(fact.get("identity_facets", {}))
            if compact and self.headings and "group" not in facets:
                facets["group"] = self.headings[-1]
            first_edge = len(self.data["relations"])
            qualifier_sources = {key: proof["source"] for key, proof in fact.get("qualifier_provenance", {}).items()
                                 if isinstance(proof, dict) and isinstance(proof.get("source"), dict)}
            qualifier_sources.update(fact.get("source", {}).get("qualifier_sources", {}))
            qualifier_sources.update(fact.get("qualifier_sources", {}))
            item = self.fact(fact["attribute"], fact["value"], fact["source"],
                             subject=fact["subject"], qualifiers=fact.get("qualifiers", {}),
                             identity=fact.get("role") == "identity", role=fact.get("role", "metric"),
                             identity_facets=facets, inherit_qualifiers=False,
                             scope=fact.get("scope"),
                             measurement_source=fact.get("value_source") if "raw_value" not in fact else None,
                             qualifier_sources=qualifier_sources,
                             record_id=fact.get("record_id") or (self.open_record(record_source) if record_source else None))
            imported_facts.append(item)
            if fact.get("id"):
                fact_ids[fact["id"]] = item["id"]
            if logical_prose or toc:
                additional = [edge for edge in self.data["relations"][first_edge:] if logical_prose
                              and edge["type"] == "qualifier_scope" and edge["left"]["type"] not in fact.get("qualifiers", {})]
                del self.data["relations"][first_edge:]
                for edge in additional:
                    edge["id"] = f"L:{len(self.data['relations'])}"
                    self.data["relations"].append(edge)
            for key in ("header_evidence", "row_evidence", "data_evidence", "row_path", "column_path", "raw_value", "role_basis", "issue_ids", "ambiguous_qualifiers", "qualifier_compositions", "qualifier_provenance"):
                if key in fact:
                    item[key] = ({**item.get(key, {}), **copy.deepcopy(fact[key])}
                                 if key == "qualifier_provenance" else copy.deepcopy(fact[key]))
            for key in ("logic", "qualifier_sources", "value_source", "attribute_source", "subject_source", "predicate", "object", "predicate_source", "object_source", "rule_id", "printed_label", "label_source",
                        "semantic_type", "semantic_role", "directory_evidence", "field_label_evidence", "record_evidence", "quoted_nominals", "subject_binding_evidence",
                        "statement_source", "subject_phrase", "object_phrase", "prepositional_complements", "compact_column", "value_logic"):
                if key in fact:
                    if key == "value_source" and item["value"] != fact["value"]:
                        continue
                    item[key] = copy.deepcopy(fact[key])
            data = fact.get("data_evidence", {})
            for edge in self.data["relations"][first_edge:]:
                edge.update(object_anchor=data.get("native_id"),
                            header_anchors=[h["native_id"] for h in fact.get("header_evidence", []) if h.get("native_id")],
                            row_anchors=[h["native_id"] for h in fact.get("row_evidence", []) if h.get("native_id")],
                            binding_evidence={**edge.get("binding_evidence", {}), "data": copy.deepcopy(data), "headers": copy.deepcopy(fact.get("header_evidence", [])),
                                              "rows": copy.deepcopy(fact.get("row_evidence", []))})
        if logical_prose or toc or result.get('record_composition'):
            for edge in result["relations"]:
                copied = {**copy.deepcopy(edge), "id": f"L:{len(self.data['relations'])}"}
                if copied.get("fact_id") in fact_ids:
                    copied["fact_id"] = fact_ids[copied["fact_id"]]
                elif copied["type"] == "field_binding":
                    # A reader's local IDs are not global graph identities. In
                    # readers without IDs, exact role origins identify a fact;
                    # repeated words or a shared S/P endpoint alone do not.
                    binding = copied.get("binding_evidence", {})
                    matches = [fact for fact in imported_facts
                               if all(binding.get(name) == fact.get(name) for name in
                                      ("subject_source", "predicate_source", "object_source"))
                               and binding.get("statement_source") == fact.get("statement_source", fact["source"])
                               and all(copied.get("right", {}).get(name) == fact.get(name)
                                       for name in ("subject", "attribute"))]
                    if len(matches) == 1:
                        copied["fact_id"] = matches[0]["id"]
                self.data["relations"].append(copied)
        self.data.setdefault("candidate_issues", []).extend(copy.deepcopy(result.get("issues", [])))

    def toc(self, result: dict[str, Any]) -> set[str]:
        if not result["matched"]:
            return set()
        for fact in result["facts"]:
            fact["scope"] = []  # Navigation identity is its own title/parent path.
        self.ingest(result, toc=True)
        self.text_projections.append(project_toc_text(result))
        self.data["toc_evidence"] = {key: copy.deepcopy(result[key]) for key in
                                      ("entries", "unresolved", "handled_block_ids")}
        return set(result["handled_block_ids"])

    def compact_projection(self, result: dict[str, Any], text: str, source: dict[str, Any]) -> None:
        if result.get("text_projection_complete"):
            projection = project_compact_text(result, self.compact_schema, source, raw_text=text)
            for atom in projection["atoms"]:
                atom.update(continuity_segment=self.continuity_segment, scope=list(self.headings))
            self.text_projections.append(projection)
        else:
            self.literal(text, source)
            self.block("compact_text_projection_incomplete", source, layers=["T"])

    def narrative(self, result: dict[str, Any], source: dict[str, Any]) -> None:
        self.ingest(result, logical_prose=True, record_source=source)
        self.data.setdefault("logical_statements", []).extend(copy.deepcopy(result["logic"]))
        operands = self.data.setdefault("semantic_operands", [])
        imported = copy.deepcopy(result.get("semantic_operands", []))
        identities = {item["id"]: f"operand:{len(operands) + index}" for index, item in enumerate(imported)}
        for item in imported:
            item["id"] = identities[item["id"]]
        operands.extend(imported)
        edges = copy.deepcopy(result.get("semantic_operand_relations", []))
        for edge in edges:
            if edge.get("fact_id") in identities:
                edge["fact_id"] = identities[edge["fact_id"]]
        self.data.setdefault("semantic_operand_relations", []).extend(edges)
        self.data["required_matcher_features"] = sorted(set(self.data.get("required_matcher_features", []))
            | set(result.get("required_matcher_features", [])))

    def prose(self, text: str, source: dict[str, Any], kind: str = "text", parents: list[str] | None = None,
              parent_evidence: list[dict[str, Any]] | None = None,
              syntax_evidence: dict[str, Any] | None = None) -> None:
        syntax_evidence = copy.deepcopy(syntax_evidence or {})
        if syntax_evidence.get("kind", kind) in {"item", "list_item"} and "item_source" not in syntax_evidence:
            syntax_evidence["item_source"] = copy.deepcopy(source)
            syntax_evidence["item_text"] = text
        if kind not in {"heading", "parent_label", "image", "image_caption", "table_caption"}:
            plan = plan_mixed_source(text, source)
            if plan:
                self.data.setdefault("source_interpretation_plans", []).append({"source": copy.deepcopy(source), **plan})
                self.text_projections.append({"atoms": [], "controls": plan["controls"], "complete": True})
                for fragment in plan["fragments"]:
                    self.prose(fragment["text"], fragment["source"], kind, parents, parent_evidence, syntax_evidence)
                return
        if kind == "heading":
            self.clear_heading_state()
        if kind in {"heading", "table", "image", "picture", "figure", "unknown", "table_caption"}:
            self.continuity_segment += 1
        self.data["syntax"].append({"kind": kind, "text": text, "source": source,
                                    "scope": list(self.headings), "parents": list(parents or []),
                                    "parent_evidence": copy.deepcopy(parent_evidence or []),
                                    "syntax_evidence": copy.deepcopy(syntax_evidence or {})})
        if kind == 'heading' and self.heading_stack and self.heading_stack[-1][1] == text:
            self.data['syntax'][-1]['heading_level'] = self.heading_stack[-1][0]
        declaration = read_enumeration_intro(text, source, scope=self.headings) if kind not in {
            "heading", "image", "image_caption", "table_caption"} else {"matched": False}
        if declaration["matched"]:
            self.unresolved_unit_boundary(text, source, kind, list(parents or []))
            self.qualifiers, self.qualifier_levels, self.qualifier_evidence = {}, {}, {}
            self.compact_schema, self.series_context = None, None
            self.subject, self.identity_facets, self.record_id = "", {}, None
            self.data["syntax"][-1].update(semantic_role="enumeration_declaration", enumeration_declaration=declaration)
            self.literal(text, source)
            return
        summary = read_financial_summary_intro(text, source, scope=self.headings) if kind == 'text' else None
        if summary:
            self.literal(summary['prefix'], summary['prefix_source'])
            start = summary['cue_source']['text_span'][0] - source.get('text_span', [0])[0]
            self.literal(text[start:], summary['cue_source'], 'label')
            self.narrative(summary['reading'], summary['prefix_source'])
            self.data['syntax'][-1]['semantic_propositions_complete'] = True
            return
        if re.fullmatch(r'.+(?:項目|项目|數據|数据|情況|情况|金額|金额|表)(?:(?:單位|单位)\s*[:：]\s*){1,3}.+', text):
            context = read_series_context(text, source, scope=self.headings)
            if context.get('caption'):
                self.series_context = context
                self.compact_schema = None
                self.ingest(context)
                self.compact_projection(context, text, source)
                self.data['syntax'][-1].update(semantic_role='qualifier_declaration', qualifier_caption=copy.deepcopy(context))
                for key, value in context['qualifiers'].items():
                    self.qualifiers[key] = value
                    self.qualifier_levels[key] = 'caption_shared'
                    self.qualifier_evidence[key] = {'text': value, 'source': copy.deepcopy(context['qualifier_sources'][key]), 'level': 'caption_shared'}
                return
        body = plan_field_body(text, source) if kind not in {"heading", "parent_label", "image", "image_caption", "table_caption"} else None
        if body:
            self.end_financial_unit_scope(text, source, kind, list(parents or []))
            self.literal(body["label"], body["label_source"], "label")
            self.data["syntax"].append({"kind": "field_body", "text": body["body"], "source": body["body_source"],
                "scope": list(self.headings), "parents": list(parents or []),
                "parent_evidence": copy.deepcopy(parent_evidence or []),
                "syntax_evidence": copy.deepcopy(syntax_evidence or {}),
                "printed_label": body["label"], "label_source": copy.deepcopy(body["label_source"])})
            self.literal(body["body"], body["body_source"])
            self.text_projections.append({"atoms": [], "complete": True, "controls": body["controls"]})
            return
        identity = next((fact for fact in reversed(self.data["business"])
                         if fact["role"] == "identity" and fact["value"] == self.subject), None)
        record_parents = []
        for depth, parent in enumerate(parents or []):
            declared = next((p for p in parent_evidence or [] if p['text'] == parent), None)
            candidates = [p for p in self.data['syntax'][:-1] if p['text'] == parent and p.get('kind') == 'parent_label'
                          and p.get('parents', []) == list(parents or [])[:depth] and p.get('scope') == self.headings]
            if declared:
                candidates = [p for p in candidates if self.source_key(p['source']) == self.source_key(declared['source'])]
            else:
                candidates = [p for p in candidates if p.get('syntax_evidence', {}).get('list_span')
                              and p['syntax_evidence']['list_span'] == syntax_evidence.get('list_span')
                              and p['syntax_evidence'].get('list_stream') == syntax_evidence.get('list_stream')]
            record_parents.append({'text': parent, 'source': copy.deepcopy(candidates[-1]['source'])} if candidates else parent)
        record = (read_labelled_record(text, source, scope=self.headings, parents=record_parents,
            qualifiers=self.qualifiers, qualifier_sources={k: p['source'] for k, p in self.qualifier_evidence.items()})
                  if self.compact_schema is None else {'matched': False})
        if record['matched']:
            self.ingest(record, series=True, record_source=source)
            projection = project_header_path_text(record)
            for atom in projection['atoms']:
                atom.update(continuity_segment=self.continuity_segment, scope=list(self.headings))
            self.text_projections.append(projection)
            self.data['syntax'][-1]['semantic_role'] = 'labelled_data_record'
            return
        field_sequence = read_field_sequence_requirements(text, source, scope=self.headings,
            subject=self.subject, subject_source=identity.get("source") if identity else None,
            qualifiers=self.qualifiers, qualifier_sources={key: proof["source"] for key, proof in self.qualifier_evidence.items()},
            identity_facets=self.identity_facets, record_id=self.record_id)
        if field_sequence["matched"]:
            self.ingest(field_sequence, record_source=source)
            projection = project_header_path_text(field_sequence)
            for atom in projection["atoms"]:
                atom.update(continuity_segment=self.continuity_segment, scope=list(self.headings))
            self.text_projections.append(projection)
            return
        if re.search(r"续表|續表|\btable\s+continued\b|\bcontinued\s+table\b", text, re.I):
            self.block("cross_page_relation_interpretation_unsupported", source, text=text)
        financial_parents = []
        for parent in parents or []:
            declared = next((item for item in parent_evidence or [] if item["text"] == parent), None)
            actual = next((item for item in reversed(self.data["syntax"][:-1]) if item["text"] == parent
                           and (declared is None or self.source_key(item["source"]) == self.source_key(declared["source"]))), None)
            financial_parents.append({"text": parent, "source": copy.deepcopy(actual["source"]),
                "financial_group_context": copy.deepcopy(actual.get("financial_group_context"))} if actual else {"text": parent})
        financial_context = read_financial_group_context(text, source, kind=kind,
            heading=self.financial_heading(), parents=financial_parents, unit=self.qualifier_evidence.get("unit"))
        if kind == "parent_label" and financial_context["matched"]:
            self.data["syntax"][-1].update(semantic_role="financial_statement_classification",
                                           financial_group_context=copy.deepcopy(financial_context))
            self.data.setdefault("financial_group_contexts", []).append(copy.deepcopy(financial_context))
            self.literal(text, source, "locator")
            return
        for parent in parents or []:
            parent_pairs = _pairs(parent)
            if not financial_context["matched"] and (not parent_pairs or any(not (IDENTITY.fullmatch(key) or QUALIFIER.fullmatch(key))
                                       for key, _ in parent_pairs)):
                actual = next((item for item in reversed(self.data["syntax"][:-1]) if item["text"] == parent), None)
                self.block("list_group_scope_interpretation_unsupported", source, parent=parent,
                           parent_source=copy.deepcopy(actual["source"]) if actual else None)
        schema = read_compact_schema(text, source, qualifiers=self.qualifiers)
        if schema["matched"]:
            self.compact_schema = schema.get("schema")
            if self.compact_schema:
                self.data.setdefault("compact_schemas", []).append({"text": text, "schema": copy.deepcopy(self.compact_schema)})
                if "compact_column_binding" not in self.data.setdefault("required_matcher_features", []):
                    self.data["required_matcher_features"].append("compact_column_binding")
            self.ingest(schema)
            self.compact_projection(schema, text, source)
            return
        header_path = read_header_path_requirements(text, source, scope=self.headings)
        if header_path["matched"]:
            self.ingest(header_path, record_source=source)
            projection = project_header_path_text(header_path)
            for atom in projection["atoms"]:
                atom.update(continuity_segment=self.continuity_segment, scope=list(self.headings))
            self.text_projections.append(projection)
            return
        pairs = _pairs(text)
        preambles = [key for key, _value in pairs if not (IDENTITY.fullmatch(key) or QUALIFIER.fullmatch(key))
                     and CLAUSAL_LABEL.search(key)]
        if preambles:
            # A declarative clause before a colon is itself asserted content,
            # not an answer-bearing field name for a later supported clause.
            self.literal(text, source)
            self.data["syntax"][-1]["unresolved_prose_preamble"] = True
            self.block("business_preamble_interpretation_unsupported", source, text=text, layers=["L", "B"],
                       policy="preamble_and_enumeration_require_interpretation_not_retrieval_identity")
            self.data.setdefault("pending_requirements", []).append({"text": text, "source": copy.deepcopy(source),
                "reason": "business_preamble_interpretation_unsupported"})
            return
        if (re.match(r"^(?:截至|於|于|(?:19|20)\d{2}年|(?:金[額额])?(?:單位|单位)|Units?|本年\s*[:：]|上年\s*[:：])", text, re.I)
                and not (pairs and all(QUALIFIER.fullmatch(key) for key, _ in pairs))):
            context = read_series_context(text, source, scope=self.headings)
            if context["matched"]:
                self.series_context = context
                self.compact_schema = None
                self.ingest(context)
                self.compact_projection(context, text, source)
                for key, value in context["qualifiers"].items():
                    self.qualifiers[key] = value
                    self.qualifier_levels[key] = "caption_shared"
                    self.qualifier_evidence[key] = {"text": value, "source": copy.deepcopy(context["qualifier_sources"][key]),
                                                    "level": "caption_shared"}
                return
        if not pairs and kind != "parent_label":
            self.end_financial_unit_scope(text, source, kind, list(parents or []))
        if self.compact_schema and kind == "parent_label" and not _pairs(text):
            self.open_record(source)
            self.literal(text, source, "locator")
            return
        parent_declarations = []
        for parent in parents or []:
            actual = next((item for item in reversed(self.data["syntax"][:-1]) if item["text"] == parent), None)
            parent_declarations.append({"text": parent, "source": copy.deepcopy(actual["source"])} if actual else parent)
        compact = read_compact_requirements(text, source, schema=self.compact_schema,
                                            parents=parent_declarations, subject=self.subject,
                                            qualifiers=self.qualifiers, identity_facets=self.identity_facets)
        if (not compact["facts"] and self.compact_schema is None
                and not (pairs and all(QUALIFIER.fullmatch(key) or IDENTITY.fullmatch(key) for key, _ in pairs))):
            series = read_series_requirements(text, source, context=self.series_context, subject=self.subject,
                parents=parents or [], parent_declarations=parent_declarations,
                subject_source=identity.get("source") if identity else None, qualifiers=self.qualifiers,
                qualifier_sources={key: proof["source"] for key, proof in self.qualifier_evidence.items()},
                identity_facets=self.identity_facets, scope=self.headings)
            if series["matched"] and (series["facts"] or not compact["matched"]):
                if series.get("series_membership"):
                    parent = series["series_membership"]["parent"]
                    self.data["blockers"] = [issue for issue in self.data["blockers"] if not (
                        issue.get("reason") == "list_group_scope_interpretation_unsupported" and issue.get("source") == source
                        and issue.get("parent_source") == parent["source"])]
                attribution_context = read_financial_attribution_context(series, heading=self.financial_heading(),
                    syntax=self.data["syntax"], pending=self.data.get("pending_requirements", []), parents=financial_parents)
                if attribution_context["matched"]:
                    unit_proof = attribution_context["unit"]
                    self.qualifiers["unit"] = unit_proof["text"]
                    self.qualifier_levels["unit"] = "caption_shared"
                    self.qualifier_evidence["unit"] = copy.deepcopy(unit_proof)
                    restored_context = attribution_context.get('series_context')
                    if restored_context:
                        self.series_context = restored_context
                        for key, value in restored_context['qualifiers'].items():
                            self.qualifiers[key] = value
                            self.qualifier_levels[key] = 'caption_shared'
                            self.qualifier_evidence[key] = {'text': value, 'source': copy.deepcopy(restored_context['qualifier_sources'][key]),
                                                            'level': 'caption_shared'}
                    series = read_series_requirements(text, source, context=self.series_context, subject=self.subject,
                        parents=parents or [], parent_declarations=parent_declarations,
                        subject_source=identity.get("source") if identity else None, qualifiers=self.qualifiers,
                        qualifier_sources={key: proof["source"] for key, proof in self.qualifier_evidence.items()},
                        identity_facets=self.identity_facets, scope=self.headings)
                    for collection in ("blockers", "pending_requirements"):
                        self.data[collection] = [issue for issue in self.data.get(collection, []) if not (
                            issue.get("reason") == "unit_scope_boundary_unresolved"
                            and issue.get("boundary") == attribution_context["boundary"]
                            and issue.get("source") == attribution_context["pending_source"])]
                    self.data.setdefault("financial_attribution_contexts", []).append(copy.deepcopy(attribution_context))
                    financial_context = attribution_context["outer_group_context"]
                    if financial_context["matched"]:
                        proven_parents = {self.source_key(row["source"]) for row in financial_context["row_evidence"]}
                        bound_sources = {self.source_key(source), self.source_key(attribution_context["boundary"]["source"])}
                        self.data["blockers"] = [issue for issue in self.data["blockers"] if not (
                            issue.get("reason") == "list_group_scope_interpretation_unsupported"
                            and self.source_key(issue.get("source", {})) in bound_sources
                            and self.source_key(issue.get("parent_source") or {}) in proven_parents)]
                bind_financial_group_facts(series, financial_context)
                self.ingest(series, series=True, record_source=source)
                if series.get("parent_bindings"):
                    for binding in series["parent_bindings"]:
                        parent = binding["parent"]
                        parent_key = self.source_key(parent["source"])
                        self.data["text"] = [atom for atom in self.data["text"] if not (
                            self.source_key(atom["source"]) == parent_key
                            and atom["text"].rstrip(":：").strip() == parent["text"])]
                        for syntax in self.data["syntax"]:
                            if self.source_key(syntax["source"]) == parent_key and syntax["text"].rstrip(":：").strip() == parent["text"]:
                                syntax["semantic_role"] = "metric_declaration"
                        self.data["blockers"] = [issue for issue in self.data["blockers"] if not (
                            issue["reason"] == "list_group_scope_interpretation_unsupported" and issue.get("parent_source")
                            and self.source_key(issue["parent_source"]) == parent_key)]
                    projection = project_header_path_text(series)
                    for atom in projection["atoms"]:
                        atom.update(continuity_segment=self.continuity_segment, scope=list(self.headings))
                    self.text_projections.append(projection)
                    self.data.setdefault("parent_bindings", []).extend(copy.deepcopy(series["parent_bindings"]))
                else:
                    self.compact_projection(series, text, source)
                return
        if compact["matched"]:
            for declaration in compact.get("metric_declarations", []):
                parent_key = self.source_key(declaration["parent_source"])
                self.data["text"] = [atom for atom in self.data["text"] if self.source_key(atom["source"]) != parent_key]
                removed = {fact["id"] for fact in self.data["business"] if self.source_key(fact["source"]) == parent_key
                           and re.fullmatch(r"Metric|指标|指標", fact["attribute"], re.I)}
                self.data["business"] = [fact for fact in self.data["business"] if fact["id"] not in removed]
                self.data["relations"] = [edge for edge in self.data["relations"] if edge.get("fact_id") not in removed]
                self.data["blockers"] = [blocker for blocker in self.data["blockers"] if not (
                    blocker["reason"] == "list_group_scope_interpretation_unsupported"
                    and blocker.get("parent_source") and self.source_key(blocker["parent_source"]) == parent_key)]
                self.text_projections.append(project_metric_declaration(declaration))
                for item in self.data["syntax"]:
                    if self.source_key(item["source"]) == parent_key:
                        item["semantic_role"] = "metric_declaration"
            # Only actual parent declarations consumed by the record grammar
            # establish roles. An unmatched or source-less parent stays pending.
            parent_proofs = [*compact.get("scope", {}).get("labels", []),
                             *compact.get("scope", {}).get("evidence", []),
                             *(proof for fact in compact.get("facts", []) for proof in fact.get("row_evidence", []))]
            proven_sources = {self.source_key(proof["source"]) for proof in parent_proofs
                              if proof.get("source") and proof["source"].get("location") != "declared_parent_text"}
            self.data["blockers"] = [blocker for blocker in self.data["blockers"] if not (
                compact.get("facts") and blocker["reason"] == "list_group_scope_interpretation_unsupported"
                and blocker.get("parent_source") and self.source_key(blocker["parent_source"]) in proven_sources)]
            record_source = compact.get("record_source", source)
            for parent in reversed(parents or []) if not compact.get("record_source") else []:
                if QUALIFIER.fullmatch(parent.split(":", 1)[0].strip()):
                    continue
                matching = [item for item in self.data["syntax"][:-1] if item["text"] == parent]
                if matching:
                    record_source = matching[-1]["source"]
                    break
            self.ingest(compact, compact=True, record_source=record_source)
            self.compact_projection(compact, text, source)
            return
        compound_series = _compound_metric_series(text, source)
        if compound_series is not None:
            self.literal(text, source)
            self.data["syntax"][-1]["unresolved_business_prose"] = True
            self.data["blockers"].append(copy.deepcopy(compound_series))
            self.data.setdefault("pending_requirements", []).append(compound_series)
            return
        pairs = _pairs(text)
        if not pairs and UNBOUND_NUMBERS.fullmatch(text):
            self.literal(text, source, "unbound_numeric")
            self.data.setdefault("candidate_issues", []).append({"category": "unadjudicated_extra_content",
                "reason": "unbound_numeric_text", "text": text, "source": copy.deepcopy(source),
                "evidence": "printed_numbers_without_a_declared_attribute_or_data_binding"})
            return
        if kind not in {"heading", "parent_label"}:
            entity = read_entity_requirements(text, source, scope=self.headings, parents=parents or [])
            if entity["matched"]:
                self.literal(text, source)
                return
        if kind not in {"heading", "parent_label"} and not (pairs and all(QUALIFIER.fullmatch(key) for key, _ in pairs)):
            label = pairs[0][0] if len(pairs) == 1 and not IDENTITY.fullmatch(pairs[0][0]) else None
            logical = read_prose_requirements(text, source, label=label, parents=parents or [], scope=self.headings)
            if logical["matched"]:
                if label and re.match(r"\s*" + re.escape(label) + r"\s*[:：]", text):
                    key, body, key_source, body_source = _pair_sources(text, source)[0]
                    self.literal(key, key_source, "label")
                    self.literal(body, body_source)
                    start, end = key_source["text_span"][1], body_source["text_span"][0]
                    self.text_projections.append({"atoms": [], "complete": True, "controls": [{
                        "text": text[start:end], "source": {**copy.deepcopy(source), "text_span": [start, end]},
                        "reason": "explicit_field_delimiter"}]})
                else:
                    self.literal(text, source)
                # Splitting this paragraph into literal sentences later must
                # not discard an asserted clause the full reader could not
                # interpret beside a supported modal statement.
                for blocker in logical["blockers"]:
                    if blocker["reason"] == "prose_clause_semantics_unsupported":
                        self.data["blockers"].append(copy.deepcopy(blocker))
                        self.data.setdefault("pending_requirements", []).append(copy.deepcopy(blocker))
                # Interpret once after legitimate source fragments have been
                # read continuously, so a native block boundary cannot drop
                # the subject, modal, condition or exception from B.
                return
        opaque = [(key, value) for key, value in pairs if not (IDENTITY.fullmatch(key) or QUALIFIER.fullmatch(key))
                  and (re.search(r"[。！？!?]", key) or LOGICAL.search(value))]
        if opaque:
            self.literal(text, source)
            self.block("business_clause_interpretation_unsupported", source, text=text, layers=["B"],
                       candidate_field_labels=[key for key, _ in opaque],
                       policy="unread_assertions_cannot_be_retrieval_labels_or_one_opaque_metric")
            self.data.setdefault("pending_requirements", []).append({"text": text, "source": copy.deepcopy(source),
                                                                     "reason": "business_clause_interpretation_unsupported"})
            return
        if not pairs:
            self.unresolved_unit_boundary(text, source, kind, list(parents or []))
            self.qualifiers = {}
            self.qualifier_levels = {}
            self.qualifier_evidence = {}
            self.series_context = None
        if pairs and not all(is_ordinary_scalar_field(key, value) for key, value in pairs) and (re.search(r"(?:19|20)\d{2}年[^;；]*[、][^;；]*[;；]", text)
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
                        self.declare_qualifier(_qualifier_key(key), value, source, record=bool(self.subject))
            # Qualifiers in a record apply to its independent sibling facts,
            # regardless of serialization order.
            pair_sources = _pair_sources(text, source)
            for key, value, _key_source, value_source in pair_sources:
                if QUALIFIER.fullmatch(key):
                    self.declare_qualifier(_qualifier_key(key), value, value_source,
                                          record=bool(self.subject) or any(not QUALIFIER.fullmatch(k) for k, _ in pairs))
            for key, value, key_source, value_source in pair_sources:
                header = read_measurement_label(key, key_source)
                if not value:
                    # An empty field is an actual printed label, not a
                    # key/value serialization. Keep its terminal delimiter in
                    # T; it cannot disappear merely because PAIR matched it.
                    offset = source.get("text_span", [0])[0]
                    start, end = key_source["text_span"][0], value_source["text_span"][0]
                    self.literal(text[start - offset:end - offset],
                                 {**copy.deepcopy(key_source), "text_span": [start, end]}, "label")
                elif not IDENTITY.fullmatch(key) and header["matched"]:
                    self.literal(header["label"], header["sources"]["label"], "label")
                    self.literal(header["unit"], header["sources"]["unit"], "unit")
                else:
                    self.literal(key, key_source, "label")
                unit_declaration = _printed_unit_declaration(value, value_source) if QUALIFIER.fullmatch(key) and _qualifier_key(key) == "unit" else None
                measurement = read_measurement_literal(value, value_source)
                if unit_declaration and unit_declaration["matched"]:
                    self.literal(unit_declaration["unit"], unit_declaration["sources"]["unit"], "value")
                    if unit_declaration["controls"]:
                        self.text_projections.append({"atoms": [], "controls": unit_declaration["controls"], "complete": True})
                elif not IDENTITY.fullmatch(key) and measurement["matched"] and measurement["unit"]:
                    self.literal(measurement["value"], measurement["sources"]["value"], "value")
                    self.literal(measurement["unit"], measurement["sources"]["unit"], "unit")
                elif value:
                    self.literal(value, value_source, "value")
                if QUALIFIER.fullmatch(key):
                    pass  # The source-bound declaration above already stored its complete token.
                elif value:
                    facets = copy.deepcopy(self.identity_facets)
                    if financial_context["matched"]:
                        facets["group"] = copy.deepcopy(financial_context["group_path"])
                    fact = self.fact(key, value, value_source, attribute_source=key_source, identity_facets=facets)
                    if financial_context["matched"]:
                        if fact["role"] == "identity":
                            binding: dict[str, Any] = {"facts": [fact]}
                            bind_financial_group_facts(binding, financial_context)
                            self.data["blockers"].extend(binding.get("blockers", []))
                            self.data.setdefault("pending_requirements", []).extend(binding.get("pending_requirements", []))
                        else:
                            fact["row_evidence"] = copy.deepcopy(financial_context["row_evidence"])
                            fact["role_basis"] = {"financial_group_context": copy.deepcopy(financial_context)}
                elif kind != "parent_label":
                    # A colon alone is a scope label, not an empty fact.
                    pass
            return
        self.literal(text, source, "heading" if kind == "heading" else "literal")
        if kind == "heading" and len(self.headings) > 1:
            self.relation("heading_parent", self.headings[-2], self.headings[-1], source)
            self.data["relations"][-1]["required_scope"] = list(self.headings)
        # Prose is interpreted after legal source fragments are joined. Its
        # business disposition must not depend on a keyword or digit hit.
        if parents:
            # Numeric sibling properties never become parent properties.
            labels = [p for p in parents if not _pairs(p) or any(IDENTITY.fullmatch(k) for k, _ in _pairs(p))]
            if labels:
                self.relation("list_membership", labels[-1], {"text": text}, source)

    def table(self, cells: list[dict[str, Any]], source: dict[str, Any]) -> None:
        self.continuity_segment += 1
        result = read_matrix(cells, source=source, context=tuple(self.qualifier_evidence.values()))
        self.ingest(result)
        projection = project_table_text(cells, result, source)
        for atom in projection["atoms"]:
            atom.update(continuity_segment=self.continuity_segment, scope=list(self.headings))
        self.text_projections.append(projection)



def _finish(graph: _Graph) -> dict[str, Any]:
    # A complete neighboring record cannot satisfy the declared slots of a
    # partial split record. Record identity follows its own actual locator.
    for declaration in graph.data.get("compact_schemas", []):
        schema = declaration["schema"]
        records = {}
        for fact in graph.data["business"]:
            binding = fact.get("compact_column", {})
            if binding.get("schema_source") == schema["source"]:
                records.setdefault((fact["record_id"], fact["subject"]), []).append(fact)
        for members in records.values():
            missing = [c for c in schema["columns"] if c["id"] not in {f["compact_column"]["id"] for f in members}]
            if missing:
                graph.block("compact_declared_columns_missing", members[0]["source"],
                            layers=["B", "L"], columns=copy.deepcopy(missing), record_id=members[0]["record_id"])
    enumerations = plan_from_syntax(graph.data["syntax"])
    graph.data["blockers"].extend(copy.deepcopy(enumerations["blockers"]))
    graph.data.setdefault("pending_requirements", []).extend(copy.deepcopy(enumerations["pending_requirements"]))
    # A shared monetary declaration inside an explicitly mixed record limits
    # its amount fields. An isolated unusual explicit field/record unit is
    # retained verbatim; generic type expectations cannot correct it.
    amount_records = {fact["record_id"] for fact in graph.data["business"] if is_amount_role(fact["attribute"])}
    removed = set()
    for fact in graph.data["business"]:
        unit = fact["qualifiers"].get("unit")
        proof = fact.get("qualifier_provenance", {}).get("unit", {})
        if (fact["record_id"] in amount_records and unit and unit_kind(unit) == "money"
                and proof.get("level") == "record_explicit" and not unit_applicable(unit, [fact["attribute"]])):
            fact["qualifiers"].pop("unit")
            if fact.get("qualifier_provenance", {}).get("currency", {}).get("derived_from") == "unit":
                fact["qualifiers"].pop("currency", None)
                fact["qualifier_provenance"]["currency"].update(
                    application="shared_amount_role_does_not_qualify_this_non_amount_field", status="not_applied")
            proof["application"] = "shared_amount_role_does_not_qualify_this_non_amount_field"
            proof["status"] = "not_applied"
            removed.add(fact["id"])
    by_fact = {fact["id"]: fact for fact in graph.data["business"]}
    graph.data["relations"] = [edge for edge in graph.data["relations"] if not
                               (edge.get("fact_id") in removed and edge["type"] == "qualifier_scope" and edge["left"]["type"]
                                not in by_fact[edge["fact_id"]]["qualifiers"])]
    for edge in graph.data["relations"]:
        if edge.get("fact_id") in removed:
            edge["right"]["qualifiers"] = copy.deepcopy(by_fact[edge["fact_id"]]["qualifiers"])
    # A trailing record Unit can backfill a previously read fact. Derive its
    # explicitly named currency only after the unit's own applicability check.
    for fact in graph.data["business"]:
        if fact["role"] == "identity" or "currency" in fact["qualifiers"]:
            continue
        proof = fact.get("qualifier_provenance", {}).get("unit", {})
        unit = read_unit_token(fact["qualifiers"].get("unit", ""), proof.get("source", fact["source"]))
        if not unit["matched"] or not unit["currency"]:
            continue
        fact["qualifiers"]["currency"] = unit["currency"]
        fact.setdefault("qualifier_provenance", {})["currency"] = {
            "text": unit["currency"], "source": unit["sources"]["currency"],
            "level": proof.get("level", "explicit_unit"), "derived_from": "unit"}
        edges = [edge for edge in graph.data["relations"] if edge.get("fact_id") == fact["id"]]
        for edge in edges:
            edge["right"]["qualifiers"]["currency"] = unit["currency"]
        if edges:
            graph.relation("qualifier_scope", {"type": "currency", "text": unit["currency"]},
                           copy.deepcopy(edges[0]["right"]), unit["sources"]["currency"])
            graph.data["relations"][-1]["fact_id"] = fact["id"]
    for index, edge in enumerate(graph.data["relations"]):
        edge["id"] = f"L:{index}"
    # Stable semantic requirements; never inferred from candidate availability.
    # Delimiter labels for qualifiers are relational syntax, while their actual
    # literals remain text. A table's schema role labels are also syntax.
    empty_context_sources = {graph.source_key(item["source"]) for item in graph.data["syntax"]
                             if re.fullmatch(r"[^:：。.!?！？;；]+[:：]", item["text"].strip())}
    graph.data["text"] = [x for x in graph.data["text"] if not
                          (x["role"] == "label" and QUALIFIER.fullmatch(x["text"])
                           and graph.source_key(x["source"]) not in empty_context_sources)]
    projection = combine_text_projections([{"atoms": graph.data["text"], "complete": True}, *graph.text_projections])
    graph.data["text"] = projection["atoms"]
    graph.data["text_projection"] = {key: copy.deepcopy(projection.get(key, [])) for key in
                                     ("origins", "aliases", "controls", "complete", "source_cells", "source_fragments")}
    fragments = graph.data["text_projection"]["source_fragments"]
    for item in graph.data["syntax"]:
        fragment = {"source": copy.deepcopy(item["source"]), "text": item["text"]}
        if item.get("semantic_role") != "toc" and fragment not in fragments:
            fragments.append(fragment)
    for blocker in projection["blockers"]:
        same = next((old for old in graph.data["blockers"] if old.get("reason") == blocker.get("reason")
                     and old.get("source") == blocker.get("source")), None)
        if same:
            same["layers"] = sorted(set(same.get("layers", ["L", "B"])) | {"T"})
        else:
            graph.data["blockers"].append({**blocker, "layers": ["T"]})
    # Read consecutive fragments of the same prose sentence in their printed
    # order. Preserve an actual word boundary. Never join numeric or field
    # atoms, and never skip intervening material.
    from .cjk_narrative_requirements import join_following_explanations

    sentence_units = []
    for item in graph.data["text"]:
        parts = [item["text"][a:b] for a, b in join_following_explanations(item['text'], _sentence_spans(item["text"]), source=item['source'])] if item["role"] == "literal" else [item["text"]]
        cursor = 0
        for i, text in enumerate(parts):
            if not text.strip():
                continue
            start = item["text"].find(text, cursor)
            cursor = start + len(text)
            source = copy.deepcopy(item["source"])
            if len(parts) > 1:
                offset = (source.get("text_span") or [0])[0]
                source["text_span"] = [offset + start, offset + cursor]
            sentence_units.append({**item, "source": source, "text": text, "id": f"{item['id']}:sentence:{i}"})
    merged = []
    for item in sentence_units:
        if (merged and merged[-1]["role"] == item["role"] == "literal"
                and merged[-1].get('syntax_kind') not in {'heading', 'image', 'image_caption', 'picture', 'figure', 'table_caption'}
                and item.get('syntax_kind') not in {'heading', 'image', 'image_caption', 'picture', 'figure', 'table_caption'}
                and merged[-1].get("list_item_source") == item.get("list_item_source")
                and merged[-1].get("continuity_segment") == item.get("continuity_segment")
                and merged[-1].get("scope") == item.get("scope")
                and not merged[-1]["source"].get("cell") and not item["source"].get("cell")
                and not re.search(r'''[。.!?！？;；:：]["”’」』）)\]]*$''', merged[-1]["text"])
                and not NUMERIC.fullmatch(merged[-1]["text"])
                and not NUMERIC.fullmatch(item["text"])):
            previous = merged[-1]
            separator = "" if re.search(r"[\u3400-\u9fff]$", previous["text"]) and re.match(r"[\u3400-\u9fff]", item["text"]) else " "
            previous["strict_text"] = previous.get("strict_text", previous["text"]) + "\n" + item.get("strict_text", item["text"])
            previous.setdefault("source_fragment_texts", [previous["text"]]).append(item.get("strict_text", item["text"]))
            previous["text"] += separator + item["text"]
            previous.setdefault("source_fragments", [previous["source"]]).append(item["source"])
        else:
            merged.append(item)
    graph.data["text"] = merged
    for item in merged:
        if item.get("enumeration_declaration"):
            continue
        if item["role"] != "literal" or item["source"].get("cell") or item.get("syntax_kind") in {
                "heading", "image", "image_caption", "picture", "figure", "table_caption"}:
            continue
        source = copy.deepcopy(item["source"])
        enumeration = member_for_source(enumerations, source)
        originals = item.get("source_fragments", [source])
        texts = item.get("source_fragment_texts", [item["text"]])
        if len(originals) > 1:
            cursor, fragments = 0, []
            for original, text in zip(originals, texts, strict=True):
                start = item["text"].find(text, cursor)
                if start < 0:
                    graph.block("prose_fragment_source_alignment_unsupported", source, layers=["B"])
                    break
                fragments.append({"source": copy.deepcopy(original), "text": text, "joined_span": [start, start + len(text)]})
                cursor = start + len(text)
            else:
                source["joined_fragments"] = fragments
        bounds = item['source'].get('text_span')
        matching = [syntax for syntax in graph.data["syntax"] if graph.source_key(syntax["source"]) == graph.source_key(item["source"])
                    and (not syntax["source"].get("text_span") or bounds and
                         syntax['source']['text_span'][0] <= bounds[0] <= bounds[1] <= syntax['source']['text_span'][1])]
        syntax = min(matching, key=lambda own: own['source']['text_span'][1] - own['source']['text_span'][0]
                     if own['source'].get('text_span') else float('inf')) if matching else None
        if syntax and syntax.get("semantic_propositions_complete"):
            item["semantic_propositions_complete"] = True
            continue
        if syntax and (syntax.get("unresolved_prose_preamble") or syntax.get("unresolved_business_prose")):
            item["unresolved_business_prose"] = True
            continue
        parent_texts = syntax.get("parents", []) if syntax else []
        parents = []
        prior = graph.data["syntax"][:graph.data["syntax"].index(syntax)] if syntax else []
        for parent in parent_texts:
            found = next((entry for entry in syntax.get("parent_evidence", []) if entry["text"] == parent), None) if syntax else None
            if found is None:
                found = next((entry for entry in reversed(prior) if entry["text"] == parent), None)
            parents.append({"text": parent, "source": copy.deepcopy(found["source"])} if found else parent)
        pairs = _pair_sources(syntax["text"], syntax["source"]) if syntax else _pair_sources(item["text"], source)
        label, label_source = (pairs[0][0], pairs[0][2]) if len(pairs) == 1 and not (
            IDENTITY.fullmatch(pairs[0][0]) or QUALIFIER.fullmatch(pairs[0][0])) else (None, None)
        if syntax and syntax.get("kind") == "field_body":
            label, label_source = syntax["printed_label"], syntax["label_source"]
        item.update(prose_label=label, prose_label_source=copy.deepcopy(label_source), prose_parents=copy.deepcopy(parents))
        # A printed reference target cannot establish its own owner or add a
        # business vote. Unread residual prose retains the ordinary fail-closed
        # route instead of being declared navigation by keyword alone.
        reference_label, reference_label_source = label, label_source
        if reference_label is None:
            bounds = source.get("text_span")
            field = next((entry for entry in reversed(graph.data["syntax"])
                          if entry.get("kind") == "field_body" and bounds
                          and graph.source_key(entry["source"]) == graph.source_key(source)
                          and entry["source"].get("text_span")
                          and entry["source"]["text_span"][0] <= bounds[0] <= bounds[1] <= entry["source"]["text_span"][1]), None)
            if field:
                reference_label, reference_label_source = field["printed_label"], field["label_source"]
        reference_owner, reference_owner_evidence = None, []
        if reference_label and reference_label_source:
            reference_owner = {"identity": {"role": "printed_field", "attribute": reference_label},
                               "scope": list(item.get("scope", []))}
            reference_owner_evidence = [{"kind": "printed_field_label", "text": reference_label,
                                         "source": copy.deepcopy(reference_label_source)}]
        elif item.get("scope"):
            heading_proofs = []
            for position, heading in enumerate(item["scope"]):
                actual = next((entry for entry in reversed(prior)
                               if entry.get("kind") == "heading" and entry["text"] == heading
                               and entry.get("scope") == item["scope"][:position + 1]), None)
                if actual is None:
                    break
                heading_proofs.append({"kind": "heading_scope", "text": heading,
                                       "source": copy.deepcopy(actual["source"])})
            if len(heading_proofs) == len(item["scope"]):
                reference_owner = {"identity": {"role": "heading_scope"}, "scope": list(item["scope"])}
                reference_owner_evidence = heading_proofs
        references = read_explicit_references(item["text"], source, scope=item.get("scope", []),
            owner=reference_owner, owner_evidence=reference_owner_evidence)
        if references["references"] and not references["residual_spans"]:
            item.update(explicit_reference_only=True, reference_owner=reference_owner,
                        reference_owner_evidence=reference_owner_evidence, semantic_propositions_complete=True)
            graph.data["blockers"] = [blocker for blocker in graph.data["blockers"] if not (
                blocker["reason"] in {"unclassified_business_prose", "logical_prose_semantics_unsupported"}
                and any(blocker["source"] == original for original in originals))]
            continue
        narrative = _read_narrative(item["text"], source, scope=item.get("scope", []))
        family_claimed = (bool({"active_aspect_scope", "temporal_prose_scope", "quantity_comparison", "year_on_year_comparison",
                               "quoted_nominal_scope", "fronted_nominal_context", "document_composition", "page_reference_binding",
                               "discourse_scope", "purpose_scope", "controlled_infinitive_scope"}
                              & set(narrative.get("required_matcher_features", []))) or any(
            issue.get("reason", "").startswith("active_aspect_") or issue.get("reason") in {
                "narrative_enumeration_operator_scope_unresolved", "narrative_quantified_comparison_scope_unresolved"}
                or issue.get("reason") == "narrative_nominal_token_boundary_unresolved"
            for issue in narrative.get("blockers", [])))
        entity = read_entity_requirements(item["text"], source, parents=parent_texts, scope=item.get("scope", []))
        if entity["matched"]:
            advanced = set(narrative.get("required_matcher_features", [])) - {"finite_tense"} if entity["blockers"] else set()
            if family_claimed or narrative["logic"] and advanced:
                graph.narrative(_bind_field_body(narrative, label, label_source), source)
                item["semantic_propositions_complete"] = narrative["complete"]
                item["unresolved_business_prose"] = not narrative["complete"]
            else:
                if syntax and syntax.get("kind") == "field_body":
                    _bind_field_body(entity, label, label_source)
                graph.ingest(entity, record_source=source)
                item["entity_assertion"] = True
            graph.data["blockers"] = [blocker for blocker in graph.data["blockers"] if not (
                blocker["reason"] in {"unclassified_business_prose", "logical_prose_semantics_unsupported"}
                and any(blocker["source"] == original for original in originals))]
            continue
        logical = read_prose_requirements(item["text"], source, label=label, label_source=label_source,
                                         parents=parents, scope=item.get("scope", []))
        if (logical["facts"] and not logical["blockers"] and "noun_phrase_composition" in narrative.get("required_matcher_features", [])
                and not (set(narrative.get("required_matcher_features", [])) & {
                    "active_aspect_scope", "temporal_prose_scope", "year_on_year_comparison", "quoted_nominal_scope",
                    "fronted_nominal_context", "document_composition", "page_reference_binding", "prepositional_attachment",
                    "discourse_scope", "purpose_scope", "controlled_infinitive_scope"})):
            family_claimed = False
        advanced = set(narrative.get("required_matcher_features", [])) - {
            "finite_tense", "coordination_scope", "modal_operator", "negation_scope", "noun_phrase_composition", "quantity_comparison"}
        prefer_narrative = narrative["complete"] and (bool(advanced) or narrative.get("syntax_language") == "zh")
        if family_claimed or not logical["facts"] or logical["blockers"] or re.search(r"\band\b", item["text"], re.I) or prefer_narrative:
            proposition = read_propositions(item["text"], source, scope=item.get("scope", []),
                subject=enumeration[1]["member_context"]["subject"] if enumeration else None)
            inherit_omitted_subject(proposition, enumeration)
            selected = (narrative if prefer_narrative or family_claimed else proposition if proposition["complete"] and (not logical["facts"] or logical["blockers"]
                        or len(proposition["facts"]) > len(logical["facts"]))
                        else narrative if narrative["logic"] and (not logical["facts"] or logical["blockers"])
                        else proposition if proposition["matched"] and (not logical["facts"] or logical["blockers"])
                        else narrative if not logical["facts"] else None)
            if selected:
                inherit_omitted_subject(selected, enumeration)
                if selected is not narrative:
                    _adopt_comparison_tree(selected, narrative)
                _bind_field_body(selected, label, label_source)
                if selected is narrative or selected.get("logic"):
                    graph.narrative(selected, source)
                else:
                    graph.ingest(selected, logical_prose=True, record_source=source)
                graph.data["required_matcher_features"] = sorted(set(graph.data.get("required_matcher_features", []))
                    | set(selected.get("required_matcher_features", [])))
                item["semantic_propositions_complete"] = bool(selected["complete"])
                item["unresolved_business_prose"] = not selected["complete"]
                reasons = {entry['reason'] for entry in selected.get('blockers', [])}
                attachment_reasons = {'cjk_causal_scope_evidence_unresolved', 'cjk_causal_attachment_declared_uncertain'}
                if reasons & attachment_reasons and reasons <= attachment_reasons | {'cjk_measurement_sequence_incomplete'}:
                    item['prose_location_supported'] = True
                if selected["complete"]:
                    _discharge_superseded_clause_pending(graph.data, item["text"], source)
                old_reasons = {"unclassified_business_prose", "logical_prose_semantics_unsupported",
                               *(entry["reason"] for entry in logical["blockers"])}
                graph.data["blockers"] = [blocker for blocker in graph.data["blockers"] if not (
                    blocker["reason"] in old_reasons
                    and any(blocker["source"] == original for original in originals))]
                continue
        if logical["matched"]:
            _adopt_comparison_tree(logical, narrative)
            _bind_field_body(logical, label, label_source)
            if logical.get("logic"):
                graph.narrative(logical, source)
            else:
                graph.ingest(logical, logical_prose=True, record_source=source)
            if narrative["complete"] and not logical["blockers"]:
                _discharge_superseded_clause_pending(graph.data, item["text"], source)
            field = next((fact.get("field_label_evidence") for fact in logical["facts"] if fact.get("field_label_evidence")), None)
            own_scope = item.get("scope", [])
            if field and own_scope and own_scope[-1] != field["text"]:
                scope = [*own_scope, field["text"]]
                if not any(edge["type"] == "heading_parent" and edge.get("required_scope") == scope for edge in graph.data["relations"]):
                    graph.relation("heading_parent", own_scope[-1], field["text"], source)
                    graph.data["relations"][-1].update(required_scope=scope, field_label_evidence=copy.deepcopy(field))
            graph.data["blockers"] = [blocker for blocker in graph.data["blockers"] if not (
                blocker["reason"] in {"unclassified_business_prose", "logical_prose_semantics_unsupported"}
                and any(blocker["source"] == original for original in originals))]
    prose_units = [{"id": item["id"], "kind": 'image_caption' if item.get('syntax_kind') == 'image_caption' else 'paragraph', "text": item["text"],
                    "source": copy.deepcopy(item["source"]), "scope": copy.deepcopy(item.get("scope", [])),
                    "label": item.get("prose_label"), "label_source": copy.deepcopy(item.get("prose_label_source")),
                    "reference_owner": copy.deepcopy(item.get("reference_owner")),
                    "reference_owner_evidence": copy.deepcopy(item.get("reference_owner_evidence", [])),
                    "parents": copy.deepcopy(item.get("prose_parents", []))}
                   for item in merged if (item["role"] == "literal" or item['role'] == 'label'
                       and re.fullmatch(r'[變变][動动化]分析[:：]', item['text'])) and not item["source"].get("cell")
                   and not item.get("enumeration_declaration")
                   and not item.get("entity_assertion")
                   and (not item.get("unresolved_business_prose") or item.get('prose_location_supported'))]
    prose = read_prose_sequence(prose_units)
    graph.data["prose_endpoints"] = prose["endpoints"]
    graph.data["explicit_references"] = copy.deepcopy(prose.get("references", []))
    graph.data["reference_roles"] = copy.deepcopy(prose.get("semantic_roles", []))
    graph.data["reference_dispositions"] = copy.deepcopy(prose.get("source_dispositions", []))
    graph.data["required_matcher_features"] = sorted(set(graph.data.get("required_matcher_features", []))
        | set(prose.get("required_matcher_features", [])))
    graph.data.setdefault("pending_requirements", []).extend(copy.deepcopy(prose.get("pending_requirements", [])))
    graph.data["blockers"].extend({**copy.deepcopy(blocker), "layers": ["L"]} for blocker in prose["blockers"])
    for edge in prose["relations"]:
        graph.data["relations"].append({**edge, "id": f"L:{len(graph.data['relations'])}"})
    bind_interpreted_members(graph.data, enumerations)
    bind_financial_summaries(graph.data)
    bind_financial_notes(graph.data)
    # Identity values are independently tested; they are not their own subject.
    for item in graph.data["business"]:
        if item["role"] == "identity" and canonical(item["value"]) == canonical(item["subject"]):
            item["subject"] = ""
    # This transient ledger detects mutation/omission between compilation and
    # grading. It is bookkeeping, not independent semantic validation.
    graph.data["requirement_ledger"] = copy.deepcopy(graph.data["business"])
    paths = {tuple(item.get("scope", [])) for item in [*graph.data["syntax"], *graph.data["business"]]
             if item.get("scope")}
    context_labels = [{"text": item["text"], "scope": copy.deepcopy(item.get("scope", [])),
                       "source": copy.deepcopy(item["source"]), "role": "printed_context_label"}
                      for item in graph.data["syntax"] if not any(char.isdigit() for char in item["text"])
                      and not _pairs(item["text"]) and (item["kind"] == "parent_label" or item["text"].endswith((":", "：")))]
    # An empty colon label is syntax, not a business fact or a numeral query.
    for item in graph.data["syntax"]:
        if (_pairs(item["text"]) and all(not value for _, value in _pairs(item["text"]))
                and not any(char.isdigit() for char in item["text"])):
            context_labels.append({"text": item["text"], "scope": copy.deepcopy(item.get("scope", [])),
                                   "source": copy.deepcopy(item["source"]), "role": "printed_context_label"})
    for item in graph.data["scope_context"]:
        if item.get("kind") != "heading" or not isinstance(item.get("text"), str):
            continue
        scopes = [syntax["scope"] for syntax in graph.data["syntax"]
                  if syntax["source"].get("path") == item.get("target_source", {}).get("path")
                  and syntax["source"].get("lines") == item.get("target_source", {}).get("lines")]
        for scope in scopes:
            context_labels.append({"text": item["text"], "scope": copy.deepcopy(scope),
                                   "source": copy.deepcopy(item.get("reference", {})), "role": "external_ancestor"})
    graph.data["scope_schema"] = {"paths": [list(path) for path in sorted(paths)], "context_labels": context_labels}
    return graph.data


def compile_markdown(markdown: str, *, sample_id: str = "synthetic",
                     selected_lines: list[tuple[int, int]] | None = None, path: str = "<markdown>") -> dict[str, Any]:
    graph = _Graph(sample_id)
    document = elements(markdown)
    syntax = [{"id": f"syntax:{index}", "kind": element.kind, "text": element.text,
               "reference": _source(path, element.lines), "cells": element.cells,
               "parents": list(element.parents), "list_span": element.list_span,
               "has_children": element.has_children, "heading_level": element.native_heading_level}
              for index, element in enumerate(document)
              if selected_lines is None or any(a <= element.lines[0] and element.lines[1] <= b for a, b in selected_lines)]
    toc_handled = graph.toc(read_toc(blocks=_toc_syntax_blocks(syntax), source={"path": path}))
    skipped_context: list[dict[str, Any]] = []
    for index, element in enumerate(document):
        source = _source(path, element.lines)
        if not _context_continues(element):
            skipped_context = [item for item in skipped_context if item["kind"] == "heading"]
        included = selected_lines is None or any(a <= element.lines[0] and element.lines[1] <= b for a, b in selected_lines)
        if not included:
            if element.kind == "heading" or any(QUALIFIER.fullmatch(k) for k, _ in _pairs(element.text)):
                skipped_context.append({"kind": "heading" if element.kind == "heading" else "qualifier",
                                        "text": element.text, "source": source})
            continue
        if skipped_context:
            dependencies = [item for item in skipped_context if item["kind"] != "heading"]
            graph.data["scope_context"].extend({"required": False, "target_source": source, **item}
                                              for item in skipped_context if item["kind"] == "heading")
            if dependencies:
                graph.block("input_scope_context", source, outside_selection=copy.deepcopy(dependencies))
            skipped_context.clear()
        if element.kind == "heading":
            level = element.native_heading_level or 1
            graph.enter_heading(element.text, level)
            graph.subject = ""
            graph.identity_facets = {}
            graph.record_start = len(graph.data["business"])
            graph.qualifiers = {}
            if f"syntax:{index}" not in toc_handled:
                graph.prose(element.text, source, "heading")
        elif f"syntax:{index}" in toc_handled:
            graph.data["syntax"].append({"kind": element.kind, "text": element.text,
                "source": {**source, "block": f"syntax:{index}"}, "scope": list(graph.headings), "semantic_role": "toc"})
        elif element.cells:
            graph.table(element.cells, source)
        else:
            graph.prose(element.text, source, "parent_label" if element.has_children else element.kind, list(element.parents),
                        syntax_evidence={"kind": element.kind, "list_span": list(element.list_span) if element.list_span else None,
                                         "list_lines": list(element.lines), "list_stream": path})
    return _finish(graph)


def compile_expected(expected: dict[str, Any]) -> dict[str, Any]:
    """Project a source-bound requirement graph, before reading candidates."""
    from .requirement_graph import (
        compile_requirement_graph,
        evaluation_projection,
        validate_requirement_graph,
    )

    if expected.get("standard") == "canonical_expected_derived_view":
        model = copy.deepcopy(expected)
    elif "business" in expected and "relations" in expected:
        return copy.deepcopy(expected)
    else:
        model = compile_requirement_graph(expected)
    validate_requirement_graph(model)
    result = evaluation_projection(model)
    result["requirement_model"] = model
    return result


def read_candidate_markdown(markdown: str, *, sample_id: str = "synthetic", pipeline: str = "test") -> dict[str, Any]:
    result = compile_markdown(markdown, sample_id=sample_id, path="<candidate-markdown>")
    result["pipeline"] = pipeline
    return result


def read_candidate(observation: dict[str, Any]) -> dict[str, Any]:
    if "business" in observation and "relations" in observation:
        return copy.deepcopy(observation)
    graph = _Graph(observation["sample_id"])
    toc_blocks = [{**block, "source": {"path": block.get("native_path", block.get("id")), "page": page.get("page"),
                                       "lines": block.get("public_lines", []), "block": block.get("id")}}
                  for page in observation.get("pages", []) for block in page.get("blocks", [])]
    toc_handled = graph.toc(read_toc(blocks=toc_blocks, source={"path": "#/candidate-toc"}))
    contexts = read_contexts(observation)
    native_blocks = {block.get("id"): (page, block) for page in observation.get("pages", []) for block in page.get("blocks", [])}
    native_paths = {block.get("native_path"): block.get("id") for _page, block in native_blocks.values() if block.get("native_path")}

    def record_parents(block):
        result, visited = [], set()
        parent = block.get("parent_id")
        while isinstance(parent, str) and parent not in visited:
            visited.add(parent)
            entry = native_blocks.get(parent) or native_blocks.get(native_paths.get(parent))
            if entry is None:
                break
            page, node = entry
            text = visible_text(node.get("text", ""), node.get("text_format", "plain"))
            pairs = _pairs(text)
            if pairs and all(IDENTITY.fullmatch(key) and value for key, value in pairs):
                result.append({"text": text, "source": {"path": node.get("native_path", node.get("id")),
                    "page": page.get("page"), "lines": node.get("public_lines", []), "block": node.get("id")}})
            parent = node.get("parent_id")
        return list(reversed(result))
    for issue in contexts["issues"]:
        if issue.get("category") == "software_unsupported":
            graph.block(issue["reason"], issue.get("source", {"path": "#/candidate-context"}))
        else:
            graph.data.setdefault("candidate_issues", []).append(copy.deepcopy(issue))
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
            if block.get("id") in toc_handled:
                if block.get("kind") in {"heading", "section_header", "title", "doc_title", "paragraph_title"}:
                    graph.enter_heading(visible_text(block.get("text", ""), block.get("text_format", "plain")),
                                        max(1, int(block.get("heading_level", block.get("level", 1)) or 1)))
                graph.continuity_segment += 1
                continue
            if block.get("cells"):
                graph.table(block["cells"], source)
            else:
                own_parents = record_parents(block)
                parent_labels = [entry["text"] for entry in own_parents]
                representation = block.get("text_format", "plain")
                text = block.get("text", "")
                kind = block.get("kind", "text")
                if representation == "markdown":
                    declared_heading = kind in {"heading", "section_header", "title", "doc_title"}
                    if declared_heading:
                        level = block.get("heading_level", block.get("level", 1)) or 1
                        graph.enter_heading(visible_text(text, representation), max(1, int(level)))
                    for element in elements(text):
                        element_source = {**source, "block_lines": list(element.lines)}
                        if element.cells:
                            graph.table(element.cells, element_source)
                        else:
                            if element.kind == "heading" and not declared_heading:
                                level = element.native_heading_level or 1
                                graph.enter_heading(element.text, level)
                            graph.prose(element.text, element_source,
                                        "heading" if declared_heading else "parent_label" if element.has_children else element.kind,
                                        [*parent_labels, *list(element.parents)], own_parents,
                                        syntax_evidence={"kind": "heading" if declared_heading else element.kind,
                                            "list_span": list(element.list_span) if element.list_span else None,
                                            "list_lines": list(element.lines), "list_stream": source["path"]})
                else:
                    if kind in {"heading", "section_header", "title", "doc_title"}:
                        level = block.get("heading_level", block.get("level", 1)) or 1
                        graph.enter_heading(visible_text(text, representation), max(1, int(level)))
                    graph.prose(visible_text(text, representation), source,
                                "heading" if kind in {"heading", "section_header", "title", "doc_title"}
                                else "parent_label" if block.get("public_has_children") else kind,
                                [*parent_labels, *block.get("public_list_parents", [])], own_parents,
                                syntax_evidence={"kind": block.get("public_syntax_kind", kind),
                                    "list_span": copy.deepcopy(block.get("public_list_span")),
                                    "list_lines": copy.deepcopy(block.get("public_lines")),
                                    "list_stream": "delivered-markdown" if "public_syntax_kind" in block else source["path"]})
    explicit_scopes = {}
    heading_by_block = {event["source"].get("block"): event for event in contexts["heading_events"]}
    for block, record in contexts["by_block"].items():
        paths = record.get("explicit_heading_paths", [])
        if len(paths) == 1 and paths[0].get("status") == "bound" and record["status"] != "ambiguous":
            path = list(paths[0]["path"])
            if block in heading_by_block:
                path.append(heading_by_block[block]["text"])
            explicit_scopes[block] = path
    for atom in [*graph.data["text"], *graph.data["syntax"],
                 *(atom for projection in graph.text_projections for atom in projection["atoms"])]:
        path = explicit_scopes.get(atom["source"].get("block"))
        if path is not None:
            atom["scope"] = list(path)
    for edge in graph.data["relations"]:
        path = explicit_scopes.get(edge["source"].get("block"))
        if path is None:
            continue
        if edge["type"] == "heading_parent" and len(path) > 1:
            edge.update(left=path[-2], right=path[-1], required_scope=list(path))
        elif isinstance(edge.get("right"), dict) and "scope" in edge["right"]:
            own = list(path)
            group = edge["right"].get("identity_facets", {}).get("group")
            if isinstance(group, str) and group and (not own or own[-1] != group):
                own.append(group)
            edge["right"]["scope"] = own
    for fact in graph.data["business"]:
        path = explicit_scopes.get(fact["source"].get("block"))
        if path is not None:
            fact["scope"] = list(path)
        record = contexts["by_block"].get(fact["source"].get("block"))
        if not record:
            continue
        # The complete reader catalogue is saved once in scope_evidence.
        # Individual hits retain their actual record identity and bounds;
        # they do not duplicate the whole heading stream for every cell.
        context_record = {key: copy.deepcopy(record.get(key)) for key in
                          ("source", "position", "segment", "status", "conflicts", "boundary", "heading_path",
                           "heading_history_range", "flat_heading_path")}
        context_record["catalogue_block"] = fact["source"].get("block")
        fact["context_evidence"] = context_record
        paths = [record.get("heading_path", []), record.get("flat_heading_path", [])]
        # An independently linked table caption is a local topic declaration.
        captions = [item for item in record["context_evidence"] if item["role"] == "table_caption"]
        if len({item["text"] for item in captions}) == 1:
            paths.extend([path + [captions[0]["text"]] for path in paths if path and path[-1] != captions[0]["text"]])
            paths.append([captions[0]["text"]])
        fact["scope_alternatives"] = [path for path in paths if path]
        for edge in graph.data["relations"]:
            if edge.get("fact_id") == fact["id"]:
                edge["scope_alternatives"] = copy.deepcopy(fact["scope_alternatives"])
                edge["context_evidence"] = copy.deepcopy(context_record)
    graph.data["native_context"] = contexts
    for heading in contexts["heading_events"]:
        block = heading["source"].get("block")
        if any(edge["type"] == "heading_parent" and edge["source"].get("block") == block for edge in graph.data["relations"]):
            continue
        graph.data["relations"].append({"id": f"L:{len(graph.data['relations'])}", "type": "heading_position",
                                        "left": None, "right": heading["text"], "source": copy.deepcopy(heading["source"]),
                                        "context_evidence": copy.deepcopy(contexts["by_block"].get(block, {})),
                                        "role_basis": "actual_heading_position_parentage_must_be_verified_separately"})
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
        rows.append({"id": item["id"], "layer": "T", "role": "literal", "expected": snapshot_copy(item),
                     "actual": snapshot_copy(actual), "outcome": "correct" if a == b else "incorrect",
                     "edits": edit, "strict_edits": strict, "source": snapshot_copy(item["source"]),
                     "root_cause": f"literal:{item['id']}"})
    denominator = sum(len(canonical(item["text"])) for item in reference)
    numerator = denominator - sum(totals.values())
    return {"numerator": numerator, "denominator": denominator,
            "score": 100 * max(0, numerator) / denominator if denominator else None,
            "complete": True, **{key: totals[key] for key in ("S", "D", "I")},
            "located_units": len(matches), "required_units": len(reference),
            "located_characters": located_characters, "unadjudicated_extra_units": snapshot_copy([candidate[j] for j in sorted(available)]),
            "full_scope_edit_rate": sum(totals.values()) / denominator if denominator else None}, rows

def grade_layers(requirements: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    with evidence_session():
        if requirements.get('comparison_contract') == 'document_ast' and requirements.get('source_form_units'):
            from .document_ast_comparison import grade_document_content

            return grade_document_content(requirements, evidence)
        return _grade_layers(requirements, evidence)


def _grade_layers(requirements: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    if requirements["sample_id"] != evidence["sample_id"]:
        raise ValueError("expected and candidate sample identities differ")
    if requirements.get("requirement_ledger") != requirements["business"]:
        raise ValueError("compiled requirements changed or were omitted before grading")
    for graph in (requirements, evidence):
        validate_scalar_sources(graph["business"], graph.get("text_projection", {}), canonicalize=canonical,
                                syntax=graph.get('syntax', []), relations=graph.get('relations', []), blockers=graph.get('blockers', []))
    layers, rows = {}, []
    layers["T"], outcomes = _text_layer(requirements["text"], evidence["text"])
    rows.extend(outcomes)
    scope_options = {"contexts": evidence.get("native_context"),
                     "declared_paths": requirements.get("scope_schema", {}).get("paths", []),
                     "context_labels": requirements.get("scope_schema", {}).get("context_labels", [])}
    layers["L"], outcomes = grade_relations(requirements["relations"], evidence["relations"], canonicalize=canonical, **scope_options)
    rows.extend(outcomes)
    layers["B"], outcomes = grade_business(requirements["business"], evidence["business"],
                                          literals=evidence["text"], canonicalize=canonical, **scope_options)
    rows.extend(outcomes)
    blockers = [{"side": side, **blocker} for side, graph in (("expected", requirements), ("candidate", evidence))
                for blocker in graph.get("blockers", [])]
    blockers.extend({"side": "expected", "reason": "reference_requirement_interpretation_unsupported",
                     "source": copy.deepcopy(issue.get("source", {})), "layers": ["L", "B"], "issue": copy.deepcopy(issue)}
                    for issue in requirements.get("candidate_issues", []) if issue.get("category") in
                    {"candidate_ambiguity", "unadjudicated_extra_content", "software_unsupported"})
    blockers.extend({"side": "comparison", **blocker} for layer in layers.values() for blocker in layer.get("blockers", []))
    from .semantic_layer_comparison import compare_semantic_layers

    semantic_comparison = compare_semantic_layers(requirements, evidence, rows, layers,
                                                   canonicalize=canonical, scope_options=scope_options)
    blockers.extend(semantic_comparison["blockers"])
    for key, layer in layers.items():
        affected = any(key in blocker.get("layers", ["L", "B"]) for blocker in blockers)
        layer["complete"] = not affected
        if affected:
            layer["score"] = None
    return {"sample_id": requirements["sample_id"], "pipeline": evidence.get("pipeline"), "protocol": snapshot_copy(PROTOCOL),
            "layers": layers, "score": sum(layer["score"] for layer in layers.values()) / 3
            if not blockers and all(layer["denominator"] for layer in layers.values()) else None,
            "publishable": not blockers, "blockers": snapshot_copy(blockers), "outcomes": rows,
            "semantic_comparison": snapshot_copy(semantic_comparison),
            "candidate_issues": snapshot_copy(evidence.get("candidate_issues", [])),
            "reference_interpretation_issues": snapshot_copy(requirements.get("candidate_issues", [])),
            "pending_requirements": {"expected": snapshot_copy(requirements.get("pending_requirements", [])),
                                     "candidate": snapshot_copy(evidence.get("pending_requirements", []))},
            "directory_evidence": {"required": snapshot_copy(requirements.get("toc_evidence")),
                                   "candidate": snapshot_copy(evidence.get("toc_evidence"))},
            "text_evidence": {"required_atoms": snapshot_copy(requirements["text"]),
                              "candidate_atoms": snapshot_copy(evidence["text"]),
                              "required_projection": snapshot_copy(requirements.get("text_projection", {})),
                              "candidate_projection": snapshot_copy(evidence.get("text_projection", {}))},
            "scope_evidence": {"contexts": snapshot_copy(evidence.get("native_context")),
                               "declared_paths": snapshot_copy(scope_options["declared_paths"]),
                               "context_labels": snapshot_copy(scope_options["context_labels"])},
            "status": evidence.get("status"), "timing": snapshot_copy(evidence.get("timing", {})),
            **{key: snapshot_copy(requirements.get(key)) for key in ("document_id", "family_id", "development_exposure")}}


def grade_expected(expected: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    if 'business' not in expected and expected.get('standard') != 'canonical_expected_derived_view':
        from .requirement_graph import compile_requirement_graph

        expected = compile_requirement_graph(expected, comparison_contract='document_ast')
    return grade_layers(compile_expected(expected), read_candidate(observation))
