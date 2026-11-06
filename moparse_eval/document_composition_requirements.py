"""Finite printed page-range document-composition assertions.

Page numbers here identify a printed reference. They are not amounts, extra
business votes, physical-page authorization or evidence that the referenced
document exists. Unsupported conditions, negation and neighbors stay pending.
"""

from __future__ import annotations

import copy
import json
import re

from .quoted_nominal import _source

_CLAIM = re.compile(r"组成部分|組成部分|\bpart\s+of\b", re.I)
_PAGE = re.compile(r"第\s*\d+\s*[页頁]|\bpages?\s+\d+\b", re.I)
_CN_DOCUMENT = (r"(?:本|该|該|此|上述)(?:合并|合併|简明|簡明|中期|年度)*"
                r"(?:财务报表|財務報表)(?:摘要)?")
_CN = re.compile(
    r"\s*(?P<pages>第(?P<start>\d+)[页頁]至第(?P<end>\d+)[页頁])"
    r"(?:所载|所載)(?:的|之)(?P<subject>附注|附註)"
    r"(?P<predicate>为|為|乃)(?P<object>" + _CN_DOCUMENT + r")(?:的|之)"
    r"(?P<attribute>组成部分|組成部分)[。.]?\s*$")
_EN_DOCUMENT = (r"(?:this|these|the\s+accompanying)\s+"
                r"(?:(?:consolidated|condensed|interim|annual)\s+)*"
                r"(?:financial\s+statements?|statements?|report)")
_EN = re.compile(
    r"\s*(?P<subject>(?:the\s+)?(?:accompanying\s+)?notes?)\s+on\s+"
    r"(?P<pages>pages?\s+(?P<start>\d+)\s+to\s+(?P<end>\d+))\s+"
    r"(?P<predicate>are|is)\s+(?P<attribute>part\s+of)\s+"
    r"(?P<object>" + _EN_DOCUMENT + r")[.]?\s*$", re.I)
FEATURES = ("document_composition", "page_reference_binding")


def read_document_composition(text, source, *, scope=()):
    """Read one bounded assertion, retaining every printed identity and cut."""
    if not isinstance(text, str) or not isinstance(source, dict) or not isinstance(source.get("path"), str):
        raise ValueError("document composition requires literal text and its actual source")
    parent = source.get("text_span")
    if parent is not None and (not isinstance(parent, (list, tuple)) or len(parent) != 2
            or any(type(v) is not int or v < 0 for v in parent) or parent[1] < parent[0]):
        raise ValueError("document composition parent source span is invalid")
    whole = _source(source, 0, len(text))
    result = {"matched": bool(_CLAIM.search(text) and _PAGE.search(text)), "complete": False,
        "semantic_complete": False, "facts": [], "relations": [], "logic": [],
        "semantic_operands": [], "semantic_operand_relations": [], "unresolved": [], "blockers": [],
        "pending_requirements": [], "issues": [], "text_atoms": [], "controls": [],
        "text_projection_complete": True, "required_matcher_features": [], "consumed_spans": [],
        "source": copy.deepcopy(source), "raw_text": text,
        "comparison_status": "not_validated_by_this_source_reader"}
    if not result["matched"]:
        return result
    result["required_matcher_features"] = list(FEATURES)
    result["text_atoms"] = [{"text": text, "role": "literal", "source": whole}]
    result["consumed_spans"] = [{"text": text, "role": "literal", "source": copy.deepcopy(whole), "span": [0, len(text)]}]
    match = _CN.fullmatch(text) or _EN.fullmatch(text)
    if match is None:
        pending = {"kind": "document_composition", "reason": "document_composition_scope_unresolved",
            "text": text, "source": whole, "scope": list(scope), "layers": ["B", "L"],
            "category": "software_unsupported"}
        for key in ("unresolved", "blockers", "pending_requirements"):
            result[key] = [copy.deepcopy(pending)]
        return result
    sources = {role: _source(source, *match.span(role))
               for role in ("subject", "predicate", "object", "attribute", "pages", "start", "end")}
    pages = {"role": "printed_page_reference_range", "text": match["pages"], "source": sources["pages"],
        "start": {"id": match["start"], "source": sources["start"]},
        "end": {"id": match["end"], "source": sources["end"]}}
    document = {"text": match["object"], "source": sources["object"], "resolution": "printed_name_only"}
    tree = {"kind": "document_composition", "subject": match["subject"], "predicate": match["predicate"],
        "attribute": match["attribute"], "object": match["object"], "source": whole,
        **{role + "_source": sources[role] for role in ("subject", "predicate", "attribute", "object")},
        "page_reference": pages, "document_identity": document, "span": [0, len(text)]}
    qualifiers = {"polarity": "positive", "page_range": match["pages"]}
    fact = {"id": "composition:0", "subject": match["subject"], "attribute": match["attribute"],
        "predicate": match["predicate"], "value": match["object"], "object": match["object"],
        "role": "description", "scope": list(scope), "qualifiers": qualifiers, "identity_facets": {},
        "source": whole, "value_source": sources["object"],
        **{role + "_source": sources[role] for role in ("subject", "predicate", "attribute", "object")},
        "qualifier_sources": {"page_range": sources["pages"]},
        "logic": copy.deepcopy(tree), "rule_id": "printed_page_range_document_composition"}
    component = {"role": "document_component", "text": match["subject"], "scope": list(scope),
                 "page_range": match["pages"]}
    assertion = {"subject": match["subject"], "attribute": match["attribute"], "scope": list(scope),
                 "qualifiers": copy.deepcopy(qualifiers), "identity_facets": {}}
    binding = {"statement_source": copy.deepcopy(whole), "page_reference": copy.deepcopy(pages),
        "document_identity": copy.deepcopy(document),
        **{role + "_source": copy.deepcopy(sources[role]) for role in ("subject", "predicate", "attribute", "object")}}
    result["facts"] = [fact]
    result["logic"] = [tree]
    result["relations"] = [
        {"type": "document_part_of", "left": component, "right": copy.deepcopy(document),
         "source": sources["attribute"], "object_anchor": None, "binding_evidence": copy.deepcopy(binding),
         "rule_id": "printed_component_to_named_document"},
        {"type": "page_reference_scope", "left": copy.deepcopy(pages), "right": assertion,
         "source": sources["pages"], "object_anchor": None, "binding_evidence": copy.deepcopy(binding),
         "rule_id": "printed_page_range_to_component_identity"}]
    result["complete"] = result["semantic_complete"] = True
    return result


def validate_document_compositions(graph, fields, literal):
    """Recover obligations from source text even if derived tags are removed.

    This is a transport/mutation guard. Independent literal-span oracles must
    still establish the admitted grammar's semantic correctness.
    """
    from .prose_requirements import _sentence_spans

    seen = set()
    for entry in graph["sources"]:
        for a, b in _sentence_spans(entry["text"]):
            origin = _source(entry["source"], a, b)
            text = entry["text"][a:b]
            key = json.dumps([origin, text], ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            result = read_document_composition(text, origin)
            if not result["matched"]:
                continue
            if literal(origin) != text:
                raise ValueError("document composition differs from its actual source")
            if not result["complete"]:
                if not any(issue.get("source") == origin and issue.get("text") == text
                           and {"B", "L"} <= set(issue.get("layers", [])) for issue in graph["unresolved"]):
                    raise ValueError("unresolved document composition lost its source scope")
                continue
            matches = [field for field in fields if field.get("source") == origin]
            if len(matches) != 1:
                raise ValueError("document composition needs one complete source-bound assertion")
            field = matches[0]
            expected = read_document_composition(text, origin, scope=field.get("scope", []))
            fact = expected["facts"][0]
            keys = ("subject", "attribute", "predicate", "value", "object", "qualifiers", "subject_source",
                    "attribute_source", "predicate_source", "value_source", "object_source", "qualifier_sources", "logic")
            if any(field.get(key) != fact[key] for key in keys):
                raise ValueError("document composition changes its source-bound component or page identity")
            if not set(FEATURES) <= set(graph["required_matcher_features"]):
                raise ValueError("document composition lacks its declared comparison dependencies")
            if not any(tree == expected["logic"][0] for tree in graph["logic"]):
                raise ValueError("document composition lost its source-bound logical assertion")
            for required in expected["relations"]:
                keys = ("type", "left", "right", "source", "binding_evidence")
                if not any(all(edge.get(key) == required[key] for key in keys) for edge in graph["relations"]):
                    raise ValueError("document composition lost its page or document relation")
