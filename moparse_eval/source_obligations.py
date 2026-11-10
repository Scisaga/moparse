"""Independent source obligations, built before any semantic interpretation.

This inventory reads selected expected syntax and declarations only. It never
imports a semantic reader, and graph kinds, features and dispositions cannot
define its scope. Its coverage audit is deliberately conservative: a literal
business role must explain the printed words; retaining T or a whole-paragraph
value does not explain a proposition. Independent semantic oracles are still
required before this evidence can authorize evaluation.
"""

from __future__ import annotations

import copy
import json
import re
from collections import Counter, defaultdict
from typing import Any

from .action_forms import AUDITED_ACTION_FORMS

_PREDICATE = re.compile(
    r"\b(?:is|are|was|were|be|owns?|owned|holds?|held|acquires?|acquired|"
    r"approves?|approved|reviews?|reviewed|pays?|paid|publishes?|published|"
    r"discloses?|disclosed|submits?|submitted|invests?|invested|increases?|increased|"
    r"decreases?|decreased|reports?|reported|declares?|declared|requires?|required|"
    r"retains?|retained|exceeds?|exceeded|provides?|provided|repays?|repaid|"
    r"guarantees?|guaranteed|sells?|sold|stores?|stored|retrieves?|retrieved|"
    r"releases?|released|deletes?|deleted|includes?|included|comprises?|comprised|"
    r"supports?|supported|operates?|operated|designs?|designed|offers?|offered|"
    r"connects?|connected|creates?|created|manages?|managed|produces?|produced|"
    r"serves?|served|develops?|developed|builds?|built|enhances?|enhanced|"
    r"maintains?|maintained|uses?|used|has|have|had|needs?|needed|attends?|attended|"
    r"votes?|voted|participates?|participated|accesses?|accessed|delivers?|delivered|"
    r"enables?|enabled|sharpens?|sharpened|helps?|helped|leverages?|leveraged|"
    r"engages?|engaged|captures?|captured|says?|said|states?|stated)\b|"
    r"持有|拥有|擁有|收购|收購|批准|审批|審批|审阅|審閱|披露|支付|偿还|償還|"
    r"投资|投資|增加|增长|增長|减少|減少|下降|组成部分|組成部分", re.I)
_OPERATORS = re.compile(
    r"\b(?:only if|unless|except when|except if|except|if|not|never|cannot|shall|"
    r"must|may|can|will|should|could|would|and|or|but|when|until|because|although|while|whereas|whether|"
    r"once|whenever|provided that|in case|as long as|as soon as|despite|since)\b|"
    r"只有|如果|除非|不得|不能|不可以|必须|必須|应当|應當|可以|并且|並且|以及|借助|随着|通过|受益于|由于|因为|为了", re.I)
# A PP is an attachment obligation. Its preposition alone cannot determine
# whether it is an argument, nominal complement or qualifier. The independent
# scanner records that question; only a source-bound interpretation answers it.
_POSTPREDICATE_SCOPE = re.compile(
    r"\b(?:subject\s+to|according\s+to|in\s+comparison\s+with|in\s+order\s+to|because\s+of|as long as|as soon as|about|above|across|after|against|along|amid|among|around|"
    r"at|before|behind|below|beneath|beside|between|beyond|by|despite|during|for|from|in|inside|into|near|off|"
    r"of|to|on|onto|outside|over|past|pending|per|regarding|since|through|throughout|till|toward|towards|under|"
    r"underneath|until|upon|via|versus|with|within|without)\b", re.I)
_DECLARATION = re.compile(r"(?:(?:截至|於|于)[^。;；\n，,]{1,35}(?:止年度|止期间|止期間|年度)[，,]\s*)?"
                          r"(?:Units?|Currency|Period|Year|(?:金[額额])?(?:单位|單位)|币种|幣種|期间|期間|年度)\s*[:：=]\s*[^。.!?！？;；]+[。.]?", re.I)
_SCHEMA_CONTROL = re.compile(r"Attribute|Property|Field|Value|Metric|Item|Record|Group|Section|属性|屬性|字段|值|指标|指標|项目|項目|分组|分組", re.I)
_ACTION_MEANING = dict(AUDITED_ACTION_FORMS)
_PUNCTUATION = set(":：=;；,.。!?！？()（）[]【】{}\"“”'‘’、，/\\|-–—")
_METADATA = re.compile(r"\s*(?:Name|Entity|Company|Subject|Identifier|ID|Code|Ticker|Role|Type|Market|Region|Location|URL|URI|Website|Address|Date and time|DateTime|Timestamp|Date|Time|名称|姓名|主体|公司名称|证券代码|证券简称|类型|职务|市场|地区|地址|日期|时间)\s*[:：=]", re.I)
_NAME_FIELD = re.compile(r"\s*(?:Name|Entity|Company|名称|公司名称)\s*[:：=]", re.I)
_LEGAL_NAME_CONTINUATION = re.compile(
    r"\s*(?:(?:holdings?|group|international|technologies|technology|systems?|services?)\s+)*"
    r"(?:inc\.?|corp\.?|ltd\.?|limited|llc|plc|co\.?|company|corporation)\s*[.]?\s*", re.I)
_NAVIGATION = re.compile(r"\s*(?:(?:[^:：=\n]{1,160})[:：=]\s*)?(?:"
    r"(?:See(?: also)?|Refer to)\s+(?:[\"“][^\"”]+[\"”]|Note\s+\d+)(?:\s+for more information)?[.]?"
    r"|(?:参见|參見|详见|詳見)\s*(?:《[^》]+》|[\"“][^\"”]+[\"”]|(?:附注|附註)\s*\d+)[。.]?"
    r"|(?:本公司|本集[团團])(?:19|20)\d{2}年[^，,。；;：:]+[与與][^，,。；;：:]+之[间間]的差[异異][说說]明"
    r"[请請]?[详詳][见見](?:合[并併])?(?:财务报表|財務報表)(?:附注|附註)\d+(?:\([A-Za-z0-9]+\))*[。.]?"
    r"|(?:[详詳]情[请請]|[请請])?(?:参见|參見|详见|詳見)(?:本(?:年度[報报]告|年[報报]|[報报]告)|按[^。；;]+[會会][計计][準准][則则])[^。；;]*[。.]?"
    r"|本公司根[據据](?:國際|国际)[財财]務[報报]告[會会][計计][準准][則则]和(?:中國|中国)企業[會会][計计][準准][則则]"
    r"[編编][製制]的[會会][計计][報报]表的主要差[異异][見见][^。；;]+[。.]?)\s*", re.I)

SEMANTIC_OBLIGATION_TYPES = frozenset({
    "assertive_proposition", "structured_field", "logical_relation", "qualifier",
    "nominal_label", "enumeration_member", "navigation_reference",
    "document_composition", "non_assertive_content", "unknown",
})


def _fragment_contract(fragment, entry, target, non_applicability_rule, navigation):
    """Classify source syntax without taking a reader's success as evidence.

    A predicate hit is positive assertion evidence, never a completeness test.
    A lack of hits therefore leaves business-looking prose unknown. Explicit
    headings, table cells, fields and list membership have their own contracts.
    """
    if navigation:
        return "navigation_reference", ["owner", "target"]
    if non_applicability_rule == "printed_qualifier_declaration":
        return "qualifier", ["dimension", "value", "scope"]
    if non_applicability_rule:
        return "nominal_label", ["label", "structural_owner"]
    field = re.match(r"\s*(?P<label>[^:：=\n]{1,160})[:：=]\s*(?P<body>\S.*)", fragment, re.S)
    if field and not re.fullmatch(r"Description|Statement|Narrative|Policy|Requirement|描述|说明|說明|陈述|陳述|政策|要求",
                                  field["label"].strip(), re.I):
        return "structured_field", ["label", "value", "binding"]
    if re.fullmatch(r"\s*(?:19|20)\d{2}年\s*[，,]\s*[^。！？!?\n]+?(?:包括|包含|如下)\s*[:：]\s*", fragment) or re.fullmatch(
            r"\s*(?:In\s+)?(?:19|20)\d{2}\s*,\s*[^:;!?]+(?:'s|’s)\s+[^:;!?]+\s+includes?\s*:\s*", fragment, re.I):
        return "logical_relation", ["subject", "period", "collection", "operator", "member_scope"]
    if _PREDICATE.search(_syntax_mask(fragment)):
        if re.search(r"组成部分|組成部分|\bpart of\b", fragment, re.I):
            return "document_composition", ["document", "part", "direction"]
        return "assertive_proposition", ["subject", "predicate", "object_or_complement", "scope"]
    if entry.get("cell"):
        return "structured_field", ["cell_value", "row_or_column_binding"]
    if target.get("list_span") or entry.get("parents"):
        return "enumeration_member", ["member", "group", "operator"]
    # Bare nominal business content still requires interpretation. It is not
    # a non-assertion exemption merely because a finite verb was not found.
    return "unknown", ["semantic_interpretation"]


def source_selection(expected: dict[str, Any]) -> dict[str, Any]:
    """A generated snapshot, never a second editable answer standard."""
    selection = json.loads(json.dumps({key: expected[key] for key in (
        "sample_id", "document_id", "source_pages", "scope", "targets", "authorized_raw_segments") if key in expected}, ensure_ascii=False))
    from .expected_readback import declared_navigation_heading

    heading = declared_navigation_heading(expected)
    if heading:
        # Preserve the original declaration needed to reproduce this generated
        # inventory when validating a saved view without a live expected object.
        selection['tags'] = ['section-toc']
        selection['navigation_declaration'] = {'role': 'section_toc', 'source': copy.deepcopy(heading['reference']),
                                              'basis': 'existing_selection_tag:section-toc'}
    return selection


def _origin(source, start, end):
    offset = source.get("text_span", [0, 0])[0]
    return {**copy.deepcopy(source), "text_span": [offset + start, offset + end]}


def _syntax_mask(text):
    """Protect quoted source names without deciding whether they are nouns."""
    result, quote, start = list(text), None, 0
    pairs = {'"': '"', '“': '”', '‘': '’', "'": "'", '「': '」', '『': '』'}
    for index, char in enumerate(text):
        if quote:
            if char == quote and (index == 0 or text[index - 1] != "\\"):
                result[start:index + 1] = " " * (index + 1 - start)
                quote = None
        elif char in pairs:
            if char == "'" and index and text[index - 1].isalnum():
                continue  # Possessive/contraction apostrophes are not quotes.
            quote, start = pairs[char], index
    # An unclosed quote is not permission to hide the rest of the paragraph.
    return "".join(result)


def _segments(text):
    mask = _syntax_mask(text)
    start = 0
    for match in re.finditer(r"[;；\n]|[。!?！？]|\.(?=\s|$)", mask):
        # Initials, domains and sentence punctuation in a literal Name/URL
        # field do not turn that name into propositions. Record separators
        # still terminate the field even when the next clause has no label.
        if match[0] not in ";；\n" and _METADATA.match(text[start:]):
            continue
        if match[0] in ";；" and _NAME_FIELD.match(text[start:]):
            following = re.split(r"[;；\n]", mask[match.end():], maxsplit=1)[0]
            if _LEGAL_NAME_CONTINUATION.fullmatch(following):
                continue  # A typed legal-form suffix is still literal name data.
        end = match.end()
        if text[start:end].strip():
            yield start, end
        start = end
    if text[start:].strip():
        yield start, len(text)


def _semantic_syntax(text):
    # Atomic metadata values are literal fields, while a subsequent Description
    # in the same source record still retains every semantic operator.
    mask = list(_syntax_mask(text))
    for start, end in _segments(text):
        if _METADATA.match(text[start:end]):
            mask[start:end] = " " * (end - start)
    return "".join(mask)


def build_source_obligation_inventory(expected: dict[str, Any]) -> dict[str, Any]:
    """Enumerate original literals and obligations independently of the graph."""
    from .authorized_source_inventory import plan_authorized_source_inventory

    raw_inventory = plan_authorized_source_inventory(expected.get("authorized_raw_segments"), expected["targets"])
    sources, obligations = [], []
    obligation_keys = set()

    def add(kind, entry, start, end, layers, rule, **detail):
        semantic_type = detail.pop("semantic_type", "logical_relation" if kind == "relation"
            else "qualifier" if kind == "qualifier" else "unknown")
        key = (kind, entry["id"], start, end, semantic_type, rule,
               detail.get("binding_role"), json.dumps(detail.get("required_scope"), sort_keys=True, ensure_ascii=False))
        if key in obligation_keys:
            return
        obligation_keys.add(key)
        obligations.append({"id": f"obligation:{len(obligations)}", "kind": kind, "semantic_type": semantic_type,
            "source_id": entry["id"], "source": _origin(entry["source"], start, end),
            "text": entry["text"][start:end], "layers": list(layers),
            "interpretation_rule": rule, "expected_roles": detail.pop("expected_roles", []),
            "source_basis": "authorized_expected_literal_and_syntax", **detail})

    for target in expected.get("targets", []):
        reference = copy.deepcopy(target["reference"])
        raw_entries = []
        cells = target.get("cells", [])
        first_row = sorted([cell for cell in cells if cell.get("row") == 0], key=lambda cell: cell.get("col", 0))
        schema = len(first_row) == 2 and re.fullmatch(r"Attribute|Property|Field|属性|屬性|字段", first_row[0].get("text", ""), re.I) and re.fullmatch(
            r"Value|值", first_row[1].get("text", ""), re.I)
        numeric_rows = sum(bool(re.fullmatch(r"[+\-−]?\d+(?:[,.]\d+)*(?:%|万[元股]|萬[元股])?", cell.get("text", "").strip()))
                           for cell in cells if cell.get("row", 0) > 0 and cell.get("col") == 1)
        schema = bool(schema and (all(cell.get("native_header_tag") or cell.get("is_column_header") for cell in first_row)
                                  or numeric_rows >= 2))
        qualifier_rows = {cell["row"] for cell in cells if schema and cell.get("col") == 0
                          and re.fullmatch(r"Units?|Currency|Period|Year|单位|單位|币种|幣種|期间|期間|年度", cell.get("text", ""), re.I)}
        # Table display markup is not an additional source-text answer. Its
        # original cells, spans and schema declarations remain independently
        # inventoried, including empty cells and non-header labels.
        if not target.get("cells"):
            raw_entries.append((target.get("raw_text", target.get("text", "")), reference, {}))
        for cell in target.get("cells", []):
            raw_entries.append((cell.get("text", ""), {**reference,
                "cell": cell.get("id", cell.get("native_path")), "row": cell.get("row"),
                "column": cell.get("col")}, {"cell": copy.deepcopy(cell)}))
        for text, origin, detail in raw_entries:
            entry = {"id": f"literal:{len(sources)}", "target_id": target["id"], "text": text,
                "source": origin, "source_kind": target["kind"],
                "parents": copy.deepcopy(target.get("parents", [])),
                "heading_scope": copy.deepcopy(target.get("selected_heading_context", [])),
                "has_children": target.get("has_children", False), **detail}
            cell = detail.get("cell", {})
            if schema and cell.get("row") == 0 or cell.get("row") in qualifier_rows and cell.get("col") == 0:
                entry["printed_schema_control"] = True
            entry["declared_parent_sources"] = [
                {"text": parent.get("raw_text", parent["text"]), "source": copy.deepcopy(parent["reference"])}
                for parent in expected["targets"] if parent.get("has_children")
                and parent.get("text") in entry["parents"] and parent["reference"].get("path") == reference.get("path")
                and parent["reference"]["lines"][1] < reference["lines"][0]]
            sources.append(entry)
            add("text", entry, 0, len(text), ("T",), "all_selected_literal_text")
            if entry['parents'] and re.match(r'[^:：;；\n]+[:：]\s*(?:19|20)\d{2}年', text):
                parents = [parent for parent in entry['declared_parent_sources'] if parent['text'] == entry['parents'][-1]]
                if len(parents) == 1 and (parent_label := re.match(r'(?P<label>[^:：;；\n]+)[:：]\s*(?:19|20)\d{2}年', parents[0]['text'])):
                    add('relation', entry, 0, len(text), ('B', 'L'), 'printed_series_list_member_requires_actual_parent',
                        binding_role='series_parent', expected_roles=['parent_metric', 'member', 'membership_scope'],
                        required_parent={'text': parent_label['label'], 'source': _origin(parents[0]['source'], *parent_label.span('label'))})
            if entry["heading_scope"] and target["kind"] != "heading" and text.strip():
                add("relation", entry, 0, len(text), ("L",), "selected_heading_owns_its_original_content",
                    binding_role="heading_scope", required_scope=copy.deepcopy(entry["heading_scope"]))
            for start, end in _segments(text):
                fragment = text[start:end]
                # These exemptions are defined from the original syntax, not
                # the graph's classification or a lack of business nodes.
                na = None
                if detail.get("cell", {}).get("is_column_header"):
                    na = "printed_column_header_context"
                elif target["kind"] in {"heading", "image_caption"} and not _PREDICATE.search(_syntax_mask(fragment)):
                    na = "printed_nonassertive_heading_or_caption"
                elif _DECLARATION.fullmatch(fragment.strip()):
                    na = "printed_qualifier_declaration"
                elif entry.get("printed_schema_control"):
                    na = "printed_property_value_schema_control"
                elif re.fullmatch(r"(?:Note|Notes|附注|附註|注)\s*[:：]", fragment.strip(), re.I):
                    na = "printed_empty_note_context_label"
                elif re.fullmatch(r'[變变][動动化]分析[:：]', fragment.strip()):
                    na = 'printed_nonassertive_analysis_context_label'
                navigation = bool(_NAVIGATION.fullmatch(fragment))
                if navigation:
                    na = "printed_navigation_has_no_independent_business_assertion"
                semantic_type, roles = _fragment_contract(fragment, entry, target, na, navigation)
                add("proposition" if semantic_type in {"assertive_proposition", "document_composition"} else "semantic_content",
                    entry, start, end, ("B",) if navigation else ("B", "L"), "each_printed_semantic_fragment",
                    semantic_type=semantic_type, expected_roles=roles,
                    **({"non_applicability_rule": na} if na else {}))
                if navigation:
                    add("relation", entry, start, end, ("L",), "printed_navigation_requires_its_actual_owner_and_target",
                        binding_role="navigation")
                field = re.match(r"\s*([^:：=\n]{1,160})\s*[:：=]\s*\S", fragment)
                scalar_field = bool(not na and field and not re.fullmatch(
                        r"Description|Statement|Narrative|Policy|Requirement|描述|说明|說明|陈述|陳述|政策|要求", field[1].strip(), re.I) and not re.match(
                            r"Year Ended\b|As of\b|As at\b|For the year\b|截至|年度", field[1].strip(), re.I))
                if scalar_field:
                    add("relation", entry, start, end, ("L",), "printed_field_requires_label_value_binding",
                        binding_role="field_binding")
                elif not na:
                    add("relation", entry, start, end, ("L",), "each_semantic_fragment_requires_its_own_binding",
                        binding_role="semantic_binding")
                operation = re.match(r"\s*(?P<marker>By|Through|In order to|For the purpose of)\s+(?P<verb>[A-Za-z]+)\b", fragment, re.I)
                if operation and (operation['marker'].lower() == 'in order to' or operation['verb'].lower().endswith('ing')):
                    add("relation", entry, start + operation.start('marker'), start + operation.end('marker'), ("B", "L"),
                        "printed_nonfinite_operation_requires_its_own_controller_operand_and_main_scope",
                        binding_role="fronted_operation", statement_source=_origin(entry['source'], start, end),
                        expected_roles=["operator", "main_proposition", "operation", "controller", "attachment"])
            mask = _semantic_syntax(text)
            for match in _PREDICATE.finditer(mask):
                add("relation", entry, *match.span(), ("B", "L"), "printed_predicate_requires_bound_roles")
            for match in _OPERATORS.finditer(mask):
                add("qualifier", entry, *match.span(), ("B", "L"), "printed_operator_requires_scope")
            operator_spans = {match.span() for match in _OPERATORS.finditer(mask)}
            for start, end in _segments(text):
                segment = mask[start:end]
                predicates = list(_PREDICATE.finditer(segment))
                for match in _POSTPREDICATE_SCOPE.finditer(segment):
                    bounds = (start + match.start(), start + match.end())
                    if match[0].casefold() == "at" and re.match(r"\s+(?:least|most)\b", segment[match.end():], re.I):
                        continue  # A threshold operator is not a PP head.
                    if bounds not in operator_spans and any(predicate.end() <= match.start() for predicate in predicates):
                        ambiguous_to = re.sub(r"\s+", " ", match[0].casefold()) in {"to", "in order to"}
                        add("relation", entry, *bounds, ("B", "L"), "printed_preposition_requires_source_bound_attachment",
                            semantic_type="logical_relation", binding_role="attachment" if ambiguous_to else "prepositional_attachment",
                            **({"attachment_candidates": ["prepositional_complement", "infinitival_marker"]} if ambiguous_to else {}),
                            statement_source=_origin(entry["source"], start, end),
                            statement_text=text[start:end],
                            expected_roles=["preposition", "head", "complement", "attachment", "semantic_role"])
                for match in re.finditer(r"\b(?:at\s+least|at\s+most|more\s+than|less\s+than)\s+\d+(?:\.\d+)?%?", segment, re.I):
                    add("relation", entry, start + match.start(), start + match.end(), ("B", "L"),
                        "printed_quantity_comparison_requires_bound_set_and_boundary", binding_role="quantity_comparison",
                        expected_roles=["operator", "quantity", "unit", "set", "scope"],
                        statement_source=_origin(entry["source"], start, end), statement_text=text[start:end])
        for declaration in target.get("outside_selection_context", []):
            obligations.append({"id": f"obligation:{len(obligations)}", "kind": "authorization_dependency",
                "source_id": None, "source": copy.deepcopy(reference), "text": declaration.get("text", ""),
                "semantic_type": "unknown", "expected_roles": ["authorized_scope_resolution"],
                "layers": ["L", "B"], "interpretation_rule": "retain_external_scope_dependency",
                "source_basis": "existing_authorized_selection_declaration", "declaration": copy.deepcopy(declaration)})
    # Raw heading ownership survives an upstream omission of selected heading
    # metadata. Only the contiguous, actually authorized raw stack is used;
    # unseen ancestors are never manufactured across selection gaps.
    scope_keys = {json.dumps([item["source_id"], item["required_scope"]], sort_keys=True, ensure_ascii=False): item
                  for item in obligations if item.get("binding_role") == "heading_scope"}
    for raw_scope in raw_inventory.get("heading_scope_obligations", []):
        if raw_scope["scope_status"] == "unclaimed":
            continue
        for entry in sources:
            # The raw ledger owns the whole table's lines; cell identity is
            # bound separately below, rather than requiring a nonexistent raw
            # cell id before the row/column bridge can run.
            outer, inner = entry["source"], raw_scope["source"]
            if (entry["source_kind"] == "heading" or outer.get("path") != inner.get("path")
                    or not outer.get("lines") or not inner.get("lines")
                    or not outer["lines"][0] <= inner["lines"][0] <= inner["lines"][1] <= outer["lines"][1]):
                continue
            if "row" in raw_scope:
                if entry.get("cell", {}).get("row") != raw_scope["row"] or entry.get("cell", {}).get("col") != raw_scope["column"]:
                    continue
            elif entry.get("cell"):
                continue
            key = json.dumps([entry["id"], raw_scope["required_scope"]], sort_keys=True, ensure_ascii=False)
            if key in scope_keys:
                scope_keys[key].setdefault("raw_scope_evidence", []).append(copy.deepcopy(raw_scope))
                if raw_scope.get("scope_is_absolute"):
                    scope_keys[key]["scope_is_absolute"] = True
                if raw_scope["scope_status"] == "pending":
                    scope_keys[key]["scope_pending"] = True
                continue
            add("relation", entry, 0, len(entry["text"]), ("L",), "original_raw_heading_stack_owns_payload",
                binding_role="heading_scope", required_scope=copy.deepcopy(raw_scope["required_scope"]),
                scope_is_relative=not raw_scope.get("scope_is_absolute"), scope_is_absolute=raw_scope.get("scope_is_absolute", False),
                scope_pending=raw_scope["scope_status"] == "pending",
                raw_scope_evidence=[copy.deepcopy(raw_scope)])
            scope_keys[key] = obligations[-1]
    return {"purpose": "source_obligation_inventory_not_reference_replacement", "sample_id": expected["sample_id"],
        "selection": source_selection(expected), "sources": sources, "obligations": obligations,
        "authorized_raw_inventory": raw_inventory, "source_complete": raw_inventory["source_complete"]}


def _same_source(outer, inner):
    if outer.get("path") != inner.get("path") or outer.get("cell") != inner.get("cell"):
        return False
    outer_lines, inner_lines = outer.get('lines', [0, 0]), inner.get('lines', [0, 0])
    if len(outer_lines) != 2 or len(inner_lines) != 2:
        return bool(outer.get('joined_fragments') and outer.get('joined_fragments') == inner.get('joined_fragments')
                    and all(outer.get(key) == inner.get(key) for key in ('block', 'native_path')))
    a, b = outer_lines
    c, d = inner_lines
    return a <= c <= d <= b


def _same_statement(outer, inner):
    if not _same_source(outer, inner):
        return False
    span = outer.get("text_span")
    other = inner.get("text_span")
    return (other is not None and span[0] <= other[0] <= other[1] <= span[1]) if span else True


def _fragment_owns_fact(obligation, fact):
    outer = obligation.get("statement_source", obligation["source"])
    statement = fact.get("statement_source", fact.get("source", {}))
    if _same_statement(outer, statement):
        return True
    if not fact.get("predicate") and _same_statement(outer, fact.get("attribute_source", {})):
        # A printed scalar label may govern a following dated series. Literal
        # label/delimiter ownership is established by _role_evidence first;
        # the fact and its edge still require their own identity and source.
        return True
    # Joined prose retains explicit original fragments. An obligation on one
    # fragment may consume the same joined assertion through that exact bridge.
    if any(_same_source(outer, part.get("source", {}))
           and part.get("source", {}).get("lines") == outer.get("lines")
           for part in statement.get("joined_fragments", [])):
        return True
    if outer.get("cell") is not None:
        return any(_same_source(outer, fact.get(name, {}))
                   for name in ("attribute_source", "value_source", "subject_source")) or any(
                       _same_source(outer, row.get("source", {})) and (row.get("text") == fact.get("subject")
                           or row.get("text") == fact.get("identity_facets", {}).get("group"))
                       for row in fact.get("row_evidence", []))
    return False


def _range(entry, source):
    if not isinstance(source, dict) or not _same_source(entry["source"], source):
        return None
    offset = entry["source"].get("text_span", [0, 0])[0]
    bounds = source.get("text_span", source.get("cell_text_span"))
    if bounds is None:
        return (0, len(entry["text"])) if source.get("lines") == entry["source"].get("lines") else None
    a, b = bounds
    return (a - offset, b - offset) if 0 <= a - offset <= b - offset <= len(entry["text"]) else None


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk(child)


def _ranges(entry, source):
    fragments = source.get("joined_fragments") if isinstance(source, dict) else None
    if fragments:
        from .source_requirements import original_source_cuts

        return [span for part in original_source_cuts(source) if (span := _range(entry, part)) is not None]
    span = _range(entry, source)
    return [span] if span is not None else []


def proposition_role_conflicts(entry, fact):
    """Reject opaque roles from their literal syntax, independently of tags.

    A source span proves where words came from, not that a nominal is an
    actor/object. In particular an embedded assertion or causal operator may
    not be paid for by the surrounding S/O string. This guard deliberately
    does not decide the missing interpretation; the inventory retains it.
    """
    predicate = _range(entry, fact.get("predicate_source", {}))
    if not fact.get("predicate") or predicate is None:
        return []
    if fact['predicate'].strip().lower() in {'and', 'or'} and entry['text'][slice(*predicate)].lower() == fact['predicate'].lower():
        return []  # Its structured leaves, not the group surface, prove roles.
    conflicts = []
    for role in ("subject", "object"):
        bounds = _range(entry, fact.get(role + "_source", {}))
        if bounds is None:
            continue  # Source-bearing parent/control contracts are audited separately.
        raw = entry["text"][slice(*bounds)]
        syntax = _syntax_mask(raw)
        reason = None
        if any(raw.count(a) != raw.count(b) for a, b in [('(', ')'), ('（', '）'), ('[', ']')]):
            reason = 'proposition_role_crosses_parenthetical_boundary'
        elif len(list(_segments(raw))) > 1 or re.search(r"[。！？!?；;]", syntax):
            reason = "proposition_role_contains_another_statement"
        elif re.search(r"主要[歸归]因[於于]|[由因][於于为為]|因[为為]|[为為]了|以便|"
                       r"\b(?:because|therefore|so that|in order to|for the purpose of|unless|if)\b", syntax, re.I):
            reason = "proposition_role_contains_unbound_scope"
        elif role == "subject" and re.search(
                r"(?:[为為]|[实實][现現])[^，,；;。]*\d|同比|(?:相[較较]|[較较比])(?:上年|\d{4}年)", syntax):
            reason = "proposition_subject_contains_measurement_or_comparison"
        elif (role == 'subject' and fact.get('logic', {}).get('kind') not in {
                'quantity_assertion', 'quantity_comparison', 'year_on_year_change'}
              and (re.match(r'借助|通过|随着|让', syntax)
                   or syntax.strip() in {'加速', '快速', '逐步', '持续'})):
            reason = 'proposition_subject_contains_unbound_introduction_or_action_modifier'
        elif "，" in syntax or re.search(r",(?!\d{3}(?:\D|$))", syntax) and _PREDICATE.search(syntax):
            reason = "proposition_role_contains_embedded_action"
        elif re.search(r'(?:并且|並且|并|並|且|以及|和|或)(?:提供|支持|批准|持有|拥有|擁有|支付|保存|存储|存儲|披露|公布|发布|發布)', syntax):
            reason = 'proposition_role_contains_coordinated_action'
        elif re.search(r'\b(?:and|or)\b', syntax, re.I) and any(
                match.start() > 0 and syntax[match.end():].strip() and not re.match(
                    r'\s*(?:of|for|in|on|by|with|from)\b', syntax[match.end():], re.I)
                for match in _PREDICATE.finditer(syntax)):
            reason = 'proposition_role_contains_coordinated_clause'
        # A finite English clause inside a role must have its own proposition,
        # even if there is no comma. A final nominal 'report' is not a clause.
        elif re.search(r"\b(?:is|are|was|were|has|have|had|shall|must|will|can)\s+\S+", syntax, re.I):
            reason = "proposition_role_contains_embedded_clause"
        if reason:
            conflicts.append({"reason": reason, "role": role, "source": _origin(entry["source"], *bounds), "text": raw})
    # Literal words from a neighboring sentence cannot establish this actor.
    subject = _range(entry, fact.get("subject_source", {}))
    if subject and subject[0] < subject[1] and not any(a <= subject[0] < subject[1] <= b and a <= predicate[0] < predicate[1] <= b
                           for a, b in _segments(entry["text"])):
        conflicts.append({"reason": "proposition_subject_borrowed_across_statement", "role": "subject",
                          "source": copy.deepcopy(fact["subject_source"]), "text": fact.get("subject")})
    return conflicts


def _role_evidence(entry, facts, *, materials=()):
    """Only explicit role literals count; whole node/source spans never do."""
    evidence = []
    for fact in facts:
        if proposition_role_conflicts(entry, fact):
            continue
        predicate = _range(entry, fact.get("predicate_source", {}))
        if ((not predicate or predicate[0] == predicate[1]) and fact.get('logic', {}).get('kind') == 'quantity_assertion'
                and fact['logic'].get('assertion_operator') == 'juxtaposed'):
            from .cjk_measurement_requirements import _valid_metric
            from .measurement_evidence import read_measurement_literal

            subject = _range(entry, fact.get('subject_source', {}))
            value = _range(entry, fact.get('value_source', {}))
            statement = _range(entry, fact.get('statement_source', fact.get('logic', {}).get('source', fact.get('source', {}))))
            point = fact.get('predicate_source', {}).get('text_span', [])
            parent = fact.get('qualifier_sources', {}).get('parent_metric', {})
            marker = _range(entry, fact.get('qualifier_sources', {}).get('membership_operator', {}))
            owners = [other for other in facts if other.get('subject_source') == parent
                      and other.get('logic', {}).get('assertion_operator') in {'equal', 'realize', 'reach'}]
            if (not subject or not value or not statement or len(point) != 2 or point[0] != point[1]
                    or point[0] - entry['source'].get('text_span', [0])[0] != subject[1]
                    or not marker or entry['text'][slice(*marker)] != '其中' or marker[1] > subject[0]
                    or not owners or not _valid_metric(entry['text'][slice(*subject)])):
                continue
            amount = read_measurement_literal(entry['text'][subject[1]:statement[1]],
                                              _origin(entry['source'], subject[1], statement[1]))
            if (not amount['matched'] or amount['value'] != fact.get('value')
                    or amount['unit'] != fact.get('qualifiers', {}).get('unit')):
                continue
            for origin, role in [(fact['subject_source'], 'subject'), (fact['value_source'], 'value'),
                                 *[(v, 'qualifier') for v in fact.get('qualifier_sources', {}).values() if isinstance(v, dict)]]:
                bounds = _range(entry, origin)
                if bounds:
                    evidence.append({'span': list(bounds), 'requirement': fact['id'], 'role': role})
            continue
        if fact.get("predicate", "").strip().casefold() in {"or", "and"}:
            # A logical group's full surface string is not an opaque
            # proposition explanation. Its independently bound leaves own it.
            continue
        if predicate:
            subject = _range(entry, fact.get("subject_source", {}))
            obj = _range(entry, fact.get("object_source", {}))
            control = fact.get("subject_binding_evidence", {})
            marker = _range(entry, control.get("operator_source", {}))
            controlled = (control.get("kind") == "fronted_operation_controller" and marker
                and entry["text"][slice(*marker)].lower() in {'by', 'through', 'in order to', 'for the purpose of'}
                and control.get("controller_source") == fact.get("subject_source")
                and any(other.get("subject_source") == control.get("controller_source")
                        and other.get("predicate_source") == control.get("main_predicate_source") for other in facts))
            realized = (fact.get("logic", {}).get("kind") == "quantity_assertion"
                        and fact.get("logic", {}).get("assertion_operator") == "realize"
                        and entry["text"][slice(*predicate)] in {"实现", "實現"}
                        and subject and subject[0] == predicate[1])
            if (subject and subject[1] > predicate[0] and not (realized or controlled)) or (obj and obj[0] < predicate[1]):
                continue  # Source-preserving S/O reversal is still incorrect.
            raw_predicate = entry["text"][predicate[0]:predicate[1]].strip().casefold()
            meaning = _ACTION_MEANING.get(raw_predicate, raw_predicate)
            attribute = fact.get("attribute", "").casefold()
            if controlled:
                from .active_aspect_requirements import active_forms

                meaning = active_forms()[1].get(raw_predicate, meaning)
            if attribute != meaning and fact.get("qualifiers", {}).get("aspect") in {"perfect", "progressive"}:
                # Source obligations remain independent of reader coverage.
                # Auditing an already interpreted verb may reuse the owning
                # lossless inflection vocabulary, without guessing a stem or
                # converting an absent predicate into a non-applicable item.
                from .active_aspect_requirements import active_forms

                perfect, progressive = active_forms()
                forms = perfect if fact["qualifiers"]["aspect"] == "perfect" else progressive
                meaning = forms.get(raw_predicate, meaning)
            composition = (attribute in {"组成部分", "組成部分", "part of"}
                           and raw_predicate in {"为", "為", "乃", "is", "are"})
            if attribute != meaning and not composition:
                continue  # Printed "owns" never proves the action "acquire".
        value_range = _range(entry, fact.get("value_source", {}))
        if (value_range and not entry.get('cell') and not fact.get('compact_column') and not fact.get('header_evidence')
                and not fact.get('predicate') and re.fullmatch(
                r'(?:金[額额])?同比[變变][動动]|YoY(?:\s+change)?', fact.get('attribute', ''), re.I)):
            valid_periods = True
            for dimension, label in (('from_period', '上年'), ('to_period', '本年')):
                value = fact.get('qualifiers', {}).get(dimension)
                if value is None:
                    continue
                origin = fact.get('qualifier_sources', {}).get(dimension, {})
                bounds = _range(entry, origin)
                local = bounds is not None and any(annual.get('attribute') == fact.get('subject')
                    and annual.get('record_id') == fact.get('record_id')
                    and annual.get('qualifier_sources', {}).get('period') == origin
                    and annual.get('qualifiers', {}).get('period') == value
                    and _range(entry, annual.get('value_source', {})) is not None for annual in facts)
                declared = any(material['text'][slice(*cut)] == value and re.search(
                    r'(?:^|[;；。])\s*' + label + r'\s*[:：]\s*$', material['text'][:cut[0]])
                    for material in materials if (cut := _range(material, origin)) is not None)
                if not (local or declared):
                    valid_periods = False
            if not valid_periods:
                continue
        period_source = fact.get("qualifier_sources", {}).get("period") or fact.get("qualifier_provenance", {}).get("period", {}).get("source", {})
        period_range = _range(entry, period_source)
        if not fact.get("predicate") and value_range and period_range and not entry.get("cell"):
            fragments = list(_segments(entry["text"]))
            if not any(a <= period_range[0] < period_range[1] <= value_range[0] < value_range[1] <= b
                       for a, b in fragments):
                continue  # A neighboring year's real token cannot own this value.
        if not fact.get("predicate") and value_range and not entry.get("cell"):
            wrong_local_unit = False
            for dimension in ("unit", "currency"):
                origin = fact.get("qualifier_sources", {}).get(dimension) or fact.get("qualifier_provenance", {}).get(dimension, {}).get("source", {})
                unit_range = _range(entry, origin)
                if unit_range and not any(a <= unit_range[0] < unit_range[1] <= b and a <= value_range[0] < value_range[1] <= b
                                          for a, b in _segments(entry["text"])):
                    # A declaration in a field label may explicitly own all
                    # following members; an inline unit from another member
                    # may not. Only the original label before ':' can do so.
                    delimiter = re.search(r"[:：=]", entry["text"])
                    if delimiter is None or unit_range[1] > delimiter.start():
                        wrong_local_unit = True
            if wrong_local_unit:
                continue
        # An opaque narrative value cannot claim semantic coverage by merely
        # echoing its entire source. Scalar field labels remain supported.
        if not fact.get("predicate") and (fact.get("role") in {"description", "logical_group"}
                or not _METADATA.match(entry["text"]) and _PREDICATE.search(_syntax_mask(fact.get("value", "")))):
            continue
        if not fact.get("predicate") and not entry.get("cell"):
            # A claimed scalar role cannot turn an arbitrary sentence into a
            # Name/metric field. The actual printed label and delimiter own it.
            origin = _range(entry, fact.get("attribute_source", {}))
            if origin is None or entry["text"][origin[0]:origin[1]] != fact.get("attribute"):
                parent = [parent for parent in entry["declared_parent_sources"] if parent["text"].rstrip(":： ") == fact.get("attribute")
                          and _same_source(parent["source"], fact.get("attribute_source", {}))]
                actor = _range(entry, fact.get("subject_source", {}))
                if len(parent) != 1 or actor is None or entry["text"][actor[0]:actor[1]] != fact.get("subject") or not re.match(
                        r"\s*[:：=]", entry["text"][actor[1]:]):
                    continue
                origin = actor
            tail = entry["text"][origin[1]:]
            direct_record = False
            direct_selection = False
            if fact.get('semantic_type') == 'printed_selection_state' and value_range:
                actor = _range(entry, fact.get('subject_source', {}))
                domains = [h for h in fact.get('header_evidence', []) if h.get('role') == 'column_group'
                           and (cut := _range(entry, h.get('source', {}))) and entry['text'][slice(*cut)] == h.get('text')
                           and cut[1] < origin[0] and re.match(r'[:：]', entry['text'][cut[1]:])]
                positions = [f for f in facts if f.get('subject_source') == fact.get('subject_source')
                             and f.get('attribute') in {'職位', '职位', '職務', '职务'} and f.get('value_logic')]
                direct_selection = bool(actor and actor[0] == 0 and entry['text'][slice(*actor)] == fact['subject']
                    and re.match(r'[;；]', entry['text'][actor[1]:]) and domains and positions
                    and value_range[0] == origin[1] and entry['text'][slice(*value_range)] in {'√', '✓', '☑', '×', '✗', '☒'})
            if fact.get('rule_id') == 'printed_financial_label_scalar_record' and value_range:
                from .field_sequence_requirements import _RECORD_METRIC
                from .measurement_evidence import read_measurement_literal

                actor = _range(entry, fact.get('subject_source', {}))
                end = next((a for a, c in enumerate(entry['text'][origin[1]:], origin[1]) if c in ';；。'), len(entry['text']))
                raw = entry['text'][origin[1]:end].lstrip(':： ')
                measured = read_measurement_literal(raw, _origin(entry['source'], end - len(raw), end))
                companions = [other for other in facts if other.get('record_id') == fact.get('record_id')
                              and other.get('subject_source') == fact.get('subject_source')]
                direct_record = bool(actor and actor[0] == 0 and _RECORD_METRIC.fullmatch(fact['attribute'])
                    and entry['text'][slice(*actor)] == fact['subject']
                    and re.match(r'[:：]', entry['text'][actor[1]:]) and len(companions) >= 2
                    and ((measured['matched'] and measured['value'] == fact['value'])
                         or raw in {'不適用', '不适用', '–', '—', '-'} and raw == fact['value']))
            direct_change = bool(value_range and re.fullmatch(
                r"(?:金[額额])?同比[變变][動动]|YoY(?:\s+change)?|增[減减](?:幅度)?|[變变][化動动]額|变化额|变动额", fact.get("attribute", ""), re.I)
                and re.fullmatch(r"\s*(?:[:：]\s*)?(?:增长|增長|增加|上升|下降|减少|減少)?\s*",
                                 entry["text"][origin[1]:value_range[0]]))
            if not re.match(r"\s*[:：=]", tail) and not re.match(
                    r"\s*;\s*(?:Year Ended|As of|As at|For the year|年度|截至)", tail, re.I) and not direct_change and not direct_record and not direct_selection:
                continue
            if value_range and not any(a <= origin[0] < origin[1] <= value_range[0] < value_range[1] <= b
                                       for a, b in _segments(entry["text"])) and period_range is None:
                continue
        for key in ("subject", "predicate", "object", "attribute", "value"):
            value, origin = fact.get(key), fact.get(key + "_source")
            if not isinstance(value, str) or not origin:
                continue
            for a, b in _ranges(entry, origin):
                if entry["text"][a:b] == value:
                    evidence.append({"span": [a, b], "requirement": fact["id"], "role": key})
        if fact.get('semantic_type') == 'printed_selection_state':
            for header in fact.get('header_evidence', []):
                bounds = _range(entry, header.get('source', {}))
                if header.get('role') == 'column_group' and bounds and entry['text'][slice(*bounds)] == header.get('text'):
                    evidence.append({'span': list(bounds), 'requirement': fact['id'], 'role': 'printed_field_domain'})
        # Qualifier sources are checked by the graph's literal/operator guard;
        # they cover only their explicitly bound spans, not the fact's source.
        qualifier_evidence = copy.deepcopy(fact.get("qualifier_sources", {}))
        for fronted in qualifier_evidence.get("fronted_contexts", []):
            bounds = _range(entry, fronted.get("context_source", {}))
            if bounds and re.match(r"[A-Za-z]+ing\b|[A-Za-z]+\s+", entry["text"][slice(*bounds)], re.I) and _range(entry, fronted.get("preposition_source", {})):
                marker_bounds = _range(entry, fronted["preposition_source"])
                if entry["text"][slice(*marker_bounds)].lower() in {'by', 'through', 'in order to', 'for the purpose of'}:
                    fronted.pop("context_source", None)  # Its structured operation must explain these words.
        for value in _walk([qualifier_evidence, fact.get("qualifier_provenance", {})]):
            if isinstance(value.get("path"), str):
                evidence.extend({"span": list(span), "requirement": fact["id"], "role": "qualifier"}
                                for span in _ranges(entry, value))
        if entry.get("cell") and not fact.get("predicate"):
            from .text_projection import _covers

            data = fact.get("data_evidence", {}).get("source", {})
            for row in fact.get("row_evidence", []):
                span = _range(entry, row.get("source", {}))
                group = (row.get("role") in {"row_group", "row_group_value"}
                         and row.get("text") == fact.get("identity_facets", {}).get("group")
                         and any(header.get("cell") and header["target_id"] == entry["target_id"]
                             and re.fullmatch(r"Group|分组|分組|组别|組別", header["text"], re.I)
                             and _covers(header["cell"], entry["cell"], "column_header") for header in materials))
                if (span and row.get("text") == entry["text"][slice(*span)]
                        and (row.get("text") == fact.get("subject") or group)
                        and data.get("row") is not None and _covers(entry["cell"], data, "row_header" if group else row.get("role", ""))):
                    evidence.append({"span": list(span), "requirement": fact["id"], "role": "explicit_native_record_locator"})
    return evidence


def _residue(text, span, evidence, *, literal=False):
    a, b = span
    covered = set()
    for proof in evidence:
        c, d = proof["span"]
        covered.update(range(max(a, c), min(b, d)))
    return [index for index in range(a, b) if index not in covered
            and not text[index].isspace() and (literal or text[index] not in _PUNCTUATION)]


def validate_relation_binding(obligation, fact, relation):
    """Verify an edge against its particular fact, never entry-wide role hits.

    Source location, both endpoints and direction are independent checks. A
    positive lexical overlap is not enough to bind an edge. The structured
    result intentionally distinguishes missing proof from explicit conflicts.
    """
    proof, conflicts, missing, unresolved = [], [], [], []
    kind = relation.get("type")
    if not kind:
        missing.append("relation_type")
    role = (obligation or {}).get("binding_role")
    if role in {"semantic_binding", "field_binding"} and kind is not None and kind != "field_binding":
        conflicts.append({"dimension": "relation_type", "required": "field_binding", "actual": kind})
    if role == "prepositional_attachment" and kind is not None and kind != "narrative_prepositional_attachment":
        conflicts.append({"dimension": "relation_type", "required": "narrative_prepositional_attachment", "actual": kind})
    if role == "attachment" and kind is not None and kind not in {
            "narrative_prepositional_attachment", "narrative_purpose_scope", "narrative_controlled_infinitive_scope"}:
        conflicts.append({"dimension": "relation_type", "required": "source_bound_prepositional_or_infinitival_attachment", "actual": kind})
    ident = relation.get("fact_id")
    if ident is not None and ident != fact.get("id"):
        conflicts.append({"dimension": "fact_id", "required": fact.get("id"), "actual": ident})

    endpoint = relation.get("right")
    if not isinstance(endpoint, dict):
        missing.append("right_endpoint")
        endpoint = {}
    for name in ("subject", "attribute"):
        actual = endpoint.get(name, endpoint.get("action") if name == "attribute" else None)
        if actual is None:
            missing.append("right_" + name)
        elif actual != fact.get(name):
            conflicts.append({"dimension": "right_" + name, "required": fact.get(name), "actual": actual})
        else:
            proof.append({"dimension": "right_" + name, "value": actual})
    for name in ("object", "value"):
        if name in endpoint and endpoint[name] != fact.get(name, {} if name in {"qualifiers", "identity_facets"} else [] if name == "scope" else None):
            conflicts.append({"dimension": "right_" + name, "required": fact.get(name), "actual": endpoint[name]})
    if "scope" in endpoint:
        from .business_correspondence import logical_context

        # Row groups are the same explicit context whether stored under scope
        # or identity_facets. Use the owning shared position contract.
        if logical_context(endpoint, lambda value: value) != logical_context(fact, lambda value: value):
            conflicts.append({"dimension": "right_scope", "required": logical_context(fact, lambda value: value),
                              "actual": logical_context(endpoint, lambda value: value)})
    else:
        missing.append("right_scope")
    # Graph normalization may add implicit positive polarity/assertion context
    # after a reader emitted its edge. Every explicit endpoint qualifier must
    # still agree; source-printed qualifiers have separate scope obligations.
    for name in ("qualifiers", "identity_facets"):
        for dimension, value in endpoint.get(name, {}).items():
            actual_value = fact.get(name, {}).get(dimension)
            if name == "qualifiers" and dimension == "currency":
                from .quantity import canonical_currency

                equivalent = canonical_currency(value) is not None and canonical_currency(value) == canonical_currency(actual_value)
            else:
                equivalent = actual_value == value
            if not equivalent:
                conflicts.append({"dimension": "right_" + name + "." + dimension,
                                  "required": fact.get(name, {}).get(dimension), "actual": value})

    left = relation.get("left")
    if not isinstance(left, dict):
        missing.append("left_endpoint")
        left = {}
    if kind == "field_binding":
        for name in ("subject", "attribute"):
            if name not in left:
                missing.append("left_" + name)
            elif left[name] != fact.get(name):
                conflicts.append({"dimension": "left_" + name, "required": fact.get(name), "actual": left.get(name)})
            else:
                proof.append({"dimension": "left_" + name, "value": left[name]})

    binding = relation.get("binding_evidence", {})
    statement = fact.get("statement_source", fact.get("source", {}))
    own = binding.get("statement_source", relation.get("source", {}))
    if not statement or not own:
        missing.append("statement_source")
    elif not _same_statement(statement, own):
        conflicts.append({"dimension": "statement_source", "required": statement, "actual": own})
    elif "statement_source" in binding and not _same_statement(own, statement):
        conflicts.append({"dimension": "statement_scope", "required": statement, "actual": own})
    elif "statement_source" not in binding and own != statement:
        # A predicate-only edge needs an explicit statement bridge. A source
        # span from a different local clause may not borrow the whole line.
        unresolved.append("relation_has_no_exact_statement_bridge")
    else:
        proof.append({"dimension": "statement_source", "source": own})

    if obligation and obligation.get("source"):
        outer = obligation.get("statement_source", obligation["source"])
        # Fragment obligations own all their facts. Token obligations instead
        # own a role within the fact and are checked by their caller below.
        if role in {"semantic_binding", "field_binding", "prepositional_attachment", "attachment"} and not _fragment_owns_fact(obligation, fact):
            conflicts.append({"dimension": "obligation_statement", "required": outer, "actual": statement})
    for name in (("subject_source", "predicate_source", "object_source", "attribute_source", "value_source")
                 if kind == "field_binding" else ()):
        if name in binding and name in fact and binding[name] != fact[name]:
            conflicts.append({"dimension": name, "required": fact[name], "actual": binding[name]})
    if kind == "field_binding" and fact.get("predicate"):
        for name in ("subject_source", "predicate_source", "object_source"):
            if name in fact and name not in binding:
                missing.append(name)
    if kind == "field_binding" and not fact.get("predicate") and ident is None:
        missing.append("fact_id")

    qualifiers = fact.get("qualifiers", {})
    if kind == "qualifier_scope" and left.get("type") in qualifiers:
        dimension, value = left["type"], left.get("text")
        expected_value = qualifiers[dimension]
        if dimension == "currency":
            from .quantity import canonical_currency

            agrees = canonical_currency(value) is not None and canonical_currency(value) == canonical_currency(expected_value)
        else:
            agrees = value == expected_value
        if not agrees:
            conflicts.append({"dimension": "qualifier_value", "required": expected_value, "actual": value})
        origin = fact.get("qualifier_sources", {}).get(dimension) or fact.get("qualifier_provenance", {}).get(dimension, {}).get("source")
        if isinstance(origin, dict):
            bridges = [binding.get("qualifier_source", {}),
                       *[header.get("source", {}) for header in binding.get("headers", [])]]
            if relation.get("source") != origin and not any(_same_statement(bridge, origin) for bridge in bridges if bridge):
                conflicts.append({"dimension": "qualifier_source", "required": origin, "actual": relation.get("source")})
    if kind in {"condition_scope", "exception_scope"}:
        dimension = "condition" if kind == "condition_scope" else "exception"
        if qualifiers.get(dimension) != binding.get("qualifier_text"):
            conflicts.append({"dimension": "qualifier_text", "required": qualifiers.get(dimension),
                              "actual": binding.get("qualifier_text")})
        if fact.get("qualifier_sources", {}).get(dimension) != binding.get("qualifier_source"):
            conflicts.append({"dimension": "qualifier_source", "required": fact.get("qualifier_sources", {}).get(dimension),
                              "actual": binding.get("qualifier_source")})
    if kind == "narrative_modality_scope" and (left.get("operator") != qualifiers.get("modality")
            or left.get("polarity") != qualifiers.get("modal_polarity", "positive")):
        conflicts.append({"dimension": "modality", "required": qualifiers.get("modality"), "actual": left})
    if kind == "narrative_modality_scope" and relation.get("source") != fact.get("qualifier_sources", {}).get("modality"):
        conflicts.append({"dimension": "modality_source", "required": fact.get("qualifier_sources", {}).get("modality"),
                          "actual": relation.get("source")})
    if kind == "narrative_negation_scope":
        dimension = "modal_polarity" if left.get("target") == "modality" else "polarity"
        if qualifiers.get(dimension) != "negative":
            conflicts.append({"dimension": "negation", "required": "negative", "actual": qualifiers.get(dimension)})
        if relation.get("source") != fact.get("qualifier_sources", {}).get(dimension):
            conflicts.append({"dimension": "negation_source", "required": fact.get("qualifier_sources", {}).get(dimension),
                              "actual": relation.get("source")})

    if kind == "narrative_prepositional_attachment":
        for name in ("preposition_source", "head_source", "complement_source", "attachment_source"):
            origin = binding.get(name)
            if not isinstance(origin, dict) or not origin:
                missing.append(name)
            elif not _same_statement(statement, origin):
                conflicts.append({"dimension": name, "required": statement, "actual": origin})
        if not left.get("preposition") or not left.get("semantic_role") or not left.get("attachment"):
            missing.append("prepositional_attachment_roles")
        pp = binding.get("preposition_source", {})
        if obligation and obligation.get("source") != pp:
            conflicts.append({"dimension": "preposition_source", "required": obligation.get("source"), "actual": pp})
        # Require a matching interpreted PP rather than accepting a standalone
        # fabricated relation carrying the right preposition token.
        attached = [node for node in _walk([fact.get("prepositional_complements", []),
                                           fact.get("object_phrase", {}), fact.get("subject_phrase", {})])
                    if node.get("kind") == "prepositional_complement"]
        matches = [node for node in attached if node.get("preposition_source") == pp
                   and node.get("preposition") == left.get("preposition")
                   and node.get("semantic_role") == left.get("semantic_role")
                   and node.get("attachment") == left.get("attachment")
                   and node.get("head_source") == binding.get("head_source")]
        if not matches:
            missing.append("fact_prepositional_complement")
        elif not any(node.get("complement", {}).get("source") == binding.get("complement_source") for node in matches):
            conflicts.append({"dimension": "complement_source", "actual": binding.get("complement_source")})
        if obligation and isinstance(obligation.get("statement_text"), str):
            origin = obligation["statement_source"]
            base = origin.get("text_span", [0, 0])[0]
            for key, expected in (("preposition_source", left.get("preposition")),
                                  ("head_source", left.get("attachment", {}).get("head")),
                                  ("complement_source", left.get("complement"))):
                own_origin = binding.get(key, {})
                bounds = own_origin.get("text_span")
                raw = obligation["statement_text"][bounds[0] - base:bounds[1] - base] if bounds and _same_statement(origin, own_origin) else None
                if raw != expected:
                    conflicts.append({"dimension": key + "_literal", "required": raw, "actual": expected})

    status = "conflict" if conflicts else "missing" if missing else "unresolved" if unresolved else "equivalent"
    return {"status": status, "equivalent": status == "equivalent", "conflict": status == "conflict",
            "unresolved": status == "unresolved", "missing": status == "missing", "proof": proof,
            "conflicts": conflicts, "missing_evidence": missing, "unresolved_evidence": unresolved}


def _bound_relations(fact, relations):
    result = []
    for edge in relations:
        endpoint = edge.get("right", {})
        if not isinstance(endpoint, dict) or endpoint.get("subject") != fact.get("subject") or endpoint.get("attribute") != fact.get("attribute"):
            continue
        if edge.get("fact_id") is not None and edge["fact_id"] != fact.get("id"):
            continue
        if validate_relation_binding(None, fact, edge)["equivalent"]:
            result.append(edge)
    return result


def _prepositional_role_evidence(entry, facts, relations):
    """Only a verified attachment can explain the words beyond a direct object."""
    evidence = []
    relations = [edge for edge in relations if edge.get("type") == "narrative_prepositional_attachment"
                 and _range(entry, edge.get("binding_evidence", {}).get("preposition_source", {}))]
    if not relations:
        return evidence
    for fact in facts:
        for edge in relations:
            if edge.get("fact_id") is not None and edge["fact_id"] != fact.get("id"):
                continue
            if not validate_relation_binding(None, fact, edge)["equivalent"]:
                continue
            binding, left = edge["binding_evidence"], edge["left"]
            for key, expected in (("preposition_source", left.get("preposition")),
                                  ("head_source", left.get("attachment", {}).get("head")),
                                  ("complement_source", left.get("complement"))):
                bounds = _range(entry, binding.get(key, {}))
                if bounds and entry["text"][bounds[0]:bounds[1]] == expected:
                    evidence.append({"span": list(bounds), "requirement": fact["id"],
                                     "relation": edge.get("id"), "role": key})
    return evidence


def _controller_binding(obligation, node, fact, facts, relations):
    control = node.get("control", {})
    expected_control = {"purpose_scope": ("subject_control", "purpose"),
                        "controlled_infinitive_scope": ("object_control", "complement")}.get(node.get("kind"))
    if expected_control != (control.get("kind"), node.get("operator")):
        return None
    role = "subject" if control.get("kind") == "subject_control" else "object" if control.get("kind") == "object_control" else None
    if role is None:
        return None
    group = node.get("child", {})
    object_group = role == "object" and group.get("kind") == "coordination" and group.get("mode") == "objects"
    if not object_group and control.get("controller") == fact.get(role) and control.get("controller_source") == fact.get(role + "_source"):
        return {"kind": "single_" + role, "requirement": fact["id"], "source": copy.deepcopy(fact[role + "_source"])}
    if role != "object" or group.get("kind") != "coordination" or group.get("mode") != "objects" or group.get("operator") != "and":
        return None
    leaves = group.get("children", [])
    if len(leaves) < 2 or any(leaf.get("kind") != "proposition" for leaf in leaves):
        return None
    origin = control.get("controller_source", {})
    statement = obligation.get("statement_source", {})
    text = obligation.get("statement_text")
    if not isinstance(text, str) or not _same_statement(statement, origin) or not origin.get("text_span"):
        return None
    base = statement.get("text_span", [0, 0])[0]
    start, end = origin["text_span"]
    if text[start - base:end - base] != control.get("controller"):
        return None
    covered, previous, members = set(), start, []
    for leaf in leaves:
        own = leaf.get("object_source", {})
        bounds = own.get("text_span")
        if (not bounds or not _same_statement(origin, own) or bounds[0] < previous
                or text[bounds[0] - base:bounds[1] - base] != leaf.get("object")
                or any(leaf.get(key) != fact.get(key) for key in ("subject", "attribute", "subject_source", "predicate_source"))):
            return None
        previous = bounds[1]
        matches = [member for member in facts if all(member.get(key) == leaf.get(key)
                   for key in ("subject", "attribute", "object", "subject_source", "predicate_source", "object_source"))]
        if len(matches) != 1:
            return None
        member = matches[0]
        own_edges = [edge for edge in relations if edge.get("type") == "field_binding"
                     and (edge.get("fact_id") is None or edge.get("fact_id") == member["id"])
                     and validate_relation_binding(None, member, edge)["equivalent"]]
        if not own_edges:
            return None
        members.append({"requirement": member["id"], "object": leaf["object"], "source": copy.deepcopy(own)})
        covered.update(range(bounds[0], bounds[1]))
    if leaves[0]["object_source"]["text_span"][0] != start or previous != end or fact["id"] not in {item["requirement"] for item in members}:
        return None
    operators = group.get("operator_sources", [])
    if not operators:
        return None
    explicit_and = False
    for operator in operators:
        bounds = operator.get("text_span")
        if not bounds or not _same_statement(origin, operator):
            return None
        raw = text[bounds[0] - base:bounds[1] - base]
        if re.fullmatch(r"\s*(?:,|and|,\s*and)\s*", raw, re.I) is None:
            return None
        explicit_and |= bool(re.search(r"\band\b", raw, re.I))
        covered.update(range(bounds[0], bounds[1]))
    if not explicit_and or any(index not in covered and not text[index - base].isspace() for index in range(start, end)):
        return None
    return {"kind": "coordinated_objects", "operator": "and", "source": copy.deepcopy(origin), "members": members}


def _infinitive_bindings(obligation, facts, relations, logic):
    """A TO token needs its actual syntactic controller and scoped operand."""
    if obligation.get("binding_role") != "attachment":
        return []
    wrappers = [node for node in _walk(logic)
        if node.get("kind") in {"purpose_scope", "controlled_infinitive_scope"}
        and node.get("operator_source") == obligation["source"]]
    if not wrappers:
        return []
    proof = []
    for edge in relations:
        if edge.get("type") not in {"narrative_purpose_scope", "narrative_controlled_infinitive_scope"}:
            continue
        binding = edge.get("binding_evidence", {})
        if binding.get("operator_source") != obligation["source"]:
            continue
        for fact in facts:
            if edge.get("fact_id") is not None and edge["fact_id"] != fact.get("id"):
                continue
            check = validate_relation_binding(obligation, fact, edge)
            if not check["equivalent"]:
                continue
            for node in wrappers:
                control, operand = node.get("control", {}), node.get("operand", {})
                expected_kind = "narrative_purpose_scope" if node["kind"] == "purpose_scope" else "narrative_controlled_infinitive_scope"
                controller_binding = _controller_binding(obligation, node, fact, facts, relations)
                if controller_binding is None:
                    continue
                if (edge["type"] == expected_kind and binding.get("operand_logic") == operand
                        and binding.get("operand_source") == operand.get("source")
                        and binding.get("controller_source") == control.get("controller_source")
                        and edge.get("left", {}).get("controller") == control.get("controller")
                        and edge.get("left", {}).get("operator") == node.get("operator")
                        and edge.get("left", {}).get("control_kind") == control.get("kind")
                        and any(_same_statement(child.get("source", {}), fact.get("statement_source", fact.get("source", {})))
                                for child in _walk(node.get("child", {})) if child.get("kind") == "proposition")):
                    proof.append({"requirement": fact["id"], "relation": edge.get("id"),
                                  "binding": check, "control": copy.deepcopy(control), "controller_binding": controller_binding})
    return proof


def _operator_edges(raw, relations):
    token = raw.strip().casefold()
    from .cjk_circumstances import CIRCUMSTANCE_MARKERS

    if token in CIRCUMSTANCE_MARKERS and token != '如果':
        return [edge for edge in relations if edge.get('type') == 'narrative_circumstance_scope'
                and edge.get('left', {}).get('operator') == CIRCUMSTANCE_MARKERS[token]]
    if token in {"and", "or", "but", "并且", "並且", "以及"}:
        expected_operator = "and" if token in {"并且", "並且", "以及"} else token
        return [edge for edge in relations if edge.get("type") in {
            "proposition_coordination_scope", "narrative_coordination_scope", "narrative_logical_group", "narrative_alternative_scope",
            "narrative_nominal_coordination_scope"}
            and edge.get("left", {}).get("operator", expected_operator) == expected_operator]
    if token in {"not", "never"}:
        return [edge for edge in relations if edge.get("type") == "narrative_negation_scope"
                or edge.get("type") == "qualifier_scope" and edge.get("left", {}).get("type") in {"polarity", "modal_polarity"}]
    if token in {"if", "unless", "only if", "except", "except when", "except if", "如果", "只有", "除非"}:
        return [edge for edge in relations if edge.get("type") in {
            "condition_scope", "exception_scope", "narrative_condition_scope"}]
    if token in {"cannot", "shall", "must", "may", "can", "will", "should", "could", "would",
                 "必须", "必須", "应当", "應當", "可以", "不得", "不能", "不可以"}:
        return [edge for edge in relations if edge.get("type") == "narrative_modality_scope"
                or edge.get("type") == "qualifier_scope" and edge.get("left", {}).get("type") in {"modality", "modal_polarity", "polarity"}]
    return []  # An unsupported PP/operator cannot be relabelled as modality.


_TOC_DIRECTORY = re.compile(r"(?:.*?\bTable of Contents|Contents|.*?目[录錄])(?:\s*[（(](?:continued|续|續)[）)])?", re.I | re.S)
_TOC_PAGE_LABEL = re.compile(r"Pages?|页码|頁碼|页|頁", re.I)
_TOC_TITLE_LABEL = re.compile(r"Title|Entry|Section|Chapter|Contents?|条目|條目|标题|標題|章节|章節|目[录錄]項?", re.I)
_TOC_PARENT_LABEL = re.compile(r"Parent(?:\s+chapter)?|Group|Chapter|父章节|父章節|上[级級]章[节節]|父目[录錄]", re.I)


def _toc_source_bindings(inventory, graph):
    """Adapt existing navigation roles through actual selected source cuts.

    TOC facts deliberately have an empty narrative scope. Their ownership is
    the real directory, entry/page axes and original parent path, never a
    generic prose membership or a semantic_type/directory_evidence label.
    """
    materials = inventory["sources"]
    facts = [node for node in graph["nodes"] if node["id"] in graph["projections"]["B"]
             and (node.get("semantic_type") == "toc_page" or node.get("attribute") == "Page")]
    edges = [edge for edge in graph["relations"] if edge["id"] in graph["projections"]["L"]]
    controls = graph.get("context", {}).get("text_projection", {}).get("controls", [])

    def cut(origin, text=None):
        found = [(entry, span) for entry in materials if (span := _range(entry, origin)) is not None
                 and (text is None or entry["text"][span[0]:span[1]] == text)]
        return found[0] if len(found) == 1 else None

    def anchor(origin):
        found = cut(origin)
        return (found[0]["id"], found[1]) if found else None

    def same(origin, bound):
        return bound is not None and anchor(origin) == (bound[0]["id"], bound[1])

    def whole(entry):
        return (entry, (len(entry["text"]) - len(entry["text"].lstrip()), len(entry["text"].rstrip())))

    def heading_stack(entry):
        raw = [item for item in inventory["obligations"] if item.get("source_id") == entry["id"]
               and item.get("binding_role") == "heading_scope" and item.get("scope_is_absolute")
               and not item.get("scope_pending")]
        stack = raw[0]["required_scope"] if raw else entry.get("heading_scope", [])
        if not stack and inventory["authorized_raw_inventory"]["scope"] == "controlled_supplied_target_fixture":
            # Target-only software fixtures may omit the redundant heading
            # stack. Their actual supplied heading objects still prove it;
            # never use this fallback for a real authorized raw selection.
            levels = []
            for target in inventory["selection"]["targets"]:
                if target["id"] == entry["target_id"]:
                    break
                if target.get("kind") != "heading" or target["reference"].get("path") != entry["source"].get("path"):
                    continue
                level = target.get("heading_level") or 1
                levels = [(own, prior) for own, prior in levels if prior < level]
                levels.append(({"text": target["text"], "reference": target["reference"]}, level))
            stack = [own for own, _level in levels]
        result = []
        for heading in stack:
            found = cut(heading.get("reference", heading.get("source", {})), heading.get("text"))
            if not found or found[0]["source_kind"] != "heading" or found[1] != whole(found[0])[1]:
                return None
            result.append(found)
        return result

    def schema_control(entry):
        return any(control.get("reason") == "explicit_toc_title_parent_schema"
                   and same(control.get("source", {}), whole(entry))
                   and control.get("text") == entry["text"].strip() for control in controls)

    proofs, owners = defaultdict(list), defaultdict(set)
    for fact in facts:
        for origin in _walk(fact):
            if isinstance(origin.get("path"), str) and (found := cut(origin)):
                owners[found[0]["id"]].add(fact["id"])
        title = cut(fact.get("subject_source", fact.get("source", {}).get("subject_source", {})), fact.get("subject"))
        page = cut(fact.get("value_source", {}), fact.get("value"))
        if not title or not page or fact.get("scope") != [] or fact.get("attribute") != "Page":
            continue
        stack = heading_stack(title[0])
        if stack is None:
            continue
        directories = []
        invalid_directory = False
        for claim in fact.get("directory_evidence", []):
            found = cut(claim.get("source", {}), claim.get("text"))
            declaration = inventory['selection'].get('navigation_declaration', {})
            declared_directory = (found and declaration.get('role') == 'section_toc'
                                  and declaration.get('basis') == 'existing_selection_tag:section-toc'
                                  and _same_source(found[0]['source'], declaration.get('source', {})))
            if (not found or found[0]["source_kind"] != "heading" or not (
                    _TOC_DIRECTORY.fullmatch(found[0]["text"].strip()) or declared_directory)
                    or found[1] != whole(found[0])[1] or not any(found[0]["id"] == own[0]["id"] for own in stack)):
                invalid_directory = True
                break
            directories.append(found)
        if invalid_directory or len(directories) > 1 or stack and not directories:
            continue
        directory_index = next((index for index, item in enumerate(stack)
                                if directories and item[0]["id"] == directories[0][0]["id"]), None)
        parents = list(stack[directory_index + 1:]) if directory_index is not None else []
        schema = []
        headers = [cut(item.get("source", {}), item.get("text")) for item in fact.get("header_evidence", [])]
        headers = [item for item in headers if item and _TOC_PAGE_LABEL.fullmatch(item[0]["text"][item[1][0]:item[1][1]])]
        if len(headers) > 1 or headers and not same(fact.get("attribute_source", {}), headers[0]):
            continue
        attribute = headers[0] if headers else None
        if title[0].get("cell"):
            if attribute is None:
                continue
            cells = [entry for entry in materials if entry["target_id"] == title[0]["target_id"] and entry.get("cell")]
            band = min((entry["cell"].get("row", -1) for entry in cells), default=-1)
            title_headers = [entry for entry in cells if entry["cell"].get("row") == band
                             and _TOC_TITLE_LABEL.fullmatch(entry["text"].strip())]
            page_headers = [entry for entry in cells if entry["cell"].get("row") == band
                            and _TOC_PAGE_LABEL.fullmatch(entry["text"].strip())]
            if len(title_headers) != len(page_headers) or len(title_headers) != 1:
                continue
            th, ph = title_headers[0], page_headers[0]
            row = title[0]["cell"].get("row")
            if (not page[0].get("cell") or page[0]["target_id"] != title[0]["target_id"]
                    or row <= band or page[0]["cell"].get("row") != row
                    or title[0]["cell"].get("col") != th["cell"].get("col")
                    or page[0]["cell"].get("col") != ph["cell"].get("col")
                    or attribute[0]["id"] != ph["id"] or not schema_control(th)):
                continue
            schema.append(th)
            valid = True
            for header in cells:
                if header["cell"].get("row") != band or header["id"] in {th["id"], ph["id"]} or not _TOC_PARENT_LABEL.fullmatch(header["text"].strip()):
                    continue
                values = [entry for entry in cells if entry["cell"].get("row") == row
                          and entry["cell"].get("col") == header["cell"].get("col")]
                if len(values) != 1 or not schema_control(header):
                    valid = False
                    break
                schema.append(header)
                if values[0]["text"].strip():
                    parents.append(whole(values[0]))
            if not valid:
                continue
        else:
            # A declared directory supplies the page role. Its source-bound
            # title/separator/page slots need not repeat the word "Page".
            if (not directories or page[0]["id"] != title[0]["id"]
                    or attribute is not None and attribute[0]["id"] != title[0]["id"]):
                continue
            literal = title[0]["text"]
            a, b = title[1]
            p, q = page[1]
            page_first = (p == 0 and q <= a and b == len(literal)
                          and re.fullmatch(r'[ \t]+', literal[q:a]) is not None)
            if page_first:
                if attribute is not None or fact.get('attribute_source') is not None:
                    continue
            elif literal[:a].strip() or literal[q:].strip() or b > p:
                continue
            elif attribute is not None:
                c, d = attribute[1]
                if (not b <= c < d <= p or re.fullmatch(r"\s*[:：]?\s*", literal[b:c]) is None
                        or re.fullmatch(r"\s*[:：]?\s*", literal[d:p]) is None):
                    continue
            elif (fact.get('attribute_source') is not None
                    or re.fullmatch(r'\s*[:：]\s*|\s*[.．·…]{2,}\s*|\t+| {2,}', literal[b:p]) is None):
                continue
            valid = True
            for label in title[0].get("parents", []):
                originals = [entry for entry in materials if entry["text"] == label
                             and any(_same_source(entry["source"], own["source"]) for own in title[0].get("declared_parent_sources", []))]
                if len(originals) != 1:
                    valid = False
                    break
                parent = originals[0]
                # A page-first parent is itself a navigation entry: its title
                # has an independent local source, while its page is not part
                # of the child's identity. Validate the printed slot syntax.
                match = re.fullmatch(r'(?:\d+(?:[-–]\d+)?|[ivxlcdmIVXLCDM]+)[ \t]+(.+)', parent['text'])
                parents.append((parent, match.span(1)) if match else whole(parent))
            if not valid:
                continue
        parent_names = [entry["text"][span[0]:span[1]] for entry, span in parents]
        if fact.get("identity_facets", {}).get("toc_parent") != parent_names:
            continue
        rows = fact.get("row_evidence", [])
        if not any(item.get("text") == fact["subject"] and same(item.get("source", {}), title) for item in rows):
            continue
        if any(not any(item.get("title", item.get("text")) == name and same(item.get("source", {}), parent)
                       for item in rows) for name, parent in zip(parent_names, parents, strict=True)):
            continue
        data = fact.get("data_evidence", {})
        if data.get("text") != fact["value"] or not same(data.get("source", {}), page):
            continue

        def bound(edge, title=title, page=page, attribute=attribute, parents=parents):
            binding = edge.get("binding_evidence", {})
            return (same(binding.get("entry_source", {}), title) and same(binding.get("page_source", {}), page)
                    and (same(binding.get("attribute_source", {}), attribute) if attribute is not None
                         else binding.get('attribute_source') is None)
                    and [anchor(origin) for origin in binding.get("parent_sources", [])]
                    == [(entry["id"], span) for entry, span in parents])

        linked = [edge for edge in edges if edge.get("type") == "toc_entry_page"
                  and same(edge.get("binding_evidence", {}).get("entry_source", {}), title)]
        required_left = {"type": "toc_entry", "title": fact["subject"], "parent_path": parent_names}
        required_right = {"type": "toc_page_slot", "title": fact["subject"], "parent_path": parent_names}
        if (len(linked) != 1 or linked[0].get("left") != required_left or linked[0].get("right") != required_right
                or not same(linked[0].get("source", {}), page) or not bound(linked[0])):
            continue
        ancestry = [edge for edge in edges if edge.get("type") == "toc_parent"
                    and same(edge.get("binding_evidence", {}).get("entry_source", {}), title)]
        if parents:
            required_parent = {"type": "toc_entry_parent", "title": parent_names[-1], "parent_path": parent_names[:-1]}
            if (len(ancestry) != 1 or ancestry[0].get("left") != required_parent or ancestry[0].get("right") != required_left
                    or not same(ancestry[0].get("source", {}), title) or not bound(ancestry[0])):
                continue
        elif ancestry:
            continue
        evidence = {"role": "source_bound_toc_protocol", "requirement": fact["id"],
                    "relations": [edge["id"] for edge in [*linked, *ancestry]],
                    "heading_sources": [{"text": own[0]["text"], "source": copy.deepcopy(own[0]["source"])} for own in stack]}
        for material in [title[0], page[0], *([attribute[0]] if attribute is not None else []), *[own[0] for own in parents], *schema]:
            literal_spans = [title[1]] if material['id'] == title[0]['id'] else [
                own[1] for own in parents if own[0]['id'] == material['id']]
            proofs[material["id"]].append({**evidence, "span": [0, len(material["text"])],
                'literal_role_spans': [list(span) for span in literal_spans],
                "schema_control": material in schema})
    return {ident: values for ident, values in proofs.items()
            if owners[ident] <= {value["requirement"] for value in values}}


def toc_schema_control(entry, projected):
    """Bridge only an actually recorded TOC header control into legacy T."""
    text, source = entry["text"].strip(), entry["source"]
    if not (entry.get("kind") == "cell" and entry.get("native", {}).get("is_column_header")
            and (_TOC_TITLE_LABEL.fullmatch(text) or _TOC_PARENT_LABEL.fullmatch(text))):
        return None
    controls = [control for control in projected.get("text_projection", {}).get("controls", [])
                if control.get("reason") == "explicit_toc_title_parent_schema" and control.get("text") == text
                and _range(entry, control.get("source", {})) == (0, len(entry["text"]))]
    for edge in projected.get("relations", []):
        binding = edge.get("binding_evidence", {})
        if edge.get("type") != "toc_entry_page":
            continue
        origins = [binding.get("entry_source", {})] if _TOC_TITLE_LABEL.fullmatch(text) else binding.get("parent_sources", [])
        if controls and any(origin.get("path") == source.get("path") and origin.get("lines") == source.get("lines")
                            and origin.get("col", origin.get("column")) == source.get("column")
                            and type(origin.get("row")) is int and origin["row"] > source.get("row", -1)
                            for origin in origins):
            return {"control": copy.deepcopy(controls[0]), "relation": copy.deepcopy(edge)}
    return None


def _structural_evidence(entry, graph, bound_relations):
    """Explain finite printed syntax only when its graph bindings still exist."""
    text, source = entry["text"], entry["source"]
    evidence = []
    # The entire printed key of a closed scalar record is a literal role.
    # Words such as AND or a terminal participle in that key are not separate
    # sentence operators. Require the original delimiter/value and an actual
    # field binding; a source label or a retained node alone is insufficient.
    from .measurement_evidence import read_measurement_literal
    from .source_requirements import _ASSERTED_LABEL

    for fact in graph['nodes']:
        if fact.get('predicate') or fact.get('logic'):
            continue
        label = _range(entry, fact.get('attribute_source', {}))
        value = _range(entry, fact.get('value_source', {}))
        if (not label or not value or label[0] != 0 or label[1] > value[0]
                or text[slice(*label)] != fact.get('attribute')
                or text[slice(*value)] != fact.get('value')
                or _ASSERTED_LABEL.search(text[slice(*label)])
                or re.fullmatch(r'\s*[:：=]\s*', text[label[1]:value[0]]) is None
                or text[value[1]:].strip(' .。')):
            continue
        literal = text[slice(*value)].rstrip('.。')
        predicate_hits = list(_PREDICATE.finditer(_syntax_mask(text[slice(*label)])))
        if predicate_hits and (len(predicate_hits) != 1 or predicate_hits[0].end() != label[1]
                               or not predicate_hits[0][0].casefold().endswith('ed')):
            continue  # An unresolved finite verb cannot be certified by a scalar alone.
        atomic = read_measurement_literal(literal[:-1] if literal.endswith('+') else literal)
        edges = [edge for edge in bound_relations(fact) if edge['type'] == 'field_binding']
        if atomic['matched'] and edges:
            evidence.append({'span': list(label), 'role': 'source_bound_atomic_scalar_key',
                'requirement': fact['id'], 'value_source': copy.deepcopy(fact['value_source']),
                'relations': [edge['id'] for edge in edges]})
    for fact in graph['nodes']:
        if fact.get('semantic_type') != 'printed_position_list':
            continue
        bounds = _range(entry, fact.get('subject_source', {}))
        edges = [edge for edge in bound_relations(fact) if edge.get('type') == 'record_label_scope'
                 and edge.get('source') == fact.get('subject_source')
                 and edge.get('left') == {'record_subject': fact.get('subject')}]
        if (bounds and bounds[0] == 0 and text[slice(*bounds)] == fact.get('subject')
                and text[bounds[1]:].startswith((';', '；')) and edges):
            evidence.append({'span': list(bounds), 'role': 'printed_person_record_label',
                             'relations': [edge['id'] for edge in edges]})
    for node in _walk(graph.get('logic', [])):
        if node.get('kind') == 'discourse_scope' and node.get('role') == 'item_label':
            bounds = _range(entry, node.get('marker_source', {}))
            edges = [edge for edge in graph['relations'] if edge.get('type') == 'narrative_discourse_scope'
                     and edge.get('source') == node.get('marker_source')
                     and edge.get('left') == {'operator': 'enumeration', 'role': 'item_label', 'marker': node.get('marker')}]
            if bounds and edges and re.fullmatch(r'[A-Za-z][.)]', text[slice(*bounds)]):
                evidence.append({'span': list(bounds), 'role': 'printed_enumeration_marker',
                                 'relations': [edge['id'] for edge in edges]})
    if re.fullmatch(r'[變变][動动化]分析[:：]', text.strip()):
        members = [edge for edge in graph['relations'] if edge.get('type') == 'prose_heading_membership'
                   and _range(entry, edge.get('source', {})) == (0, len(text))]
        for member in members:
            forward = [edge for edge in graph['relations'] if edge.get('type') == 'prose_reading_order'
                       and edge.get('left') == member['right']]
            if forward:
                evidence.append({'span': [0, len(text)], 'role': 'printed_analysis_label_and_following_prose',
                                 'relations': [member['id'], *(edge['id'] for edge in forward)]})
    for node in _walk(graph.get('logic', [])):
        if node.get('kind') != 'fronted_context' or node.get('operator') != 'according_to':
            continue
        from .fronted_nominal_context import validate_fronted_operation

        def basis_literal(origin, label):
            bounds = _range(entry, origin or {})
            return text[slice(*bounds)] if bounds else None
        try:
            validate_fronted_operation(node, basis_literal)
        except (ValueError, KeyError):
            continue
        edges = [edge for fact in graph['nodes'] if fact.get('kind') in {'business', 'business_fact', 'semantic_operand'} or fact['id'] in graph['projections']['B']
                 for edge in bound_relations(fact) if edge.get('type') == 'narrative_fronted_context_scope'
                 and edge.get('source') == node['operator_source']
                 and edge.get('binding_evidence', {}).get('context_phrase') == node['context_phrase']]
        if edges:
            for part in _walk(node['context_phrase']):
                if part.get('kind') == 'cjk_dependency' and (bounds := _range(entry, part.get('marker_source', {}))):
                    evidence.append({'span': list(bounds), 'role': 'source_bound_basis_nominal_action',
                                     'relations': [edge['id'] for edge in edges]})
    declarations = [i for i in graph.get('context', {}).get('syntax', [])
                    if i.get('semantic_role') == 'qualifier_declaration' and i.get('text') == text
                    and _range(entry, i['source']) == (0, len(text))]
    for declaration in declarations:
        from .cjk_circumstances import validate_cjk_nominal
        from .series_requirements import read_series_context

        context = read_series_context(text, source, scope=declaration.get('scope', []))
        if context.get('caption') and not context['blockers'] and context == declaration.get('qualifier_caption'):
            try:
                validate_cjk_nominal(context['caption']['logic'], lambda origin, label: entry['text'][slice(*_range(entry, origin))]
                                     if _range(entry, origin) is not None else None)
            except ValueError:
                continue
            owners = [f for f in graph['nodes'] if f['id'] in graph['projections']['B']
                      and f.get('qualifiers', {}).get('table_caption') == context['caption']['text']
                      and f.get('qualifier_sources', {}).get('table_caption') == context['caption']['source']]
            edges = [e for f in owners for e in bound_relations(f) if e.get('type') == 'qualifier_scope'
                     and e.get('left') == {'type': 'table_caption', 'text': context['caption']['text']}
                     and e.get('source') == context['caption']['source']]
            if edges:
                evidence.append({'span': [0, len(text)], 'role': 'source_bound_caption_and_unit_scope', 'relations': [e['id'] for e in edges]})
    emphasis = re.match(r'\s*(?P<open>\*\*|__)[^:：=\n*]+[:：=](?P<close>\*\*|__)\s*\S', text)
    if emphasis and emphasis['open'] == emphasis['close']:
        evidence.extend({'span': list(emphasis.span(key)), 'role': 'balanced_field_label_emphasis'} for key in ('open', 'close'))
    for fact in graph['nodes']:
        label = fact.get('field_label_evidence', {})
        bounds = _range(entry, label.get('source', {}))
        if not bounds or text[slice(*bounds)] != label.get('text') or (fact.get('scope') or [None])[-1] != label.get('text'):
            continue
        edges = [edge for edge in bound_relations(fact) if edge.get('type') == 'field_binding'
                 and (edge.get('right', {}).get('scope') or [None])[-1] == label['text']]
        if edges:
            evidence.append({'span': list(bounds), 'role': 'source_bound_printed_field_owner',
                             'requirement': fact['id'], 'relations': [edge['id'] if 'id' in edge else
                                f"operand-edge:{graph.get('operand_relations', []).index(edge)}" for edge in edges]})
    from .series_requirements import _METRIC_PARENT

    if entry["has_children"] and (re.fullmatch(
            r"[^:：;；。！？!?\n]+?(?:\s+attributable\s+to|[归歸][属屬][于於])\s*[:：]?", text.strip(), re.I)
            or _METRIC_PARENT.fullmatch(text.strip())):
        declared = [binding for binding in graph.get("context", {}).get("parent_bindings", [])
                    if binding.get("parent", {}).get("text") == text
                    and _range(entry, binding["parent"].get("source", {})) == (0, len(text))]
        owners = [fact for fact in graph["nodes"] if fact["id"] in graph["projections"]["B"]
                  and fact.get("attribute") == text and _range(entry, fact.get("attribute_source", {})) == (0, len(text))]
        edges = [edge for fact in owners for edge in bound_relations(fact)
                 if edge.get("type") == "field_binding"]
        if declared and edges:
            evidence.append({"span": [0, len(text)], "role": "printed_attribution_parent_declaration",
                             "relations": [edge["id"] for edge in edges]})
    targets = graph.get("source_obligation_inventory", {}).get("selection", {}).get("targets", [])
    # The declaration owns its source roles and raw collection scope even
    # when a child's business syntax is unknown. It never proves that child's
    # fact-to-collection endpoint; those obligations remain independently pending.
    from .enumeration_context import enumeration_declaration

    for context in graph.get("context", {}).get("enumeration_contexts", []):
        declaration = context.get("declaration", {})
        if (declaration.get("introduction", {}).get("text") != text
                or _range(entry, context.get("source", {})) != (0, len(text))
                or not declaration.get("lexical_complete")
                or not context.get("members")):
            continue
        roles = declaration.get("roles", {})
        if not all((bounds := _range(entry, item.get("source", {}))) is not None
                   and text[bounds[0]:bounds[1]] == item.get("text") for item in roles.values()):
            continue
        required = enumeration_declaration(context)
        edges = [edge for edge in graph["relations"] if edge.get("type") == "enumeration_declaration"
                 and all(edge.get(key) == required[key] for key in ("left", "right", "source", "binding_evidence"))]
        if edges:
            evidence.append({"span": [0, len(text)], "role": "printed_enumeration_declaration",
                             "relations": [edge["id"] for edge in edges]})
    for context in graph.get('context', {}).get('financial_summary_contexts', []):
        bounds = _range(entry, context.get('cue_source', {}))
        if bounds and text[slice(*bounds)].strip() in {'其中:', '其中：'}:
            edges = [e for e in graph['relations'] if e.get('type') == 'qualifier_scope'
                     and e.get('left') == {'type': 'membership_operator', 'text': '其中'}
                     and e.get('source') == context['marker_source']
                     and e.get('binding_evidence', {}).get('financial_summary', {}).get('introduction_source') == context['source']]
            if edges:
                evidence.append({'span': list(bounds), 'role': 'printed_financial_summary_membership',
                                 'relations': [e['id'] for e in edges]})
    # Composition glue is limited to the actual syntax between already bound
    # page/component/document roles. No whole statement is exempted.
    composition = re.fullmatch(r"第\d+[页頁]至第\d+[页頁](?P<glue>所[载載][的之])"
        r"(?:附注|附註)[为為乃](?:本|该|該|此|上述)(?:合并|合併|简明|簡明|中期|年度)*"
        r"(?:财务报表|財務報表)(?:摘要)?(?P<link>[的之])(?:组成部分|組成部分)[。.]?", text)
    if composition and any(edge.get("type") == "document_part_of"
            and _same_statement(_origin(source, 0, len(text)), edge.get("binding_evidence", {}).get("statement_source", {}))
            for edge in graph["relations"]):
        evidence.extend({"span": list(composition.span(key)), "role": "printed_composition_syntax",
                         "requirement": "source_bound_document_part_of"} for key in ("glue", "link"))
    english_page_link = re.search(r"\bon\b(?=\s+pages?\s+\d+\s+to\s+\d+\s+(?:is|are)\s+part\s+of\b)", text, re.I)
    if english_page_link and any(edge.get("type") == "document_part_of"
            and _same_statement(_origin(source, 0, len(text)), edge.get("binding_evidence", {}).get("statement_source", {}))
            for edge in graph["relations"]):
        evidence.append({"span": list(english_page_link.span()), "role": "printed_component_page_link",
                         "requirement": "source_bound_document_part_of"})
    for reported in re.finditer(r"\b(?:say|says|said|report|reports|reported|state|states|stated)(?P<link>\s+that\s+)", _syntax_mask(text), re.I):
        predicate = _origin(source, reported.start(), reported.start("link"))
        edges = [edge for edge in graph["relations"] if edge.get("type") == "narrative_reporting_scope"
                 and edge.get("source") == predicate]
        if edges:
            evidence.append({"span": list(reported.span("link")), "role": "printed_reporting_complement",
                             "relations": [edge["id"] for edge in edges]})
    temporal = re.match(r"\s*(?P<operator>In|During)\s+(?:[A-Za-z]+\s+)?(?:19|20)\d{2}\s*,", text, re.I)
    if temporal:
        edges = [edge for edge in graph["relations"] if edge.get("type") == "narrative_temporal_scope"
                 and _range(entry, edge.get("source", {})) == temporal.span("operator")]
        edges.extend(edge for edge in graph["relations"] if edge.get("type") == "qualifier_scope"
                     and edge.get("left", {}).get("type") == "period" and any(
                         temporal.end("operator") <= a < b < temporal.end()
                         for a, b in _ranges(entry, edge.get("source", {}))))
        if edges:
            evidence.append({"span": list(temporal.span("operator")), "role": "printed_temporal_operator",
                             "relations": [edge["id"] for edge in edges]})
    if entry["has_children"] and re.fullmatch(
            r"(?:non[- ]current\s+|current\s+)?(?:assets|liabilities)|(?:owners['’]?\s+)?equity|(?:非流[动動]|流[动動])?(?:[资資][产產]|[负負][债債])|所有者[权權]益", text.strip(), re.I):
        position_heading = any(target.get("kind") == "heading" and re.fullmatch(
            r"(?:(?:condensed|consolidated)\s+)*(?:statement[s]? of financial position|balance sheets?)|(?:合并|合併)?(?:[资資][产產][负負][债債]表|[财財]务[状狀][况況]表)", target.get("text", ""), re.I) for target in targets)
        owners = [fact for fact in graph["nodes"] if fact["id"] in graph["projections"]["B"]
                  and text in fact.get("identity_facets", {}).get("group", [])
                  and any(proof.get("text") == text and _range(entry, proof.get("source", {})) == (0, len(text))
                          for proof in fact.get("row_evidence", []))]
        edges = [edge for fact in owners for edge in bound_relations(fact)
                 if edge.get("type") == "field_binding"]
        if position_heading and edges:
            evidence.append({"span": [0, len(text)], "role": "printed_financial_classification_parent",
                             "relations": [edge["id"] for edge in edges]})
    for node in _walk(graph.get("logic", [])):
        if node.get('kind') == 'coordination' and node.get('mode') == 'circumstance_operations' and node.get('shared_actor'):
            from .cjk_circumstances import _ACTOR, _leaves

            bounds = _range(entry, node.get('shared_actor_source', {}))
            origin = _range(entry, node.get('source', {}))
            leaves = _leaves(node)
            bank = [fact for fact in graph['nodes'] if fact.get('kind') == 'semantic_operand']
            owners = [fact for leaf in leaves for fact in bank if all(fact.get(key) == leaf.get(key)
                      for key in ('subject_source', 'predicate_source', 'object_source')) and bound_relations(fact)]
            scope_edges = [edge for edge in graph['relations'] if edge.get('type') == 'narrative_circumstance_scope'
                           and any(own == node for own in _walk(edge.get('binding_evidence', {}).get('operand_logic', {})))
                           and any(validate_relation_binding(None, fact, edge)['equivalent'] for fact in graph['nodes']
                                   if fact['id'] in graph['projections']['B'])]
            if (bounds and origin and bounds[0] == origin[0] and text[slice(*bounds)] == node['shared_actor']
                    and _ACTOR.fullmatch(node['shared_actor']) and leaves and len(owners) == len(leaves) and scope_edges):
                evidence.append({'span': list(bounds), 'role': 'source_bound_shared_cause_actor',
                                 'relations': [e['id'] for e in scope_edges]})
        if node.get("kind") != "discourse_scope":
            continue
        bounds = _range(entry, node.get("marker_source", {}))
        if bounds is None or text[bounds[0]:bounds[1]] != node.get("marker"):
            continue
        literal_operator = re.sub(r"\s+", "_", node["marker"].casefold())
        literal_roles = {"for_example": "example", "for_instance": "example", "however": "contrast",
                         "moreover": "addition", "in_addition": "addition", "in_particular": "focus"}
        if literal_operator != node.get("operator") or node.get("role") != literal_roles.get(literal_operator):
            continue
        edges = [edge for edge in [*graph["relations"], *graph.get("operand_relations", [])]
                 if edge.get("type") == "narrative_discourse_scope"
                 and edge.get("left", {}).get("operator") == node["operator"]
                 and edge.get("left", {}).get("role") == node.get("role")
                 and edge.get("binding_evidence", {}).get("marker_source") == node["marker_source"]
                 and any(validate_relation_binding(None, fact, edge)["equivalent"]
                         and any(_same_statement(child.get("source", {}), fact.get("statement_source", fact.get("source", {})))
                                 for child in _walk(node.get("child", {})) if child.get("kind") == "proposition")
                         for fact in graph["nodes"] if fact["id"] in graph["projections"]["B"])]
        if edges:
            evidence.append({"span": list(bounds), "role": "source_bound_discourse_marker",
                             "relations": [edge["id"] for edge in edges]})
    return evidence


def _text_syntax_evidence(entry):
    """Only delimiters proved by the original printed field/header syntax."""
    text, evidence = entry["text"], []
    emphasis = re.match(r'\s*(?P<open>\*\*|__)[^:：=\n*]+[:：=](?P<close>\*\*|__)\s*\S', text)
    if emphasis and emphasis['open'] == emphasis['close']:
        evidence.extend({'span': list(emphasis.span(key)), 'role': 'balanced_field_label_emphasis'} for key in ('open', 'close'))
    if _DECLARATION.fullmatch(text.strip()):
        label = re.search(r"(?:Units?|Currency|Period|Year|(?:金[額额])?(?:单位|單位)|币种|幣種|期间|期間|年度)\s*[:：=]", text, re.I)
        if label:
            evidence.append({"span": list(label.span()), "role": "printed_qualifier_declaration_key"})
    if re.fullmatch(r"(?:Note|Notes|附注|附註|注)\s*[:：]", text.strip(), re.I):
        colon = max(text.rfind(":"), text.rfind("："))
        evidence.append({"span": [colon, colon + 1], "role": "printed_empty_note_label_delimiter"})
    for a, b in _segments(text):
        fragment = text[a:b]
        field = re.match(r"\s*(?P<label>[^:：=\n]{1,160})(?P<delimiter>[:：=])\s*\S", fragment)
        if (field and not _PREDICATE.search(_syntax_mask(field["label"]))
                and field["label"].strip().casefold() not in {"http", "https", "mailto"}
                and not fragment[field.end("delimiter"):].startswith("//")):
            evidence.append({"span": [a + field.start("delimiter"), a + field.end("delimiter")],
                             "role": "printed_field_delimiter"})
        if fragment.endswith((";", "；")):
            evidence.append({"span": [b - 1, b], "role": "printed_fragment_separator"})
    if entry.get("cell") and any(entry["cell"].get(key) for key in
            ("is_column_header", "column_header", "is_row_header", "row_header", "native_header_tag")):
        from .measurement_evidence import read_unit_token

        for match in re.finditer(r"[（(]([^()（）]+)[）)]", text):
            if not read_unit_token(match[1])["matched"]:
                continue
            evidence.extend({"span": [index, index + 1], "role": "printed_header_qualifier_delimiter"}
                            for index in (match.start(), match.end() - 1))
    return evidence


def _text_node_evidence(entry, node):
    evidence = []
    for a, b in _ranges(entry, node.get("source", {})):
        if entry["text"][a:b] == node["text"]:
            evidence.append({"span": [a, b], "requirement": node["id"], "role": "text"})
    for origin in node.get("origins", []):
        for a, b in _ranges(entry, origin.get("source", {})):
            if entry["text"][a:b] == origin.get("text") == node["text"]:
                evidence.append({"span": [a, b], "requirement": node["id"], "role": "retained_literal_origin"})
    originals, texts = node.get("source_fragments", []), node.get("source_fragment_texts", [])
    if originals and len(originals) == len(texts):
        cursor = 0
        for origin, fragment in zip(originals, texts, strict=True):
            start = node["text"].find(fragment.strip(), cursor)
            if start < 0:
                break
            cursor = start + len(fragment.strip())
            for a, b in _ranges(entry, origin):
                if re.sub(r"\s+", " ", entry["text"][a:b]).strip() == re.sub(r"\s+", " ", fragment).strip():
                    evidence.append({"span": [a, b], "requirement": node["id"], "role": "joined_literal_fragment"})
    return evidence


def _text_field_delimiters(entry, text_nodes):
    """Bridge only syntax between two exact, independently retained T roles.

    A lexical word such as "Report" in a field label does not invalidate its
    original delimiter. This proof neither interprets that label's business
    meaning nor discharges any B/L obligation.
    """
    labels = []
    for node in text_nodes:
        span = _range(entry, node.get("source", {}))
        if node.get("role") == "label" and span and entry["text"][slice(*span)] == node["text"]:
            labels.append((node, span))
    evidence = []
    for value in text_nodes:
        origin = value.get("source", {})
        span = _range(entry, origin)
        label_span = _range(entry, origin.get("attribute_source", {}))
        if (value.get("role") != "value" or not span or not label_span
                or entry["text"][slice(*span)] != value["text"] or label_span[1] > span[0]):
            continue
        for label, retained_span in labels:
            if retained_span != label_span:
                continue
            delimiter = entry["text"][label_span[1]:span[0]]
            if re.fullmatch(r"\s*[:：=]\s*", delimiter):
                evidence.append({"span": [label_span[1], span[0]], "role": "printed_field_delimiter",
                                 "requirements": [label["id"], value["id"]]})
                break
    return evidence


def _compact_source_bindings(inventory, graph, bound_relations):
    """Audit printed columns against their actual record slots, independently.

    Reader success and column IDs are not proof. Every label, year, unit and
    value must occupy its declared slot in the original text and own an edge.
    This is a finite schema/record audit, never a narrative-text exemption.
    """
    from .measurement_evidence import read_measurement_literal, read_unit_token

    entries = inventory["sources"]
    facts = [node for node in graph["nodes"] if node["id"] in graph["projections"]["B"]]
    result = defaultdict(list)
    for declaration in graph.get("context", {}).get("compact_schemas", []):
        schema, text = declaration["schema"], declaration["text"]
        own = next((e for e in entries if _range(e, schema["source"]) == (0, len(text)) and e["text"] == text), None)
        if own is None:
            continue
        intro = re.search(r"各[項项]分[別别]列示|列[說说]明\s*[:：]|Columns?\s*[:：]", text, re.I)
        if not intro:
            continue
        columns, header, valid = schema.get("columns", []), [], True
        years = list(re.finditer(r"(?:19|20)\d{2}年?", text[intro.end():]))
        if len(years) != 2 or [m[0] for m in years] != schema.get("periods"):
            continue
        previous = intro.end()
        for index, column in enumerate(columns):
            bounds = _range(own, column.get("source", {}))
            label = column.get("attribute", "")
            patterns = {"amount": r"金[額额]|Amount", "share": r"[佔占][^、，,;；。\n（）()]*?比|Share|Ratio|Percentage|比例",
                        "change": r"(?:金[額额]|[佔占][^、，,;；。\n（）()]*?比重?)(?:同比|按年)(?:[變变][動动]|[變变]化|增[減减])|(?:Amount\s+)?(?:YoY|year.on.year)(?:\s+change)?"}
            if (not bounds or bounds[0] < previous or column.get("id") != f"column:{index}"
                    or text[slice(*bounds)] != label or not re.fullmatch(patterns.get(column.get("kind"), r"(?!)"), label, re.I)):
                valid = False
                break
            previous = bounds[1]
            header.append({"span": list(bounds), "role": "declared_column_label"})
            if column["kind"] != "change":
                year = _range(own, column.get("period_source", {}))
                preceding = [m for m in re.finditer(r"(?:19|20)\d{2}年?", text[:bounds[0]]) if m.start() >= intro.end()]
                if not year or text[slice(*year)] != column.get("period") or not preceding or year != preceding[-1].span():
                    valid = False
                    break
                header.append({"span": list(year), "role": "declared_column_period"})
            if column.get("unit"):
                unit = _range(own, column.get("unit_source", {}))
                if not unit or text[slice(*unit)] != column["unit"] or not read_unit_token(column["unit"])["matched"]:
                    valid = False
                    break
                if unit[0] < intro.start():
                    caption = re.search(r"(?:(?:金[額额])?(?:單位|单位)|Units?)\s*[:：=]\s*", text[:intro.start()], re.I)
                    if column["kind"] != "amount" or not caption or unit[0] != caption.end():
                        valid = False
                        break
                elif (not re.fullmatch(r"\s*[（(]\s*", text[bounds[1]:unit[0]])
                      or not re.match(r"\s*[)）]", text[unit[1]:])):
                    valid = False
                    break
                else:
                    header.extend({"span": [i, i + 1], "role": "bound_unit_bracket", "control": True}
                                  for i in range(bounds[1], unit[0]) if text[i] in "(（")
                    close = re.match(r"\s*[)）]", text[unit[1]:])
                    header.append({"span": [unit[1], unit[1] + close.end()], "role": "bound_unit_bracket", "control": True})
                header.append({"span": list(unit), "role": "declared_column_unit"})
        if not valid or len(columns) < 4:
            continue
        for left, right in zip(columns, columns[1:], strict=False):
            end = _range(own, left['source'])[1]
            unit = _range(own, left.get('unit_source', {}))
            if unit and unit[0] >= end:
                end = unit[1]
            begin = _range(own, right['source'])[0]
            period = _range(own, right.get('period_source', {}))
            if period and period[0] >= end:
                begin = period[0]
            gap = text[end:begin]
            if re.fullmatch(r'[\s，,、;；()（）.。]*(?:及|和|and)[\s，,、;；()（）.。]*', gap, re.I):
                for connector in re.finditer(r'及|和|and', gap, re.I):
                    header.append({'span': [end + connector.start(), end + connector.end()],
                                   'role': 'bound_column_connector', 'control': True})
        header.append({"span": list(intro.span()), "role": "bound_column_introduction", "control": True})
        for key, value in schema.get("qualifiers", {}).items():
            bounds = _range(own, schema.get("qualifier_sources", {}).get(key, {}))
            if not bounds or text[slice(*bounds)] != value:
                valid = False
                break
            header.append({"span": list(bounds), "role": "declared_column_" + key})
        caption = re.search(r"(?:(?:金[額额])?(?:單位|单位)|Units?)\s*[:：=]\s*", text[:intro.start()], re.I)
        if caption:
            header.append({"span": list(caption.span()), "role": "bound_unit_declaration_key", "control": True})
        if not valid or _residue(text, (0, len(text)), header):
            continue
        covered_columns, record_proofs = set(), defaultdict(list)
        for fact in facts:
            binding = fact.get("compact_column", {})
            if binding.get("schema_source") != schema["source"]:
                continue
            column = next((c for c in columns if c["id"] == binding.get("id")), None)
            if column is None or fact.get("attribute") != column["attribute"] or fact.get("attribute_source") != column["source"]:
                continue
            edges = bound_relations(fact)
            if not any(edge["type"] == "field_binding" for edge in edges):
                continue
            row = next((e for e in entries if _range(e, fact.get("source", {})) and e["source_kind"] != "fragment"), None)
            if row is None:
                continue
            raw = row["text"]
            value = _range(row, fact.get("source", {}))
            slots, syntax = [], []
            for a, b in _segments(raw):
                segment = raw[a:b].rstrip(";；。.")
                offset = a
                label = re.match(r"([^:：]+)[:：]\s*(?=(?:19|20)\d{2}年?)", segment)
                if label:
                    syntax.append({"span": [offset, offset + label.end(1)], "role": "printed_record_subject"})
                    offset += label.end()
                    segment = segment[label.end():]
                period = re.match(r"((?:19|20)\d{2}年?)\s*[:：，,]?\s*", segment)
                selected = []
                if period:
                    syntax.append({"span": [offset, offset + period.end(1)], "role": "printed_record_period"})
                    selected = [c for c in columns if c.get("period") == period[1] and c["kind"] != "change"]
                    offset += period.end()
                    segment = segment[period.end():]
                else:
                    changed = next((c for c in columns if c["kind"] == "change" and segment.startswith(c["attribute"])), None)
                    if changed:
                        syntax.append({"span": [offset, offset + len(changed["attribute"])], "role": "printed_record_change"})
                        offset += len(changed["attribute"])
                        segment = segment[len(changed["attribute"]):]
                        selected = [changed]
                    elif len(list(_segments(raw))) == 1 and "、" in segment:
                        locator = re.match(r"[^:：]+[:：]\s*", segment)
                        if locator:
                            syntax.append({"span": [offset, offset + locator.end() - 1], "role": "printed_record_subject"})
                            offset += locator.end()
                            segment = segment[locator.end():]
                            selected = columns
                field = re.fullmatch(r"\s*([^:：]+)[:：]\s*(.*)", segment)
                if field:
                    selected = [c for c in selected if c["attribute"] == field[1].strip()]
                    syntax.append({"span": [offset + field.start(1), offset + field.end(1)], "role": "printed_record_label"})
                    offset += field.start(2)
                    segment = field[2]
                else:
                    spaces = re.match(r"\s*[:：]?\s*", segment).end()
                    offset += spaces
                    segment = segment[spaces:]
                pieces = list(re.finditer(r"[^、]+", segment))
                if len(selected) == len(pieces):
                    for c, piece in zip(selected, pieces, strict=True):
                        left = offset + piece.start() + len(piece[0]) - len(piece[0].lstrip())
                        right = offset + piece.end() - (len(piece[0]) - len(piece[0].rstrip()))
                        slots.append((c, (left, right)))
            if not any(c["id"] == column["id"] and span == value for c, span in slots):
                continue
            printed = read_measurement_literal(raw[slice(*value)], fact["source"])
            if not printed["matched"] or printed["value"] != fact["value"]:
                continue
            required = dict(schema.get("qualifiers", {}))
            origins = dict(schema.get("qualifier_sources", {}))
            if column["kind"] == "change":
                for key, period in zip(("to_period", "from_period"), schema["periods"], strict=True):
                    required[key] = period
                    origins[key] = next(c["period_source"] for c in columns if c.get("period") == period)
            else:
                required["period"], origins["period"] = column["period"], column["period_source"]
            unit = printed["unit"] or column.get("unit")
            if unit:
                unit_origin = printed["sources"].get("unit") or column["unit_source"]
                unit_info = read_unit_token(unit, unit_origin)
                required["unit"], origins["unit"] = unit, unit_origin
                if unit_info["currency"]:
                    required["currency"], origins["currency"] = unit_info["currency"], unit_info["sources"]["currency"]
            if any(fact.get("qualifiers", {}).get(k) != v
                   or not _same_source(fact.get("qualifier_sources", {}).get(k, {}), origins[k])
                   or fact.get("qualifier_sources", {}).get(k, {}).get("text_span") != origins[k].get("text_span")
                   or not any(e["type"] == "qualifier_scope" and e.get("left") == {"type": k, "text": v} for e in edges)
                   for k, v in required.items()):
                continue
            if any(k in fact.get("qualifiers", {}) and k not in required for k in
                   ("unit", "currency", "period", "period_basis", "from_period", "to_period")):
                continue
            covered_columns.add(column["id"])
            proof = {"span": list(value), "role": "source_bound_compact_value", "requirement": fact["id"],
                     "relations": [e["id"] for e in edges]}
            record_proofs[row["id"]].extend([proof, *syntax])
            for item in fact.get("row_evidence", []):
                for entry in entries:
                    span = _range(entry, item.get("source", {}))
                    if span and entry["text"][slice(*span)] == item["text"]:
                        record_proofs[entry["id"]].append({"span": list(span), "role": "source_bound_compact_row", "requirement": fact["id"]})
        for ident, evidence in record_proofs.items():
            result[ident].extend(evidence)
        if covered_columns == {c["id"] for c in columns}:
            result[own["id"]].extend(header)
    return result


def audit_source_obligations(inventory: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    """Explain each independent obligation or retain precise pending evidence."""
    sources = {entry["id"]: entry for entry in inventory["sources"]}
    nodes = {node["id"]: node for node in graph["nodes"]}
    text_nodes = [nodes[ident] for ident in graph["projections"]["T"]]
    facts = [nodes[ident] for ident in graph["projections"]["B"]]
    operands = [node for node in graph["nodes"] if node.get("kind") == "semantic_operand"]
    relations = [*graph["relations"], *graph.get("operand_relations", [])]
    role_conflicts = {entry["id"]: {fact["id"]: conflicts for fact in [*facts, *operands]
                     if (conflicts := proposition_role_conflicts(entry, fact))} for entry in inventory["sources"]}
    rejected = {ident for local in role_conflicts.values() for ident in local}
    facts = [fact for fact in facts if fact["id"] not in rejected]
    operands = [fact for fact in operands if fact["id"] not in rejected]
    fact_by_id = {fact["id"]: fact for fact in [*facts, *operands]}
    attachment_obligations = defaultdict(list)
    for item in inventory["obligations"]:
        if item.get("binding_role") == "attachment":
            attachment_obligations[item.get("source_id")].append(item)
    toc_bindings = _toc_source_bindings(inventory, graph)
    bound_cache, role_cache, structural_cache, heading_cache, fact_source_cache = {}, {}, {}, {}, {}

    def bound_relations(fact):
        key = id(fact)
        if key not in bound_cache:
            bound_cache[key] = _bound_relations(fact, relations)
        return bound_cache[key]

    compact_bindings = _compact_source_bindings(inventory, graph, bound_relations)
    # This evidence depends on the record's source, not the current obligation
    # or role. Preserve the original ordered membership predicate once rather
    # than scan every fact inside the obligation/fact/role loops.
    companion_groups = defaultdict(list)
    for fact in facts:
        if fact.get('header_evidence') and bound_relations(fact):
            companion_groups[json.dumps(fact.get('subject_source'), sort_keys=True)].append(fact)

    def operator_binding(edge):
        if edge.get("type") == "proposition_coordination_scope":
            members = edge.get("binding_evidence", {}).get("members", [])
            return len(members) >= 2 and all(any(
                all(member.get(key) == fact.get(key) for key in ("subject_source", "predicate_source", "object_source"))
                and any(own.get("type") == "field_binding" for own in bound_relations(fact))
                for fact in [*facts, *operands]) for member in members)
        if edge.get("fact_id") is not None:
            owners = [fact_by_id[edge["fact_id"]]] if edge["fact_id"] in fact_by_id else []
        else:
            endpoint = edge.get("right", {})
            owners = [fact for fact in [*facts, *operands] if isinstance(endpoint, dict)
                      and endpoint.get("subject") == fact.get("subject")
                      and endpoint.get("attribute", endpoint.get("action")) == fact.get("attribute")]
        return any(validate_relation_binding(None, fact, edge)["equivalent"] for fact in owners)

    rows = []
    for obligation in inventory["obligations"]:
        status, proof, reason = "pending", [], "source_obligation_has_no_independent_explanation"
        entry = sources.get(obligation["source_id"])
        if obligation["kind"] == "authorization_dependency":
            declaration = obligation["declaration"]
            # Non-heading dependencies remain explicit until actual selected
            # evidence resolves them; do not import external answer text.
            if declaration.get("kind") == "heading":
                status, reason = "explicitly_not_applicable", "external_heading_is_context_not_an_imported_answer"
            else:
                issues = [item for item in graph["unresolved"] if item.get("reason") == "input_scope_context"
                          and declaration in item.get("outside_selection", [])]
                if issues:
                    proof = [{"unresolved": item["id"]} for item in issues]
                    reason = "authorized_input_scope_dependency_retained"
                else:
                    # Unit/period dependencies may be resolved by selected
                    # source-bearing qualifiers; the external literal never
                    # provides coverage itself.
                    origin = obligation["source"]
                    local = [fact for fact in facts if _same_source(origin, fact.get("source", {}))]
                    label = re.match(r"\s*(Units?|Currency|Period|Year|单位|單位|币种|幣種|期间|期間|年度)\s*[:：=]", declaration.get("text", ""), re.I)
                    dimension = ("unit" if label and label[1].casefold() in {"unit", "units", "单位", "單位"}
                                 else "currency" if label and label[1].casefold() in {"currency", "币种", "幣種"}
                                 else "period" if label else None)

                    def selected_proof(fact, dimension=dimension):
                        if dimension is None or dimension not in fact.get("qualifiers", {}):
                            return False
                        proof = fact.get("qualifier_sources", {}).get(dimension) or fact.get("qualifier_provenance", {}).get(dimension, {}).get("source")
                        return bool(proof and any(_ranges(entry, proof) for entry in sources.values()))

                    relevant = [fact for fact in local if not (dimension == "unit" and fact.get("role") == "identity")]
                    replacements = [entry for entry in sources.values() if _same_source(origin, entry["source"])
                                    and _DECLARATION.fullmatch(entry["text"].strip()) and label
                                    and re.match(r"\s*" + re.escape(label[1]) + r"\s*[:：=]", entry["text"], re.I)]
                    if replacements:
                        status, reason = "explicitly_not_applicable", "selected_declaration_replaces_external_default"
                        proof = [{"source_id": entry["id"], "source": entry["source"]} for entry in replacements]
                    elif relevant and all(selected_proof(fact) for fact in relevant):
                        status, reason = "explained", "selected_qualifier_evidence_resolves_external_dependency"
                        proof = [{"requirement": fact["id"]} for fact in local]
        elif obligation.get("non_applicability_rule"):
            status, reason = "explicitly_not_applicable", obligation["non_applicability_rule"]
        elif not obligation["text"].strip():
            status, reason = "explicitly_not_applicable", "empty_literal_has_no_text_or_semantic_payload"
        else:
            span = _range(entry, obligation["source"])
            if entry["id"] not in role_cache:
                role_cache[entry["id"]] = [*_role_evidence(entry, [*facts, *operands], materials=inventory["sources"]),
                    *_prepositional_role_evidence(entry, [*facts, *operands], relations)]
                for attachment in attachment_obligations[entry["id"]]:
                    bindings = _infinitive_bindings(attachment, [*facts, *operands], relations, graph.get("logic", []))
                    for binding in bindings:
                        role_cache[entry["id"]].append({"span": list(_range(entry, attachment["source"])),
                            "requirement": binding["requirement"], "relation": binding["relation"],
                            "role": "source_bound_infinitival_marker"})
                structural_cache[entry["id"]] = [*_structural_evidence(entry, graph, bound_relations),
                                                  *toc_bindings.get(entry["id"], []),
                                                  *compact_bindings.get(entry["id"], [])]
            role_evidence = role_cache[entry["id"]]
            structural = structural_cache[entry["id"]]
            navigation_labels = [item for item in toc_bindings.get(entry['id'], [])
                if any(a <= span[0] < span[1] <= b for a, b in item.get('literal_role_spans', []))]
            if navigation_labels and (obligation['kind'] == 'qualifier' or obligation['kind'] == 'relation'
                    and obligation.get('binding_role') in {None, 'attachment', 'prepositional_attachment'}):
                rows.append({'obligation_id': obligation['id'], 'status': 'explained', 'layers': obligation['layers'],
                    'interpretation_rule': obligation['interpretation_rule'],
                    'reason': 'printed_navigation_title_or_parent_is_its_bound_literal_role',
                    'source_basis': obligation['source_basis'], 'evidence': navigation_labels,
                    'unexplained_character_positions': []})
                continue
            if obligation["kind"] == "text":
                evidence = [*_text_syntax_evidence(entry), *_text_field_delimiters(entry, text_nodes)]
                for node in text_nodes:
                    evidence.extend(_text_node_evidence(entry, node))
                evidence.extend(item for item in compact_bindings.get(entry["id"], []) if item.get("control"))
                for control in graph.get("context", {}).get("text_projection", {}).get("controls", []):
                    for a, b in _ranges(entry, control.get("source", {})):
                        raw = entry["text"][a:b]
                        # A control label cannot hide a number, sign, decimal
                        # point, percent or accounting parentheses from T.
                        if raw == control.get("text"):
                            for position in range(a, b):
                                character = entry["text"][position]
                                if character.isspace() or character in ":：=;；,，、。|" or character == "." and position + 1 == len(entry["text"]):
                                    evidence.append({"span": [position, position + 1], "role": "printed_format_control"})
                proof = evidence
                toc_control = [item for item in toc_bindings.get(entry["id"], []) if item.get("schema_control")]
                if toc_control:
                    status, proof, reason = "explicitly_not_applicable", toc_control, "actual_toc_schema_control_has_bound_records"
                elif entry.get("printed_schema_control") or any(entry.get("cell", {}).get(key) for key in
                        ("is_column_header", "column_header")) and _SCHEMA_CONTROL.fullmatch(entry["text"].strip()):
                    status, reason = "explicitly_not_applicable", "printed_property_value_schema_control"
                elif not _residue(entry["text"], span, evidence, literal=True):
                    status, proof, reason = "explained", evidence, "literal_source_ranges_retained_by_T"
            elif obligation["kind"] == "relation":
                if obligation.get('binding_role') == 'series_parent':
                    parent = obligation['required_parent']
                    owners = [fact for fact in facts if _range(entry, fact.get('value_source', {})) is not None]
                    complete = owners and all(fact.get('qualifiers', {}).get('parent_metric') == parent['text']
                        and fact.get('qualifier_sources', {}).get('parent_metric') == parent['source']
                        and fact.get('identity_facets', {}).get('group') == parent['text']
                        and any(edge.get('type') == 'qualifier_scope' and edge.get('left', {}).get('type') == 'parent_metric'
                                for edge in bound_relations(fact)) for fact in owners)
                    if complete:
                        status, reason = 'explained', 'series_member_has_its_actual_source_bound_parent_metric'
                        proof = [{'requirement': fact['id'], 'parent': copy.deepcopy(parent)} for fact in owners]
                    rows.append({'obligation_id': obligation['id'], 'status': status, 'layers': obligation['layers'],
                        'interpretation_rule': obligation['interpretation_rule'], 'reason': reason, 'source_basis': obligation['source_basis'],
                        'evidence': proof, 'unexplained_character_positions': []})
                    continue
                if obligation.get("binding_role") == "fronted_operation":
                    from .fronted_nominal_context import validate_fronted_operation
                    from .infinitival_syntax import _main_leaves

                    for node in _walk(graph.get("logic", [])):
                        if node.get("kind") != "fronted_context" or _range(entry, node.get("operator_source", {})) != span:
                            continue
                        def local_literal(origin, label, entry=entry):
                            bounds = _range(entry, origin or {})
                            return entry['text'][slice(*bounds)] if bounds else None
                        try:
                            validate_fronted_operation(node, local_literal)
                        except (ValueError, KeyError, TypeError):
                            continue
                        leaves = _main_leaves(node.get('operation', {'kind': 'unknown'}))
                        main = _main_leaves(node.get('child', {'kind': 'unknown'}))
                        def owns(leaf, bank):
                            return [fact for fact in bank if all(fact.get(key) == leaf.get(key) for key in
                                ('subject_source', 'predicate_source', 'object_source')) and bound_relations(fact)]
                        operand_facts = [fact for leaf in leaves for fact in owns(leaf, operands)]
                        main_facts = [fact for leaf in main for fact in owns(leaf, facts)]
                        edges = [edge for fact in main_facts for edge in bound_relations(fact)
                                 if edge.get('type') == 'narrative_fronted_context_scope' and edge.get('source') == node['operator_source']]
                        if leaves and main and len(operand_facts) == len(leaves) and len(main_facts) == len(main) and edges:
                            status, reason = 'explained', 'printed_nonfinite_operation_has_independent_operand_main_and_controller'
                            proof = [{'requirement': fact['id']} for fact in [*main_facts, *operand_facts]]
                            proof.extend({'relation': edge['id']} for edge in edges)
                    rows.append({'obligation_id': obligation['id'], 'status': status, 'layers': obligation['layers'],
                        'interpretation_rule': obligation['interpretation_rule'], 'reason': reason, 'source_basis': obligation['source_basis'],
                        'evidence': proof, 'unexplained_character_positions': list(range(*span)) if status == 'pending' else []})
                    continue
                if obligation.get("binding_role") == "heading_scope":
                    declared = obligation["required_scope"]
                    names = [heading["text"] for heading in declared]
                    heading_key = json.dumps(declared, sort_keys=True, ensure_ascii=False)
                    if heading_key not in heading_cache:
                        heading_cache[heading_key] = all(any(material["source_kind"] == "heading" and material["text"] == heading["text"]
                            and _range(material, heading.get("reference", heading.get("source", {}))) == (0, len(material["text"]))
                            for material in sources.values()) for heading in declared)
                    headings_present = heading_cache[heading_key]
                    for fact in [*facts, *operands]:
                        if id(fact) not in fact_source_cache:
                            fact_source_cache[id(fact)] = [origin for origin in _walk(fact) if isinstance(origin.get("path"), str)]
                    owners = [fact for fact in [*facts, *operands] if any(_ranges(entry, origin)
                              for origin in fact_source_cache[id(fact)])]
                    relative_scope = obligation.get("scope_is_relative")
                    absolute_scope = obligation.get("scope_is_absolute")

                    def matches_scope(scope, fact=None, names=names, relative=relative_scope, absolute=absolute_scope, entry=entry):
                        if not isinstance(scope, (list, tuple)):
                            return False
                        if absolute:
                            if list(scope) == names:
                                return True
                            group = (fact or {}).get('identity_facets', {}).get('group', [])
                            group = [group] if isinstance(group, str) else group
                            if (group and (fact or {}).get('scope') == names and list(scope) == [*names, *group]
                                    and all(any(row.get('text') == label and any(material['text'][slice(*bounds)] == label
                                        for material in sources.values() if (bounds := _range(material, row.get('source', {}))))
                                        for row in (fact or {}).get('row_evidence', [])) for label in group)):
                                return True
                            label = (fact or {}).get("field_label_evidence") or {}
                            bounds = _range(entry, label.get("source", {}))
                            return bool(fact and fact.get("predicate") and bounds and
                                entry["text"][bounds[0]:bounds[1]] == label.get("text") and
                                list(scope) == [*names, label["text"]])
                        if relative:
                            return bool(names) and any(scope[index:index + len(names)] == names for index in range(len(scope)))
                        return bool(names) and scope[:len(names)] == names

                    owner_edges = [[edge for edge in bound_relations(fact) if edge.get("type") == "field_binding"
                                    and matches_scope(edge.get("right", {}).get("scope", []), fact)] for fact in owners]
                    own_scopes = bool(owners) and all(matches_scope(fact.get("scope", []), fact) and bound
                        for fact, bound in zip(owners, owner_edges, strict=True))
                    edges = [edge for bound in owner_edges for edge in bound]
                    memberships = [edge for edge in relations if edge.get("type") == "prose_heading_membership"
                                   and isinstance(edge.get("left"), list) and matches_scope(edge["left"])
                                   and _ranges(entry, edge.get("source", {}))]
                    navigation = [item for item in toc_bindings.get(entry["id"], []) if all(any(
                        heading["text"] == own["text"] and _same_source(heading.get("reference", heading.get("source", {})), own["source"])
                        for own in item["heading_sources"]) for heading in declared)]
                    if entry.get("printed_schema_control"):
                        status, reason = "explicitly_not_applicable", "printed_schema_controls_are_owned_by_their_table_records"
                    elif not obligation.get("scope_pending") and headings_present and navigation:
                        status, proof, reason = "explained", navigation, "actual_toc_axes_and_parent_relations_retain_directory_ownership"
                    elif not obligation.get("scope_pending") and headings_present and (own_scopes if owners else bool(memberships)):
                        status, reason = "explained", "selected_original_headings_retain_content_ownership"
                        proof = [{"heading": heading["text"], "source": heading.get("reference", heading.get("source"))}
                                 for heading in declared]
                        proof.extend({"relation": edge.get("id", f"operand-edge:{relations.index(edge)}")} for edge in [*edges, *memberships])
                    rows.append({"obligation_id": obligation["id"], "status": status, "layers": obligation["layers"],
                        "interpretation_rule": obligation["interpretation_rule"], "reason": reason,
                        "source_basis": obligation["source_basis"], "evidence": proof, "unexplained_character_positions": []})
                    continue
                if obligation.get("binding_role") == "navigation":
                    # A printed field owns its directive through its separate
                    # label source. The reference reader faithfully keeps only
                    # the directive in reference.source; requiring the whole
                    # field there rejects a complete, correctly bound result.
                    field = re.fullmatch(r"\s*(?P<label>[^:：=\n]{1,160})[:：=]\s*(?P<body>\S.*?)\s*",
                                         obligation["text"], re.S)
                    reference_span = (span[0] + field.start("body"), span[0] + field.end("body")) if field else span
                    references = [item for item in graph.get("explicit_references", [])
                                  if item.get("text") == entry["text"][slice(*reference_span)]
                                  and _range(entry, item.get("source", {})) == reference_span and item.get("owner_proof")
                                  and any(edge.get('type') == 'reference_directive_scope'
                                          and edge.get('left') == item['owner_proof']['owner']
                                          and edge.get('right', {}).get('owner') == item['owner_proof']['owner']
                                          and edge.get('binding_evidence', {}).get('owner_proof') == item['owner_proof']
                                          and edge.get('source') == item.get('directive_source') for edge in relations)]
                    if field:
                        label = field["label"].strip()
                        label_start = span[0] + field.start("label") + len(field["label"]) - len(field["label"].lstrip())
                        label_span = (label_start, label_start + len(label))
                        references = [item for item in references
                            if item["owner_proof"].get("owner", {}).get("identity") == {
                                "role": "printed_field", "attribute": label}
                            and any(proof.get("kind") == "printed_field_label" and proof.get("text") == label
                                    and _range(entry, proof.get("source", {})) == label_span
                                    for proof in item["owner_proof"].get("evidence", []))
                            and any(edge.get("type") == "reference_directive_scope"
                                    and edge.get("left") == item["owner_proof"]["owner"]
                                    and edge.get("right", {}).get("owner") == item["owner_proof"]["owner"]
                                    and edge.get("binding_evidence", {}).get("owner_proof") == item["owner_proof"]
                                    and edge.get("binding_evidence", {}).get("directive_source") == item.get("directive_source")
                                    and _range(entry, edge.get("source", {})) == _range(entry, item.get("directive_source", {}))
                                    for edge in relations)]
                    edges = [edge for edge in relations if edge.get("type") == "explicit_reference_target"
                             and _range(entry, edge.get("source", {})) == reference_span
                             and any(edge.get("right") == item.get("target") and edge.get("left", {}).get("owner") == item["owner_proof"]["owner"]
                                     and (not field or edge.get("binding_evidence", {}).get("owner_proof") == item["owner_proof"]
                                          and edge.get("binding_evidence", {}).get("directive_source") == item.get("directive_source")
                                          and edge.get("binding_evidence", {}).get("target_source") == item.get("target_source"))
                                     for item in references)]
                    if references and edges:
                        status, reason = "explained", "printed_navigation_keeps_its_own_owner_target_binding"
                        proof = [{"relation": edge["id"]} for edge in edges]
                    rows.append({"obligation_id": obligation["id"], "status": status, "layers": obligation["layers"],
                        "interpretation_rule": obligation["interpretation_rule"], "reason": reason,
                        "source_basis": obligation["source_basis"], "evidence": proof, "unexplained_character_positions": []})
                    continue
                if obligation.get("binding_role") == "semantic_binding":
                    local_roles = [item for item in role_evidence if "span" in item
                                   and max(item["span"][0], span[0]) < min(item["span"][1], span[1])]
                    ids = {item.get("requirement") for item in local_roles}
                    owners = [fact for fact in [*facts, *operands] if fact["id"] in ids
                              and _fragment_owns_fact(obligation, fact)]
                    bindings = {fact["id"]: [edge for edge in bound_relations(fact)
                                             if edge.get("type") == "field_binding"
                                             and validate_relation_binding(obligation, fact, edge)["equivalent"]] for fact in owners}
                    qualifier_owners = [fact for fact in [*facts, *operands] if fact["id"] in ids and fact not in owners]
                    qualifier_edges = [edge for fact in qualifier_owners for edge in bound_relations(fact)
                        if edge.get("type") == "qualifier_scope" and any(
                            _range(entry, origin) == span for origin in _walk(edge.get("binding_evidence", {}))
                            if isinstance(origin.get("path"), str))
                        and edge.get("left", {}).get("text") == obligation["text"].strip()]
                    exceptional = [item for item in structural if item.get("relations")
                                   and item["span"][0] <= span[0] and span[1] <= item["span"][1]]
                    exceptional.extend(item for item in structural if item['role'] == 'printed_person_record_label'
                                       and item.get('relations') and not _residue(entry['text'], span, [item]))
                    if (compact_bindings.get(entry["id"]) and not _residue(entry["text"], span, compact_bindings[entry["id"]])):
                        status, proof, reason = "explained", compact_bindings[entry["id"]], "printed_compact_slots_have_their_own_bindings"
                    elif qualifier_edges:
                        status, reason = "explained", "fragment_has_its_own_qualifier_owner_relation"
                        proof = [{"relation": edge["id"]} for edge in qualifier_edges]
                    elif exceptional or owners and all(bindings.values()):
                        status, reason = "explained", "fragment_has_its_own_business_or_declaration_relations"
                        proof = exceptional or [{"requirement": ident, "relations": [edge.get("id", f"operand-edge:{relations.index(edge)}")
                                  for edge in edges]} for ident, edges in bindings.items()]
                    else:
                        # Document-composition relations use the named document
                        # endpoint rather than a generic field-binding schema.
                        composition = [edge for edge in relations if edge.get("type") == "document_part_of"
                                       and _same_statement(obligation["source"], edge.get("binding_evidence", {}).get("statement_source", {}))]
                        if composition:
                            status, reason = "explained", "printed_document_composition_has_its_own_relation"
                            proof = [{"relation": edge["id"]} for edge in composition]
                    rows.append({"obligation_id": obligation["id"], "status": status, "layers": obligation["layers"],
                        "interpretation_rule": obligation["interpretation_rule"], "reason": reason,
                        "source_basis": obligation["source_basis"], "evidence": proof, "unexplained_character_positions": []})
                    continue
                if obligation.get("binding_role") in {"prepositional_attachment", "attachment"}:
                    checks = [(fact, edge, validate_relation_binding(obligation, fact, edge))
                              for fact in [*facts, *operands] for edge in relations
                              if edge.get("type") == "narrative_prepositional_attachment"
                              and (edge.get("fact_id") is None or edge.get("fact_id") == fact["id"])
                              and edge.get("binding_evidence", {}).get("preposition_source") == obligation["source"]]
                    equivalent = [(fact, edge, check) for fact, edge, check in checks if check["equivalent"]]
                    infinitives = _infinitive_bindings(obligation, [*facts, *operands], relations, graph.get("logic", []))
                    if equivalent:
                        status, reason = "explained", "printed_preposition_has_its_own_head_complement_attachment"
                        proof = [{"requirement": fact["id"], "relation": edge.get("id"), "binding": check}
                                 for fact, edge, check in equivalent]
                    elif infinitives:
                        status, reason = "explained", "printed_infinitival_marker_has_its_own_controller_and_operand"
                        proof = infinitives
                    else:
                        proof = [{"requirement": fact["id"], "relation": edge.get("id"), "binding": check}
                                 for fact, edge, check in checks]
                        reason = "prepositional_attachment_missing_or_unresolved"
                        composition = [edge for edge in relations if edge.get("type") == "document_part_of"
                            and any(a <= span[0] < span[1] <= b for a, b in _ranges(entry,
                                edge.get("binding_evidence", {}).get("attribute_source", {})))
                            and _same_statement(obligation["statement_source"], edge.get("binding_evidence", {}).get("statement_source", {}))
                            and any(fact.get("subject") == edge.get("left", {}).get("text")
                                and fact.get("object") == edge.get("right", {}).get("text")
                                and all(fact.get(key) == edge.get("binding_evidence", {}).get(key)
                                        for key in ("subject_source", "predicate_source", "object_source", "attribute_source"))
                                for fact in facts)]
                        if composition:
                            status, reason = "explained", "printed_part_of_has_its_own_component_document_direction"
                            proof = [{"relation": edge["id"]} for edge in composition]
                    rows.append({"obligation_id": obligation["id"], "status": status, "layers": obligation["layers"],
                        "interpretation_rule": obligation["interpretation_rule"], "reason": reason,
                        "source_basis": obligation["source_basis"], "evidence": proof,
                        "unexplained_character_positions": list(range(*span)) if status == "pending" else []})
                    continue
                if obligation.get("binding_role") == "quantity_comparison":
                    for fact in [*facts, *operands]:
                        for edge in bound_relations(fact):
                            if edge.get("type") != "narrative_quantity_scope":
                                continue
                            binding = edge.get("binding_evidence", {})
                            if _range(entry, binding.get("quantity_source", {})) != span:
                                continue
                            quantities = [node for node in _walk([fact.get("object_phrase", {}), fact.get("subject_phrase", {}),
                                          fact.get("prepositional_complements", [])]) if node.get("kind") == "quantity_comparison"]
                            if any(node.get("source") == binding.get("quantity_source") and all(
                                node.get(key) == edge.get("left", {}).get(key) for key in ("operator", "value", "unit", "quantity_role"))
                                for node in quantities):
                                proof.append({"requirement": fact["id"], "relation": edge.get("id")})
                    if proof:
                        status, reason = "explained", "printed_quantity_boundary_has_its_own_nominal_scope"
                    rows.append({"obligation_id": obligation["id"], "status": status, "layers": obligation["layers"],
                        "interpretation_rule": obligation["interpretation_rule"], "reason": reason,
                        "source_basis": obligation["source_basis"], "evidence": proof,
                        "unexplained_character_positions": list(range(*span)) if status == "pending" else []})
                    continue
                for fact in [*facts, *operands]:
                    predicate = _range(entry, fact.get("predicate_source", {}))
                    bound = [edge for edge in bound_relations(fact) if edge.get("type") == "field_binding"]
                    scalar_proof = [item for item in role_evidence if item.get("requirement") == fact["id"]]
                    # A printed calendar series binds its nominal metric
                    # before ':' to multiple independently dated values. A
                    # lexical action inside that proven label is a noun use;
                    # it is not an additional asserted investment/action.
                    role_basis = fact.get('role_basis')
                    if bound and predicate is None and isinstance(role_basis, dict) and role_basis.get('period_selector'):
                        label = _range(entry, fact.get('attribute_source', {}))
                        if (label and label[0] <= span[0] < span[1] <= label[1]
                                and re.match(r'\s*[:：]', entry['text'][label[1]:])
                                and any(item['span'][0] <= span[0] < span[1] <= item['span'][1]
                                        and item.get('role') == 'attribute' for item in scalar_proof)):
                            proof.append({'requirement': fact['id'], 'role': 'calendar_series_nominal_metric',
                                          'relations': [edge.get('id', f'operand-edge:{relations.index(edge)}') for edge in bound]})
                    if bound and predicate is None:
                        for role in ('subject', 'attribute'):
                            label = _range(entry, fact.get(role + '_source', {}))
                            companions = companion_groups[json.dumps(fact.get('subject_source'), sort_keys=True)]
                            positional = isinstance(role_basis, dict) and role_basis.get('period_selector')
                            if (label and label[0] <= span[0] < span[1] <= label[1]
                                    and re.match(r'\s*[:：]', entry['text'][label[1]:])
                                    and (positional or len({o['attribute'] for o in companions}) >= 2)
                                    and any(item.get('requirement') == fact['id'] and item.get('role') == role
                                            and item['span'][0] <= span[0] < span[1] <= item['span'][1] for item in scalar_proof)):
                                proof.append({'requirement': fact['id'], 'role': 'printed_nominal_record_key',
                                              'relations': [edge.get('id', f'operand-edge:{relations.index(edge)}') for edge in bound]})
                    if (bound and predicate is None and scalar_proof and obligation.get("binding_role") == "semantic_binding"
                            and not _residue(entry["text"], span, scalar_proof)):
                        proof.append({"requirement": fact["id"], "role": "source_bound_scalar_fragment",
                                      "relations": [edge.get('id', f'operand-edge:{relations.index(edge)}') for edge in bound]})
                    direction = _range(entry, fact.get("qualifier_sources", {}).get("change_direction", {}))
                    if bound and direction == span and any(edge.get("type") == "qualifier_scope"
                            and edge.get("left", {}).get("type") == "change_direction" for edge in bound_relations(fact)):
                        proof.append({"requirement": fact["id"], "role": "printed_change_direction",
                                      "relations": [edge.get('id', f'operand-edge:{relations.index(edge)}') for edge in bound]})
                    if obligation.get("binding_role") == "field_binding":
                        labels = _ranges(entry, fact.get("attribute_source", {}))
                        if fact.get("attribute") in entry["parents"]:
                            labels.extend(_ranges(entry, fact.get("subject_source", {})))
                        values = _ranges(entry, fact.get("value_source", {}))
                        if bound and any(span[0] <= a < b <= span[1] for a, b in labels) and any(
                                span[0] <= a < b <= span[1] for a, b in values):
                            proof.append({"requirement": fact["id"], "relations": [edge.get("id", f"operand-edge:{relations.index(edge)}") for edge in bound]})
                        continue
                    if bound and predicate is not None and predicate[0] <= span[0] < span[1] <= predicate[1]:
                        proof.append({"requirement": fact["id"], "relations": [edge.get("id", f"operand-edge:{relations.index(edge)}") for edge in bound]})
                    # A lexical verb candidate can be a bound nominal (Report)
                    # or a condition fragment (approved by four directors).
                    # Its explicit role, independent literal and own binding
                    # explain that ambiguity; casing never does.
                    if bound and predicate is not None and not (predicate[0] <= span[0] < span[1] <= predicate[1]):
                        for key in ("subject", "object"):
                            for a, b in _ranges(entry, fact.get(key + "_source", {})):
                                if a <= span[0] < span[1] <= b:
                                    proof.append({"requirement": fact["id"], "role": key,
                                                  "relations": [edge.get("id", f"operand-edge:{relations.index(edge)}") for edge in bound]})
                        for item in role_evidence:
                            if (item.get("requirement") == fact["id"] and item.get("relation")
                                    and item["span"][0] <= span[0] < span[1] <= item["span"][1]):
                                proof.append({"requirement": fact["id"], "role": item["role"],
                                              "relations": [item["relation"]]})
                    for key, origin in fact.get("qualifier_sources", {}).items():
                        if key not in {"condition", "exception"} or not isinstance(origin, dict):
                            continue
                        if any(a <= span[0] < span[1] <= b for a, b in _ranges(entry, origin)):
                            edges = [edge for edge in relations if edge.get("type") == key + "_scope"
                                     and edge.get("binding_evidence", {}).get("qualifier_source") == origin]
                            if edges:
                                proof.append({"requirement": fact["id"], "role": key,
                                              "relations": [edge.get("id", f"operand-edge:{relations.index(edge)}") for edge in edges]})
                    attribute = _range(entry, fact.get("attribute_source", {}))
                    if (attribute == span or predicate == span) and any(edge.get("type") == "document_part_of"
                            and edge.get("binding_evidence", {}).get("attribute_source") == fact.get("attribute_source")
                            and edge.get("binding_evidence", {}).get("predicate_source") == fact.get("predicate_source")
                            for edge in relations):
                        proof.append({"requirement": fact["id"], "role": "document_composition_relation"})
                if not proof and obligation.get("binding_role") == "field_binding" and any(
                        item["role"] == "source_bound_toc_protocol" for item in structural):
                    proof.extend(structural)
                if not proof and obligation.get('binding_role') == 'field_binding':
                    proof.extend(item for item in structural if item['role'] == 'source_bound_caption_and_unit_scope'
                                 and item['span'][0] <= span[0] and span[1] <= item['span'][1])
                if (not proof and obligation.get("binding_role") in {None, "field_binding", "semantic_binding"}
                        and compact_bindings.get(entry["id"]) and not _residue(entry["text"], span, compact_bindings[entry["id"]])):
                    proof.extend(compact_bindings[entry["id"]])
                if not proof and obligation.get('binding_role') is None:
                    proof.extend(item for item in structural if item['role'] in {'source_bound_printed_field_owner', 'source_bound_basis_nominal_action',
                                                                               'source_bound_atomic_scalar_key'}
                                 and item['span'][0] <= span[0] < span[1] <= item['span'][1])
                if proof:
                    status, reason = "explained", "printed_predicate_has_its_own_role_binding"
                elif obligation.get("binding_role") is None:
                    edges = [edge for edge in relations if edge.get("type") == "narrative_reporting_scope"
                             and _range(entry, edge.get("source", {})) == span
                             and any(entry["text"][a:b] == edge.get("left", {}).get("subject")
                                     for a, b in _ranges(entry, edge.get("binding_evidence", {}).get("speaker_source", {})))]
                    if edges:
                        status, reason = "explained", "printed_reporter_has_its_own_complement_scope"
                        proof = [{"relation": edge["id"]} for edge in edges]
                    else:
                        edges = [edge for edge in relations if edge.get("type") == "narrative_active_aspect_scope"
                                 and _range(entry, edge.get("source", {})) == span
                                 and any(fact.get("qualifier_sources", {}).get("aspect") == edge.get("source")
                                         for fact in [*facts, *operands])]
                        if edges:
                            status, reason = "explained", "printed_auxiliary_has_its_own_aspect_scope"
                            proof = [{"relation": edge["id"]} for edge in edges]
            elif obligation["kind"] == "qualifier":
                # A token in a subject/object is not proof of its logical
                # scope. Require operator evidence plus an actual relation.
                origins = [value for fact in [*facts, *operands] for value in _walk(fact.get("qualifier_sources", {}))
                           if isinstance(value.get("path"), str)]
                origins.extend(value for tree in graph.get("logic", []) for node in _walk(tree)
                               for key, value in node.items() if key.endswith("_source")
                               and isinstance(value, dict) and key not in {"subject_source", "object_source", "predicate_source"})
                scoped = _operator_edges(obligation["text"], relations)
                origins.extend(value for edge in scoped for node in _walk(edge)
                               for key, value in node.items() if key in {"operator_source", "operator_sources"}
                               for value in (value if isinstance(value, list) else [value]) if isinstance(value, dict))
                for tree in graph.get("logic", []):
                    for node in _walk(tree):
                        if node.get("operator_spans") and node.get("source") and node.get("span"):
                            offset = node["source"].get("text_span", [0, 0])[0] - node["span"][0]
                            origins.extend({**node["source"], "text_span": [offset + a, offset + b]}
                                           for a, b in node["operator_spans"])
                edges = [edge for edge in scoped if operator_binding(edge) and any(a <= span[0] < span[1] <= b
                          for origin in [edge.get("source", {}), *[v for node in _walk(edge.get("binding_evidence", {}))
                              for k, v in node.items() if k.endswith("_source") and isinstance(v, dict)]]
                          for a, b in _ranges(entry, origin))]
                if edges and any(a <= span[0] < span[1] <= b for origin in origins for a, b in _ranges(entry, origin)):
                    status, reason = "explained", "printed_operator_has_source_bound_scope"
                    proof = [{"relation": edge.get("id", f"operand-edge:{relations.index(edge)}")} for edge in edges]
                nominal_key = [item for item in structural if item['role'] == 'source_bound_atomic_scalar_key'
                               and item['span'][0] <= span[0] < span[1] <= item['span'][1]]
                if nominal_key:
                    status, reason, proof = 'explained', 'printed_word_is_part_of_its_bound_scalar_key', nominal_key
            else:
                # The semantic fragment must be explained word by word by
                # explicit roles and scoped operators. Generic T/source
                # retention and a sibling's fact cannot satisfy this check.
                extras = list(structural)
                for edge in relations:
                    if edge.get("type") == "proposition_coordination_scope":
                        extras.extend({"span": list(bounds), "role": "printed_coordination_operator", "requirement": edge["id"]}
                                      for bounds in _ranges(entry, edge.get("operator_source", {})))
                for tree in graph.get("logic", []):
                    for node in _walk(tree):
                        if node.get("operator_spans") and node.get("source") and node.get("span"):
                            offset = node["source"].get("text_span", [0, 0])[0] - node["span"][0]
                            for a, b in node["operator_spans"]:
                                extras.extend({"span": list(bounds), "role": "logical_operator", "requirement": "source_bound_logic"}
                                              for bounds in _ranges(entry, {**node["source"], "text_span": [offset + a, offset + b]}))
                body_label = re.match(r"\s*(?:Description|Statement|Narrative|Policy|Requirement|描述|说明|說明|陈述|陳述|政策|要求)\s*[:：=]", entry["text"], re.I)
                if body_label:
                    extras.append({"span": list(body_label.span()), "role": "printed_body_label", "requirement": "printed_field_syntax"})
                for edge in relations:
                    for origin in [edge.get("source", {})]:
                        for a, b in _ranges(entry, origin):
                            if b - a < len(entry["text"]) and not _residue(entry["text"], (a, b), role_evidence):
                                extras.append({"span": [a, b], "requirement": edge.get("id", f"operand-edge:{relations.index(edge)}"), "role": "bound_relation"})
                proof = [*role_evidence, *extras]
                if (role_evidence or structural) and not _residue(entry["text"], span, proof):
                    status, reason = "explained", "all_fragment_words_have_explicit_business_roles"
        missing = []
        if status == "pending" and entry is not None and obligation["kind"] in {"text", "proposition", "semantic_content"}:
            missing = _residue(entry["text"], _range(entry, obligation["source"]), [item for item in proof if "span" in item],
                               literal=obligation["kind"] == "text")
        conflicts = [{"requirement": ident, **conflict} for ident, issues in role_conflicts.get(obligation["source_id"], {}).items()
                     for conflict in issues if _same_source(obligation["source"], conflict["source"])
                     or _same_source(conflict["source"], obligation["source"])] if obligation["kind"] != "text" else []
        if status == "pending" and conflicts:
            reason = "opaque_proposition_roles_do_not_explain_independent_semantics"
        rows.append({"obligation_id": obligation["id"], "status": status, "layers": obligation["layers"],
            "interpretation_rule": obligation["interpretation_rule"], "reason": reason,
            "source_basis": obligation["source_basis"], "evidence": proof, "unexplained_character_positions": missing,
            **({"role_conflicts": conflicts} if conflicts else {})})
    for item in inventory["authorized_raw_inventory"]["obligations"]:
        rows.append({"obligation_id": item["id"], "status": item["status"], "layers": ["T", "L", "B"],
            "interpretation_rule": item["interpretation_rule"], "reason": item["reason"],
            "source_basis": "canonical_authorized_raw_expected_text", "evidence": copy.deepcopy(item["evidence"]),
            "unexplained_character_positions": []})
    # Interpretation and disposition are separate from the immutable inventory.
    # Each carries its local evidence and exact remaining original cuts.
    by_obligation = {item["id"]: item for item in inventory["obligations"]}
    for row in rows:
        item = by_obligation.get(row["obligation_id"])
        if item is None:
            continue
        row["semantic_type"] = item["semantic_type"]
        row["expected_roles"] = copy.deepcopy(item.get("expected_roles", []))
        row["source"] = copy.deepcopy(item["source"])
        row["text"] = item["text"]
        row["unexplained_ranges"] = []
        positions = row["unexplained_character_positions"]
        if positions:
            entry = sources[item["source_id"]]
            start, previous = positions[0], positions[0]
            for index in [*positions[1:], None]:
                if index is None or index != previous + 1:
                    row["unexplained_ranges"].append({"source": _origin(entry["source"], start, previous + 1),
                        "text": entry["text"][start:previous + 1]})
                    start = index
                previous = index
    return {"source_complete": inventory["source_complete"], "semantic_complete": all(row["status"] != "pending" for row in rows),
        "dispositions": rows, "status_counts": dict(Counter(row["status"] for row in rows))}


def validate_source_obligations(graph: dict[str, Any], *, expected: dict[str, Any] | None = None) -> None:
    """Reject synchronized graph mutations without trusting derived claims."""
    inventory = graph.get("source_obligation_inventory")
    if not isinstance(inventory, dict):
        raise ValueError("source obligation inventory is required")
    reference = expected if expected is not None else inventory.get("selection")
    if not isinstance(reference, dict) or build_source_obligation_inventory(reference) != inventory:
        raise ValueError("source obligation inventory differs from authorized source selection")
    coverage = audit_source_obligations(inventory, graph)
    if any(row["status"] == "explained" and not row["evidence"] for row in coverage["dispositions"]):
        raise ValueError("explained source obligation lacks actual role or relationship evidence")
    if graph.get("source_obligation_coverage") != coverage:
        raise ValueError("source obligation explanation changed or omitted source semantics")
    obligations = {item["id"]: item for item in inventory["obligations"]}
    dispositions = {row["obligation_id"]: row for row in coverage["dispositions"]}
    for issue in graph["unresolved"]:
        if issue.get("reason") != "input_scope_context":
            continue
        for ident in issue.get("source_obligation_ids", []):
            obligation, disposition = obligations.get(ident, {}), dispositions.get(ident, {})
            source, origin = obligation.get("source", {}), issue.get("source", {})
            if (obligation.get("kind") != "authorization_dependency"
                    or obligation.get("declaration") not in issue.get("outside_selection", [])
                    or any(source.get(key) != origin.get(key) for key in ("path", "lines", "cell"))
                    or disposition.get("status") != "pending"
                    or not any(proof.get("unresolved") == issue.get("id") for proof in disposition.get("evidence", []))):
                raise ValueError("input_scope_context cannot absorb an unrelated pending source obligation")
    pending = {row["obligation_id"] for row in coverage["dispositions"] if row["status"] == "pending"}
    retained = {item["obligation_id"] for item in graph["unresolved"] if item.get("reason") == "source_obligation_pending"}
    retained.update(ident for item in graph["unresolved"] for ident in item.get("source_obligation_ids", []))
    if pending != retained:
        raise ValueError("source obligation pending semantics were omitted or fabricated")
