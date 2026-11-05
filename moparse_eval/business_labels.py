"""Finite spellings of the same printed metric role, never entity repair.

These complete aliases are exact role declarations. The shared final engine
separately checks bounded label differences against independent context.
Values, subjects and source text retain their actual spelling.
"""

import re

from .entity_requirements import canonical_entity_role

ROLE_SPELLINGS = (
    ("金額", "金额"),
    ("佔營業收入比", "占营业收入比"),
    ("佔營業成本比", "占营业成本比"),
    ("佔總收入比", "占总收入比"),
    ("金額同比變動", "金额同比变动"),
)
_CANONICAL = {spelling: group[0] for group in ROLE_SPELLINGS for spelling in group}
_AMOUNT_ROLE = re.compile(r"^(?:Revenue|Profit|Amount|Balance|Salary|(?:营业|營業|销售|銷售)?收入|營收|营收|(?:净|淨|营业|營業)?(?:利潤|利润)|金額|金额|餘額|余额|薪酬)$", re.I)


def role_label(label: str) -> str:
    return _CANONICAL.get(label, canonical_entity_role(label))


def is_amount_role(label: str) -> bool:
    return bool(_AMOUNT_ROLE.fullmatch(label))
