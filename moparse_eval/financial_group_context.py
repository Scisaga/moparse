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
