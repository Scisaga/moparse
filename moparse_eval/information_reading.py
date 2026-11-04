"""Candidate-only literal unit lexer retained for saved service readback.

No business target interpretation, matching or scoring is implemented here.
"""

from __future__ import annotations

import re
from functools import lru_cache

from .metrics import normalize_text

_UNIT = re.compile(r"(?:(?:人民币|人民幣|美元|港元|港幣|港币|欧元|歐元)?(?:万亿元|萬億元|千亿元|千億元|百亿元|百億元|十亿元|十億元|亿元|億元|千万元|千萬元|百万元|百萬元|千元|万元|萬元|元)|RMBbn|RMB['’]000|(?:RMB|USD|HKD|CNY)\s+million|(?<!\w)(?:in\s+)?(?:thousands?|millions?|billions?|[Dd]ays?|[Tt]imes)(?!\w)|\bcontracts?\b|[十百千万萬亿億]*股(?!\w)|USD|EUR|HKD|CNY|RMB|\$\s*(?:in\s+millions|bn|m)|['’]\s*000\s+(?:contracts|lots)|[个個]?百分点|[个個]?百分點|percentage points?|basis points?|bps|(?:毫克|千克|公斤|(?:千萬|千万|百萬|百万|萬|万|千)?(?:吨|噸))|[%‰$€£¥])(?:/[A-Za-z\u3400-\u9fff0-9³²]+)?")


def units(text: str) -> list[str]:
    return list(_cached_units(text))


@lru_cache(maxsize=8192)
def _cached_units(text: str) -> tuple[str, ...]:
    text = normalize_text(text)
    explicit = list(re.finditer(r"(?:^|[（(\s])(?:单位|單位)\s*[:：(（]\s*([^()（）,，。;；\n]{1,48})", text))
    known = list(_UNIT.finditer(text))
    values = [re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "",
                     re.split(r"(?:币种|幣種|currency)\s*[:：]", m[1], maxsplit=1, flags=re.I)[0].strip())
              for m in explicit]
    values += [m.group() for m in known
               if not any(a.start(1) <= m.start() and m.end() <= a.end(1) for a in explicit)]
    values += [m.group() for m in re.finditer(r"(?<!\w)(?:人|次|股|台|家|个|個|天|日)(?!\w)", text)
               if not any(a.start(1) <= m.start() and m.end() <= a.end(1) for a in explicit)
               and not any(a.start() <= m.start() and m.end() <= a.end() for a in known)]
    values += [unit for word, unit in (("次数", "次"), ("次數", "次"), ("年限", "年"),
                                      ("人数", "人"), ("人數", "人"), ("股数", "股"), ("股數", "股"))
               if word in text]
    return tuple(dict.fromkeys(values))


def unit_scope_literal(text: str) -> bool:
    text = normalize_text(text, collapse_whitespace=True)
    unwrapped = text.strip(" ()（）")
    in_clause = re.fullmatch(r"in\s+(.+)", unwrapped, re.I)
    return bool(units(text) and (unwrapped in units(text) or re.search(
        r"(?:^|[（(])\s*(?:单位|單位)\s*[:：（(]", text)
        or in_clause and in_clause[1] in units(in_clause[1])
        or re.fullmatch(r"\$\s*in\s+millions(?:,\s*except\s+per\s+share\s+(?:data|amounts))?", unwrapped, re.I)))
