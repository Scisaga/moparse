"""Source-only accounting classifications within an explicit financial statement.

This grammar supplies group and qualifier bindings, never inferred amounts or
additional assertions. A short label, a unit, or numeric children alone cannot
establish a financial statement or a classification parent.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .measurement_evidence import read_unit_token

_INCOME = re.compile(
    r"(?:概要|简明|簡明)?(?:合并|合併)?(?:利润|利潤)(?:及其他(?:综合|綜合)收益)?表"
    r"|(?:概要|简明|簡明)?(?:合并|合併)?(?:其他)?(?:综合|綜合)收益表"
    r"|(?:(?:condensed|consolidated)\s+)*statements?\s+of\s+"
    r"(?:profit\s+or\s+loss(?:\s+and\s+other\s+comprehensive\s+income)?|(?:comprehensive\s+)?income)", re.I)
_POSITION = re.compile(
    r"(?:概要|简明|簡明)?(?:合并|合併)?(?:财务状况|財務狀況|资产负债|資產負債)表"
    r"|(?:(?:condensed|consolidated)\s+)*(?:statements?\s+of\s+financial\s+position|balance\s+sheets?)", re.I)
_ANNOTATION = re.compile(
    r"(?:税后(?:及重分类调整后)?金额|稅後(?:及重分類調整後)?金額|税后|稅後|net\s+of\s+tax|after\s+tax)"
    r"(?:\s*[,，]\s*(?:附注|附註|notes?)\s*\d+(?:[（(][a-zA-Z][）)])?)?"
    r"|(?:附注|附註|notes?)\s*\d+(?:[（(][a-zA-Z][）)])?", re.I)
_COMPREHENSIVE = re.compile(r"其他(?:综合|綜合)收益|other\s+comprehensive\s+income", re.I)
_RECLASSIFICATION = re.compile(
    r"(?:不能|能够|能夠|能|可|不可)(?:重分类|重分類)(?:进|進|至|入)(?:损益|損益)"
    r"|items?\s+(?:(?:that|which)\s+)?(?:(?:will|may|can)\s+)?(?:not\s+)?be\s+reclassified\s+to\s+profit\s+or\s+loss", re.I)
_POSITION_GROUP = re.compile(
    r"(?:非流动|非流動|流动|流動)?(?:资产|資產|负债|負債)|所有者权益|所有者權益|权益|權益"
    r"|(?:non[- ]current\s+|current\s+)?(?:assets|liabilities)|(?:shareholders['’]?\s+|owners['’]?\s+)?equity", re.I)
_VALUATION_DESIGNATION = re.compile(
    r'(?P<basis_link>以)(?P<basis>公允[价價]值)(?P<measurement>[计計]量)(?P<join>且)'
    r'(?P<change_link>其)?(?P<recognition>[变變][动動][计計]入)(?P<destination>[当當]期[损損]益)'
    r'(?P<link>的)(?P<head>金融[资資][产產])')


def financial_metric_designation(text):
    """Recognize a printed accounting designation, never a new value fact."""
    return _VALUATION_DESIGNATION.fullmatch(text)


def validate_financial_metric_facts(facts, literal):
    """An intact metric string cannot hide missing accounting relationships."""
    for fact in facts:
        subject = fact.get('subject', '')
        designation = financial_metric_designation(subject)
        if designation and fact.get('logic', {}).get('kind') in {'quantity_assertion', 'year_on_year_change'}:
            phrase = fact.get('subject_phrase') or {}
            if (phrase.get('kind') != 'cjk_nominal' or phrase.get('source') != fact.get('subject_source')
                    or phrase.get('head') != designation['head']
                    or [(d.get('role'), d.get('marker'), d.get('child', {}).get('head')) for d in phrase.get('parts', [])] != [
                        ('measurement_basis', designation['measurement'], designation['basis']),
                        ('valuation_change_recognition', designation['recognition'], designation['destination'])]):
                raise ValueError('Financial metric lacks its complete measurement and recognition designation')
        classification = re.fullmatch(r'(?P<parent>.+?)中的(?P<metric>.+)', subject)
        if classification and _POSITION_GROUP.fullmatch(classification['parent']) and fact.get('predicate'):
            qs = fact.get('qualifiers', {})
            origins = fact.get('qualifier_sources', {})
            source = fact.get('subject_source', {})
            base = source.get('text_span', [0])[0]
            required = {'parent_metric': classification['parent'], 'membership_operator': '中的'}
            cuts = {'parent_metric': [base, base + classification.end('parent')],
                    'membership_operator': [base + classification.end('parent'), base + classification.start('metric')]}
            if any(qs.get(k) != v or origins.get(k) != {**source, 'text_span': cuts[k]}
                   or literal(origins[k], k) != v for k, v in required.items()):
                raise ValueError('Financial metric is not bound to its printed internal classification')


def financial_statement_kind(heading: dict[str, Any] | None) -> str | None:
    """A heading role and its complete printed label prove the statement kind."""
    if not heading or not isinstance(heading.get("source"), dict) or not heading["source"].get("path"):
        return None
    text = heading.get("text", "").strip()
    return "income" if _INCOME.fullmatch(text) else "position" if _POSITION.fullmatch(text) else None


def _classification(text: str, statement: str, parents: list[dict[str, Any]]) -> str | None:
    label = text.strip()
    annotation = re.fullmatch(r"(.+?)\s*[（(]([^（）()]*)[）)]", label)
    if annotation:
        if not _ANNOTATION.fullmatch(annotation[2].strip()):
            return None
        label = annotation[1].strip()
    if statement == "income" and _COMPREHENSIVE.fullmatch(label):
        return "other_comprehensive_income"
    if (statement == "income" and _RECLASSIFICATION.fullmatch(label)
            and any(parent.get("financial_group_context", {}).get("classification") == "other_comprehensive_income"
                    for parent in parents)):
        return "reclassification_category"
    if statement == "position" and _POSITION_GROUP.fullmatch(label):
        return "financial_position_category"
    return None


def read_financial_group_context(text: str, source: dict[str, Any], *, kind: str,
                                 heading: dict[str, Any] | None,
                                 parents: list[dict[str, Any]], unit: dict[str, Any] | None) -> dict[str, Any]:
    """Prove an actual parent or expose the complete proved parent chain of a field.

    Every parent must have its own previously read classification proof under
    this exact statement heading. Callers must end the active unit context at
    prose, images, new headings and unresolved business parents. A field call
    only binds the parents; the field reader still owns its metric/value role.
    """
    result: dict[str, Any] = {"matched": False}
    statement = financial_statement_kind(heading)
    if (not source.get("path") or statement is None or not unit or unit.get("level") != "caption_shared"
            or not read_unit_token(unit.get("text", ""), unit.get("source", {}))["matched"]):
        return result
    rows = []
    for position, parent in enumerate(parents):
        proof = parent.get("financial_group_context") if isinstance(parent, dict) else None
        if (not proof or not proof.get("matched") or proof.get("heading") != heading
                or proof.get("group_path") != [item["text"] for item in parents[:position + 1]]
                or proof.get("label", {}).get("source") != parent.get("source")):
            return result
        rows.append({"text": parent["text"], "source": copy.deepcopy(parent["source"]),
                     "role": "row_group", "classification": proof["classification"],
                     "rule_id": "printed_financial_statement_classification"})
    classification = None
    if kind == "parent_label":
        classification = _classification(text, statement, parents)
        if classification is None:
            return result
        rows.append({"text": text, "source": copy.deepcopy(source), "role": "row_group",
                     "classification": classification, "rule_id": "printed_financial_statement_classification"})
    elif not rows:
        return result
    result.update(matched=True, heading=copy.deepcopy(heading), statement_kind=statement,
                  classification=classification, label={"text": text, "source": copy.deepcopy(source)},
                  group_path=[row["text"] for row in rows], row_evidence=rows,
                  unit_binding={"declaration": copy.deepcopy(unit), "rule_id": "statement_caption_across_explicit_classification_parents"},
                  source_disposition={"role": "financial_statement_classification", "business_vote": False,
                                      "semantics": "source_bound_group_identity_and_unit_scope",
                                      "rule_id": "printed_financial_statement_classification"})
    return result


def bind_financial_group_facts(result: dict[str, Any], context: dict[str, Any]) -> None:
    """Bind already-read scalar facts without changing any literal or count."""
    if not context.get("matched"):
        return
    for fact in result.get("facts", []):
        if fact.get("role") == "identity":
            issue = {"reason": "financial_classification_identity_binding_unsupported", "layers": ["L"],
                     "source": copy.deepcopy(fact["source"]), "text": fact["value"],
                     "group_evidence": copy.deepcopy(context["row_evidence"]),
                     "policy": "independent_identity_value_retained_without_claiming_its_unread_group_binding"}
            result.setdefault("blockers", []).append(copy.deepcopy(issue))
            result.setdefault("pending_requirements", []).append(issue)
            continue
        facets = fact.setdefault("identity_facets", {})
        if "group" in facets and facets["group"] != context["group_path"]:
            continue
        facets["group"] = copy.deepcopy(context["group_path"])
        fact.setdefault("row_evidence", []).extend(copy.deepcopy(context["row_evidence"]))
        fact.setdefault("role_basis", {})["financial_group_context"] = copy.deepcopy(context)


def _same_object(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return bool(left.get("path") and all(left.get(key) == right.get(key)
                                        for key in ("path", "lines", "cell", "block", "block_lines")))


def read_financial_attribution_context(series: dict[str, Any], *, heading: dict[str, Any] | None,
                                       syntax: list[dict[str, Any]], pending: list[dict[str, Any]],
                                       parents: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve a deferred Unit only through a complete existing reader proof.

    No metric or attribution keyword is read here. The existing series reader
    must have bound every scalar to an actual parent and recipient. Its first
    child must directly follow the deferred structural parent, so ordinary
    prose, an unknown ancestor, a new heading, or an image cannot be bypassed.
    """
    result: dict[str, Any] = {"matched": False}
    bindings = series.get("parent_bindings", [])
    if not financial_statement_kind(heading) or len(bindings) != 1 or not parents or len(syntax) < 2:
        return result
    binding = bindings[0]
    parent = binding.get("parent", {})
    facts = series.get("facts", [])
    if (binding.get("kind") != "attribution" or binding.get("rule_id") != "printed_attribution_parent_and_recipient"
            or not facts or {item.get("id") for item in facts} != {item.get("fact_id") for item in binding.get("facts", [])}
            or not _same_object(parent.get("source", {}), parents[-1].get("source", {}))
            or not _same_object(binding.get("child", {}).get("source", {}), syntax[-1].get("source", {}))
            or any(not _same_object(fact.get("source", {}), syntax[-1].get("source", {})) for fact in facts)
            or any(fact.get("role_basis", {}).get("attribution", {}).get("parent") != parent for fact in facts)):
        return result
    previous = syntax[-2]
    if (previous.get("kind") != "parent_label" or not _same_object(previous.get("source", {}), parent.get("source", {}))
            or previous.get("text", "").strip().rstrip(":：").rstrip() != parent.get("text")
            or previous.get("scope") != syntax[-1].get("scope")
            or previous.get("parents", []) != [item["text"] for item in parents[:-1]]):
        return result
    for issue in pending:
        boundary = issue.get("boundary", {})
        if (issue.get("reason") != "unit_scope_boundary_unresolved" or boundary.get("kind") != "parent_label"
                or not _same_object(boundary.get("source", {}), parent.get("source", {}))
                or boundary.get("text") != previous["text"] or issue.get("scope") != previous.get("scope")):
            continue
        unit = {"text": issue["unit"], "source": copy.deepcopy(issue["unit_source"]), "level": "caption_shared"}
        if not read_unit_token(unit["text"], unit["source"])["matched"]:
            continue
        outer = read_financial_group_context("", syntax[-1]["source"], kind="field", heading=heading,
                                              parents=parents[:-1], unit=unit)
        if parents[:-1] and not outer["matched"]:
            continue
        result.update(matched=True, unit=unit, parent_binding=copy.deepcopy(binding),
                      boundary=copy.deepcopy(boundary), pending_source=copy.deepcopy(issue["source"]),
                      outer_group_context=outer,
                      rule_id="statement_unit_resumed_by_source_bound_parent_recipient_proof")
        return result
    return result
