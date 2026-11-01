"""Literal measurement applicability; independent of references and parsers.

This module never supplies a missing unit or changes a number. It only rejects
incompatible inheritance or an explicitly printed incompatible qualification.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence


def unit_kind(unit: str) -> str:
    text = unicodedata.normalize("NFKC", unit).strip().casefold()
    if re.search(r"%|‰|百分|percentage|basis points?|bps", text):
        return "ratio"
    if re.search(r"元|美元|港币|港幣|币种|幣種|[$€£¥]|\b(?:rmb|cny|usd|hkd|eur|gbp)\b", text):
        return "money"
    if re.search(r"股|\bshares?\b", text):
        return "shares"
    if re.fullmatch(r"岁|歲|年|years?", text):
        return "age"
    if re.fullmatch(r"人|persons?|people|employees?", text):
        return "people"
    if re.fullmatch(r"(?:in\s+)?(?:thousands?|millions?|billions?)", text):
        return "scale"
    return "other"


def measurement_kind(labels: Sequence[str]) -> str | None:
    text = " / ".join(unicodedata.normalize("NFKC", label).strip() for label in labels)
    if re.search(r"年龄|年齡|\bAge\b|任职年限|任職年限", text, re.I):
        return "age"
    if any(re.fullmatch(r".*(?:代码|代碼|编号|編號|编码|編碼)|序号|序號|姓名|名称|名稱|"
                        r"Name|ID|Code|Index|No\.?|.*日期|Date", label.strip(), re.I) for label in labels):
        return "identifier"
    if re.search(r"金额|金額|余额|餘額|额度|額度|报酬|報酬|薪酬|\bAmount\b|\bBalance\b|\bSalary\b", text, re.I):
        return "money"
    if re.search(r"股数|股數|持股数量|持股數量|股份数量|股份數量|number of shares|shares held", text, re.I):
        return "shares"
    if re.search(r"人数|人數|number of (?:people|employees)|headcount", text, re.I):
        return "people"
    if re.search(r"比例|比率|利率|占比|佔比|同比|\bpercent(?:age)?\b|\bratio\b|\brate\b|[（(]\s*[%‰]\s*[）)]", text, re.I):
        return "ratio"
    return None


def unit_applicable(unit: str, columns: Sequence[str], rows: Sequence[str] = ()) -> bool:
    kind = measurement_kind(columns) or measurement_kind(rows)
    if kind is None:
        return True
    actual = unit_kind(unit)
    # An explicitly percent-denominated amount is a share of an amount.
    # Literal percent declarations take precedence over a generic Amount
    # label; they do not authorize a currency unit on a ratio or count.
    return kind != "identifier" and (actual == kind or kind == "money" and actual == "ratio"
                                     or actual == "scale" and kind in {"money", "shares", "people"})
