"""Bounded Chinese circumstances and their explicitly printed operations.

This extends the existing Narrative AST. Adjunct operations are non-counting
operands; no omitted actor, date, financial cause or numerical answer is filled
in. Unsupported syntax raises the shared reader's unresolved result.
"""

from __future__ import annotations

import copy
import json
import re

from .narrative_requirements import _Unknown

CIRCUMSTANCE_MARKERS = {'借助': 'means', '通过': 'means', '随着': 'background',
                         '由于': 'cause', '因为': 'cause', '受益于': 'cause',
                         '为了': 'purpose', '带来的': 'cause', '受': 'cause', '受到': 'cause',
                         '由於': 'cause', '因為': 'cause', '是': 'cause', '归因于': 'cause', '歸因於': 'cause',
                         '帶來的': 'cause', '导致': 'cause', '導致': 'cause'}
_EVENT = re.compile(r'增长|增長|增加|上升|下降|减少|減少|恢复|提升|优化|转型|变动|稳健|发展|建设|建設|变革|流入|流出|加大|投資|投资')
_QUALIFIER = re.compile(r'保持|逐步|持续|同比')
_ACTION = re.compile(r'(?P<manner>持续|持續)?(?P<verb>加大|坚持|优化|優化|偿还|償還|购买|購買|取得|分配|发行|發行|募集|注销|註銷|购回|購回|推進|推进|加強|加强|投資|投资)(?P<body>.+)')
_ACTOR = re.compile(r'本集[团團]|本公司')
FINANCIAL_NOMINAL = re.compile(r'(?:投資|投资|研究開發|研究开发)(?:支出|費用|费用)|(?:投資|投资)(?:者|公司|基金)|(?:經營|经营)(?:收益|狀況|状况|管理|情況|情况|業績|业绩)')
NOMINAL_TERM = re.compile(r'信息披露|資訊披露|资讯披露|[會会][計计]核算|業務流程|业务流程|[內内]部控制制度|決策機制|决策机制|[稅税]金及附加')
CJK_TITLE = re.compile(r'《[^《》]+》')


def outside_titles(text, matches):
    quoted = [m.span() for m in CJK_TITLE.finditer(text)]
    return [m for m in matches if not any(a <= m.start() < b for a, b in quoted)]
_ATTACHMENT = {'兩項變化均': 'all', '两项变化均': 'all', '兩項變化共同': 'all', '两项变化共同': 'all',
               '兩項均': 'all', '两项均': 'all', '均': 'all', '共同': 'all',
               '前者的變化': 'former', '前者的变化': 'former', '前者': 'former',
               '後者的變化': 'latter', '后者的变化': 'latter', '後者': 'latter', '后者': 'latter',
               '僅前者的變化': 'former', '仅前者的变化': 'former',
               '僅後者的變化': 'latter', '仅后者的变化': 'latter',
               '其中一項或兩項變化': 'unspecified_subset', '其中一项或两项变化': 'unspecified_subset'}
_CAUSE = re.compile(r'[，,。](?P<attachment>' + '|'.join(sorted(_ATTACHMENT, key=len, reverse=True)) + r')?'
                    r'(?P<degree>主要|部分)?(?P<marker>由于|由於|因为|因為|归因于|歸因於|是)'
                    r'(?P<body>.+?)(?P<non_exhaustive>等)?(?P<combined>综合影响|綜合影響)?'
                    r'(?P<suffix>所致|导致|導致)?$')


def trailing_cause(text):
    match = _CAUSE.search(text.rstrip('。.'))
    # 是 is a cause introducer only in the complete X导致 frame.
    return match if match and (match['marker'] != '是' or match['suffix'] in {'导致', '導致'}) else None


def _closed_parallel_reference(child, reader, operand):
    """A local parallel record and its common cause object, without values."""
    clauses = child.get('clauses', [])
    if reader is None or len(clauses) != 4 or operand.get('kind') != 'proposition':
        return False
    offset = reader.source.get('text_span', [0])[0]

    def printed(origin):
        a, b = origin['text_span']
        return reader.text[a - offset:b - offset]

    if re.search(r'。|[；;]|\n\s*\n', printed(child['source'])):
        return False
    parents, metrics = [], []
    for amount, change in zip(clauses[::2], clauses[1::2], strict=True):
        match = re.fullmatch(r'(?P<parent>非?流[动動][资資][产產]|非?流[动動][负負][债債])中的(?P<metric>.+)', amount.get('subject', ''))
        if (amount.get('kind') != 'quantity_assertion' or change.get('kind') != 'year_on_year_change'
                or amount.get('subject_source') != change.get('subject_source') or not match):
            return False
        parents.append(match['parent'].translate(str.maketrans('動資產負債', '动资产负债')))
        metrics.append(match['metric'])
    if (parents[0].removeprefix('非') != parents[1].removeprefix('非')
            or {p.startswith('非') for p in parents} != {False, True}
            or metrics[0] != metrics[1] or operand.get('object') != metrics[0]):
        return False
    prefixes = []
    for amount in clauses[::2]:
        origin = {**amount['source'], 'text_span': [amount['source']['text_span'][0], amount['subject_source']['text_span'][0]]}
        prefixes.append(printed(origin).strip())
    return (not prefixes[1] and (not prefixes[0] or re.fullmatch(r'(?:本公司|本集[团團]|[该該]事[业業]部)(?:的)?', prefixes[0])))


def causal_targets(child, attachment=None, *, reader=None, operand=None):
    """Bind explicit selectors or a source-proved closed parallel reference.

    Quantities, change direction and year values never select a cause target.
    A repeated metric/classification alone cannot establish common scope.
    """
    clauses = child.get('clauses', [])
    if attachment == 'unspecified_subset':
        raise _Unknown('cjk_causal_attachment_declared_uncertain')
    if attachment:
        if (len(clauses) != 4 or any(a.get('kind') != 'quantity_assertion'
                or b.get('kind') != 'year_on_year_change' or a.get('subject') != b.get('subject')
                for a, b in zip(clauses[::2], clauses[1::2], strict=True))):
            raise _Unknown('cjk_causal_scope_antecedents_unresolved')
        indexes = {'all': [1, 3], 'former': [1], 'latter': [3]}[attachment]
        return [copy.deepcopy(clauses[i]['source']) for i in indexes]
    if sum(c.get('kind') == 'year_on_year_change' for c in clauses) > 1:
        if _closed_parallel_reference(child, reader, operand or {}):
            return [copy.deepcopy(clauses[i]['source']) for i in (1, 3)]
        raise _Unknown('cjk_causal_scope_evidence_unresolved')
    return [copy.deepcopy(clauses[-1]['source'])] if clauses else []


def dependency(reader, role, child, marker=None):
    return {'kind': 'cjk_dependency', 'role': role, 'child': child,
            'marker': reader.text[slice(*marker)] if marker else None,
            **({'marker_span': list(marker)} if marker else {}),
            'span': [min(child['span'][0], marker[0] if marker else child['span'][0]),
                     max(child['span'][1], marker[1] if marker else child['span'][1])]}


def arithmetic_nominal(reader, start, end, depth=0):
    """A printed named-term expression; no calculation or percentage is added."""
    if depth > 8:
        raise _Unknown('cjk_formula_depth_unsupported')
    start, end = reader.trim(start, end)
    raw = reader.text[start:end]
    nesting, top = 0, []
    for i, char in enumerate(raw):
        if char in '(（':
            nesting += 1
        elif char in ')）':
            nesting -= 1
        elif nesting == 0 and char in '/÷+＋-−－':
            top.append((start + i, char))
        if nesting < 0:
            raise _Unknown('cjk_formula_parenthesis_unsupported')
    if nesting:
        raise _Unknown('cjk_formula_parenthesis_unsupported')
    operators = [(a, char) for a, char in top if char in '+＋-−－'] or top
    if operators:
        a, char = operators[-1]
        if not start < a < end - 1:
            raise _Unknown('cjk_formula_operand_missing')
        left = arithmetic_nominal(reader, start, a, depth + 1)
        if char in '/÷':
            return {'kind': 'cjk_nominal', 'head': '', 'head_span': [end, end], 'designation': 'arithmetic',
                    'parts': [dependency(reader, 'dividend', left),
                              dependency(reader, 'divisor', arithmetic_nominal(reader, a + 1, end, depth + 1), [a, a + 1])],
                    'span': [start, end]}
        role = 'addend' if char in '+＋' else 'subtrahend'
        # Commas in a printed right-hand subtraction list retain the same
        # operation. They never move an item across parentheses or division.
        commas = [a] + [a + 1 + m.start() for m in re.finditer('、', reader.text[a + 1:end])]
        parts = [dependency(reader, 'arithmetic_base', left)]
        for index, mark in enumerate(commas):
            stop = commas[index + 1] if index + 1 < len(commas) else end
            parts.append(dependency(reader, role, arithmetic_nominal(reader, mark + 1, stop, depth + 1), [mark, mark + 1]))
        return {'kind': 'cjk_nominal', 'head': '', 'head_span': [end, end], 'designation': 'arithmetic',
                'parts': parts, 'span': [start, end]}
    if raw.startswith(('（', '(')) and raw.endswith(('）', ')')):
        child = arithmetic_nominal(reader, start + 1, end - 1, depth + 1)
        return {'kind': 'cjk_nominal', 'head': '', 'head_span': [end, end], 'designation': 'arithmetic_group',
                'parts': [dependency(reader, 'arithmetic_group', child)], 'link_spans': [[start, start + 1], [end - 1, end]],
                'span': [start, end]}
    if not re.fullmatch(r'[\u3400-\u9fffA-Za-z0-9]+', raw):
        raise _Unknown('cjk_formula_named_operand_unsupported')
    return nominal(reader, start, end)


def nominal(reader, start, end):
    """A bounded literal nominal, or an explicit coordinated nominal group."""
    start, end = reader.trim(start, end)
    raw = reader.text[start:end]
    if CJK_TITLE.fullmatch(raw):
        return {'kind': 'cjk_nominal', 'head': raw[1:-1], 'head_span': [start + 1, end - 1], 'parts': [],
                'designation': 'book_title', 'link_spans': [[start, start + 1], [end - 1, end]], 'span': [start, end]}
    if NOMINAL_TERM.fullmatch(raw):
        return {'kind': 'cjk_nominal', 'head': raw, 'head_span': [start, end], 'parts': [],
                'lexical_role': 'nominal_term', 'span': [start, end]}
    goal = re.fullmatch(r'(?P<body>.+)的(?P<head>目標|目标)', raw)
    if goal:
        body_end = start + goal.end('body')
        joins = list(re.finditer(r'、|以及', goal['body']))
        chunks, cursor = [], start
        for join in joins:
            chunks.append((cursor, start + join.start()))
            cursor = start + join.end()
        chunks.append((cursor, body_end))
        children = []
        for a, b in chunks:
            match = re.match(r'平抑|穩定|稳定|防範|防范', reader.text[a:b])
            if match is None:
                raise _Unknown('cjk_nominal_goal_action_unresolved')
            middle = a + match.end()
            children.append({'kind': 'proposition', 'subject': '', 'subject_span': None, 'subject_phrase': None,
                             'attribute': match[0], 'predicate': match[0], 'predicate_span': [a, middle],
                             'object': reader.text[middle:b], 'object_span': [middle, b],
                             'object_phrase': nominal(reader, middle, b), 'role': 'description', 'span': [a, b]})
        operation = children[0] if len(children) == 1 else {'kind': 'coordination', 'operator': 'and', 'mode': 'goals',
            'children': children, 'operator_spans': [[start + j.start(), start + j.end()] for j in joins], 'span': [start, body_end]}
        return {'kind': 'cjk_nominal', 'head': goal['head'], 'head_span': [body_end + 1, end],
                'parts': [dependency(reader, 'goal_description', operation)], 'link_spans': [[body_end, body_end + 1]], 'span': [start, end]}
    dated = re.fullmatch(r'(?P<owner>本公司|本集[團团])(?P<years>(?:19|20)\d{2}年(?:[及和](?:19|20)\d{2}年)+)(?P<head>.+)', raw)
    if dated:
        ya, yb = start + dated.start('years'), start + dated.end('years')
        return {'kind': 'cjk_nominal', 'head': dated['head'], 'head_span': [yb, end],
                'parts': [dependency(reader, 'owner', nominal(reader, start, ya)),
                          dependency(reader, 'period_members', nominal(reader, ya, yb))], 'span': [start, end]}
    categories = re.fullmatch(r'(?P<members>[^類类、及和]+[類类](?:[及和、][^類类、及和]+[類类])+)(?P<head>.+(?:[業业]務|业务))', raw)
    if categories:
        middle = start + categories.end('members')
        return {'kind': 'cjk_nominal', 'head': categories['head'], 'head_span': [middle, end],
                'parts': [dependency(reader, 'shared_categories', nominal(reader, start, middle))], 'span': [start, end]}
    approved = re.fullmatch(r'(?P<actor>[^的]+?)(?P<marker>批准|[審审]批|制定|制[訂订])的(?P<head>.+)', raw)
    if approved:
        ma, mb = start + approved.start('marker'), start + approved.end('marker')
        child = nominal(reader, mb + 1, end)
        child['parts'].append(dependency(reader, 'governing_action_actor', nominal(reader, start, ma), [ma, mb]))
        child.setdefault('link_spans', []).append([mb, mb + 1])
        child['span'] = [start, end]
        return child
    if not raw or re.search(r'[，,。；;:：]|借助|随着|通过|受益于|因为|由于|为了|如果|同比|列示|列说明|带动', raw) or re.match(r'[一二三四五六七八九十]+是', raw):
        raise _Unknown('cjk_circumstance_nominal_boundary_unresolved')
    from .financial_group_context import financial_metric_designation

    designation = financial_metric_designation(raw)
    if designation:
        def bounds(key):
            return [start + designation.start(key), start + designation.end(key)]
        return {'kind': 'cjk_nominal', 'head': designation['head'], 'head_span': bounds('head'),
                'parts': [dependency(reader, 'measurement_basis', nominal(reader, *bounds('basis')), bounds('measurement')),
                          dependency(reader, 'valuation_change_recognition', nominal(reader, *bounds('destination')), bounds('recognition'))],
                'designation': 'fair_value_through_profit_or_loss',
                'link_spans': [bounds(k) for k in ('basis_link', 'join', 'change_link', 'link') if designation[k]],
                'span': [start, end]}
    related = re.fullmatch(r'(?P<owner>[^與与]+)?(?P<join>與|与)(?P<domain>.+?)(?P<marker>相關|相关)的(?P<head>.+)', raw)
    if related:
        ha = start + related.start('head')
        child = nominal(reader, ha, end)
        da, db = start + related.start('domain'), start + related.end('domain')
        ma, mb = start + related.start('marker'), start + related.end('marker')
        child['parts'].append(dependency(reader, 'related_to', nominal(reader, da, db), [ma, mb]))
        if related['owner']:
            child['parts'].append(dependency(reader, 'owner', nominal(reader, start, start + related.end('owner'))))
        child['designation'] = 'related_nominal'
        child.setdefault('link_spans', []).extend([[start + related.start('join'), da], [mb, ha]])
        child['span'] = [start, end]
        return child
    paid = re.fullmatch(r'(?P<payer>.+?)(?P<marker>支付)的(?P<head>.+)', raw)
    if paid:
        ma, mb = start + paid.start('marker'), start + paid.end('marker')
        ha = start + paid.start('head')
        child = nominal(reader, ha, end)
        child['parts'].append(dependency(reader, 'payer', nominal(reader, start, ma), [ma, mb]))
        child.setdefault('link_spans', []).append([mb, ha])
        child['span'] = [start, end]
        return child
    attribution = re.fullmatch(r'(?P<marker>歸屬於|归属于|於|于)(?P<owner>[^的]+)的(?P<head>淨利潤|净利润|權益|权益)', raw)
    if attribution:
        oa, ob = start + attribution.start('owner'), start + attribution.end('owner')
        ha = start + attribution.start('head')
        return {'kind': 'cjk_nominal', 'head': attribution['head'], 'head_span': [ha, end],
                'parts': [dependency(reader, 'attribution_recipient' if attribution['marker'] in {'歸屬於', '归属于'} else 'investee',
                                     nominal(reader, oa, ob), [start, oa])],
                'link_spans': [[ob, ha]], 'span': [start, end]}
    maturity = re.fullmatch(r'(?P<term>[一二三四五六七八九十\d]+年[內内])(?P<marker>到期)的(?P<head>非?流[動动]負債|非?流[動动]负债)', raw)
    if maturity:
        ha = start + maturity.start('head')
        ma, mb = start + maturity.start('marker'), start + maturity.end('marker')
        return {'kind': 'cjk_nominal', 'head': maturity['head'], 'head_span': [ha, end],
                'parts': [dependency(reader, 'maturity_term', nominal(reader, start, ma), [ma, mb])],
                'link_spans': [[mb, ha]], 'span': [start, end]}
    if raw.endswith(('淨變動', '净变动')) and len(raw) > 3:
        head = end - 3
        return {'kind': 'cjk_nominal', 'head': raw[-3:], 'head_span': [head, end],
                'parts': [dependency(reader, 'change_item', nominal(reader, start, head))], 'span': [start, end]}
    if raw.endswith('力度') and len(raw) > 2:
        head = end - 2
        return {'kind': 'cjk_nominal', 'head': '力度', 'head_span': [head, end],
                'parts': [dependency(reader, 'activity', nominal(reader, start, head))], 'span': [start, end]}
    if raw in {'轉型升級', '转型升级'}:
        return {'kind': 'cjk_nominal', 'head': raw, 'head_span': [start, end], 'parts': [], 'span': [start, end]}
    if FINANCIAL_NOMINAL.fullmatch(raw):
        return {'kind': 'cjk_nominal', 'head': raw, 'head_span': [start, end], 'parts': [],
                'lexical_role': 'financial_nominal', 'span': [start, end]}
    if re.fullmatch(r'(?:無效|无效|有效|可靠|安全|不安全|公開|公开|可用)的', raw):
        return {'kind': 'cjk_nominal', 'head': raw[:-1], 'head_span': [start, end - 1], 'parts': [],
                'link_spans': [[end - 1, end]], 'span': [start, end]}
    quantifier = re.match(r'部分|全部', raw)
    if quantifier:
        head = start + quantifier.end()
        child = nominal(reader, head, end)
        child.update(quantifier=quantifier[0], quantifier_span=[start, head], span=[start, end])
        return child
    actor = _ACTOR.match(raw)
    if actor and actor.end() < len(raw) and not _ACTION.match(raw[actor.end():]):
        child = nominal(reader, start + actor.end(), end)
        child['parts'].append(dependency(reader, 'owner', nominal(reader, start, start + actor.end())))
        child['span'] = [start, end]
        return child
    if re.match(r'(?:发行|發行).+募集.+$', raw):
        cut = start + raw.index('募集')
        return {'kind': 'cjk_nominal', 'head': '', 'head_span': [end, end],
                'parts': [dependency(reader, 'nominalized_event', operations(reader, start, cut)),
                          dependency(reader, 'nominalized_event', operations(reader, cut, end))], 'span': [start, end]}
    if raw.endswith('投入') and raw.startswith('对'):
        head = end - 2
        orient = re.search(r'面向(?P<target>[^的]+)的', raw[1:-2])
        parts = []
        if orient:
            oa = start + 1 + orient.start()
            ob = start + 1 + orient.end()
            parts.append(dependency(reader, 'target_domain', nominal(reader, start + 1, oa), [start, start + 1]))
            activity = nominal(reader, ob, head)
            activity['parts'].append(dependency(reader, 'orientation',
                nominal(reader, oa + 2, ob - 1), [oa, oa + 2]))
            activity['link_spans'] = [[ob - 1, ob]]
            activity['span'] = [oa, head]
            parts.append(dependency(reader, 'activity', activity))
        else:
            target_end = head - 1 if reader.text[head - 1:head] == '的' else head
            parts.append(dependency(reader, 'target_domain', nominal(reader, start + 1, target_end), [start, start + 1]))
        return {'kind': 'cjk_nominal', 'head': '投入', 'head_span': [head, end], 'parts': parts,
                'link_spans': [[head - 1, head]] if not orient and target_end < head else [], 'span': [start, end]}
    if re.fullmatch(r'(?:(?:轉型|转型)?(?:升級|升级)|創新|创新)投入', raw):
        head = end - 2
        activity = {'kind': 'cjk_nominal', 'head': reader.text[start:head], 'head_span': [start, head],
                    'parts': [], 'span': [start, head]}
        return {'kind': 'cjk_nominal', 'head': '投入', 'head_span': [head, end],
                'parts': [dependency(reader, 'activity', activity)], 'span': [start, end]}
    # A nominal flow owns the printed activity, not an opaque action string.
    flow = re.search(r'淨現金流出|净现金流出|淨流出|净流出|流入$', raw)
    if flow and flow.end() == len(raw) and _ACTION.match(raw[:flow.start()].rstrip('的')):
        head = start + flow.start()
        limit = head - 1 if reader.text[head - 1:head] == '的' else head
        activity = operations(reader, start, limit)
        return {'kind': 'cjk_nominal', 'head': reader.text[head:end], 'head_span': [head, end],
                'parts': [dependency(reader, 'nominalized_event', activity)],
                'link_spans': [[limit, head]] if limit < head else [], 'span': [start, end]}
    if flow and flow.end() == len(raw) and flow.start() > 0:
        head = start + flow.start()
        return {'kind': 'cjk_nominal', 'head': reader.text[head:end], 'head_span': [head, end],
                'parts': [dependency(reader, 'flow_item', nominal(reader, start, head))], 'span': [start, end]}
    possession = re.fullmatch(r'(?P<owner>.+)的(?P<head>[^的]+)', raw)
    if possession:
        modifiers = {'標準', '标准', '合理', '充分', '清晰', '完整'}
        if (possession['owner'] not in modifiers and not re.fullmatch(
                r'[\u3400-\u9fffA-Za-z0-9]{0,30}(?:公司|集團|集团|裝置|装置|部門|部门|機構|机构|董事會|董事会|委員會|委员会|股東|股东|董事|人員|人员|業務|业务|規則|规则|政策|制度|風險|风险|報告|报告)', possession['owner'])):
            raise _Unknown('cjk_circumstance_nominal_possessor_unresolved')
        boundary = start + possession.end('owner')
        child = nominal(reader, boundary + 1, end)
        child['parts'].append(dependency(reader, 'modifier' if possession['owner'] in modifiers else 'owner',
                                         nominal(reader, start, boundary)))
        child.setdefault('link_spans', []).append([boundary, boundary + 1])
        child['span'] = [start, end]
        return child
    # Printed actor + repurchase is a restrictive event inside the shares
    # being cancelled; it is not a second unconditional purchase assertion.
    actor = _ACTOR.match(raw)
    if actor and _ACTION.match(raw[actor.end():]):
        child = operations(reader, start, end)
        return {'kind': 'cjk_nominal', 'head': '', 'head_span': [end, end],
                'parts': [dependency(reader, 'nominalized_event', child)], 'span': [start, end]}
    if _ACTION.match(raw):
        return {'kind': 'cjk_nominal', 'head': '', 'head_span': [end, end],
                'parts': [dependency(reader, 'nominalized_event', operations(reader, start, end))], 'span': [start, end]}
    suffix = re.search(r'等(?:领域)?$', raw)
    if suffix:
        middle = start + suffix.start()
        head_start = middle + 1
        return {'kind': 'cjk_nominal', 'head': reader.text[head_start:end], 'head_span': [head_start, end],
                'parts': [dependency(reader, 'non_exhaustive_members', nominal(reader, start, middle), [middle, middle + 1])],
                'span': [start, end]}
    # A nominal event owns its actual participant and change/state predicate.
    if ((matches := list(_EVENT.finditer(raw))) and matches[-1].end() == len(raw)
            and (len(matches) == 1 or not re.search(r'以及|与|與|和|及|、', raw))):
        child = event(reader, start, end)
        return {'kind': 'cjk_nominal', 'head': '', 'head_span': [end, end],
                'parts': [dependency(reader, 'nominalized_event', child)], 'span': [start, end]}
    joins = outside_titles(raw, re.finditer(r'以及|与|與|和|及|、', raw))
    if joins:
        spans, cursor = [], start
        for join in joins:
            spans.append((cursor, start + join.start()))
            cursor = start + join.end()
        spans.append((cursor, end))
        children = [nominal(reader, a, b) for a, b in spans]
        return {'kind': 'cjk_nominal', 'head': '', 'head_span': [end, end],
                'parts': [{'kind': 'coordination', 'operator': 'and', 'mode': 'nominal_members',
                           'children': children, 'operator_spans': [[start + j.start(), start + j.end()] for j in joins],
                           'span': [start, end]}], 'span': [start, end]}
    if '的' in raw or _EVENT.search(raw) and not re.fullmatch(r'.{0,12}(?:规模|能力|费用率|性能|流程|组合)', raw):
        raise _Unknown('cjk_circumstance_nominal_operation_unresolved')
    return {'kind': 'cjk_nominal', 'head': raw, 'head_span': [start, end], 'parts': [], 'span': [start, end]}


def event(reader, start, end):
    """A printed intransitive change/state; nominalized events stay operands."""
    start, end = reader.trim(start, end)
    raw = reader.text[start:end]
    verbs = list(_EVENT.finditer(raw))
    if not verbs or verbs[-1].end() != len(raw):
        raise _Unknown('cjk_circumstance_event_unresolved')
    verb = verbs[-1]
    pa, pb = start + verb.start(), start + verb.end()
    sa, sb = start, pa
    qualifiers, spans = {}, {}
    actor = _ACTOR.match(reader.text, sa, sb)
    if actor and actor.end() < sb:
        qualifiers['actor'], spans['actor'] = actor[0], [sa, actor.end()]
        sa = actor.end()
    while True:
        qualifier = next((m for m in _QUALIFIER.finditer(reader.text[sa:sb]) if sa + m.end() == sb), None)
        if qualifier is None:
            break
        key = 'comparison_basis' if qualifier[0] == '同比' else 'manner'
        qualifiers[key] = 'year_on_year' if key == 'comparison_basis' else qualifier[0]
        spans[key] = [sa + qualifier.start(), sa + qualifier.end()]
        sb = sa + qualifier.start()
    if reader.text[sa:sb].endswith('的'):
        spans['nominalization'] = [sb - 1, sb]
        sb -= 1
    phrase = nominal(reader, sa, sb) if sa < sb else None
    return {'kind': 'proposition', 'subject': reader.text[sa:sb], 'subject_span': [sa, sb] if sa < sb else None,
            'subject_phrase': phrase, 'attribute': verb[0], 'predicate': verb[0], 'predicate_span': [pa, pb],
            'object': '', 'object_span': [end, end], 'object_phrase': None, 'prepositional_complements': [],
            'role': 'description', 'lexical_qualifiers': qualifiers, 'lexical_qualifier_spans': spans,
            'span': [start, end]}


def operations(reader, start, end):
    """Only explicit conjunctions with complete event members license a group."""
    start, end = reader.trim(start, end)
    raw = reader.text[start:end]
    if re.search(r'\d', raw):
        measured = measurement_tree(reader, start, end)
        if measured is not None and all(c.get('subject_source') == measured['clauses'][0].get('subject_source')
                                        for c in measured['clauses']):
            return measured
    separators = [m for m in re.finditer(r'[，；;](?:以及)?|(?<!\d),(?!\d)(?:以及)?|以及|、', raw)
                  if m[0][0] in '，,；;' or re.search(r'(?:' + _EVENT.pattern + r'|管理)$', raw[:m.start()])]
    if re.match(r'(?:持续)?(?:加大|坚持)', raw):
        separators = [m for m in separators if m[0][0] in '，,；;']  # Internal NP lists stay inside their action.
    if separators:
        children, cursor = [], start
        actor = _ACTOR.match(raw) if not re.search(r'\d', raw) else None
        if actor:
            cursor += actor.end()
        for join in separators:
            children.append(operations(reader, cursor, start + join.start()))
            cursor = start + join.end()
        children.append(operations(reader, cursor, end))
        return {'kind': 'coordination', 'operator': 'and', 'mode': 'circumstance_operations',
                'children': children, 'operator_spans': [[start + j.start() + token.start(), start + j.start() + token.end()]
                    for j in separators for token in re.finditer(r'[，,、；;]|以及', j[0])],
                **({'shared_actor': actor[0], 'shared_actor_span': [start, start + actor.end()]} if actor else {}),
                'span': [start, end]}
    brought = re.search(r'带来的|帶來的|导致|導致', raw)
    if brought:
        pa, pb = start + brought.start(), start + brought.end()
        return {'kind': 'circumstance_scope', 'operator': 'cause', 'direction': 'operand_to_child',
                'degree': None, 'simultaneous': False, 'operator_span': [pa, pb], 'span': [start, end],
                'operand': operations(reader, start, pa), 'child': measurement_tree(reader, pb, end) or event(reader, pb, end)}
    actor = _ACTOR.match(raw)
    body_start = start + actor.end() if actor else start
    if actor is None and raw.startswith('公司') and _ACTION.match(raw[2:]):
        actor = re.match('公司', raw)
        body_start = start + 2
    body = reader.text[body_start:end]
    reclassify = re.fullmatch(r'(?P<subject>.+?)(?P<verb>重分類為|重分类为)(?P<object>.+)', body)
    if reclassify:
        sa, sb = body_start + reclassify.start('subject'), body_start + reclassify.end('subject')
        pa, pb = body_start + reclassify.start('verb'), body_start + reclassify.end('verb')
        return {'kind': 'proposition', 'subject': reader.text[sa:sb], 'subject_span': [sa, sb],
                'subject_phrase': nominal(reader, sa, sb), 'attribute': reclassify['verb'], 'predicate': reclassify['verb'],
                'predicate_span': [pa, pb], 'object': reader.text[pb:end], 'object_span': [pb, end],
                'object_phrase': nominal(reader, pb, end), 'prepositional_complements': [], 'role': 'description',
                'lexical_qualifiers': {}, 'lexical_qualifier_spans': {}, 'span': [start, end]}
    # A changed flow is a state proposition with an internally interpreted
    # activity nominal, rather than a purchase action swallowing the change.
    if ((re.search(r'(?:增长|增長|增加|减少|減少|下降)$', body) and re.search(r'流出|流入', body))
            or body.endswith(('流入', '流出'))):
        return event(reader, start, end)
    action = _ACTION.match(body)
    if action:
        pa, pb = body_start + action.start('verb'), body_start + action.end('verb')
        obj = nominal(reader, pb, end)
        return {'kind': 'proposition', 'subject': actor[0] if actor else '',
                'subject_span': [start, body_start] if actor else None,
                'subject_phrase': nominal(reader, start, body_start) if actor else None,
                'attribute': action['verb'], 'predicate': action['verb'], 'predicate_span': [pa, pb],
                'object': reader.text[pb:end], 'object_span': [pb, end], 'object_phrase': obj,
                'prepositional_complements': [], 'role': 'description', 'span': [start, end],
                'lexical_qualifiers': {'manner': action['manner']} if action['manner'] else {},
                'lexical_qualifier_spans': {'manner': [body_start, pa]} if action['manner'] else {}}
    # A separator inside a participant list is not an event conjunction.
    joins = [m for m in re.finditer(r'以及|、|，', raw)
             if any(raw[:m.start()].endswith(v) for v in ('优化', '提升', '增长', '稳健', '转型', '下降'))]
    if not joins:
        return event(reader, start, end)
    children, cursor = [], start
    for join in joins:
        children.append(event(reader, cursor, start + join.start()))
        cursor = start + join.end()
    children.append(event(reader, cursor, end))
    return {'kind': 'coordination', 'operator': 'and', 'mode': 'circumstance_operations',
            'children': children, 'operator_spans': [[start + j.start(), start + j.end()] for j in joins],
            'span': [start, end]}


def parse_circumstance(reader, start, end):
    start, end = reader.trim(start, end)
    leading = re.match(r'(?P<simultaneous>同时)?(?P<marker>借助|通过|随着|由于|因为|为了|受益于)', reader.text[start:end])
    if leading is None:
        return None
    boundary = re.search(r'[，,]', reader.text[start + leading.end():end])
    if boundary is None:
        raise _Unknown('cjk_circumstance_main_boundary_unresolved')
    cut = start + leading.end() + boundary.start()
    child = measurement_tree(reader, cut + 1, end) or operations(reader, cut + 1, end)
    return {'kind': 'circumstance_scope', 'operator': CIRCUMSTANCE_MARKERS[leading['marker']],
            'direction': 'operand_to_child', 'degree': None, 'simultaneous': bool(leading['simultaneous']),
            **({'simultaneous_span': [start, start + 2]} if leading['simultaneous'] else {}),
            'operator_span': [start + leading.start('marker'), start + leading.end('marker')], 'span': [start, end],
            'operand': operations(reader, start + leading.end(), cut),
            'child': child}


def measurement_tree(reader, start, end):
    from .cjk_measurement_requirements import read_cjk_measurements

    result = read_cjk_measurements(reader.text[start:end], reader.source_at(start, end), scope=reader.scope)
    return result['logic'][0] if result['complete'] else None


def measurement_spans(text, start, end):
    """Syntax-only measurement cuts; the enclosing adjunct remains obligatory."""
    raw = text[start:end]
    explanation = re.match(r'(?:主要|部分)?(?:歸因於|归因于|由于|由於|因为|因為)', raw)
    if explanation:
        # Each local scalar is exposed independently; this does not decide
        # the causal attachment or turn operations into unconditional facts.
        boundaries = [start + explanation.end(), *[start + m.end() for m in re.finditer(r'[，；;]|(?<!\d),(?!\d)', raw)], end]
        return [(a, b - 1 if i < len(boundaries) - 2 else b)
                for i, (a, b) in enumerate(zip(boundaries, boundaries[1:], strict=False))]
    cause = trailing_cause(raw) or re.search(r'[，,](?:主要)?受.+的影响[。.]?$', raw)
    if cause:
        cuts = [(start, start + cause.start())]
        if cause.groupdict().get('body'):
            a, b = start + cause.start('body'), start + cause.end('body')
            cursor = a
            for join in re.finditer(r'[，；;](?:以及)?|(?<!\d),(?!\d)(?:以及)?|带来的|帶來的|导致|導致', text[a:b]):
                cuts.append((cursor, a + join.start()))
                cursor = a + join.end()
            cuts.append((cursor, b))
        return cuts
    if raw.startswith(('通过', '借助')):
        dated = list(re.finditer(r'[，,](?=(?:19|20)\d{2}年)', raw))
        if dated:
            return [(start + dated[-1].end(), end - 1 if text[end - 1] in '。.' else end)]
    return [(start, end)]


def composition_spans(text, start, end):
    """Expose independently asserted clauses; keep each adjunct with its owner."""
    raw = text[start:end]
    if raw.startswith(('通过', '借助')):
        dated = list(re.finditer(r'[，,](?=(?:19|20)\d{2}年)', raw))
        if dated and re.search(r'[，,]', raw[:dated[-1].start()]):
            # Through X, do Y, dated Z: the first comma licenses X -> Y.
            # A later dated assertion does not establish Y -> Z causation.
            cut = start + dated[-1].start()
            return [(start, cut), (cut + 1, end)]
    attached = re.search(r'[，,](?=同时受益于)', raw)
    if attached:
        cut = start + attached.start()
        prefix = text[start:cut]
        comma = re.search(r'[，,]', prefix)
        if comma:
            return [(start, start + comma.start()), (start + comma.end(), cut), (cut + 1, end)]
        return [(start, cut), (cut + 1, end)]
    return [(start, end)]


def parse_composed(reader, start, end):
    composed = parse_circumstance(reader, start, end)
    if composed is not None:
        return composed
    start, end = reader.trim(start, end)
    raw = reader.text[start:end]
    tail = trailing_cause(raw)
    if tail:
        cut = start + tail.start()
        child = measurement_tree(reader, start, cut)
        if child is None:
            raise _Unknown('cjk_causal_result_unresolved')
        operand = operations(reader, start + tail.start('body'), start + tail.end('body'))
        result = {'kind': 'circumstance_scope', 'operator': 'cause', 'direction': 'operand_to_child',
                  'degree': tail['degree'], 'simultaneous': False,
                  'operator_span': [start + tail.start('marker'), start + tail.end('marker')],
                  'operand': operand,
                  'child': child, 'target_source': copy.deepcopy(child['clauses'][-1]['source']), 'span': [start, end]}
        attachment = _ATTACHMENT.get(tail['attachment'])
        targets = causal_targets(child, attachment, reader=reader, operand=operand)
        result['target_source'] = copy.deepcopy(targets[0])
        if attachment:
            result['attachment'] = attachment
            result['attachment_span'] = [start + tail.start('attachment'), start + tail.end('attachment')]
        elif len(targets) > 1:
            result['attachment'] = 'all'
            result['implicit_attachment_sources'] = [copy.deepcopy(child['source']), reader.source_at(*operand['object_span'])]
        if len(targets) > 1:
            result.pop('target_source')
            result['target_sources'] = targets
        for name, role in (('degree', 'degree'), ('non_exhaustive', 'non_exhaustive'), ('combined', 'combined'), ('suffix', 'suffix')):
            if tail[name]:
                result[role + '_span'] = [start + tail.start(name), start + tail.end(name)]
                if role in {'combined', 'non_exhaustive'}:
                    result[role] = True
        return result
    cause = re.search(r'[，,](?P<degree>主要)?(?P<marker>受到|受)(?P<body>.+)的影响$', raw)
    if cause:
        cut = start + cause.start()
        child = measurement_tree(reader, start, cut)
        if child is None:
            raise _Unknown('cjk_causal_result_unresolved')
        pa, pb = start + cause.start('marker'), start + cause.end('marker')
        operand = operations(reader, start + cause.start('body'), end - 3)
        targets = causal_targets(child, reader=reader, operand=operand)
        result = {'kind': 'circumstance_scope', 'operator': 'cause', 'direction': 'operand_to_child',
                'degree': '主要' if cause['degree'] else None, 'simultaneous': False,
                **({'degree_span': [start + cause.start('degree'), start + cause.end('degree')]} if cause['degree'] else {}),
                'operator_span': [pa, pb], 'suffix_span': [end - 3, end], 'span': [start, end],
                'operand': operand, 'child': child, 'target_source': targets[0]}
        if len(targets) > 1:
            result.pop('target_source')
            result.update(target_sources=targets, attachment='all',
                          implicit_attachment_sources=[copy.deepcopy(child['source']), reader.source_at(*operand['object_span'])])
        return result
    if re.match(r'(?:持续)?(?:加大|坚持|优化|偿还)', raw):
        return operations(reader, start, end)
    if re.search(r'\d', raw):
        measured = measurement_tree(reader, start, end)
        if measured is not None:
            return measured
    # A bare 变动/发展/建设 may be a column or activity label. Its nominal
    # use is licensed inside an explicit adjunct, not as an asserted main
    # clause merely because a suffix resembles an event.
    if not re.search(r'[，,]', raw) and re.search(r'(?:增长|上升|下降|减少|恢复|提升)$', raw):
        return event(reader, start, end)
    return None


def validate_cjk_nominal(node, literal):
    """Check every nominal constituent and its complete literal coverage.

    This is a constituent audit, independent of the parser. A whole phrase
    source cannot pay for deleted constituents or borrowed neighboring text.
    """
    if node.get('kind') != 'cjk_nominal':
        raise ValueError('Chinese nominal type missing')
    origin = node.get('source', {})
    raw = literal(origin, 'Chinese nominal')
    bounds = origin.get('text_span', [])
    if not isinstance(raw, str) or len(bounds) != 2 or len(raw) != bounds[1] - bounds[0]:
        raise ValueError('Chinese nominal source missing')
    covered = set()

    def cut(source, value=None):
        span = source.get('text_span', []) if isinstance(source, dict) else []
        if (len(span) != 2 or any(source.get(k) != origin.get(k) for k in ('path', 'lines', 'cell', 'block', 'native_path'))
                or not bounds[0] <= span[0] <= span[1] <= bounds[1]):
            raise ValueError('Chinese nominal constituent is not local')
        printed = literal(source, 'Chinese nominal constituent')
        if value is not None and printed != value:
            raise ValueError('Chinese nominal constituent differs from source')
        covered.update(range(*span))
        return printed

    cut(node.get('head_source'), node.get('head'))
    roles = {'financial_nominal': FINANCIAL_NOMINAL, 'nominal_term': NOMINAL_TERM}
    if node.get('lexical_role') and (node['lexical_role'] not in roles or not roles[node['lexical_role']].fullmatch(node['head'])):
        raise ValueError('Chinese noun role differs from its complete printed term')
    if 'quantifier' in node:
        if node['quantifier'] not in {'部分', '全部'}:
            raise ValueError('Chinese nominal quantifier unsupported')
        cut(node.get('quantifier_source'), node['quantifier'])
    for part in node.get('parts', []):
        if part.get('kind') == 'cjk_dependency':
            role, marker = part.get('role'), part.get('marker')
            permitted = {'target_domain': {'对'}, 'orientation': {'面向'},
                         'non_exhaustive_members': {'等'}, 'activity': {None}, 'nominalized_event': {None}, 'owner': {None},
                         'flow_item': {None}, 'change_item': {None}, 'maturity_term': {'到期'},
                         'attribution_recipient': {'歸屬於', '归属于'}, 'investee': {'於', '于'},
                         'related_to': {'相關', '相关'}, 'payer': {'支付'}, 'modifier': {None},
                         'period_members': {None}, 'shared_categories': {None},
                         'goal_description': {None},
                         'dividend': {None}, 'divisor': {'/', '÷'}, 'arithmetic_base': {None}, 'arithmetic_group': {None},
                         'subtrahend': {'-', '−', '－', '、'}, 'addend': {'+', '＋', '、'},
                         'governing_action_actor': {'批准', '審批', '审批', '制定', '制訂', '制订'},
                         'measurement_basis': {'计量', '計量'}, 'valuation_change_recognition': {'变动计入', '變動計入'}}
            if marker not in permitted.get(role, set()):
                raise ValueError('Chinese nominal dependency role differs from marker')
            if marker is not None:
                cut(part.get('marker_source'), marker)
            child = part.get('child', {})
            if child.get('kind') == 'cjk_nominal':
                validate_cjk_nominal(child, literal)
            elif role == 'goal_description' and child.get('kind') == 'coordination' and child.get('mode') == 'goals':
                group_source = child.get('source', {})
                group_span = group_source.get('text_span', [])
                group_text = literal(group_source, 'goal coordination')
                used = set()
                for member in child.get('children', []):
                    validate_cjk_event(member, literal)
                for origin in [*(member.get('source', {}) for member in child.get('children', [])), *child.get('operator_sources', [])]:
                    own = origin.get('text_span', [])
                    if (len(group_span) != 2 or len(own) != 2 or not group_span[0] <= own[0] < own[1] <= group_span[1]
                            or any(origin.get(k) != group_source.get(k) for k in ('path', 'lines', 'cell', 'block', 'native_path'))):
                        raise ValueError('Chinese goal member is not local to its group')
                    used.update(range(*own))
                if not isinstance(group_text, str) or any(i not in used and not c.isspace() for i, c in enumerate(group_text, group_span[0])):
                    raise ValueError('Chinese goal group lost a printed member')
            elif role not in {'nominalized_event', 'goal_description'} or child.get('kind') != 'proposition':
                raise ValueError('Chinese nominal dependency child unsupported')
            else:
                validate_cjk_event(child, literal)
            cut(child.get('source'))
            continue
        if part.get('kind') != 'coordination' or part.get('operator') != 'and' or len(part.get('children', [])) < 2:
            raise ValueError('Chinese nominal relation unsupported')
        for source in part.get('operator_sources', []):
            if cut(source) not in {'以及', '与', '與', '和', '及', '、'}:
                raise ValueError('Chinese nominal conjunction differs from source')
        for child in part['children']:
            validate_cjk_nominal(child, literal)
            cut(child['source'])
    for source in node.get('link_sources', []):
        allowed = ({'《', '》'} if node.get('designation') == 'book_title' else
                   {'(', ')', '（', '）'} if node.get('designation') == 'arithmetic_group' else
                   {'的', '以', '且', '其'} if node.get('designation') == 'fair_value_through_profit_or_loss'
                   else {'的', '與', '与'} if node.get('designation') == 'related_nominal' else {'的'})
        if cut(source) not in allowed:
            raise ValueError('Chinese nominal grammatical link differs from source')
    missing = [i for i in range(*bounds) if i not in covered and not raw[i - bounds[0]].isspace()]
    if missing:
        raise ValueError(f'Chinese nominal has unexplained literal constituents: {origin} {missing}')


def validate_cjk_event(node, literal, *, joint_sources=()):
    """Audit interpreted event roles and markers without calling its parser."""
    source = node.get('source', {})
    raw = literal(source, 'Chinese event')
    outer = source.get('text_span', [])
    if not isinstance(raw, str) or len(outer) != 2:
        raise ValueError('Chinese event source missing')
    covered = set()

    def own(origin, value):
        span = origin.get('text_span', []) if isinstance(origin, dict) else []
        if (len(span) != 2 or any(origin.get(k) != source.get(k) for k in ('path', 'lines', 'cell', 'block', 'native_path'))
                or not outer[0] <= span[0] <= span[1] <= outer[1] or literal(origin, 'event constituent') != value):
            raise ValueError('Chinese event constituent not bound to own source')
        covered.update(range(*span))

    from .cjk_narrative_requirements import _MANNER, _VERB

    if node.get('attribute') != node.get('predicate') or not re.fullmatch(
            _EVENT.pattern + '|' + _VERB.pattern + '|' + _ACTION.pattern.split('(?P<verb>')[1].split(')')[0] + '|重分類為|重分类为', node.get('predicate', '')):
        raise ValueError('Chinese event predicate differs from interpreted action')
    own(node.get('predicate_source'), node['predicate'])
    for role in ('subject', 'object'):
        value, phrase = node.get(role), node.get(role + '_phrase')
        if value:
            control = node.get('subject_binding_evidence', {})
            if role == 'subject' and control.get('kind') == 'enumeration_subject':
                origin = node.get('subject_source', {})
                intro, member = control.get('introduction_source', {}), control.get('member_source', {})
                cut, intro_cut, member_cut = origin.get('text_span', []), intro.get('text_span', []), member.get('text_span', [])
                intro_lines, member_lines = intro.get('lines', []), member.get('lines', [])
                prior = bool(intro_lines and member_lines and (intro_lines[1] < member_lines[0]
                    or intro_lines == member_lines and len(intro_cut) == len(member_cut) == 2 and intro_cut[1] <= member_cut[0]))
                if (control.get('controller') != value or control.get('controller_source') != origin
                        or literal(origin, 'enumeration subject') != value or phrase is not None
                        or len(cut) != 2 or len(intro_cut) != 2 or len(member_cut) != 2
                        or origin.get('path') != intro.get('path') or origin.get('lines') != intro_lines
                        or any(origin.get(k) != intro.get(k) for k in ('cell', 'block', 'native_path'))
                        or not intro_cut[0] <= cut[0] < cut[1] <= intro_cut[1]
                        or not member_cut[0] <= outer[0] < outer[1] <= member_cut[1]
                        or intro.get('path') != source.get('path') or member.get('path') != source.get('path')
                        or member.get('lines') != source.get('lines')
                        or not prior):
                    raise ValueError('Chinese event subject lacks its explicit enumeration controller')
                # The owning graph additionally validates the actual printed
                # declaration, list membership and stopping boundary.
                continue
            own(node.get(role + '_source'), value)
            if not phrase or phrase.get('source') != node.get(role + '_source'):
                raise ValueError('Chinese event nominal does not own its whole role')
            if phrase.get('kind') == 'noun_phrase':
                from .nominal_syntax import validate_nominal_sources

                validate_nominal_sources({'logic': [phrase]}, {}, literal)
            else:
                validate_cjk_nominal(phrase, literal)
        elif phrase is not None:
            raise ValueError('Chinese event has an invented empty participant')
    qs = node.get('lexical_qualifiers', {})
    origins = node.get('lexical_qualifier_sources', {})
    for key, origin in origins.items():
        printed = literal(origin, 'Chinese event qualifier')
        if key == 'nominalization':
            if printed != '的':
                raise ValueError('Chinese event nominalization differs from source')
        elif key == 'comparison_basis':
            if printed != '同比' or qs.get(key) != 'year_on_year':
                raise ValueError('Chinese qualitative comparison basis differs from source')
        elif key == 'actor':
            if not _ACTOR.fullmatch(printed) or qs.get(key) != printed:
                raise ValueError('Chinese event actor differs from source')
        elif key == 'aspect' and printed in {'已', '已經', '已经', '了'} and qs.get(key) == 'perfect':
            pass
        elif key == 'completion_link' and printed in {'已', '已經', '已经', '了'}:
            pass
        elif key != 'manner' or not (printed == '保持' or _MANNER.fullmatch(printed)) or qs.get(key) != printed:
            raise ValueError('Chinese qualitative manner differs from source')
        own(origin, printed)
    if set(qs) - set(origins):
        raise ValueError('Chinese event qualifier lacks its printed source')
    # Explicit action coordination can share a later object and an earlier
    # actor. Only independently checked constituent cuts pay for the gaps;
    # another member's enclosing statement span cannot do so.
    for origin in joint_sources:
        if (all(origin.get(k) == source.get(k) for k in ('path', 'lines', 'cell', 'block', 'native_path'))
                and len(span := origin.get('text_span', [])) == 2):
            covered.update(range(max(outer[0], span[0]), min(outer[1], span[1])))
    if any(i not in covered and not char.isspace() and char not in '，,。' for i, char in enumerate(raw, outer[0])):
        raise ValueError('Chinese event has unexplained source content')


def _leaves(node):
    if node.get('kind') == 'proposition':
        return [node]
    if node.get('kind') == 'cjk_measurement_sequence':
        return node['clauses']
    if node.get('kind') == 'coordination':
        return [leaf for child in node['children'] for leaf in _leaves(child)]
    return _leaves(node['child']) if isinstance(node.get('child'), dict) else []


def _role_sources(node):
    return [node.get('subject_source'), node.get('predicate_source', node.get('operator_source')),
            node.get('object_source', node.get('value_source'))]


def validate_circumstance_graph(graph, literal):
    """Bind every adjunct to its actual main fact and its non-counting operands.

    The audit checks source constituents, role identity and complete edges.
    Retained text, a summary flag, or an equal but unrelated neighbor cannot
    discharge these checks. No candidate or reference answer table is used.
    """
    from .narrative_requirements import _Reader
    from .source_obligations import validate_relation_binding

    if 'projections' in graph:
        business_ids = set(graph['projections']['B'])
        business = [n for n in graph['nodes'] if n['id'] in business_ids]
        operands = [n for n in graph['nodes'] if n.get('kind') == 'semantic_operand']
    else:
        business, operands = graph.get('business', []), graph.get('semantic_operands', [])
    facts = [*business, *operands]
    from .financial_group_context import validate_financial_metric_facts

    validate_financial_metric_facts(facts, literal)
    edges = [*graph.get('relations', []), *graph.get('operand_relations', graph.get('semantic_operand_relations', []))]
    expected = {fact['id']: [] for fact in facts}
    expected_sources = {fact['id']: [] for fact in facts}

    def bound_leaf(leaf, operand):
        candidates = [f for f in (operands if operand else business) if _role_sources(f) == _role_sources(leaf)]
        if len(candidates) != 1:
            raise ValueError('Chinese scope main/operand lacks its independent source-bound fact')
        fact = candidates[0]
        if not any(edge.get('type') == 'field_binding' and edge.get('fact_id') == fact['id']
                   and validate_relation_binding(None, fact, edge)['equivalent'] for edge in edges):
            raise ValueError('Chinese scope fact lacks its own field binding')
        return fact

    def walk(node, operand=False, joint_sources=()):
        kind = node.get('kind')
        if kind == 'circumstance_scope':
            source = node.get('source', {})
            raw = literal(source, 'Chinese circumstance')
            marker = literal(node.get('operator_source'), 'Chinese circumstance marker')
            if CIRCUMSTANCE_MARKERS.get(marker) != node.get('operator') or node.get('direction') != 'operand_to_child':
                raise ValueError('Chinese circumstance operator/direction differs from source')
            if marker == '是' and literal(node.get('suffix_source'), 'causative suffix') not in {'导致', '導致'}:
                raise ValueError('Chinese copula alone cannot prove causation')
            outer = source.get('text_span', [])
            covered = set()
            for name in ('operator_source', 'degree_source', 'simultaneous_source', 'suffix_source', 'combined_source', 'non_exhaustive_source', 'attachment_source'):
                origin = node.get(name)
                if not origin:
                    continue
                span = origin.get('text_span', [])
                if (len(span) != 2 or any(origin.get(k) != source.get(k) for k in ('path', 'lines', 'cell', 'block', 'native_path'))
                        or not outer[0] <= span[0] < span[1] <= outer[1]):
                    raise ValueError('Chinese circumstance marker borrowed from another source')
                printed = literal(origin, name)
                if name == 'attachment_source' and _ATTACHMENT.get(printed) != node.get('attachment'):
                    raise ValueError('Chinese causal attachment differs from its printed scope marker')
                if name == 'degree_source' and (printed not in {'主要', '部分'} or node.get('degree') != printed):
                    raise ValueError('Chinese causal degree differs from source')
                if name == 'simultaneous_source' and (printed != '同时' or node.get('simultaneous') is not True):
                    raise ValueError('Chinese circumstance simultaneity differs from source')
                if name == 'suffix_source' and printed not in {'的影响', '所致', '导致', '導致'}:
                    raise ValueError('Chinese causal suffix differs from source')
                if name in {'combined_source', 'non_exhaustive_source'} and (
                        printed not in ({'综合影响', '綜合影響'} if name == 'combined_source' else {'等'})
                        or node.get(name[:-7]) is not True):
                    raise ValueError('Chinese causal combination/restriction differs from source')
                covered.update(range(*span))
            if any(bool(node.get(k)) != bool(node.get(k + '_source')) for k in ('degree', 'simultaneous', 'combined', 'non_exhaustive')):
                raise ValueError('Chinese circumstance restriction lacks its own source')
            for child in (node['operand'], node['child']):
                own = child['source']
                span = own.get('text_span', [])
                if (len(span) != 2 or any(own.get(k) != source.get(k) for k in ('path', 'lines', 'cell', 'block', 'native_path'))
                        or not outer[0] <= span[0] < span[1] <= outer[1]):
                    raise ValueError('Chinese circumstance child is not local')
                covered.update(range(*span))
            if any(i not in covered and not c.isspace() and c not in '，,。' for i, c in enumerate(raw, outer[0])):
                raise ValueError('Chinese circumstance has unexplained source content')
            leaves = _leaves(node['child'])
            trailing = node['operator_source']['text_span'][0] >= node['child']['source']['text_span'][1]
            if node['child'].get('kind') == 'cjk_measurement_sequence' and node['operator'] == 'cause' and trailing:
                # Independent constituent/ordinal audit: never ask the
                # production target selector to certify its own answer.
                clauses = node['child']['clauses']
                scope = node.get('attachment')
                if scope:
                    implicit = node.get('implicit_attachment_sources')
                    printed = literal(node.get('attachment_source'), 'causal attachment') if node.get('attachment_source') else None
                    if (len(clauses) != 4 or not implicit and _ATTACHMENT.get(printed) != scope
                            or implicit and (scope != 'all' or printed is not None)):
                        raise ValueError('Chinese cause lacks two local scope antecedents')
                    for a, b in ((clauses[0], clauses[1]), (clauses[2], clauses[3])):
                        if (a.get('kind') != 'quantity_assertion' or b.get('kind') != 'year_on_year_change'
                                or a.get('subject_source') != b.get('subject_source')):
                            raise ValueError('Chinese cause scope does not own complete amount/change pairs')
                    if implicit:
                        # Independent raw-role audit. This deliberately does
                        # not call causal_targets or its closure predicate.
                        labels = [literal(clauses[i]['subject_source'], 'classified subject') for i in (0, 2)]
                        groups = [re.fullmatch(r'(?P<term>非?流[动動])(?P<family>[资資][产產]|[负負][债債])中的(?P<metric>.+)', label)
                                  for label in labels]
                        if (not all(groups) or groups[0]['metric'] != groups[1]['metric']
                                or groups[0]['family'].translate(str.maketrans('資產負債', '资产负债'))
                                != groups[1]['family'].translate(str.maketrans('資產負債', '资产负债'))
                                or {g['term'].startswith('非') for g in groups} != {False, True}):
                            raise ValueError('Chinese implicit cause lacks a complete complementary classification pair')
                        common = groups[0]['metric']
                        operation = node['operand']
                        if (operation.get('kind') != 'proposition' or operation.get('object') != common
                                or literal(operation.get('object_source'), 'common causal object') != common
                                or implicit != [node['child']['source'], operation['object_source']]):
                            raise ValueError('Chinese implicit cause has no common printed metric reference')
                        body = literal(node['child']['source'], 'closed classified record')
                        if re.search(r'。|[；;]|\n\s*\n', body):
                            raise ValueError('Chinese implicit cause crosses an independent record boundary')
                        prefixes = []
                        for amount in (clauses[0], clauses[2]):
                            own = {**amount['source'], 'text_span': [amount['source']['text_span'][0], amount['subject_source']['text_span'][0]]}
                            prefixes.append(literal(own, 'local actor prefix').strip())
                        if prefixes[1] or prefixes[0] and not re.fullmatch(r'(?:本公司|本集[团團]|[该該]事[业業]部)(?:的)?', prefixes[0]):
                            raise ValueError('Chinese implicit cause borrows across a newly printed actor or record')
                    selected = [clauses[1], clauses[3]] if scope == 'all' else [clauses[1 if scope == 'former' else 3]]
                else:
                    if node.get('attachment_source') or sum(c.get('kind') == 'year_on_year_change' for c in clauses) > 1:
                        raise ValueError('Chinese multi-result cause lacks unambiguous printed scope')
                    selected = clauses[-1:]
                targets = node.get('target_sources', [node.get('target_source')])
                if targets != [c['source'] for c in selected] or (node.get('target_sources') and node.get('target_source')):
                    raise ValueError('Chinese cause targets differ from the independently audited scope')
                leaves = selected
            elif node.get('target_source') or node.get('target_sources'):
                raise ValueError('Chinese causal attachment target is not its printed measurement result')
            for leaf in leaves:
                fact = bound_leaf(leaf, operand)
                descriptor = circumstance_descriptor(_Reader, node)
                expected[fact['id']].append(descriptor)
                expected_sources[fact['id']].append(circumstance_sources(node))
                owned = [e for e in edges if e.get('type') == 'narrative_circumstance_scope' and e.get('fact_id') == fact['id']
                         and e.get('source') == node['operator_source']]
                left = {k: descriptor[k] for k in ('operator', 'direction', 'degree', 'simultaneous', 'combined', 'non_exhaustive') if k in descriptor}
                left['operand'] = _Reader.endpoint(node['operand'])
                if (len(owned) != 1 or owned[0].get('left') != left
                        or owned[0].get('binding_evidence', {}).get('operand_logic') != node['operand']
                        or not validate_relation_binding(None, fact, owned[0])['equivalent']):
                    raise ValueError('Chinese circumstance lacks its independently bound scope relation')
            for leaf in _leaves(node['operand']):
                bound_leaf(leaf, True)
            walk(node['operand'], True)
            walk(node['child'], operand)
        elif kind == 'coordination':
            joint = list(joint_sources)
            if node.get('mode') in {'actions', 'objects'}:
                joint.extend(node.get('operator_sources', []))
                for leaf in _leaves(node):
                    joint.extend(origin for origin in [leaf.get(k + '_source') for k in ('subject', 'predicate', 'object')]
                                 if isinstance(origin, dict))
                    joint.extend(leaf.get('lexical_qualifier_sources', {}).values())
            if node.get('mode') == 'circumstance_operations':
                origin = node['source']
                covered = set()
                for own in [*(c['source'] for c in node['children']), *node.get('operator_sources', [])]:
                    if any(own.get(k) != origin.get(k) for k in ('path', 'lines', 'cell', 'block', 'native_path')):
                        raise ValueError('Chinese operation group borrows neighboring source')
                    covered.update(range(*own['text_span']))
                if node.get('shared_actor'):
                    own = node.get('shared_actor_source', {})
                    if literal(own, 'shared actor') != node['shared_actor'] or not _ACTOR.fullmatch(node['shared_actor']):
                        raise ValueError('Chinese operation group actor is not printed')
                    if any(own.get(k) != origin.get(k) for k in ('path', 'lines', 'cell', 'block', 'native_path')) or own['text_span'][0] != origin['text_span'][0]:
                        raise ValueError('Chinese operation group actor borrowed from neighbor')
                    covered.update(range(*own['text_span']))
                raw = literal(origin, 'operation group')
                if any(i not in covered and not c.isspace() for i, c in enumerate(raw, origin['text_span'][0])):
                    raise ValueError('Chinese operation group has unexplained content')
            for child in node.get('children', []):
                walk(child, operand, joint)
        elif kind == 'proposition' and 'lexical_qualifiers' in node:
            validate_cjk_event(node, literal, joint_sources=joint_sources)
            fact = bound_leaf(node, operand)
            if any(fact.get('qualifiers', {}).get(k) != v for k, v in node['lexical_qualifiers'].items()):
                raise ValueError('Chinese qualitative fact differs from its AST qualifiers')
            if any(fact.get('qualifier_sources', {}).get(k) != v for k, v in node.get('lexical_qualifier_sources', {}).items()):
                raise ValueError('Chinese qualitative qualifier source differs from its AST owner')

    for tree in graph.get('logic', graph.get('logical_statements', [])):
        walk(tree)
    def propositions(value):
        if isinstance(value, dict):
            if value.get('kind') == 'proposition':
                yield value
            for child in value.values():
                yield from propositions(child)
        elif isinstance(value, list):
            for child in value:
                yield from propositions(child)
    bank = {}
    for node in propositions(graph.get('logic', graph.get('logical_statements', []))):
        bank.setdefault(json.dumps(_role_sources(node), sort_keys=True), []).append(node)
    for fact in facts:
        if fact.get('rule_id') != 'explicit_narrative_proposition' or not (
                re.search(r'[\u3400-\u9fff]', fact.get('attribute', ''))
                or any(fact.get(role + '_phrase', {}).get('kind') == 'cjk_nominal'
                       for role in ('subject', 'object') if isinstance(fact.get(role + '_phrase'), dict))):
            continue
        matches = bank.get(json.dumps(_role_sources(fact), sort_keys=True), [])
        if len(matches) != 1 or any(fact.get(k) != matches[0].get(other) for k, other in (
                ('subject', 'subject'), ('attribute', 'attribute'), ('object', 'object'), ('value', 'object'))):
            raise ValueError('Chinese proposition lost or changed its complete source-bound narrative leaf')
    for fact in facts:
        if fact.get('qualifiers', {}).get('circumstances', []) != expected[fact['id']]:
            raise ValueError('Chinese fact circumstance summary differs from its owning AST scope')
        if fact.get('qualifier_sources', {}).get('circumstances', []) != expected_sources[fact['id']]:
            raise ValueError('Chinese fact circumstance sources differ from their own AST scope')
        for role in ('subject', 'object'):
            phrase = fact.get(role + '_phrase')
            if isinstance(phrase, dict) and phrase.get('kind') == 'cjk_nominal':
                if phrase.get('source') != fact.get(role + '_source'):
                    raise ValueError('Chinese fact nominal lost its original role boundary')
                validate_cjk_nominal(phrase, literal)
                def require_parts(value, owner_fact=fact):
                    if isinstance(value, dict):
                        if value.get('kind') == 'cjk_dependency':
                            own = [e for e in edges if e.get('type') == 'narrative_cjk_nominal_scope'
                                   and e.get('fact_id') == owner_fact['id'] and e.get('binding_evidence', {}).get('nominal_logic') == value]
                            if len(own) != 1 or own[0].get('left') != _Reader.summary(value) or not validate_relation_binding(None, owner_fact, own[0])['equivalent']:
                                raise ValueError('Chinese nominal dependency lacks its own relation')
                        if value.get('kind') == 'cjk_nominal' and value.get('quantifier'):
                            own = [e for e in edges if e.get('type') == 'narrative_cjk_quantifier_scope'
                                   and e.get('fact_id') == owner_fact['id'] and e.get('source') == value.get('quantifier_source')]
                            if len(own) != 1 or own[0].get('left') != {'quantifier': value['quantifier']}:
                                raise ValueError('Chinese nominal quantifier lacks its own scope relation')
                        if value.get('kind') == 'coordination' and value.get('mode') == 'nominal_members':
                            for origin in value.get('operator_sources', []):
                                own = [e for e in edges if e.get('type') == 'narrative_nominal_coordination_scope'
                                       and e.get('fact_id') == owner_fact['id'] and e.get('source') == origin
                                       and e.get('binding_evidence', {}).get('coordination_logic') == value]
                                if len(own) != 1 or not validate_relation_binding(None, owner_fact, own[0])['equivalent']:
                                    raise ValueError('Chinese nominal members lack their own coordination relation')
                        for child in value.values():
                            require_parts(child)
                    elif isinstance(value, list):
                        for child in value:
                            require_parts(child)
                require_parts(phrase)


def circumstance_descriptor(reader, node):
    return {'operator': node['operator'], 'direction': node['direction'], 'degree': node['degree'],
            'simultaneous': node['simultaneous'], 'operand': reader.summary(node['operand']),
            **{k: node[k] for k in ('combined', 'non_exhaustive') if k in node}}


def circumstance_sources(node):
    return {key: copy.deepcopy(node[key]) for key in (
        'operator_source', 'simultaneous_source', 'degree_source', 'suffix_source', 'combined_source', 'non_exhaustive_source', 'attachment_source', 'implicit_attachment_sources')
        if key in node}


def emit_circumstance(reader, node, context):
    reader.features.add('circumstance_scope')
    operand_context = copy.deepcopy(context)
    operand_context['semantic_operand'] = True
    operand_context['assertion_context'] = node['operator'] + '_operand'
    operand_context['contexts'].append(operand_context['assertion_context'])
    reader.emit(node['operand'], operand_context)
    context.setdefault('circumstance_nodes', []).append(node)
    reader.emit(node['child'], context)


def emit_measurements(reader, node, context):
    """Import the existing measurement reader and bind only the stated result."""
    from .cjk_measurement_requirements import read_cjk_measurements

    origin = node['source']
    offset = reader.source.get('text_span', [0])[0]
    a, b = origin['text_span']
    read = read_cjk_measurements(reader.text[a - offset:b - offset], origin, scope=reader.scope)
    if not read['complete'] or read['logic'][0] != node:
        raise _Unknown('cjk_circumstance_measurement_import_unresolved')
    reader.features.update(read['required_matcher_features'])
    identities = {}
    operand = bool((context or {}).get('semantic_operand'))
    destination = reader.operands if operand else reader.facts
    for original in read['facts']:
        fact = copy.deepcopy(original)
        identities[fact['id']] = fact['id'] = f'cjk_measurement{"_operand" if operand else ""}:{len(destination)}'
        if operand:
            fact['semantic_role'] = 'operand'
        for wrapper in (context or {}).get('circumstance_nodes', []):
            if wrapper.get('target_sources') and fact['source'] not in wrapper['target_sources']:
                continue
            if wrapper.get('target_source') and fact['source'] != wrapper['target_source']:
                continue
            fact['qualifiers'].setdefault('circumstances', []).append(circumstance_descriptor(reader, wrapper))
            fact['qualifier_sources'].setdefault('circumstances', []).append(circumstance_sources(wrapper))
            descriptor = circumstance_descriptor(reader, wrapper)
            descriptor['operand'] = reader.endpoint(wrapper['operand'])
            reader.edge('narrative_circumstance_scope', descriptor,
                fact, wrapper['operator_source'], operator_source=wrapper['operator_source'], operand_logic=wrapper['operand'])
        destination.append(fact)
    for original in read['relations']:
        edge = copy.deepcopy(original)
        if edge.get('fact_id') in identities:
            edge['fact_id'] = identities[edge['fact_id']]
        (reader.operand_relations if operand else reader.relations).append(edge)
