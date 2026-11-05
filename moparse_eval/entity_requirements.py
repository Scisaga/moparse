"""Finite, source-only identity assertions for explicitly printed business roles.

This reader copies a role and its asserted entity. It does not resolve names,
complete omitted parties, or decide whether an entity is the expected answer.
Unknown or qualified role assignments remain pending business requirements.
"""

from __future__ import annotations

import copy
import re
from typing import Any

_ENGLISH_ROLES = frozenset({
    "borrower", "lender", "issuer", "guarantor", "trustee", "beneficiary", "creditor", "debtor",
    "grantor", "owner", "operator", "employer", "employee", "director", "chairperson", "secretary",
    "auditor", "registrar", "purchaser", "seller", "customer", "supplier", "applicant", "respondent",
})
_CHINESE_ROLES = frozenset({
    "借款人", "贷款人", "貸款人", "发行人", "發行人", "担保人", "擔保人", "受托人", "受託人",
    "受益人", "债权人", "債權人", "债务人", "債務人", "所有者", "运营方", "營運方", "雇主", "僱主",
    "雇员", "僱員", "董事", "主席", "审计师", "審計師", "购买方", "購買方", "卖方", "賣方", "供应商", "供應商",
})
_EN_ASSIGNMENT = re.compile(r"(?:(?i:the)\s+)?(?P<role>[A-Za-z][A-Za-z ]{0,70}?)\s+(?P<verb>is|are)\s+(?P<value>.*)", re.I | re.S)
_ZH_ASSIGNMENT = re.compile(r"(?P<role>[\u3400-\u9fff]{1,20}?)(?P<verb>不是|并非|並非|为|為|是)(?P<value>.*)", re.S)
_PAIR = re.compile(r"(?P<role>[A-Za-z][A-Za-z ]{0,70}|[\u3400-\u9fff]{1,20})\s*[:：]\s*(?P<value>.*)", re.S)
_QUALIFICATION = re.compile(r"\b(?:not|never|no|if|unless|except|only|and|or|but|is|are|was|were|subject\s+to)\b|(?:不是|并非|並非|除非|如果|若|或|以及|及|且|但)", re.I)
_NON_ENTITY = re.compile(r"ready|eligible|liable|responsible|available|required|permitted|unknown|none|null|unavailable|insolvent|not applicable", re.I)
_UNSUPPORTED_ROLE = re.compile(
    r"(?:agent|administrator|manager|holder|arranger|bookrunner|custodian|depositary|servicer|nominee|counterparty|lessee|lessor|licensor|licensee)$"
    r"|(?:管理人|代理人|保管人|登记人|登記人|承销商|承銷商|承租人|出租人|交易对手|交易對手)$", re.I)
_IMPORTANT_ENTITY_ROLES = frozenset({
    "company", "entity", "subject", "legal entity", "organisation", "organization", "corporation", "party",
    "borrowers", "lenders", "issuers", "guarantors", "公司", "本公司", "主体", "主體", "企业", "企業",
    "机构", "機構", "本集团", "本集團",
})
_EXISTING_PRIMARY_LABELS = frozenset({"name", "entity", "company", "subject", "名称", "姓名", "主体", "公司名称"})
_ROLE_MENTION = re.compile(r"\b(?:" + "|".join(sorted(_ENGLISH_ROLES)) + r")\b|"
                           + "|".join(sorted(_CHINESE_ROLES, key=len, reverse=True)), re.I)
_ASSIGNMENT_CUE = re.compile(r"\b(?:is|are|means|named|called|identified)\b|为|為|是|名稱|名称", re.I)
_QUOTES = {'"': '"', "'": "'", "“": "”", "‘": "’", "「": "」", "『": "』"}


def canonical_entity_role(role: str) -> str:
    """Only known English property roles have case-insensitive spellings."""
    return role.casefold() if role.casefold() in _ENGLISH_ROLES else role


def _result() -> dict[str, Any]:
    return {"matched": False, "facts": [], "relations": [], "text_spans": [], "blockers": [], "issues": [],
            "pending_requirements": [], "consumed_spans": [], "unmatched_spans": []}


def _source(source: dict[str, Any], start: int, end: int) -> dict[str, Any]:
    span = source.get("text_span")
    offset = span[0] if isinstance(span, (list, tuple)) and len(span) == 2 and type(span[0]) is int else 0
    return {**copy.deepcopy(source), "text_span": [offset + start, offset + end]}


def _sentences(text: str) -> list[tuple[int, int]]:
    result, start, quote = [], 0, None
    for index, character in enumerate(text):
        if quote:
            if character == quote:
                quote = None
            continue
        if character in _QUOTES and not (character == "'" and index and text[index - 1].isalnum()):
            quote = _QUOTES[character]
            continue
        if character not in ".!?。！？" or (index + 1 < len(text) and not text[index + 1].isspace() and character in ".!?"):
            continue
        if character == "." and re.search(r"\b(?:Ltd|Inc|Corp|Co|Dr|Mr|Mrs)\.$", text[start:index + 1]) and index + 1 < len(text):
            continue
        if text[start:index + 1].strip():
            result.append((start, index + 1))
        start = index + 1
    if text[start:].strip():
        result.append((start, len(text)))
    return result


def _pending(result, source, text, role, reason):
    result["pending_requirements"].append({"kind": "entity_role_assertion", "role": "identity", "attribute": role,
                                           "text": text, "source": copy.deepcopy(source), "reason": reason})
    result["blockers"].append({"reason": reason, "source": copy.deepcopy(source), "text": text, "layers": ["B"]})


def read_entity_requirements(text: str, source: dict[str, Any], *, scope=(), parents=()) -> dict[str, Any]:
    """Read explicit role/party clauses with their own immutable source spans."""
    del parents  # A surrounding record never supplies a missing entity answer.
    result = _result()

    def unread_role(fragment, start, end):
        mention = _ROLE_MENTION.search(fragment)
        if mention is None or _ASSIGNMENT_CUE.search(fragment) is None:
            return False
        prefix, suffix = fragment[:mention.start()].strip(), fragment[mention.end():].strip()
        subject_role = prefix.casefold() in {"", "the", "本", "该", "該"} and _ASSIGNMENT_CUE.search(suffix)
        reverse_role = (re.fullmatch(r"[.!?。！？]*", suffix) is not None
                        and re.search(r"\b(?:is|are)(?:\s+the)?$|(?:是|为|為)$", prefix, re.I))
        if not subject_role and not reverse_role:
            return False
        result["matched"] = True
        result["consumed_spans"].append([start, end])
        _pending(result, _source(source, start, end), fragment, mention[0], "entity_assignment_syntax_unsupported")
        return True

    spans = _sentences(text)
    for raw_start, raw_end in spans:
        start, end = raw_start, raw_end
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        fragment = text[start:end]
        pair = _PAIR.fullmatch(fragment)
        match = pair or _EN_ASSIGNMENT.fullmatch(fragment) or _ZH_ASSIGNMENT.fullmatch(fragment)
        if match is None:
            if not unread_role(fragment, start, end):
                result["unmatched_spans"].append([start, end])
            continue
        role = match["role"].strip()
        known = role.lower() in _ENGLISH_ROLES or role in _CHINESE_ROLES
        value = match["value"].strip()
        # Existing fields retain their grammar. Unknown copulas are important
        # entity assertions only when the role itself supplies that evidence;
        # capital letters and CJK text do not establish a business role.
        important = role.casefold() in _IMPORTANT_ENTITY_ROLES or bool(_UNSUPPORTED_ROLE.search(role))
        if pair is not None and role.casefold() in _EXISTING_PRIMARY_LABELS:
            result["unmatched_spans"].append([start, end])
            continue
        if not known and not important:
            if not unread_role(fragment, start, end):
                result["unmatched_spans"].append([start, end])
            continue
        if pair is None and re.match(r"required\s+to\b", value, re.I):
            # This is the modal grammar's explicit obligation, not a party name.
            result["unmatched_spans"].append([start, end])
            continue
        result["matched"] = True
        result["consumed_spans"].append([start, end])
        clause_source = _source(source, start, end)
        if not known:
            _pending(result, clause_source, fragment, role, "entity_role_semantics_unsupported")
            continue
        value_start, value_end = start + match.start("value"), start + match.end("value")
        while value_start < value_end and text[value_start].isspace():
            value_start += 1
        while value_end > value_start and text[value_end - 1].isspace():
            value_end -= 1
        if pair is None and value_end > value_start and text[value_end - 1] in ".!?。！？":
            # A bare legal abbreviation at a sentence end is ambiguous. Quote
            # it or use a labelled field to state its exact punctuation.
            if re.search(r"\b(?:Ltd|Inc|Corp|Co)\.$", text[value_start:value_end]):
                _pending(result, clause_source, fragment, role, "entity_name_terminal_punctuation_ambiguous")
                continue
            value_end -= 1
        value = text[value_start:value_end]
        if not value:
            _pending(result, clause_source, fragment, role, "entity_name_missing")
            continue
        quoted = value[0] in _QUOTES
        if quoted:
            close = _QUOTES[value[0]]
            if len(value) < 3 or value[-1] != close or close in value[1:-1]:
                _pending(result, clause_source, fragment, role, "entity_name_quote_scope_unsupported")
                continue
            value_start += 1
            value_end -= 1
            value = text[value_start:value_end]
        if ((not quoted and (_QUALIFICATION.search(value) or any(char in value for char in ";；:&")))
                or match.groupdict().get("verb") in {"不是", "并非", "並非"}
                or _NON_ENTITY.fullmatch(value)
                or "\n" in value):
            _pending(result, clause_source, fragment, role, "qualified_or_compound_entity_assertion_unsupported")
            continue
        role_start = start + match.start("role")
        role_end = role_start + len(role)
        result["facts"].append({"subject": "", "attribute": role, "value": value, "role": "identity", "qualifiers": {},
                                "identity_facets": {}, "scope": list(scope), "source": clause_source,
                                "attribute_source": _source(source, role_start, role_end),
                                "value_source": _source(source, value_start, value_end),
                                "subject_source": _source(source, role_start, role_end),
                                "role_basis": "explicit_printed_entity_role", "entity_syntax": "labelled" if pair else "copular"})
    if result["matched"]:
        result["text_spans"] = [{"text": text, "span": [0, len(text)], "role": "original_entity_prose",
                                  "source": _source(source, 0, len(text))}]
        if result["unmatched_spans"]:
            _pending(result, _source(source, 0, len(text)), text, "", "mixed_entity_prose_unsupported")
    return result
