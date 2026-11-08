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
    if len(bindings) != 1 or not parents or len(syntax) < 2:
        return result
    binding = bindings[0]
    metric_owner = (binding.get('kind') == 'metric_owner' and binding.get('rule_id') == 'printed_metric_parent_and_entity_record')
    if not financial_statement_kind(heading) and not metric_owner:
        return result
    parent = binding.get("parent", {})
    facts = series.get("facts", [])
    if (not metric_owner and (binding.get("kind") != "attribution" or binding.get("rule_id") != "printed_attribution_parent_and_recipient")
            or not facts or {item.get("id") for item in facts} != {item.get("fact_id") for item in binding.get("facts", [])}
            or not _same_object(parent.get("source", {}), parents[-1].get("source", {}))
            or not _same_object(binding.get("child", {}).get("source", {}), syntax[-1].get("source", {}))
            or any(not _same_object(fact.get("source", {}), syntax[-1].get("source", {})) for fact in facts)
            or any(fact.get("role_basis", {}).get(binding['kind'], {}).get("parent") != parent for fact in facts)):
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
        from .series_requirements import read_series_context

        context = read_series_context(issue.get('text', ''), issue['source'], scope=issue['scope'])
        result.update(matched=True, unit=unit, series_context=context if context['matched'] and not context['blockers'] else None,
                      parent_binding=copy.deepcopy(binding),
                      boundary=copy.deepcopy(boundary), pending_source=copy.deepcopy(issue["source"]),
                      outer_group_context=outer,
                      rule_id="statement_unit_resumed_by_source_bound_parent_recipient_proof")
        return result
    return result


def read_financial_summary_intro(text, source, *, scope=()):
    """Read an asserted total followed by a printed classification cue."""
    from .cjk_measurement_requirements import read_cjk_measurements

    cue = re.search(r'其中[:：]\s*$', text)
    if cue is None:
        return None
    offset = source.get('text_span', [0])[0]
    prefix_source = {**copy.deepcopy(source), 'text_span': [offset, offset + cue.start()]}
    reading = read_cjk_measurements(text[:cue.start()], prefix_source, scope=scope)
    if (not reading['complete'] or not reading['facts']
            or reading['facts'][0]['subject'] not in {'總資產', '总资产', '總負債', '总负债'}):
        return None
    return {'text': text, 'source': copy.deepcopy(source), 'prefix_source': prefix_source,
            'prefix': text[:cue.start()], 'marker_source': {**copy.deepcopy(source), 'text_span': [offset + cue.start(), offset + cue.start() + 2]},
            'cue_source': {**copy.deepcopy(source), 'text_span': [offset + cue.start(), offset + len(text)]},
            'reading': reading, 'scope': list(scope)}


def bind_financial_summaries(data):
    """Bind only the two immediate complementary classification records.

    The printed total and 其中 own this finite scope. A heading, image,
    different record type or missing counterpart cannot be skipped.
    """
    syntax = data.get('syntax', [])
    for position, item in enumerate(syntax):
        intro = read_financial_summary_intro(item['text'], item['source'], scope=item.get('scope', []))
        if intro is None:
            continue
        root = intro['reading']['facts'][0]
        family = root['subject'][1:]
        members = syntax[position + 1:position + 3]
        groups = []
        for member in members:
            if member.get('kind') != 'text' or member.get('scope') != item.get('scope'):
                break
            facts = [f for f in data['business'] if f['source'].get('path') == member['source'].get('path')
                     and f['source'].get('lines') == member['source'].get('lines')]
            labels = {f['subject'] for f in facts}
            label = next((x for x in ('流動' + family, '非流動' + family, '流动' + family, '非流动' + family) if x in labels), None)
            if not label or labels != {label}:
                break
            groups.append((member, label, facts))
        normalized = {label.translate(str.maketrans('動資產負債', '动资产负债')) for _, label, _ in groups}
        if len(groups) != 2 or normalized != {'流动' + family.translate(str.maketrans('資產負債', '资产负债')),
                                            '非流动' + family.translate(str.maketrans('資產負債', '资产负债'))}:
            issue = {'reason': 'financial_summary_members_unresolved', 'source': copy.deepcopy(item['source']),
                     'text': item['text'], 'layers': ['B', 'L'], 'category': 'software_unsupported'}
            data['blockers'].append(issue)
            data.setdefault('pending_requirements', []).append(copy.deepcopy(issue))
            continue
        context = {k: copy.deepcopy(intro[k]) for k in ('text', 'source', 'prefix_source', 'marker_source', 'cue_source', 'scope')}
        context['parent'] = {'text': root['subject'], 'source': copy.deepcopy(root['subject_source'])}
        context['members'] = []
        for member, label, facts in groups:
            context['members'].append({'text': label, 'source': copy.deepcopy(member['source'])})
            for fact in facts:
                additions = {'parent_metric': root['subject'], 'membership_operator': '其中'}
                origins = {'parent_metric': root['subject_source'], 'membership_operator': intro['marker_source']}
                for key in ('actor', 'period'):
                    if key not in fact['qualifiers'] and key in root['qualifiers']:
                        additions[key], origins[key] = root['qualifiers'][key], root['qualifier_sources'][key]
                fact['financial_summary_evidence'] = {'introduction_source': copy.deepcopy(item['source']),
                    'member_source': copy.deepcopy(member['source']), 'inherited': sorted(additions)}
                for key, value in additions.items():
                    fact['qualifiers'][key] = value
                    fact['qualifier_sources'][key] = copy.deepcopy(origins[key])
                    data['relations'].append({'id': f"L:{len(data['relations'])}", 'type': 'qualifier_scope',
                        'left': {'type': key, 'text': value},
                        'right': {k: copy.deepcopy(fact[k]) for k in ('subject', 'attribute', 'scope')},
                        'source': copy.deepcopy(origins[key]), 'fact_id': fact['id'], 'object_anchor': None,
                        'binding_evidence': {'statement_source': copy.deepcopy(fact['source']),
                            'qualifier_source': copy.deepcopy(origins[key]), 'data_source': copy.deepcopy(fact['value_source']),
                            'financial_summary': copy.deepcopy(fact['financial_summary_evidence'])}})
        data.setdefault('financial_summary_contexts', []).append(context)
        data['required_matcher_features'] = sorted(set(data.get('required_matcher_features', [])) | {'financial_summary_scope'})


def validate_financial_summaries(data, literal, *, allow_unresolved=False):
    """Check source roles and complete member/qualifier edges independently."""
    contexts = data.get('financial_summary_contexts', [])
    syntax = data.get('syntax', [])
    discovered = [i for i in syntax if read_financial_summary_intro(i['text'], i['source'], scope=i.get('scope', []))]
    if allow_unresolved:
        pending_sources = [i['source'] for i in data.get('blockers', []) if i.get('reason') == 'financial_summary_members_unresolved']
        discovered = [i for i in discovered if i['source'] not in pending_sources]
    if len(discovered) != len(contexts):
        raise ValueError('financial summary lost its original declaration or members')
    facts = data.get('business', [])
    for declaration, context in zip(discovered, contexts, strict=True):
        readback = read_financial_summary_intro(declaration['text'], declaration['source'], scope=declaration.get('scope', []))
        root = readback['reading']['facts'][0]
        if context['source'] != declaration['source'] or literal(context['source']) != context['text']:
            raise ValueError('financial summary borrows a declaration source')
        if (any(context.get(key) != readback[key] for key in ('prefix_source', 'marker_source', 'cue_source', 'scope'))
                or context['parent'] != {'text': root['subject'], 'source': root['subject_source']}):
            raise ValueError('financial summary source cuts differ from its own total and cue')
        if (literal(context['marker_source']) != '其中' or literal(context['cue_source']).strip() not in {'其中:', '其中：'}
                or literal(context['parent']['source']) != context['parent']['text']):
            raise ValueError('financial summary marker or parent differs from source')
        following = syntax[syntax.index(declaration) + 1:syntax.index(declaration) + 3]
        if len(following) != 2 or [i['source'] for i in following] != [m['source'] for m in context['members']]:
            raise ValueError('financial summary crosses an intervening source')
        labels = [m['text'].translate(str.maketrans('動資產負債', '动资产负债')) for m in context['members']]
        family = context['parent']['text'].translate(str.maketrans('總資產負債', '总资产负债'))[1:]
        if set(labels) != {'流动' + family, '非流动' + family}:
            raise ValueError('financial summary lacks its complementary category pair')
        for member in context['members']:
            own = [f for f in facts if f['source'].get('path') == member['source'].get('path')
                   and f['source'].get('lines') == member['source'].get('lines')]
            if not own or any(f['subject'] != member['text'] for f in own):
                raise ValueError('financial summary has an unbound or foreign member')
            for fact in own:
                evidence = fact.get('financial_summary_evidence', {})
                if (evidence.get('introduction_source') != context['source'] or evidence.get('member_source') != member['source']
                        or fact['qualifiers'].get('parent_metric') != context['parent']['text']
                        or fact['qualifiers'].get('membership_operator') != '其中'):
                    raise ValueError('financial summary fact lost its actual parent scope')
                inherited = {'parent_metric', 'membership_operator'} | {
                    k for k in ('actor', 'period') if k in root['qualifiers']
                    and fact['qualifier_sources'].get(k) == root['qualifier_sources'][k]}
                if set(evidence.get('inherited', [])) != inherited:
                    raise ValueError('financial summary changes an independently owned native qualifier')
                for key in evidence['inherited']:
                    source = fact['qualifier_sources'][key]
                    expected_source = (context['parent']['source'] if key == 'parent_metric' else context['marker_source']
                                       if key == 'membership_operator' else root['qualifier_sources'][key])
                    if source != expected_source or literal(source) != fact['qualifiers'][key]:
                        raise ValueError('financial summary qualifier differs from source')
                    edges = [e for e in data['relations'] if e.get('fact_id') == fact['id'] and e['type'] == 'qualifier_scope'
                             and e.get('left') == {'type': key, 'text': fact['qualifiers'][key]} and e['source'] == source
                             and e.get('right') == {k: fact[k] for k in ('subject', 'attribute', 'scope')}
                             and e.get('binding_evidence', {}).get('statement_source') == fact['source']
                             and e.get('binding_evidence', {}).get('financial_summary') == evidence]
                    if len(edges) != 1:
                        raise ValueError('financial summary qualifier has no unique bound relation')
    return {'declarations': len(contexts), 'members': sum(len(c['members']) for c in contexts), 'business_votes_added': 0}


def financial_note_relations(data):
    """Bind a printed note label to the immediately preceding physical list.

    The note marker and actual list interval select the owner. Formula values
    and metric agreement never select a row or repair a contradictory note.
    """
    syntax, facts = data.get('syntax', []), data.get('business', [])
    original = [s for s in syntax if s.get('kind') != 'field_body']

    def record(a, b):
        return all(a.get(k) == b.get(k) for k in ('path', 'lines', 'cell', 'block', 'native_path'))

    relations = []
    for body in syntax:
        label = body.get('printed_label')
        if body.get('kind') != 'field_body' or label not in {'註', '注'} or '=' not in body['text']:
            continue
        formulas = [f for f in facts if f.get('role') == 'formula_definition'
                    and record(f.get('source', {}), body['source']) and f.get('printed_label') == label]
        if not formulas and any(record(issue.get('source', {}), body['source']) for issue in data.get('blockers', [])):
            continue  # A declared interpretation gap remains a gap.
        if len(formulas) != 1:
            raise ValueError('printed formula note lost its independently read business assertion')
        formula = formulas[0]
        at = next((i for i, s in enumerate(original) if record(s['source'], body['source'])), None)
        if at is None or at == 0:
            continue
        previous = original[at - 1]
        scope = list(body.get('scope', []))
        evidence = previous.get('syntax_evidence', {})
        interval, stream = evidence.get('list_span'), evidence.get('list_stream')
        if previous.get('scope') != scope or not interval or not stream:
            continue
        rows = [s for s in original[:at] if s.get('scope') == scope
                and s.get('syntax_evidence', {}).get('list_span') == interval
                and s.get('syntax_evidence', {}).get('list_stream') == stream]
        for fact in facts:
            if not any(record(fact.get('source', {}), row['source']) for row in rows):
                continue
            for header in fact.get('header_evidence', []):
                note = re.fullmatch(r'(?P<metric>.+?)[（(](?P<label>註|注)[）)]', header.get('text', ''))
                if note is None or note['label'] != label:
                    continue
                relations.append({'type': 'financial_note_scope',
                    'left': {'note_label': label, 'defined_metric': formula['subject']},
                    'right': {key: copy.deepcopy(fact[key]) for key in ('subject', 'attribute', 'scope')},
                    'source': copy.deepcopy(header['source']), 'fact_id': fact['id'], 'object_anchor': None,
                    'binding_evidence': {'statement_source': copy.deepcopy(fact.get('statement_source', fact['source'])),
                        'header_source': copy.deepcopy(header['source']), 'header_text': header['text'],
                        'note_label_source': copy.deepcopy(body['label_source']),
                        'formula_subject_source': copy.deepcopy(formula['subject_source']),
                        'note_statement_source': copy.deepcopy(formula.get('statement_source', formula['source'])),
                        'list_span': copy.deepcopy(interval), 'list_stream': stream},
                    'rule_id': 'printed_note_marker_and_immediately_preceding_list'})
    return relations


def bind_financial_notes(data):
    edges = financial_note_relations(data)
    if any(re.search(r'[（(][註注][）)]', item.get('text', '')) for item in data.get('syntax', [])):
        data['required_matcher_features'] = sorted(set(data.get('required_matcher_features', [])) | {'financial_note_scope'})
    for edge in edges:
        data['relations'].append({'id': f"L:{len(data['relations'])}", **edge})


def validate_financial_notes(data, literal):
    expected = financial_note_relations(data)
    actual = [{k: v for k, v in edge.items() if k != 'id'} for edge in data.get('relations', [])
              if edge.get('type') == 'financial_note_scope']
    if actual != expected:
        raise ValueError('financial note lost or changed its original header ownership')
    for edge in expected:
        proof = edge['binding_evidence']
        if (literal(proof['header_source']) != proof['header_text']
                or literal(proof['note_label_source']) != edge['left']['note_label']
                or literal(proof['formula_subject_source']) != edge['left']['defined_metric']):
            raise ValueError('financial note borrows a neighboring header or definition')
    return {'note_bindings': len(expected), 'business_votes_added': 0}
