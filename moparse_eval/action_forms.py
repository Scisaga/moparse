"""Finite action inflections shared by readers and source-role verification.

These are lexical declarations, not an interpretation or an obligation list.
The source scanner still enumerates printed material independently, including
unknown forms, and semantic audits still require exact source role evidence.
"""

PROPOSITION_ACTION_FORMS = {
    "own": "own", "owns": "own", "owned": "own", "hold": "hold", "holds": "hold", "held": "hold",
    "acquire": "acquire", "acquires": "acquire", "acquired": "acquire",
    "approve": "approve", "approves": "approve", "approved": "approve",
    "review": "review", "reviews": "review", "reviewed": "review",
    "pay": "pay", "pays": "pay", "paid": "pay", "publish": "publish", "publishes": "publish",
    "disclose": "disclose", "discloses": "disclose", "submit": "submit", "submits": "submit",
    "invest": "invest", "invests": "invest", "invested": "invest",
    "increase": "increase", "increases": "increase", "increased": "increase",
    "decrease": "decrease", "decreases": "decrease", "decreased": "decrease",
    "report": "report", "reports": "report", "reported": "report",
    "declare": "declare", "declares": "declare", "declared": "declare",
    "require": "require", "requires": "require", "retain": "retain", "retains": "retain",
    "exceed": "exceed", "exceeds": "exceed", "exceeded": "exceed",
    "provide": "provide", "provides": "provide", "repay": "repay", "repays": "repay",
    "guarantee": "guarantee", "guarantees": "guarantee", "sell": "sell", "sells": "sell", "sold": "sell",
}

NARRATIVE_ACTION_FORMS = dict(PROPOSITION_ACTION_FORMS)
NARRATIVE_PAST_FORMS = {word for word, base in NARRATIVE_ACTION_FORMS.items()
         if word != base and (word.endswith('ed') or word in {'held', 'paid', 'sold'})}
for _base, _forms in {
    "store": ("stores", "stored"), "retrieve": ("retrieves", "retrieved"),
    "release": ("releases", "released"), "delete": ("deletes", "deleted"),
    "include": ("includes", "included"), "comprise": ("comprises", "comprised"),
    "support": ("supports", "supported"), "operate": ("operates", "operated"),
    "design": ("designs", "designed"), "offer": ("offers", "offered"),
    "connect": ("connects", "connected"), "create": ("creates", "created"),
    "manage": ("manages", "managed"), "produce": ("produces", "produced"),
    "serve": ("serves", "served"), "develop": ("develops", "developed"),
    "build": ("builds", "built"), "enhance": ("enhances", "enhanced"),
    "maintain": ("maintains", "maintained"), "use": ("uses", "used"),
    "have": ("has", "had"), "need": ("needs", "needed"),
    "attend": ("attends", "attended"), "vote": ("votes", "voted"),
    "participate": ("participates", "participated"), "access": ("accesses", "accessed"),
    "deliver": ("delivers", "delivered"), "enable": ("enables", "enabled"),
    "sharpen": ("sharpens", "sharpened"),
    "help": ("helps", "helped"), "leverage": ("leverages", "leveraged"),
    "engage": ("engages", "engaged"), "capture": ("captures", "captured"),
}.items():
    NARRATIVE_ACTION_FORMS[_base] = _base
    NARRATIVE_ACTION_FORMS.update(dict.fromkeys(_forms, _base))
    NARRATIVE_PAST_FORMS.add(_forms[-1])
NARRATIVE_ACTION_FORMS.update(dict.fromkeys(("be", "is", "are", "was", "were"), "be"))
NARRATIVE_PAST_FORMS.update({'was', 'were'})

# These forms were already recognized by the independent source scanner. Some
# remain outside the smaller proposition reader's bounded grammar.
AUDITED_ACTION_FORMS = {
    **NARRATIVE_ACTION_FORMS,
    "published": "publish", "disclosed": "disclose", "submitted": "submit",
    "required": "require", "retained": "retain", "provided": "provide",
    "repaid": "repay", "guaranteed": "guarantee",
    "say": "say", "says": "say", "said": "say",
    "state": "state", "states": "state", "stated": "state",
}
