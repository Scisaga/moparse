"""Printed dated enumeration roles and bounded source-list membership.

This module reads only the supplied text and actual syntax stream. It does
not parse member business claims, rewrite their actors, add a declaration
business vote, infer a company from a pronoun, or continue a later peer list.
"""

from __future__ import annotations

import copy
import re
from typing import Any

_YEAR = r"(?:19|20)\d{2}年"
_CUE = re.compile(r"(?:包括|包含|如下|includes?)\s*[:：]\s*$", re.I)
_DOMAIN = re.compile(rf"\s*(?P<period>{_YEAR})\s*[，,]\s*(?P<subject>[^，,:：;；]+?)在"
                     r"(?P<domain>[^，,:：;；]+?)方面(?:所取得的|取得的|的)(?P<collection>[^，,:：;；]+?)"
                     r"(?P<operator>包括|包含|如下)\s*[:：]\s*$")
_POSSESSIVE = re.compile(rf"\s*(?P<period>{_YEAR})\s*[，,]\s*(?P<subject>[^，,:：;；]+?)的"
                         r"(?P<collection>[^，,:：;；]+?)(?P<operator>包括|包含|如下)\s*[:：]\s*$")
_ENGLISH = re.compile(r"\s*(?:In\s+)?(?P<period>(?:19|20)\d{2})\s*,\s*"
                      r"(?P<subject>[A-Za-z][A-Za-z0-9 ._-]*?)(?:'s|’s)\s+"
                      r"(?P<collection>[^:;!?]+?)\s+(?P<operator>includes?)\s*:\s*$", re.I)
_UNCERTAIN = re.compile(r"如果|除非|虽然|雖然|尽管|儘管|可能|必须|必須|不得|不能|不应|不應|"
                        r"所取得|\b(?:if|unless|although|might|may|must|not|cannot)\b|[。！？!?\n]", re.I)


def _source(source, a, b):
    result = copy.deepcopy(source)
    offset = source.get("text_span", [0, 0])[0]
    result["text_span"] = [offset + a, offset + b]
    if "cell_text_span" in source:
        cell_offset = source["cell_text_span"][0]
        result["cell_text_span"] = [cell_offset + a, cell_offset + b]
    return result


def _result():
    return {"matched": False, "lexical_complete": False, "facts": [], "roles": {}, "qualifiers": {},
            "qualifier_sources": {}, "blockers": [], "pending_requirements": [], "text_atoms": [],
            "controls": [], "required_matcher_features": []}


def _pending(result, reason, text, source, **evidence):
    item = {"kind": "enumeration_context", "reason": reason, "text": text, "source": copy.deepcopy(source),
            "layers": ["B", "L"], **copy.deepcopy(evidence)}
    result["pending_requirements"].append(item)
    result["blockers"].append(copy.deepcopy(item))


def read_enumeration_intro(text: str, source: dict[str, Any], *, scope=()) -> dict[str, Any]:
    """Expose explicit actor, year, category and inclusion roles, never a B vote."""
    result = _result()
    if not _CUE.search(text):
        return result
    if not isinstance(source, dict) or not source.get("path"):
        raise ValueError("enumeration introduction requires its actual source")
    whole = _source(source, 0, len(text))
    result.update(matched=True, source=whole, introduction={"text": text, "source": whole}, scope=list(scope))
    # Every printed word stays a literal. Source role views do not delete its
    # wording or manufacture text copies for as-yet-uninterpreted members.
    result["text_atoms"] = [{"text": text, "role": "literal", "span": [0, len(text)], "source": copy.deepcopy(whole)}]
    match = _DOMAIN.fullmatch(text) or _POSSESSIVE.fullmatch(text) or _ENGLISH.fullmatch(text)
    if match is None:
        _pending(result, "enumeration_introduction_roles_unresolved", text, whole)
        return result
    for name in ("period", "subject", "domain", "collection", "operator"):
        if name not in match.groupdict() or match[name] is None:
            continue
        a, b = match.span(name)
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        result["roles"][name] = {"text": text[a:b], "source": _source(source, a, b)}
    nominal = [result["roles"][name]["text"] for name in ("subject", "collection", "domain") if name in result["roles"]]
    if (any(not value or _UNCERTAIN.search(value) for value in nominal)
            or not re.search(r"[A-Za-z\u3400-\u9fff]", result["roles"]["subject"]["text"])):
        _pending(result, "enumeration_introduction_roles_unresolved", text, whole, roles=result["roles"])
        return result
    result["lexical_complete"] = True
    result["qualifiers"] = {"period": result["roles"]["period"]["text"]}
    result["qualifier_sources"] = {"period": copy.deepcopy(result["roles"]["period"]["source"])}
    result["required_matcher_features"] = ["enumeration_context_scope"]
    return result


def _block_source(block):
    return block.get("source", block.get("reference", {}))


def _list_span(block):
    value = block.get("list_span")
    return tuple(value) if (isinstance(value, (list, tuple)) and len(value) == 2
                            and all(type(v) is int for v in value) and 0 <= value[0] <= value[1]) else None


def _same_stream(first, second):
    a, b = first.get("list_stream"), second.get("list_stream")
    if a is not None or b is not None:
        return bool(a) and a == b
    path = _block_source(first).get("path")
    return bool(path) and path == _block_source(second).get("path")


def _syntax_lines(block):
    value = block.get("public_lines", block.get("list_lines"))
    if value is None and block.get("list_stream") is None:
        value = _block_source(block).get("lines")
    return value if (isinstance(value, (list, tuple)) and len(value) == 2
                     and all(type(v) is int for v in value)) else None


def _own_parent(block, intro):
    if not _same_stream(block, intro):
        return False
    if block.get("parent_id") == intro["id"]:
        return True
    for proof in block.get("parent_evidence", []):
        if proof.get("text") == intro["text"] and _block_source(proof) == _block_source(intro):
            return True
    # A real printed parent plus the same native list interval establishes a
    # syntax ancestor. A parent string alone, without that source, never does.
    return (intro.get("has_children") is True and intro["text"] in block.get("parents", [])
            and _list_span(intro) is not None and _list_span(intro) == _list_span(block))


def _boundary(kind, block=None, *, natural=True, **evidence):
    result = {"kind": kind, "natural_end_proved": natural, **copy.deepcopy(evidence)}
    if block:
        result["source"] = _source(_block_source(block), 0, len(block["text"]))
    return result


def plan_enumeration_scopes(blocks: list[dict[str, Any]], *, selection_end=None) -> dict[str, Any]:
    """Bind actual children or one immediately following declared list stream.

    Boundaries use original syntax, not actor changes, value agreement, or a
    later same-looking paragraph. A selected-input end may bound a prefix of
    a real list without claiming that unseen members or the natural end were
    interpreted.
    """
    result = {"matched": False, "contexts": [], "by_member": {}, "blockers": [], "pending_requirements": []}
    identifiers = [block.get("id") for block in blocks]
    if any(not ident for ident in identifiers) or len(identifiers) != len(set(identifiers)):
        raise ValueError("enumeration syntax blocks require distinct actual identities")
    declarations = {}
    for index, block in enumerate(blocks):
        declaration = read_enumeration_intro(block["text"], _block_source(block), scope=block.get("scope", []))
        if declaration["matched"]:
            result["matched"] = True
            declarations[index] = declaration
            result["blockers"].extend(copy.deepcopy(declaration["blockers"]))
            result["pending_requirements"].extend(copy.deepcopy(declaration["pending_requirements"]))
    for index, declaration in declarations.items():
        if not declaration["lexical_complete"]:
            continue
        intro = blocks[index]
        following = blocks[index + 1:]
        if not following:
            _pending(result, "enumeration_members_unavailable", intro["text"], declaration["source"])
            continue
        first = following[0]
        span = _list_span(first)
        explicit = _own_parent(first, intro)
        if (not _block_source(first).get("path") or not _same_stream(intro, first)
                or not explicit and (first.get("kind") != "item" or span is None)):
            _pending(result, "enumeration_list_structure_unavailable", intro["text"], declaration["source"])
            continue
        context = {"id": "enumeration:" + intro["id"], "declaration": copy.deepcopy(declaration), "members": [],
                   "source": copy.deepcopy(declaration["source"]), "scope": copy.deepcopy(declaration["scope"]),
                   "list_stream": copy.deepcopy(first.get("list_stream")),
                   "list_span": list(span) if span else None, "binding_rule": "actual_parent_path" if explicit else "actual_contiguous_list_span"}
        stop = None
        for position, member in enumerate(following, index + 1):
            own = _block_source(member)
            if member.get("kind") == "heading":
                stop = _boundary("heading_boundary", member)
                break
            if position in declarations:
                stop = _boundary("next_enumeration_introduction", member)
                break
            linked = _own_parent(member, intro)
            same_list = (span is not None and _list_span(member) == span and member.get("kind") == "item"
                         and _same_stream(member, first))
            if not linked and not same_list:
                stop = _boundary("different_list_boundary" if member.get("kind") == "item" else "non_list_boundary", member)
                break
            syntax_lines = _syntax_lines(member)
            if span and syntax_lines and not (span[0] <= syntax_lines[0] <= syntax_lines[1] <= span[1]):
                _pending(result, "enumeration_list_source_conflict", member["text"], own, list_span=list(span))
                stop = _boundary("unproved_end", member, natural=False)
                break
            member_source = _source(own, 0, len(member["text"]))
            inherited = {"subject": declaration["roles"]["subject"]["text"],
                "subject_source": copy.deepcopy(declaration["roles"]["subject"]["source"]),
                "qualifiers": copy.deepcopy(declaration["qualifiers"]),
                "qualifier_sources": copy.deepcopy(declaration["qualifier_sources"]),
                "enumeration_owner": copy.deepcopy(declaration["roles"]["subject"]),
                "collection": copy.deepcopy(declaration["roles"]["collection"]),
                "scope": copy.deepcopy(declaration["scope"]),
                "required_matcher_features": ["enumeration_context_scope"]}
            if "domain" in declaration["roles"]:
                inherited["domain"] = copy.deepcopy(declaration["roles"]["domain"])
            context["members"].append({"id": member["id"], "text": member["text"], "source": member_source,
                                       "syntax_lines": copy.deepcopy(syntax_lines),
                                       "member_context": inherited})
        if not context["members"]:
            _pending(result, "enumeration_members_unavailable", intro["text"], declaration["source"])
            continue
        if stop is None:
            last = context["members"][-1]
            if selection_end:
                stop = _boundary("selected_input_end", natural=False, evidence=selection_end)
            elif span and last.get("syntax_lines") and last["syntax_lines"][1] >= span[1] - 1:
                stop = _boundary("declared_list_span_end", list_span=list(span), evidence_source=_block_source(first))
            else:
                stop = _boundary("unproved_end", natural=False)
                _pending(result, "enumeration_end_boundary_unavailable", intro["text"], declaration["source"])
        context["boundary"] = stop
        result["contexts"].append(context)
        for member in context["members"]:
            if member["id"] in result["by_member"]:
                _pending(result, "enumeration_overlapping_contexts_unresolved", member["text"], member["source"])
            else:
                result["by_member"][member["id"]] = {"context_id": context["id"], **copy.deepcopy(member)}
    for block in blocks:
        unresolved_parents = [label for label in block.get("parents", []) if isinstance(label, str)
                              and _CUE.search(label) and block["id"] not in result["by_member"]]
        if unresolved_parents:
            _pending(result, "enumeration_parent_context_unavailable", block["text"], _block_source(block),
                     declared_parent_labels=unresolved_parents)
    return result


def enumeration_declaration(context):
    """Represent printed collection roles without claiming child meanings.

    The relation owns the declared syntax interval and every raw member source.
    Separate membership edges still require interpreted facts; an unknown child
    cannot become accepted through this declaration.
    """
    declaration = context["declaration"]
    roles = declaration["roles"]
    if not declaration.get("lexical_complete") or not all(key in roles for key in ("subject", "period", "collection", "operator")):
        raise ValueError("collection declaration lacks source-bound roles")
    left = {"subject": roles["subject"]["text"], "attribute": roles["collection"]["text"],
            "scope": copy.deepcopy(context.get("scope", [])), "qualifiers": copy.deepcopy(declaration["qualifiers"])}
    if "domain" in roles:
        left["domain"] = roles["domain"]["text"]
    members = [{"ordinal": index, "source": copy.deepcopy(member["source"]), "text": member["text"]}
               for index, member in enumerate(context["members"])]
    return {"type": "enumeration_declaration", "left": left,
        "right": {"role": "declared_collection_scope", "operator": roles["operator"]["text"],
                  "members": copy.deepcopy(members)},
        "source": copy.deepcopy(declaration["source"]),
        "binding_evidence": {"introduction_source": copy.deepcopy(declaration["source"]),
            "roles": copy.deepcopy(roles), "member_sources": members, "end_boundary": copy.deepcopy(context["boundary"])},
        "rule_id": "printed_collection_declaration_with_separate_member_semantics"}


def enumeration_membership(context, member, fact):
    """Attach one already interpreted claim to its own proven list member."""
    if not any(item["id"] == member["id"] and item["source"] == member["source"] for item in context["members"]):
        raise ValueError("enumeration membership is outside the actual context")
    own, source = fact.get("source", {}), member["source"]
    if (own.get("path") != source.get("path") or own.get("lines") != source.get("lines")
            or own.get("cell") != source.get("cell")):
        raise ValueError("enumeration fact is outside its actual member source")
    a, b = own.get("text_span", source["text_span"])
    if not source["text_span"][0] <= a <= b <= source["text_span"][1]:
        raise ValueError("enumeration fact is outside its member span")
    declaration = context["declaration"]
    roles = declaration["roles"]
    edge = {"type": "enumeration_membership", "left": {"subject": roles["subject"]["text"],
        "attribute": roles["collection"]["text"], "qualifiers": copy.deepcopy(declaration["qualifiers"])},
        "right": {key: copy.deepcopy(fact[key]) for key in ("subject", "attribute", "scope", "identity_facets") if key in fact},
        "source": copy.deepcopy(source), "rule_id": "printed_introduction_and_bounded_list_member",
        "binding_evidence": {"introduction_source": copy.deepcopy(declaration["source"]),
            "member_source": copy.deepcopy(source), "subject_source": copy.deepcopy(roles["subject"]["source"]),
            "period_source": copy.deepcopy(roles["period"]["source"]),
            "collection_source": copy.deepcopy(roles["collection"]["source"]),
            "operator_source": copy.deepcopy(roles["operator"]["source"]),
            "end_boundary": copy.deepcopy(context["boundary"])}}
    if "domain" in roles:
        edge["left"]["domain"] = roles["domain"]["text"]
        edge["binding_evidence"]["domain_source"] = copy.deepcopy(roles["domain"]["source"])
    return edge
