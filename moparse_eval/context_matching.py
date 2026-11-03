"""Query printed context anchors over faithful candidate text, without values.

Expected headings are search keys and boundary requirements here, never input
to the native reader. Evidence is an actual complete line or adjacent title
parts with source paths. Finer titles do not erase a printed parent scope.
"""

from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache
from typing import Any

from .information import business_scope_text
from .information_reading import _PRINTED_REPORT_TITLE, report_title_transition, unit_scope_literal

_NUMBERED_CAPTION = re.compile(
    r"^(?:Table|附表|图表|圖表|表)\s*\d+(?:[.\-]\d+)*(?:\s|[:：.]|$)", re.I
)
_DOCUMENT_IDENTIFIER = re.compile(
    r"(?:编号|編號|文件编号|文件編號|报告编号|報告編號|文号|文號|"
    r"(?:Document|Report|Reference)\s+(?:ID|number|No\.?)|ID)\s*[:：]\s*[^\n。!?！？]{1,120}",
    re.I,
)


@lru_cache(maxsize=16384)
def heading_context_keys(text: str) -> frozenset[str]:
    """Keep complete printed language components, never shorter name aliases."""
    keys = {business_scope_text(text), business_scope_text(text.rstrip(' ,，'))}
    if re.search(r"[A-Za-z]", text):
        keys.update(business_scope_text(match[0]) for match in re.finditer(
            r"[\u3400-\u9fff]+(?:\s+[\u3400-\u9fff]+)*", text))
    return frozenset(keys)


def consecutive_title_pairs(titles):
    unique = {}
    for title in titles:
        unique.setdefault(tuple(title['position']), title)
    ordered = sorted(unique.values(), key=lambda title: title['position'])
    return [(left, right) for left, right in zip(ordered, ordered[1:], strict=False)
            if left['position'][0] == right['position'][0]
            and left['position'][1] + 1 == right['position'][1]
            and all(item.get('declared_title', True) for item in (left, right))
            and all(item.get('kind') != 'doc_title' for item in (left, right))]


def repeated_ancestor_evidence(text, owners, actual_titles, start, kind, where, pairs=None):
    """A repeated, already open ancestor does not start a different child."""
    if kind == "doc_title":
        return None
    keys = heading_context_keys(text) if kind in {'heading','title','paragraph_title','section_header'} else {business_scope_text(text)}
    pairs = consecutive_title_pairs(actual_titles) if pairs is None else pairs
    for owner in owners:
        for ancestor in owner["context"][:-1]:
            if business_scope_text(ancestor) not in keys:
                for pair in pairs:
                    if not any(tuple(item['position']) == tuple(where) and item['text'] == text for item in pair):
                        continue
                    if not any(business_scope_text(ancestor) in heading_context_keys(item['text']) for item in pair):
                        continue
                    prior_pairs = [prior for prior in pairs if tuple(prior[-1]['position']) < tuple(start)
                        and [business_scope_text(item['text']) for item in prior]
                        == [business_scope_text(item['text']) for item in pair]]
                    if prior_pairs:
                        return {'printed_title':text,'owner':owner['text'],'ancestor':ancestor,
                                'current_title_bundle':list(pair),'preceding_bundle':list(prior_pairs[-1]),
                                'method':'repeated_identical_consecutive_title_bundle'}
                continue
            prior = [anchor for anchor in actual_titles if tuple(anchor["position"]) < tuple(start)
                     and business_scope_text(ancestor) in (heading_context_keys(anchor["text"])
                         if anchor.get('declared_title',True) else {business_scope_text(anchor['text'])})]
            if prior:
                return {"printed_title": text, "owner": owner["text"],
                        "ancestor": ancestor, "preceding_anchor": prior[-1],
                        "method": "complete_repeated_open_ancestor"}
    return None


def literal_context_members(targets: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Read clauses explicitly assigned to an authored parent, without values.

    A native renderer can mark a finer caption at its parent's display level.
    Explicit reference membership keeps that display choice from cutting off
    the parent. It never supplies a missing candidate title or text.
    """
    members: dict[str, set[str]] = {}
    for target in targets:
        for label in target.get('parents',[]):
            members.setdefault(business_scope_text(label),set()).update(business_scope_text(name) for name in target['context'])
        if target["kind"] not in {"text", "unit_caption", "item"} or target.get('record'):
            continue
        for clause in [target['text'], *re.split(r"[，,。；;\n\u3000]", target["text"])]:
            key = business_scope_text(clause.strip())
            if key:
                members.setdefault(key, set()).update(
                    business_scope_text(label) for label in target["context"]
                )
    return members


def flat_display_levels(headings, anchors):
    """Read a demonstrated display convention from complete printed titles.

    A known parent and child printed at the same level show that this level
    cannot also prove sibling ownership. Known sibling titles, document
    boundaries and explicit captions still delimit ranges. No values enter
    this evidence, and the actual title strings and positions are retained.
    """
    evidence = {}
    for child in headings:
        for parent in headings:
            if parent["text"] not in child["context"][:-1] or (
                parent.get("heading_level") or 1
            ) >= (child.get("heading_level") or 1):
                continue
            for start in anchors.get(parent["id"], []):
                for end in anchors.get(child["id"], []):
                    level = start.get("level")
                    if (
                        isinstance(level, int)
                        and level == end.get("level")
                        and start["position"] < end["position"]
                    ):
                        evidence.setdefault(
                            (level, parent["id"]),
                            {
                                "level": level,
                                "parent": parent["text"],
                                "child": child["text"],
                                "parent_evidence": start,
                                "child_evidence": end,
                            },
                        )
    return {
        "levels": sorted({level for level, _parent in evidence}),
        "evidence": list(evidence.values()),
    }


def flat_level_in_scope(display, labels, level, position):
    """Keep a demonstrated display convention inside its printed parent."""
    wanted = {business_scope_text(label) for label in labels}
    return any(
        proof["level"] == level
        and business_scope_text(proof["parent"]) in wanted
        and tuple(proof["parent_evidence"]["position"]) <= tuple(position)
        for proof in display["evidence"]
    )


class PrintedScopeIndex:
    def __init__(
        self,
        candidates: list[dict[str, Any]],
        headings: list[dict[str, Any]],
        context_members: dict[str, set[str]] | None = None,
        direct_scopes: list[str] | None = None,
    ) -> None:
        self.headings: dict[str, dict[str, Any]] = {}
        for heading in headings:
            key = business_scope_text(heading["text"])
            previous = self.headings.get(key)
            # Reprinting a root title inside a later section does not turn
            # that root into its own descendant. Keep its shallowest declared
            # ownership; every physical title anchor is still indexed below.
            if previous is None or len(heading["context"]) < len(previous["context"]):
                self.headings[key] = heading
        self.context_members = context_members or {}
        self.direct_scopes = {business_scope_text(scope) for scope in direct_scopes or []}
        self.candidates = {item["id"]: item for item in candidates}
        printed = sorted(
            [
                item
                if item["kind"] == "text"
                else {**item, "kind": "text", "order": (*item["order"][:-1], -1)}
                for item in candidates
                if item["kind"] == "text" or item.get("cell", {}).get("public_record_literal")
            ],
            key=lambda item: item["order"],
        )
        self.source_orders = {item.get("native_path"): item["order"] for item in printed}
        self.source_orders.update({item["id"]: item["order"] for item in printed})
        self.lines = []
        for index, item in enumerate(printed):
            complete = item["text"].strip()
            if "\n" in complete and len(complete) <= 512:
                start = len(item["text"]) - len(item["text"].lstrip())
                self.lines.append(self._line(item, complete, start, start + len(complete)))
            offset = 0
            for raw in item["text"].splitlines(keepends=True):
                line = raw.strip()
                if line:
                    a = offset + len(raw) - len(raw.lstrip())
                    self.lines.append(self._line(item, line, a, a + len(line)))
                    # A declared multilingual title can print a complete CJK
                    # title between separate Latin strings. Keep the
                    # entire CJK run: a shorter same-script name is not a hit.
                    if self.lines[-1]["declared_title"]:
                        for part in re.finditer(r"[\u3400-\u9fff]+(?:\s+[\u3400-\u9fff]+)*", line):
                            heading = self.headings.get(business_scope_text(part[0]), {})
                            if heading and part[0] != line and re.search(r"[A-Za-z]", line):
                                self.lines.append(
                                    self._line(item, part[0], a + part.start(), a + part.end())
                                )
                offset += len(raw)
            parts = []
            metadata = []
            for following in printed[index : index + 3]:
                if (
                    following["kind"] != "text"
                    or following.get("page") != item.get("page")
                    or len(following["text"]) > 512
                ):
                    break
                if (len(parts) == 1 and not metadata
                        and self._line(item, item["text"], 0, len(item["text"]))["declared_title"]
                        and not self._line(following, following["text"], 0, len(following["text"]))["declared_title"]
                        and _DOCUMENT_IDENTIFIER.fullmatch(following["text"].strip())):
                    metadata.append({"native_id": following["id"],
                                     "native_path": following.get("native_path"),
                                     "text": following["text"]})
                    continue
                parts.append(following)
                if len(parts) > 1:
                    joined = self._line(
                        item, "\n".join(part["text"] for part in parts), 0, len(item["text"])
                    )
                    joined["end"] = (*parts[-1]["order"], len(parts[-1]["text"]))
                    joined["sources"] = [part["id"] for part in parts]
                    if metadata:
                        if joined["key"] not in self.headings:
                            continue
                        joined["intervening_metadata"] = list(metadata)
                    self.lines.append(joined)
        self.by_key: dict[str, list[dict[str, Any]]] = {}
        for line in self.lines:
            self.by_key.setdefault(line["key"], []).append(line)
        self.report_titles = list(
            dict.fromkeys(
                line["text"]
                for line in self.lines
                if not line.get("sources")
                and line["kind"] not in {"footer", "page_footer", "page_number", "number"}
                and _PRINTED_REPORT_TITLE.fullmatch(line["text"])
            )
        )
        title_counts = Counter(business_scope_text(text) for _identity, text in {
            ((line['native_id'], *line['span']), line['text']) for line in self.lines
            if not line.get('sources') and _PRINTED_REPORT_TITLE.fullmatch(line['text'])})
        self.repeated_report_titles = {key for key, count in title_counts.items() if count >= 2} if len(title_counts) == 1 else set()
        self.heading_anchors = {
                heading["id"]: [
                    {
                        "level": line["level"],
                        "position": line["start"],
                        "native_ids": line.get("sources", [line["native_id"]]),
                    }
                    for line in self.by_key.get(business_scope_text(heading["text"]), [])
                    if line["declared_title"]
                ]
                for heading in headings
            }
        self.display_levels = flat_display_levels(headings, self.heading_anchors)
        self.actual_titles = [{"text": line["text"], "position": line["start"],
                               "native_ids": line.get('sources',[line['native_id']]), "kind":line['kind'],
                               'declared_title':line['declared_title']} for line in self.lines]
        self.title_pairs = consecutive_title_pairs(self.actual_titles)
        self.report_markers = [item for item in self.actual_titles if _PRINTED_REPORT_TITLE.fullmatch(item['text'])]
        self.cache: dict[tuple[Any, ...], dict[str, Any]] = {}

    @staticmethod
    def _line(item, text, start, end):
        block = item.get("block", {})
        markup = (
            re.match(r"^\s*(#{1,6})\s+", str(block.get("text", "")))
            if block.get("text_format") == "markdown"
            else None
        )
        return {
            "text": text,
            "key": business_scope_text(text),
            "native_id": item["id"],
            "native_path": item.get("native_path"),
            "span": [start, end],
            "start": (*item["order"], start),
            "end": (*item["order"], end),
            "kind": block.get("kind"),
            "level": block.get(
                "heading_level", block.get("level", len(markup[1]) if markup else None)
            ),
            "declared_title": bool(
                markup
                or block.get("kind")
                in {"heading", "title", "doc_title", "paragraph_title", "section_header"}
            ),
        }

    def frontmatter(self, anchor: dict[str, Any], where: tuple, level: int | None) -> bool:
        """Read only initial, explicitly delimited metadata before a root title."""
        if level != 1 or where[0] != anchor["start"][0] or where >= anchor["start"]:
            return False
        prior = [
            line
            for line in self.lines
            if not line.get("sources") and line["start"] < anchor["start"]
        ]
        return bool(prior) and all(
            not line["declared_title"]
            and len(line["text"]) <= 240
            and re.search(r"[:：]", line["text"])
            and not re.search(r"[。!?！？]", line["text"])
            for line in prior
        )

    def search(self, scope: str, item: dict[str, Any], *, direct: bool = False) -> dict[str, Any]:
        order = tuple(item["order"])
        span = item.get("cell", {}).get("information_source_span")
        source = item.get("cell", {}).get("information_source_block") or item.get("native_path")
        if span and source in self.source_orders:
            order = tuple(self.source_orders[source])
        elif "cell" in item:
            order = (*order[:-1], -1)
        where = (*order, span[0] if span else 0)
        key = business_scope_text(scope)
        cached = self.cache.get((key, where, direct))
        if cached is not None:
            return cached
        required = self.headings.get(key, {})
        expected_level = required.get("heading_level")
        considered = []
        conflicts = []
        selected = None
        for anchor in self.by_key.get(key, []):
            boundary = []
            repeated = []
            caption = (
                anchor["kind"] in {"table_caption", "caption", "figure_title"}
                or bool(re.match(r"^(?:19|20)\d{2}\s*年", anchor["text"]))
                or bool(_NUMBERED_CAPTION.match(anchor["text"]))
            )
            for line in self.lines:
                if line["key"] == key:
                    continue
                target = self.headings.get(line["key"])
                if line["start"] <= anchor["end"]:
                    # A root-looking first title part must not reopen the
                    # root when the complete adjacent title names its child.
                    if (direct and target and line["key"] in self.direct_scopes
                            and key in {business_scope_text(label) for label in target["context"][:-1]}
                            and line["start"] <= anchor["start"]
                            and line["end"] > anchor["end"]):
                        boundary.append({**line, "relation": "separate_direct_business_scope"})
                    continue
                if line.get("sources") and not target:
                    continue
                repeat = repeated_ancestor_evidence(line["text"], [required] if required else [],
                    self.actual_titles, anchor["start"], line["kind"],line['start'],self.title_pairs)
                if repeat:
                    repeated.append({**repeat, "position": line["start"], "native_id": line["native_id"]})
                    continue
                if line['kind'] != 'doc_title' and line['key'] in self.repeated_report_titles:
                    repeated.append({'text': line['text'], 'position': line['start'],
                        'native_id': line['native_id'], 'method': 'same_complete_repeated_report_title'})
                    continue
                sibling = (
                    target
                    and expected_level is not None
                    and target.get("heading_level", 999) <= expected_level
                )
                child = (
                    target
                    and expected_level is not None
                    and target.get("heading_level", 0) > expected_level
                ) or key in self.context_members.get(line["key"], set())
                # A declared child can retain the parent's ancestry while
                # owning different facts. Do not let a direct parent fact
                # borrow that child's same-named value. This uses scope
                # labels and printed positions, never either expected value.
                if direct and child and line["key"] in self.direct_scopes:
                    boundary.append({**line, "relation": "separate_direct_business_scope"})
                    continue
                if (_PRINTED_REPORT_TITLE.fullmatch(line['text']) and not child and not sibling
                        and not report_title_transition(line['text'], line['kind'], line['start'], self.report_markers)):
                    repeated.append({'text':line['text'], 'position':line['start'], 'native_id':line['native_id'],
                        'method':'initial_or_unchanged_printed_report_period'})
                    continue
                declared_sibling = (
                    not target
                    and not child
                    and isinstance(anchor["level"], int)
                    and isinstance(line["level"], int)
                    and not flat_level_in_scope(
                        self.display_levels,
                        required.get("context", [scope]),
                        line["level"],
                        anchor["start"],
                    )
                    and line["level"] <= anchor["level"]
                )
                caption_line = (
                    line["kind"] in {"table_caption", "caption", "figure_title"}
                    or len(line["text"]) <= 160
                    and not re.search(r"[。；;!?！？\n]", line["text"])
                    and (
                        re.match(r"^(?:19|20)\d{2}\s*年", line["text"])
                        or _NUMBERED_CAPTION.match(line["text"])
                    )
                )
                next_caption = (
                    caption
                    and not child
                    and caption_line
                    and not unit_scope_literal(line["text"])
                    and not re.fullmatch(
                        r"[（(]?\s*(?:货币单位|貨幣單位|单位|單位|Units?)\s*[:：].+",
                        line["text"],
                        re.I,
                    )
                )
                document_boundary = (line["kind"] == "doc_title" or line['kind'] in {'text','paragraph','heading','title','section_header'}
                                     and _PRINTED_REPORT_TITLE.fullmatch(line['text'])) and not child
                if sibling or declared_sibling or next_caption or document_boundary:
                    boundary.append(line)
            stop = min(boundary, key=lambda line: line["start"]) if boundary else None
            preamble = self.frontmatter(anchor, where, expected_level)
            within = (anchor["end"] <= where or preamble) and (
                stop is None or where < stop["start"]
            )
            evidence = {
                "anchor": {k: v for k, v in anchor.items() if k != "key"},
                "boundary": {k: v for k, v in stop.items() if k != "key"} if stop else None,
                "repeated_ancestors": repeated,
                "decision": "within_scope" if within else "outside_scope",
                "method": "initial_delimited_metadata_before_root_title"
                if preamble
                else "printed_anchor_order",
            }
            considered.append(evidence)
            if (direct and anchor["end"] <= where and stop is not None
                    and stop.get("relation") == "separate_direct_business_scope"
                    and where >= stop["start"]):
                conflicts.append(evidence["boundary"])
            if within and (selected is None or anchor["start"] > selected["anchor"]["start"]):
                selected = evidence
        result = {
            "query": scope,
            "anchors": considered,
            "selected": selected,
            "display_level_evidence": self.display_levels,
            "direct_scope_conflicts": conflicts,
        }
        self.cache[key, where, direct] = result
        return result

    def contextualize(
        self, item: dict[str, Any], scope: str | None, parents: list[str] | None = None
    ) -> dict[str, Any]:
        proof = (
            self.search(scope, item, direct=True) if scope else {"query": None, "anchors": [], "selected": None}
        )
        cell = {**item["cell"], "information_scope_search": proof}
        if not proof["selected"] and proof.get("direct_scope_conflicts"):
            cell["information_business_scope_exclusion"] = proof["direct_scope_conflicts"]
        periods = []
        for report_title in self.report_titles:
            search = self.search(report_title, item)
            if search["selected"]:
                actual = search["selected"]["anchor"]
                periods.append(
                    {
                        "id": actual["native_id"],
                        "native_path": actual["native_path"],
                        "text": actual["text"],
                        "kind": "period",
                        "scope_search": search,
                        "readback_evidence": "bounded_printed_report_period",
                    }
                )
        if periods:
            cell["information_context"] = [*cell.get("information_context", []), *periods]
        if parents:
            searches = [self.search(parent, item) for parent in parents]
            proof = {**proof, "parents": searches}
            cell["information_scope_search"] = proof
            actual = []
            for parent, search in zip(parents, searches, strict=True):
                if search["selected"]:
                    parent_anchor = search["selected"]["anchor"]
                    actual.append(parent_anchor["text"])
                    cell["information_context"] = [
                        *cell.get("information_context", []),
                        {
                            "id": parent_anchor["native_id"],
                            "native_path": parent_anchor["native_path"],
                            "text": parent_anchor["text"],
                            "kind": "business_heading",
                            "readback_evidence": "matched_complete_printed_scope",
                            "span": parent_anchor["span"],
                        },
                    ]
                    continue
                paths = [cell.get("row_header_path", []), *cell.get("printed_subject_paths", [])]
                paths.extend(
                    re.split(r"\s+/\s+", context["text"])
                    for context in cell.get("information_context", [])
                    if context.get("kind") in {"table_caption", "explicit_table_introduction"}
                )
                literal = next(
                    (
                        label
                        for path in paths
                        for label in path
                        if business_scope_text(label) == business_scope_text(parent)
                    ),
                    None,
                )
                if literal is not None:
                    actual.append(literal)
                    search["printed_path_witness"] = {
                        "text": literal,
                        "native_path": item.get("native_path"),
                    }
            if len(actual) == len(parents):
                cell.setdefault("parent_scopes", actual)
        if proof["selected"]:
            anchor = proof["selected"]["anchor"]
            cell["information_context"] = [
                *cell.get("information_context", []),
                {
                    "id": anchor["native_id"],
                    "native_path": anchor["native_path"],
                    "text": anchor["text"],
                    "kind": "table_caption"
                    if anchor["kind"] in {"table_caption", "caption", "figure_title"}
                    else "business_heading",
                    "readback_evidence": "matched_complete_printed_scope",
                    "span": anchor["span"],
                },
            ]
        return {**item, "cell": cell}
