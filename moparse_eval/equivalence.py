"""One auditable final equivalence decision for business and logical roles."""

from __future__ import annotations

import copy
import re
import unicodedata
from datetime import date
from typing import Any

from rapidfuzz.distance import Levenshtein

from .business_labels import role_label
from .period_evidence import DATE_PATTERN, calendar_date
from .quantity import (
    canonical_currency,
    exact_number,
    normalize_quantity,
    normalize_unit,
    ratio,
    unit_key,
)

_PROTECTED = re.compile(r"\d+(?:\.\d+)?|>=|<=|[<>≤≥=≠%‰]|\b(?:gross|net|before|after|not|no|non|without|except|unless|only|"
                        r"roa|roe|roic|income|cost|tax|yoy|qoq|usd|rmb|cny|hkd|eur|bps|pp)\b|"
                        r"毛|净|淨|税前|稅前|税后|稅後|收入|成本|同比|环比|環比|不|未|非|除外|美元|人民币|人民幣", re.I)
_PERIODS = {"period", "from_period", "to_period", "comparison_period"}
_MONTHS = {name.casefold(): index for index, names in enumerate((
    ("Jan", "January"), ("Feb", "February"), ("Mar", "March"), ("Apr", "April"), ("May",),
    ("Jun", "June"), ("Jul", "July"), ("Aug", "August"), ("Sep", "Sept", "September"),
    ("Oct", "October"), ("Nov", "November"), ("Dec", "December")), 1) for name in names}


def normalize_period_basis(value):
    if not isinstance(value, str):
        return None
    literal = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).strip()).casefold()
    if literal in {"at", "as of", "as at", "截至"}:
        return {"kind": "instant", "duration_months": None}
    month_count = None
    english = re.fullmatch(r"(?:(?:for\s+)?(?:the\s+)?)?(?:(?:fiscal\s+)?(?P<year>years?)|"
                           r"(?P<quarter>quarters?)|(?P<count>six|6|three|3|twelve|12)\s+months?)\s+ended", literal)
    if english:
        month_count = 12 if english["year"] else 3 if english["quarter"] else {
            "six": 6, "6": 6, "three": 3, "3": 3, "twelve": 12, "12": 12}[english["count"]]
    elif re.fullmatch(r"止年度|止(?:十二|12)[个個]月", literal):
        month_count = 12
    elif re.fullmatch(r"止(?:六|6)[个個]月", literal):
        month_count = 6
    elif re.fullmatch(r"止季度|止(?:三|3)[个個]月", literal):
        month_count = 3
    return {"kind": "ending_interval", "duration_months": month_count} if month_count is not None else None


def _calendar_day(value):
    if not isinstance(value, str):
        return False, None
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})|(\d{4})年(\d{1,2})月(\d{1,2})日", value)
    english = re.fullmatch(r"([A-Za-z]+)\.?\s*(\d{1,2})\s*,\s*(\d{4})", value)
    if match:
        components = match.groups()[:3] if match[1] else match.groups()[3:]
        year, month, day = map(int, components)
    elif english and english[1].casefold() in _MONTHS:
        year, month, day = int(english[3]), _MONTHS[english[1].casefold()], int(english[2])
    else:
        parsed = calendar_date(value)
        if parsed is not None:
            return True, parsed
        return (True, None) if re.fullmatch(DATE_PATTERN, value, re.I) else (False, None)
    try:
        return True, date(year, month, day).isoformat()
    except ValueError:
        return True, None


def _canonical(value: Any, context: dict[str, Any]) -> Any:
    canonicalize = context.get("canonicalize")
    if isinstance(value, str):
        return canonicalize(value) if canonicalize else unicodedata.normalize("NFKC", value).strip()
    if isinstance(value, dict):
        return {key: _canonical(item, context) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item, context) for item in value]
    return value


def _context_proof(context: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    checks = context.get("independent_checks", [])
    valid = [copy.deepcopy(check) for check in checks if check.get("correct") is True
             and check.get("dimension") in {"subject", "scope", "period", "unit", "currency", "identity_facets", "record"}
             and isinstance(check.get("source"), dict) and check["source"].get("path")]
    dimensions = {check["dimension"] for check in valid}
    anchor = evidence.get("independent_binding") is True and bool(evidence.get("source", {}).get("path"))
    return {"sufficient": anchor or len(dimensions) >= 2 and bool(dimensions & {"subject", "scope", "record"}),
            "independent_checks": valid, "independent_binding": bool(anchor)}


def decide_equivalence(required: Any, actual: Any, dimension: str, *, context: dict[str, Any] | None = None,
                       evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    context, evidence = context or {}, evidence or {}
    a, b = _canonical(required, context), _canonical(actual, context)
    result = {"equivalent": False, "status": "mismatch", "rule_id": "literal_mismatch", "dimension": dimension,
              "raw": {"required": copy.deepcopy(required), "actual": copy.deepcopy(actual)},
              "canonical": {"required": a, "actual": b}, "conflicts": [], "proof": {}}

    def finish(correct, rule, *, conflicts=(), proof=None, status=None):
        result.update(equivalent=bool(correct), status=status or ("equivalent" if correct else "mismatch"),
                      rule_id=rule, conflicts=list(conflicts), proof=proof or {})
        return result

    if dimension == "structure":
        if isinstance(required, dict) and isinstance(actual, dict):
            decisions = {}
            for key in sorted(set(required) | set(actual)):
                first, second = required.get(key), actual.get(key)
                child_dimension = key
                if key == "text" and required.get("type") in {"unit", "currency", "period_basis", *_PERIODS}:
                    child_dimension = required["type"]
                elif key in {"attribute", "action"}:
                    child_dimension = "label"
                elif isinstance(first, (dict, list)) or isinstance(second, (dict, list)):
                    child_dimension = "structure"
                if key == "unit":
                    first = {"unit": first, "currency": required.get("currency"), "quantity_role": required.get("quantity_role")}
                    second = {"unit": second, "currency": actual.get("currency"), "quantity_role": actual.get("quantity_role")}
                elif key == "text" and child_dimension == "unit":
                    first = {"unit": first, "currency": required.get("currency")}
                    second = {"unit": second, "currency": actual.get("currency")}
                decisions[key] = decide_equivalence(first, second, child_dimension, context=context, evidence=evidence)
                if key not in required or key not in actual:
                    decisions[key].update(equivalent=False, status="mismatch", conflicts=["missing_structural_field"])
            correct = all(item["equivalent"] for item in decisions.values())
            result["canonical"] = {side: {key: decision["canonical"][side] for key, decision in decisions.items()}
                                   for side in ("required", "actual")}
            return finish(correct, "complete_structural_roles", conflicts=[key for key, item in decisions.items() if not item["equivalent"]],
                          proof={"fields": decisions})
        if isinstance(required, (list, tuple)) and isinstance(actual, (list, tuple)):
            decisions = [decide_equivalence(first, second, "structure", context=context, evidence=evidence)
                         for first, second in zip(required, actual, strict=False)]
            correct = len(required) == len(actual) and all(item["equivalent"] for item in decisions)
            result["canonical"] = {side: [item["canonical"][side] for item in decisions]
                                   + _canonical(list(original[len(decisions):]), context)
                                   for side, original in (("required", required), ("actual", actual))}
            return finish(correct, "ordered_structural_roles", conflicts=[] if correct else ["ordered_roles"], proof={"items": decisions})
        if type(required) is not type(actual):
            return finish(False, "structural_type_mismatch", conflicts=["structural_type"])
        return decide_equivalence(required, actual, "literal", context=context, evidence=evidence)

    if dimension == "quantity":
        if not isinstance(required, dict) or not isinstance(actual, dict):
            return finish(False, "quantity_input_unresolved", conflicts=["quantity_requires_value_and_own_unit"], status="unresolved")
        first, second = normalize_quantity(required), normalize_quantity(actual)
        result["canonical"] = {"required": first, "actual": second}
        if not first["matched"] or not second["matched"]:
            first_number, second_number = exact_number(required.get("value")), exact_number(actual.get("value"))
            same_literal = (bool(required.get("unit")) and _canonical(required.get("unit"), context) == _canonical(actual.get("unit"), context)
                            and canonical_currency(required.get("currency")) == canonical_currency(actual.get("currency"))
                            and required.get("quantity_role") == actual.get("quantity_role"))
            if (not first["unit"]["conflicts"] and not second["unit"]["conflicts"] and same_literal
                    and first_number is not None and second_number is not None):
                result["canonical"] = {side: {"dimension": "literal_unit", "unit": _canonical(item["unit"], context),
                    "currency": canonical_currency(item.get("currency")), "quantity_role": item.get("quantity_role"), "value": ratio(number)}
                    for side, item, number in (("required", required, first_number), ("actual", actual, second_number))}
                equal = first_number == second_number
                return finish(equal, "exact_number_same_literal_unit", conflicts=[] if equal else ["quantity_value"],
                              proof={"arithmetic": "Fraction(Decimal)", "unit_conversion": False, "no_missing_unit_inference": True})
            return finish(False, "quantity_syntax_unresolved", conflicts=first["conflicts"] + second["conflicts"] or ["unknown_unit"],
                          proof={"arithmetic": "Fraction(Decimal)", "no_rounding": True}, status="unresolved")
        compatible = unit_key(first["unit"]) == unit_key(second["unit"])
        equal = compatible and first["value"] == second["value"]
        result["canonical"] = {side: {**{key: normalized["unit"][key] for key in
            ("dimension", "family", "currency", "quantity_role")}, "value": normalized["value"]}
            for side, normalized in (("required", first), ("actual", second))}
        return finish(equal, "exact_quantity_scale_conversion", conflicts=[] if equal else ["quantity_value" if compatible else "quantity_dimension_currency_or_role"],
                      proof={"arithmetic": "Fraction(Decimal)", "required_scale": first["unit"]["scale"],
                             "actual_scale": second["unit"]["scale"], "no_rounding": True, "no_missing_value_inference": True})
    if dimension == "unit":
        first = normalize_unit(a.get("unit"), a.get("currency"), a.get("quantity_role")) if isinstance(a, dict) else normalize_unit(a)
        second = normalize_unit(b.get("unit"), b.get("currency"), b.get("quantity_role")) if isinstance(b, dict) else normalize_unit(b)
        result["canonical"] = {side: list(unit_key(parsed)) if parsed["matched"] else {
            "literal_unit": value.get("unit") if isinstance(value, dict) else value,
            "currency": parsed["currency"], "quantity_role": parsed["quantity_role"]}
            for side, parsed, value in (("required", first, a), ("actual", second, b))}
        if first["conflicts"] or second["conflicts"]:
            return finish(False, "unit_currency_or_role_conflict", conflicts=first["conflicts"] + second["conflicts"])
        if result["canonical"]["required"] != result["canonical"]["actual"] and (not first["matched"] or not second["matched"]):
            return finish(False, "unit_syntax_unresolved", conflicts=["unknown_unit_conversion"],
                          proof={"required_unit": first, "actual_unit": second, "value_used": False}, status="unresolved")
        equal = (result["canonical"]["required"] == result["canonical"]["actual"] or
                 first["matched"] and second["matched"] and unit_key(first) == unit_key(second))
        return finish(equal, "compatible_unit_dimension" if first["matched"] and second["matched"] else "same_literal_unit",
                      conflicts=[] if equal else ["unit_dimension_currency_or_role"],
                      proof={"required_unit": first, "actual_unit": second, "value_used": False})
    if dimension == "currency":
        a, b = canonical_currency(a), canonical_currency(b)
    elif dimension == "period_basis":
        first_basis, second_basis = normalize_period_basis(a), normalize_period_basis(b)
        if first_basis is not None or second_basis is not None:
            result["canonical"] = {"required": first_basis if first_basis is not None else a,
                                   "actual": second_basis if second_basis is not None else b}
            equal = first_basis is not None and first_basis == second_basis
            return finish(equal, "declared_period_basis_equivalence", conflicts=[] if equal else ["period_role_or_explicit_duration"],
                          proof={"required_basis": first_basis, "actual_basis": second_basis,
                                 "start_inferred": False, "fiscal_year_inferred": False})
    elif dimension in _PERIODS:
        a = a.removesuffix("年") if isinstance(a, str) and re.fullmatch(r"(?:19|20)\d{2}年?", a) else a
        b = b.removesuffix("年") if isinstance(b, str) and re.fullmatch(r"(?:19|20)\d{2}年?", b) else b
        first_date, second_date = _calendar_day(a), _calendar_day(b)
        if first_date[0] or second_date[0]:
            if first_date == (True, None) or second_date == (True, None):
                return finish(False, "invalid_full_calendar_day", conflicts=["invalid_calendar_day"], status="unresolved")
            a = first_date[1] if first_date[0] else a
            b = second_date[1] if second_date[0] else b
    elif dimension in {"label", "attribute", "action"} and isinstance(a, str) and isinstance(b, str):
        a, b = role_label(a), role_label(b)
    elif dimension == "number":
        first, second = exact_number(a), exact_number(b)
        if first is not None and second is not None:
            a, b = ratio(first), ratio(second)
    result["canonical"] = {"required": a, "actual": b}
    if a == b:
        return finish(True, "declared_role_spelling" if required != actual and dimension in {"label", "attribute", "action"} else "exact_canonical_literal")
    if dimension in {"label", "attribute", "action"} and isinstance(a, str) and isinstance(b, str):
        proof = _context_proof(context, evidence)
        protected_a, protected_b = [x.casefold() for x in _PROTECTED.findall(a)], [x.casefold() for x in _PROTECTED.findall(b)]
        if (len(a) >= 6 and len(b) >= 6 and Levenshtein.distance(a, b) <= 1
                and protected_a == protected_b and proof["sufficient"]):
            result["canonical"]["actual"] = a
            return finish(True, "label_one_edit_with_independent_context", proof={**proof, "edit_distance": 1,
                          "protected_tokens": protected_a, "actual_label": b})
        return finish(False, "label_equivalence_rejected", conflicts=["protected_token_change" if protected_a != protected_b else
                      "short_label_or_edit_distance" if len(a) < 6 or len(b) < 6 or Levenshtein.distance(a, b) > 1 else "independent_context_insufficient"], proof=proof)
    return finish(False, "literal_mismatch", conflicts=[dimension])
