"""Read explicit candidate navigation entries without reference answers.

Contents headings, printed Title/Page schemas and native document-index roles
provide navigation evidence. A number at an arbitrary line boundary does not.
Page values are asserted content; stable entry and page-slot identities depend
only on their own source objects and actual parent declarations.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .adapters import html_cells, markdown_cells
from .native_relations import heading_evidence
from .representations import visible_text

_PAGE = r"(?:[A-Za-z]+[-–])?\d+(?:[-–]\d+)?|[ivxlcdmIVXLCDM]+"
_PAGE_VALUE = re.compile(rf"(?:{_PAGE})$")
_PAGE_LABEL = re.compile(r"Pages?|页码|頁碼|页|頁", re.I)
_TITLE_LABEL = re.compile(r"Title|Entry|Section|Chapter|Contents?|条目|條目|标题|標題|章节|章節|目[录錄]項?", re.I)
_PARENT_LABEL = re.compile(r"Parent(?:\s+chapter)?|Group|Chapter|父章节|父章節|上[级級]章[节節]|父目[录錄]", re.I)
_TOC_TITLE = re.compile(r"(?:.*?\bTable of Contents|Contents|.*?[目][录錄])(?:\s*[（(](?:continued|续|續)[）)])?$", re.I | re.S)
_HEADING = re.compile(r"^\s{0,3}(#{1,6})[ \t]+(.+?)\s*#*\s*$")
_BULLET = re.compile(r"^(\s*)([-+*]|\d+[.)])[ \t]+(.*)$")
_FURNITURE = {"footer", "header", "page_footer", "page_header", "page_number", "number"}
_MEDIA = {"image", "picture", "chart", "image_body", "chart_body"}


def _native_anchor(evidence: dict[str, Any]) -> str | int | None:
    value = evidence.get("native_id", evidence.get("native_attributes", {}).get("id"))
    return value if isinstance(value, (str, int)) and not isinstance(value, bool) else None


def _origin(source: dict[str, Any], start: int = 0, end: int | None = None, **extra: Any) -> dict[str, Any]:
    result = {**copy.deepcopy(source), **extra}
    if end is not None:
        base = source.get("text_span", [0])[0]
        result["text_span"] = [base + start, base + end]
    return result


def _directory(item: dict[str, Any]) -> bool:
    text = item.get("text", "").strip()
    kind = item.get("kind", item.get("role", ""))
    return bool(item.get("source") and (kind in {"document_index", "toc", "toc_schema"}
                or kind in {"heading", "title", "section_header", "paragraph_title", "table_caption"}
                and _TOC_TITLE.fullmatch(text)))


class _Reader:
    def __init__(self, source: dict[str, Any], context: tuple | list):
        self.source = copy.deepcopy(source)
        self.context = [copy.deepcopy(item) for item in context if _directory(item)]
        self.active = bool(self.context)
        self.root_level = None
        self.groups: list[dict[str, Any]] = []
        self.alias_requests: list[dict[str, Any]] = []
        self.input_block_ids = {source["block"]} if source.get("block") is not None else set()
        self.directory_evidence = copy.deepcopy(self.context[-1:])
        self.directory_instances = copy.deepcopy(self.context)
        self.parent_resolution = {"unknown": False, "root_evidence": []}
        self.page_declaration = next((copy.deepcopy(item) for item in context if self.active and item.get("source")
            and item.get("kind", item.get("role")) in {"table_caption", "column_header"}
            and _PAGE_LABEL.fullmatch(item.get("text", "").strip())), None)
        self.result: dict[str, Any] = {"matched": False, "recognized": False, "complete": False,
            "entries": [], "facts": [], "relations": [], "text_atoms": [], "controls": [],
            "issues": [], "blockers": [], "unresolved": [], "consumed_spans": [],
            "source_cells": [], "source_fragments": [], "handled_block_ids": [],
            "text_projection_complete": True, "reader": "candidate_toc_evidence"}

    def handled(self, source: dict[str, Any]) -> None:
        ident = source.get("block")
        if ident in self.input_block_ids and ident not in self.result["handled_block_ids"]:
            self.result["handled_block_ids"].append(ident)

    def directory(self, text: str, source: dict[str, Any]) -> None:
        entry = {"text": text, "source": copy.deepcopy(source), "role": "actual_directory_heading"}
        same = [item for item in self.directory_instances if item["text"] == text and all(
            item["source"].get(key) == source.get(key) for key in ("path", "block", "lines", "block_lines"))
            and (item["source"].get("text_span") is None or source.get("text_span") is None
                 or item["source"]["text_span"] == source["text_span"])]
        if not same:
            self.directory_instances.append(entry)
        elif same[0]["source"].get("text_span") is None and source.get("text_span") is not None:
            self.directory_instances[self.directory_instances.index(same[0])] = entry
        if len(self.directory_instances) > 1 and not any(item["reason"] == "toc_multiple_directory_scope_alignment_unsupported"
                                                        for item in self.result["blockers"]):
            self.issue("toc_multiple_directory_scope_alignment_unsupported", source, category="software_unsupported",
                       actual_directories=copy.deepcopy(self.directory_instances))
        self.directory_evidence = [entry]
        self.handled(source)

    def atom(self, text: str, source: dict[str, Any], role: str) -> dict[str, Any]:
        atom = {"text": text, "source": copy.deepcopy(source), "span": list(source.get("text_span", [0, len(text)])), "role": role}
        if text and atom not in self.result["text_atoms"]:
            for request in self.alias_requests:
                if request["origin"] == source:
                    atom.setdefault("aliases", []).extend(copy.deepcopy(request["aliases"]))
            self.result["text_atoms"].append(atom)
        if role in {"toc_heading", "toc_parent_label"}:
            self.handled(source)
        return atom

    def aliases(self, literal: str, origin: dict[str, Any], entries: list[dict[str, Any]]) -> None:
        existing = {alias["entry_id"] for request in self.alias_requests if request["origin"] == origin for alias in request["aliases"]}
        aliases = [{"text": literal, "origin": copy.deepcopy(origin),
                    "data_source": copy.deepcopy(entry["page_evidence"]["source"]), "entry_id": entry["id"],
                    "role": "finite_printed_header_alias"} for entry in entries if entry["id"] not in existing]
        if not aliases:
            return
        self.alias_requests.append({"origin": copy.deepcopy(origin), "aliases": aliases})
        for atom in self.result["text_atoms"]:
            if atom["source"] == origin:
                atom["role"] = "attribute"
                atom.setdefault("aliases", []).extend(copy.deepcopy(aliases))

    def control(self, text: str, source: dict[str, Any], reason: str) -> None:
        if text:
            self.result["controls"].append({"text": text, "source": copy.deepcopy(source),
                "span": list(source.get("text_span", [0, len(text)])), "reason": reason})

    def unresolved(self, text: str, source: dict[str, Any], reason: str) -> None:
        self.result["unresolved"].append({"text": text, "source": copy.deepcopy(source), "reason": reason})
        self.atom(visible_text(text, "markdown"), source, "unresolved_literal")

    def issue(self, reason: str, source: dict[str, Any], *, category: str = "candidate_ambiguity", **detail: Any) -> None:
        item = {"id": f"toc-issue:{len(self.result['issues'])}", "category": category, "reason": reason,
                "source": copy.deepcopy(source), "affected_data_sources": [copy.deepcopy(source)], "header_ids": [], **detail}
        self.result["issues"].append(item)
        if category == "software_unsupported":
            self.result["blockers"].append(item)

    def entry(self, title: str, page: str, title_evidence: dict[str, Any], page_evidence: dict[str, Any], *,
              parents: list[dict[str, Any]], explicit_root: bool, attribute_source: dict[str, Any] | None = None,
              attribute_text: str | None = None, root_evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        ident = f"{page_evidence['source'].get('block', self.source.get('path', 'toc'))}/toc/entry[{len(self.result['entries'])}]"
        parent_path = [item["title"] for item in parents]
        roots = copy.deepcopy(self.parent_resolution["root_evidence"] or root_evidence or [])
        if explicit_root and not roots:
            roots = [{"kind": "top_level_navigation_list", "source": copy.deepcopy(title_evidence["source"])}]
        proven = not self.parent_resolution["unknown"] and bool(parents or roots)
        entry = {"id": ident, "title": title, "parent_path": parent_path, "page": page,
            "record_id": ident, "source": copy.deepcopy(page_evidence["source"]),
            "title_evidence": copy.deepcopy(title_evidence), "page_evidence": copy.deepcopy(page_evidence),
            "parent_evidence": copy.deepcopy(parents), "parentage": "explicit" if proven else "unknown",
            "root_evidence": roots if proven and not parents else [],
            "directory_evidence": copy.deepcopy(self.directory_evidence)}
        if not proven and not self.parent_resolution["unknown"]:
            self.issue("toc_parentage_unproven", page_evidence["source"], parent_path=copy.deepcopy(parent_path))
        self.handled(page_evidence["source"])
        for parent in parents:
            self.handled(parent["source"])
        self.result["entries"].append(entry)
        fact_source = {**copy.deepcopy(entry["source"]), "attribute_source": copy.deepcopy(attribute_source),
                       "subject_source": copy.deepcopy(title_evidence["source"]), "qualifier_sources": {},
                       "parentage": entry["parentage"], "root_evidence": copy.deepcopy(entry["root_evidence"])}
        fact = {"id": ident + ":page", "subject": title, "attribute": "Page", "value": page,
                "raw_value": page, "qualifiers": {}, "identity_facets": {"toc_parent": parent_path if proven else None},
                "record_id": ident, "role": "metric", "semantic_type": "toc_page", "source": fact_source, "scope": [],
                "directory_evidence": copy.deepcopy(self.directory_evidence),
                "header_evidence": [{"text": attribute_text, "source": copy.deepcopy(attribute_source), "role": "column_header"}] if attribute_source else [],
                "row_evidence": [copy.deepcopy(title_evidence), *copy.deepcopy(parents)], "data_evidence": copy.deepcopy(page_evidence)}
        self.result["facts"].append(fact)
        endpoint = {"type": "toc_entry", "title": title, "parent_path": list(parent_path) if proven else None}
        binding = {"entry_id": ident, "entry_source": copy.deepcopy(title_evidence["source"]),
                   "page_source": copy.deepcopy(page_evidence["source"]),
                   "parent_sources": [copy.deepcopy(parent["source"]) for parent in parents],
                   "attribute_source": copy.deepcopy(attribute_source)}
        anchor = {"entry": {"id": ident, "source": copy.deepcopy(title_evidence["source"])},
                  "page": {"id": ident + ":page-slot", "source": copy.deepcopy(page_evidence["source"])}}
        binding["objects"] = copy.deepcopy(anchor)
        self.result["relations"].append({"type": "toc_entry_page", "left": endpoint,
            "right": {"type": "toc_page_slot", "title": title, "parent_path": list(parent_path) if proven else None},
            "source": copy.deepcopy(page_evidence["source"]), "role_basis": "own_navigation_entry_and_page_slot",
            "binding_evidence": copy.deepcopy(binding), "data_object_id": ident,
            "object_anchor": _native_anchor(page_evidence)})
        if parents:
            parent = parents[-1]
            self.result["relations"].append({"type": "toc_parent", "left": {"type": "toc_entry_parent", "title": parent["title"],
                "parent_path": list(parent_path[:-1]) if proven else None}, "right": copy.deepcopy(endpoint),
                "source": copy.deepcopy(title_evidence["source"]), "role_basis": parent.get("role", "explicit_navigation_parent"),
                "binding_evidence": copy.deepcopy(binding), "data_object_id": ident,
                "object_anchor": _native_anchor(title_evidence)})
        return entry

    @staticmethod
    def _parts(text: str) -> dict[str, Any] | None:
        patterns = [
            (rf"^\s*(?P<title>.+?)\s*[:：]?\s+(?P<label>Pages?|页码|頁碼|页|頁)\s*[:：]?\s*(?P<page>{_PAGE})\s*$", "explicit_page_label"),
            (rf"^\s*(?P<title>[^:：]+?)\s*[:：]\s*(?P<page>{_PAGE})\s*$", "colon_page_slot_under_own_directory_role"),
            (rf"^\s*(?P<title>.+?)(?P<separator>\s*[.．·…]{{2,}}\s*|\t+| {{2,}})(?P<page>{_PAGE})\s*$", "printed_toc_alignment_separator"),
            (rf"^\s*(?P<page>{_PAGE})(?P<separator>\s+|、)(?P<title>\S.*?)\s*$", "page_first_under_own_directory_role"),
        ]
        for pattern, basis in patterns:
            match = re.fullmatch(pattern, text, re.I | re.S)
            if match and match["title"].strip() and not re.search(r"[。!?！？]$", match["title"].strip()):
                title_span = list(match.span("title"))
                while title_span[1] > title_span[0] and text[title_span[1] - 1] in ":： ":
                    title_span[1] -= 1
                return {"title": visible_text(text[title_span[0]:title_span[1]], "markdown"), "page": match["page"],
                        "title_span": title_span, "page_span": list(match.span("page")),
                        "label_span": list(match.span("label")) if "label" in match.groupdict() else None, "basis": basis}
        return None

    def text(self, text: str, source: dict[str, Any], *, kind: str = "text", representation: str = "markdown", level: Any = None,
             native_cells_present: bool = False) -> None:
        if kind == "toc_group" and self.active and self._parts(text) is None:
            literal = visible_text(text, representation).strip()
            if literal:
                self.atom(literal, _origin(source, len(text) - len(text.lstrip()), len(text.rstrip())), "toc_parent_label")
            return
        if "<table" in text.lower():
            if len(re.findall(r"<table\b", text, re.I)) != 1:
                self.issue("multiple_embedded_toc_tables_not_separated", source, category="software_unsupported")
                self.unresolved(text, source, "embedded_table_boundaries_unread")
                return
            parts = re.split(r"(<table\b.*?</table\s*>)", text, maxsplit=1, flags=re.I | re.S)
            if len(parts) != 3:
                if native_cells_present:
                    self.result["unresolved"].append({"text": text, "source": copy.deepcopy(source),
                        "reason": "embedded_table_boundaries_unread"})
                else:
                    self.unresolved(text, source, "embedded_table_boundaries_unread")
                if self.active or kind in {"document_index", "toc"}:
                    self.result["matched"] = True
                    self.handled(source)
                    self.result["text_projection_complete"] = False
                    self.issue("toc_embedded_table_boundary_unavailable", source, category="software_unsupported", layers=["T", "L", "B"])
                return
            before, body, after = parts
            for outside in [before, after]:
                literal = visible_text(outside, "html").strip()
                if literal:
                    self.atom(literal, source, "literal")
                    if _TOC_TITLE.fullmatch(literal):
                        self.active = True
                        self.directory(literal, source)
            from html.parser import HTMLParser

            class OutsideCells(HTMLParser):
                def __init__(self):
                    super().__init__(convert_charrefs=True)
                    self.depth = 0
                    self.fragments = []

                def handle_starttag(self, tag, attrs):
                    if tag in {"td", "th"}:
                        self.depth += 1

                def handle_endtag(self, tag):
                    if tag in {"td", "th"}:
                        self.depth = max(0, self.depth - 1)

                def handle_data(self, data):
                    if not self.depth and data.strip():
                        line, column = self.getpos()
                        start = sum(len(value) for value in body.splitlines(keepends=True)[:line - 1]) + column
                        self.fragments.append((data, start))

            outside_cells = OutsideCells()
            outside_cells.feed(body)
            for literal, start in outside_cells.fragments:
                leading = len(literal) - len(literal.lstrip())
                origin = _origin(source, len(before) + start + leading, len(before) + start + len(literal.rstrip()),
                                 text_span_basis="decoded_html_character_data")
                self.atom(literal.strip(), origin, "toc_heading" if _TOC_TITLE.fullmatch(literal.strip()) else "literal")
                if _TOC_TITLE.fullmatch(literal.strip()):
                    self.active = True
                    if not self.directory_evidence or self.directory_evidence[0]["text"] != literal.strip():
                        self.directory(literal.strip(), origin)
                    else:
                        self.directory_evidence[0].setdefault("repeated_sources", []).append(copy.deepcopy(origin))
                elif self.active and _PAGE_LABEL.fullmatch(literal.strip()):
                    self.page_declaration = {"text": literal.strip(), "source": origin}
            if not native_cells_present:
                self.cells(html_cells(body, str(source.get("path", source.get("block", "toc"))) + "/html"), source)
            return
        if "|" in text and "---" in text:
            from markdown_it import MarkdownIt

            ranges = [token.map for token in MarkdownIt("commonmark").enable("table").parse(text) if token.type == "table_open"]
            if ranges:
                lines = text.splitlines(keepends=True)
                offsets = [0]
                for line in lines:
                    offsets.append(offsets[-1] + len(line))
                cursor = 0
                for begin, end in ranges:
                    if begin > cursor:
                        self.text("".join(lines[cursor:begin]), _origin(source, offsets[cursor], offsets[begin]), representation=representation)
                    table_source = _origin(source, offsets[begin], offsets[end], local_lines=[begin + 1, end])
                    self.cells(markdown_cells("".join(lines[begin:end]), str(source.get("path", source.get("block", "toc"))) + f"/gfm/L{begin + 1}"), table_source)
                    cursor = end
                if cursor < len(lines):
                    self.text("".join(lines[cursor:]), _origin(source, offsets[cursor], len(text)), representation=representation)
                return
        whole_heading = heading_evidence({"kind": kind, "text": text, "text_format": representation, "level": level})
        if whole_heading["role"] == "heading" or whole_heading["markdown_status"] == "single_heading":
            literal = visible_text(text, representation).strip()
            if _TOC_TITLE.fullmatch(literal):
                self.active, self.root_level, self.groups, self.page_declaration = True, whole_heading.get("resolved_level"), [], None
                self.result["matched"] = True
                raw_heading = re.search(r"(?m)^\s{0,3}#{1,6}[ \t]+(.+?)\s*#*\s*$", text) if representation == "markdown" else None
                begin, end = raw_heading.span(1) if raw_heading else (len(text) - len(text.lstrip()), len(text.rstrip()))
                self.atom(literal, _origin(source, begin, end), "toc_heading")
                self.directory(literal, _origin(source, begin, end))
                if raw_heading:
                    self.control(text[:begin], _origin(source, 0, begin), "markdown_heading_syntax")
                    self.control(text[end:], _origin(source, end, len(text)), "markdown_heading_syntax")
                return
            if self.active and type(level) is int and type(self.root_level) is int and level > self.root_level:
                self.groups = [item for item in self.groups if item.get("level", 0) < level]
                self.groups.append({"title": literal, "source": copy.deepcopy(source), "role": "declared_heading_group", "level": level})
                self.atom(literal, source, "toc_parent_label")
                return
            self.active, self.groups, self.page_declaration = False, [], None
            self.unresolved(text, source, "toc_context_unproven")
            return
        lines = text.splitlines(keepends=True)
        offset = 0
        stack = []
        for index, raw in enumerate(lines):
            literal = raw.rstrip("\r\n")
            start = offset
            offset += len(raw)
            if not literal.strip():
                continue
            heading = _HEADING.fullmatch(literal)
            if heading:
                self.text(literal, _origin(source, start, start + len(literal), local_lines=[index + 1, index + 1]),
                          kind="heading", representation="markdown", level=len(heading[1]))
                stack = []
                continue
            bullet = _BULLET.fullmatch(literal)
            content_start = bullet.start(3) if bullet else len(literal) - len(literal.lstrip())
            content = literal[content_start:]
            own = _origin(source, start + content_start, start + len(literal), local_lines=[index + 1, index + 1])
            if not self.active:
                self.unresolved(text if len(lines) > 1 and index == 0 else content, source if len(lines) > 1 and index == 0 else own, "toc_context_unproven")
                if index == 0:
                    return
                continue
            if _PAGE_LABEL.fullmatch(content.strip()):
                self.atom(content.strip(), own, "attribute")
                self.page_declaration = {"text": content.strip(), "source": own}
                self.handled(source)
                continue
            parents = list(self.groups)
            if bullet:
                indent = len(bullet[1].expandtabs(4))
                while stack and stack[-1][0] >= indent:
                    stack.pop()
                parents.extend(item[1] for item in stack)
                self.control(literal[:content_start], _origin(source, start, start + content_start), "markdown_list_syntax")
            parts = self._parts(content)
            if parts is None:
                next_line = next((item.rstrip("\r\n") for item in lines[index + 1:] if item.strip()), "")
                following = _BULLET.fullmatch(next_line)
                if bullet and following and len(following[1].expandtabs(4)) > indent:
                    group = {"title": visible_text(content, representation), "source": own, "role": "explicit_list_parent"}
                    stack.append((indent, group))
                    self.atom(group["title"], own, "toc_parent_label")
                    continue
                self.unresolved(content, own, "nonentry_content_ends_directory_range")
                self.active, self.groups, self.page_declaration = False, [], None
                continue
            self.result["matched"] = True
            occupied = []
            evidence = {}
            for field, role in [("title", "toc_title"), ("page", "page_reference")]:
                begin, end = parts[field + "_span"]
                origin = _origin(source, start + content_start + begin, start + content_start + end, local_lines=[index + 1, index + 1])
                evidence[field] = {"text": parts[field], "source": origin, "role": role, "raw_text": content[begin:end]}
                self.atom(parts[field], origin, role)
                occupied.append((begin, end))
            attribute_source = None
            if parts["label_span"]:
                begin, end = parts["label_span"]
                attribute_source = _origin(source, start + content_start + begin, start + content_start + end)
                self.atom(content[begin:end], attribute_source, "attribute")
                occupied.append((begin, end))
            cursor = 0
            for begin, end in sorted(occupied):
                self.control(content[cursor:begin], _origin(source, start + content_start + cursor, start + content_start + begin), "toc_entry_separator")
                cursor = end
            self.control(content[cursor:], _origin(source, start + content_start + cursor, start + len(literal)), "toc_entry_separator")
            entry = self.entry(parts["title"], parts["page"], evidence["title"], evidence["page"], parents=parents,
                               explicit_root=bool(bullet), attribute_source=attribute_source or
                                copy.deepcopy(self.page_declaration["source"]) if attribute_source or self.page_declaration else None,
                               attribute_text=content[slice(*parts["label_span"])] if parts["label_span"] else
                                self.page_declaration["text"] if self.page_declaration else None,
                               root_evidence=[{"kind": "flat_text_entry_schema", "source": copy.deepcopy(self.directory_evidence[0]["source"]),
                                               "entry_source": copy.deepcopy(evidence["title"]["source"]), "syntax": parts["basis"]}]
                                   if not parents and self.directory_evidence and self.active else [])
            if not parts["label_span"] and self.page_declaration:
                self.aliases(self.page_declaration["text"], self.page_declaration["source"], [entry])
            if bullet:
                stack.append((indent, {"title": entry["title"], "source": entry["title_evidence"]["source"], "entry_id": entry["id"], "role": "explicit_list_parent"}))

    def cells(self, cells: list[dict[str, Any]], source: dict[str, Any], *, native_index: bool = False) -> None:
        def literal(cell):
            value = cell.get("text", "")
            return value.strip() if isinstance(value, str) else ""

        if not isinstance(cells, list):
            self.result["unresolved"].append({"text": "", "source": copy.deepcopy(source),
                "reason": "toc_cell_collection_unsupported", "raw_cells": copy.deepcopy(cells)})
            if self.active or native_index:
                self.result["matched"] = True
                self.handled(source)
                self.issue("toc_cell_collection_unsupported", source, category="software_unsupported")
            return
        indexed = [(index, copy.deepcopy(cell)) for index, cell in enumerate(cells)]
        positions = {id(cell): index for index, cell in indexed if isinstance(cell, dict)}

        def located(cell):
            return (all(type(cell.get(key)) is int and cell[key] >= 0 for key in ("row", "col"))
                    and all(type(cell.get(key, 1)) is int and cell.get(key, 1) > 0 for key in ("row_span", "col_span")))

        def evidence(cell, role):
            origin = {**copy.deepcopy(source), "cell": cell.get("id", cell.get("native_path"))}
            origin.update({key: cell[key] for key in ("row", "col") if type(cell.get(key)) is int and cell[key] >= 0})
            if not located(cell) or origin["cell"] is None:
                origin["cell_position"] = positions[id(cell)]
            if "text_span" in origin:
                origin["container_text_span"] = origin.pop("text_span")
            raw = cell.get("text", "") if isinstance(cell.get("text", ""), str) else ""
            origin.update(text_span=[len(raw) - len(raw.lstrip()), len(raw.rstrip())], text_span_basis="native_cell_text")
            return {"text": literal(cell), "source": origin, "role": role, "native_id": cell.get("native_id"),
                    "native_attributes": copy.deepcopy(cell.get("native_attributes")) if isinstance(cell.get("native_attributes"), dict) else {}}

        if not cells:
            return
        valid, unknown = [], []
        counts = {}
        for _index, cell in indexed:
            if isinstance(cell, dict) and located(cell):
                counts[cell["row"], cell["col"]] = counts.get((cell["row"], cell["col"]), 0) + 1
        for index, cell in indexed:
            if not isinstance(cell, dict):
                origin = {**copy.deepcopy(source), "cell_position": index}
                unknown.append(origin)
                self.result["source_cells"].append({"source": origin, "text": "", "raw_cell": copy.deepcopy(cell)})
                self.result["unresolved"].append({"text": "", "source": origin,
                    "reason": "toc_cell_object_unsupported", "raw_cell": copy.deepcopy(cell)})
                continue
            origin = evidence(cell, "literal")["source"]
            snapshot_source = {key: copy.deepcopy(value) for key, value in origin.items() if key not in {"text_span", "cell_text_span"}}
            self.result["source_cells"].append({"source": snapshot_source, "text": cell.get("text", "") if isinstance(cell.get("text", ""), str) else "",
                "row_span": cell.get("row_span", 1), "col_span": cell.get("col_span", 1),
                "native_declarations": copy.deepcopy(cell.get("native_attributes", {}))})
            self.atom(literal(cell), origin, "literal")
            if (not located(cell) or counts.get((cell.get("row"), cell.get("col")), 0) != 1
                    or cell.get("service_grid_scope_state") in {"unknown", "geometry_only_unclassified"}
                    or not isinstance(cell.get("native_attributes", {}), dict)
                    or not isinstance(cell.get("text", ""), str)):
                unknown.append(origin)
                self.result["unresolved"].append({"text": literal(cell), "source": origin,
                    "reason": "toc_cell_position_or_scope_unavailable", "raw_cell": copy.deepcopy(cell)})
                continue
            valid.append(cell)
        cells = valid
        if not cells:
            if unknown and (self.active or native_index):
                self.result["matched"] = True
                self.handled(source)
                self.issue("toc_cell_position_or_scope_unavailable", source, category="software_unsupported",
                           affected_data_sources=unknown)
            return
        rows = sorted({cell["row"] for cell in cells})
        headers = [cell for cell in cells if cell.get("is_column_header") or cell.get("column_header")
                   or cell.get("native_attributes", {}).get("role") == "columnheader"
                   or cell.get("native_attributes", {}).get("scope") in {"col", "colgroup"}]
        first = [cell for cell in cells if cell["row"] == rows[0]]
        if any(_PAGE_LABEL.fullmatch(literal(cell)) for cell in first) and any(_TITLE_LABEL.fullmatch(literal(cell)) for cell in first):
            headers = list({id(cell): cell for cell in [*headers, *first]}.values())
        elif (self.active or native_index) and sum(bool(_PAGE_LABEL.fullmatch(literal(cell))) for cell in first) == 1 and all(
                not literal(cell) or _PAGE_LABEL.fullmatch(literal(cell)) for cell in first):
            headers = list({id(cell): cell for cell in [*headers, *first]}.values())
        page_headers = [cell for cell in headers if _PAGE_LABEL.fullmatch(literal(cell))]
        title_headers = [cell for cell in headers if _TITLE_LABEL.fullmatch(literal(cell)) and not _PARENT_LABEL.fullmatch(literal(cell))]
        if not title_headers:
            title_headers = [cell for cell in headers if _TITLE_LABEL.fullmatch(literal(cell))]
        declared = len(page_headers) == len(title_headers) == 1
        if not declared and not self.active and not native_index:
            self.result["unresolved"].append({"text": "\n".join(literal(cell) for cell in cells),
                "source": copy.deepcopy(source), "reason": "toc_context_unproven",
                "literal_sources": [evidence(cell, "unresolved")["source"] for cell in cells]})
            return
        self.result["matched"] = True
        self.handled(source)
        if unknown:
            self.issue("toc_cell_position_or_scope_unavailable", source, category="software_unsupported",
                       affected_data_sources=unknown)
        page_header = page_headers[0] if len(page_headers) == 1 else None
        if page_header:
            page_col = page_header["col"]
        else:
            columns = {cell["col"] for cell in cells}
            possible = [col for col in columns if any(literal(cell) for cell in cells if cell["col"] == col)
                        and all(not literal(cell) or _PAGE_VALUE.fullmatch(literal(cell)) for cell in cells if cell["col"] == col)]
            if len(possible) != 1:
                self.issue("toc_page_and_title_axes_unproven", source, affected_data_sources=[evidence(cell, "unresolved")["source"] for cell in cells])
                return
            page_col = possible[0]
        if len(title_headers) == 1:
            title_col = title_headers[0]["col"]
        else:
            other = {cell["col"] for cell in cells} - {page_col}
            if len(other) != 1:
                self.issue("toc_title_axis_unproven", source)
                return
            title_col = next(iter(other))
        parent_headers = [cell for cell in headers if cell["col"] not in {title_col, page_col} and _PARENT_LABEL.fullmatch(literal(cell))]
        schema_headers = [cell for cell in [*title_headers, *parent_headers] if literal(cell) not in {"Contents", "目录", "目錄"}]
        for header in schema_headers:
            origin = evidence(header, "schema")["source"]
            self.result["text_atoms"] = [atom for atom in self.result["text_atoms"] if atom["source"] != origin]
            self.control(literal(header), origin, "explicit_toc_title_parent_schema")
        header_rows = {cell["row"] for cell in headers}
        references_by_row = {}
        for cell in cells:
            declaration = cell.get("native_attributes", {}).get("headers", "")
            references = declaration.split() if isinstance(declaration, str) else declaration
            if not references:
                continue
            references_by_row.setdefault(cell["row"], []).append((cell, list(references)))
        referenced_rows = set(references_by_row)
        for row, declared in references_by_row.items():
            affected = [item for item in cells if item["row"] == row or row in header_rows and item["row"] not in header_rows]
            self.issue("toc_explicit_header_reference_interpretation_unsupported", evidence(declared[0][0], "unresolved")["source"],
                       category="software_unsupported", affected_data_sources=[evidence(item, "unresolved")["source"] for item in affected],
                       header_ids=list(dict.fromkeys(reference for _, targets in declared for reference in targets)),
                       raw_references=[{"source": evidence(cell, "unresolved")["source"], "declarations": copy.deepcopy(cell.get("native_attributes", {}))}
                                       for cell, _ in declared])
        if referenced_rows & header_rows:
            referenced_rows.update(rows)
        groups = []
        added = []
        for row in rows:
            if row in header_rows or row in referenced_rows:
                continue
            band = [cell for cell in cells if cell["row"] == row]
            explicit_group = [cell for cell in band if cell.get("row_section") or cell.get("native_attributes", {}).get("scope") == "rowgroup"]
            if explicit_group:
                groups = [{"title": literal(cell), "source": evidence(cell, "row_group")["source"], "role": "explicit_rowgroup"}
                          for cell in explicit_group if literal(cell)]
                continue
            title = [cell for cell in band if cell["col"] == title_col]
            page = [cell for cell in band if cell["col"] == page_col]
            if len(title) != 1 or len(page) != 1 or title[0].get("col_span", 1) != 1 or not literal(title[0]):
                for cell in band:
                    self.result["unresolved"].append({"text": literal(cell), "source": evidence(cell, "unresolved")["source"], "reason": "toc_row_binding_unproven"})
                continue
            parents = [*copy.deepcopy(self.groups), *groups]
            for header in parent_headers:
                values = [cell for cell in band if cell["col"] == header["col"]]
                if len(values) == 1 and literal(values[0]):
                    parents.append({"title": literal(values[0]), "source": evidence(values[0], "parent_value")["source"], "role": "explicit_parent_column"})
            entry = self.entry(literal(title[0]), literal(page[0]), evidence(title[0], "toc_title"), evidence(page[0], "page_reference"),
                               parents=parents, explicit_root=False,
                               attribute_source=evidence(page_header, "column_header")["source"] if page_header else
                                                copy.deepcopy(self.page_declaration["source"]) if self.page_declaration else None,
                               attribute_text=literal(page_header) if page_header else self.page_declaration["text"] if self.page_declaration else None,
                               root_evidence=[{"kind": "flat_title_page_schema", "source": copy.deepcopy(source),
                                   "title_header": evidence(title_headers[0], "title_header") if title_headers else None,
                                   "page_header": evidence(page_header, "page_header") if page_header else copy.deepcopy(self.page_declaration),
                                   "directory_evidence": copy.deepcopy(self.directory_evidence), "native_document_index": native_index}]
                                   if not parents and not parent_headers and (declared or native_index or self.directory_evidence) else [])
            added.append(entry)
        if page_header:
            self.aliases(literal(page_header), evidence(page_header, "column_header")["source"], added)
        elif self.page_declaration:
            self.aliases(self.page_declaration["text"], self.page_declaration["source"], added)

    def blocks(self, blocks: list[dict[str, Any]]) -> None:
        blocks = copy.deepcopy(blocks)
        list_stack = []
        list_span = None
        for block in blocks:
            if block.get("public_syntax_kind") != "item":
                list_stack, list_span = [], None
                continue
            span = block.get("public_list_span")
            if span != list_span:
                list_stack = []
            list_span = span
            declared_parents = block.get("public_list_parents", [])
            depth = len(declared_parents)
            list_stack = list_stack[:depth]
            if block.get("public_has_children"):
                block["kind"] = "toc_group"
            if depth and len(list_stack) == depth and not block.get("parent_id"):
                parent = list_stack[-1]
                printed = str(parent.get("text", ""))
                declared = str(declared_parents[-1])
                parent_parts, declared_parts = self._parts(printed), self._parts(declared)
                # Actual AST position supplies the object; compare labels only,
                # never use a parent entry's asserted page value for identity.
                if (parent_parts["title"] if parent_parts else printed) == (declared_parts["title"] if declared_parts else declared):
                    block["parent_id"] = parent["id"]
                    block["_toc_parent_role"] = "public_markdown_list_parent"
            list_stack.append(block)

        def block_source(block, index):
            return {**copy.deepcopy(self.source), "path": block.get("native_path", block.get("id", self.source.get("path"))),
                    "position": index, "native_sequence": copy.deepcopy(block.get("native_sequence")),
                    **copy.deepcopy(block.get("source", {})), "block": block.get("id")}

        by_id = {block.get("id"): block for block in blocks}
        sources = {block.get("id"): block_source(block, index) for index, block in enumerate(blocks)}
        self.input_block_ids = set(by_id)
        for block in blocks:
            if isinstance(block.get("text"), str):
                self.result["source_fragments"].append({"source": copy.deepcopy(sources[block.get("id")]), "text": block["text"]})
        parents: dict[str, set[str]] = {}
        for block in blocks:
            if block.get("parent_id"):
                parents.setdefault(block["id"], set()).add(block["parent_id"])
            for child in block.get("native_children", []):
                parents.setdefault(child, set()).add(block["id"])
        own_captions = {}
        for block in blocks:
            if block.get("cells") is None:
                continue
            container = block.get("native_table_container", block.get("parent_id"))
            refs = block.get("native_references", {}).get("captions", [])
            matching = [caption for caption in blocks if caption.get("kind") == "table_caption"
                        and _PAGE_LABEL.fullmatch(caption.get("text", "").strip())
                        and (caption.get("id") in refs or container and caption.get("parent_id") == container)]
            if len(matching) == 1:
                caption = matching[0]
                own_captions[block["id"]] = {"text": caption["text"].strip(), "source": sources[caption["id"]]}
        owned_caption_ids = {item["source"]["block"] for item in own_captions.values()}
        parsed_blocks = {}

        def native_parents(ident, seen):
            if ident in seen:
                self.issue("toc_native_parent_cycle", sources[ident])
                self.parent_resolution["unknown"] = True
                return [], True
            paths = []
            for parent_id in parents.get(ident, set()):
                parent = by_id.get(parent_id)
                if parent is None:
                    # Adapter-declared structural containers are not TOC
                    # entry parents. Explicit navigation parent references are.
                    node = by_id.get(ident, {})
                    body_reference = isinstance(parent_id, str) and re.fullmatch(r"#/(?:documents/\d+/document/)?body", parent_id)
                    structural_role = node.get("native_parent_role", node.get("native_parent_kind")) in {
                        "body", "document_body", "document_root", "page_header", "page_footer", "page_furniture"}
                    if node.get("native_parent") == parent_id and (body_reference or structural_role):
                        continue
                    self.parent_resolution["unknown"] = True
                    self.issue("toc_parent_reference_target_unavailable", sources[ident], target=parent_id)
                    continue
                literal = visible_text(parent.get("text", ""), parent.get("text_format", "plain")).strip()
                if _directory({**parent, "text": literal, "source": sources[parent_id]}):
                    self.parent_resolution["root_evidence"].append({"kind": "explicit_directory_parent_reference",
                        "source": copy.deepcopy(sources[parent_id]), "child_source": copy.deepcopy(sources[ident])})
                    paths.append([])
                    continue
                prefix, _ = native_parents(parent_id, seen | {ident})
                evidence = None
                parent_role = by_id.get(ident, {}).get("_toc_parent_role", "explicit_native_parent_reference")
                if parent_id in parsed_blocks and len(parsed_blocks[parent_id]) == 1:
                    entry = parsed_blocks[parent_id][0]
                    evidence = {"title": entry["title"], "source": entry["title_evidence"]["source"],
                                "role": parent_role, "native_parent": parent_id}
                elif parent.get("kind") in {"toc_entry", "toc_group"}:
                    parts = self._parts(parent.get("text", ""))
                    if parts:
                        evidence = {"title": parts["title"], "source": _origin(sources[parent_id], *parts["title_span"]),
                                    "role": parent_role, "native_parent": parent_id}
                    elif parent.get("kind") == "toc_group" and literal:
                        evidence = {"title": literal, "source": sources[parent_id], "role": parent_role, "native_parent": parent_id}
                    else:
                        self.issue("declared_toc_parent_entry_unread", sources[parent_id], category="software_unsupported")
                elif literal and (parent.get("kind") == "toc_group" or heading_evidence(parent)["role"] == "heading"):
                    evidence = {"title": literal, "source": sources[parent_id], "role": "explicit_native_parent_reference", "native_parent": parent_id}
                elif not prefix:
                    self.parent_resolution["unknown"] = True
                    self.issue("toc_parent_role_interpretation_unsupported", sources[parent_id], category="software_unsupported", layers=["L", "B"])
                paths.append([*prefix, evidence] if evidence else prefix)
            distinct = []
            for path in paths:
                if path not in distinct:
                    distinct.append(path)
            if len(distinct) > 1:
                self.issue("toc_conflicting_native_parent_paths", sources[ident], paths=copy.deepcopy(distinct))
                self.parent_resolution["unknown"] = True
                return [], True
            return (distinct[0], True) if distinct else ([], False)

        for block in blocks:
            source = sources[block.get("id")]
            kind = block.get("kind", "text")
            if kind in _MEDIA or kind in {"document_boundary", "new_document"} or block.get("document_start"):
                if block.get("text"):
                    self.atom(visible_text(block["text"], block.get("text_format", "plain")), source, "boundary_literal")
                self.active, self.groups, self.page_declaration = False, [], None
                continue
            if kind in _FURNITURE:
                self.atom(block.get("text", ""), source, "page_furniture")
                continue
            if block.get("cells") is not None:
                declarations = []
                if block.get("id") in own_captions:
                    self.page_declaration = own_captions[block["id"]]
                    declarations.append(copy.deepcopy(self.page_declaration))
                if block["cells"] and "<table" in block.get("text", "").lower():
                    prior_active = self.active
                    if kind in {"document_index", "toc"}:
                        self.active = True
                    self.text(block["text"], source, representation=block.get("text_format", "html"), native_cells_present=True)
                    if kind in {"document_index", "toc"} and not prior_active and not self.directory_evidence:
                        self.active = prior_active
                    if self.page_declaration:
                        declarations.append(copy.deepcopy(self.page_declaration))
                first = len(self.result["entries"])
                if block["cells"]:
                    self.cells(block["cells"], source, native_index=kind in {"document_index", "toc"})
                elif block.get("text"):
                    self.text(block["text"], source, representation=block.get("text_format", "plain"))
                if block.get("id") in self.result["handled_block_ids"] and block.get("id") in own_captions:
                    self.handled(own_captions[block["id"]]["source"])
                for declaration in declarations:
                    self.aliases(declaration["text"], declaration["source"], self.result["entries"][first:])
                self.page_declaration = None
            elif block.get("id") in owned_caption_ids:
                self.atom(block.get("text", ""), source, "attribute")
            else:
                previous_groups = self.groups
                previous_active = self.active
                previous_resolution = self.parent_resolution
                self.parent_resolution = {"unknown": False, "root_evidence": []}
                navigation = kind == "toc_entry" or self.active and (kind == "toc_group" or self._parts(block.get("text", "")) is not None)
                actual_parents, has_explicit = native_parents(block.get("id"), frozenset()) if navigation else ([], False)
                if has_explicit:
                    self.groups = actual_parents
                if kind == "toc_entry":
                    self.active = True
                first = len(self.result["entries"])
                self.text(block.get("text", ""), source, kind=kind, representation=block.get("text_format", "plain"),
                          level=block.get("heading_level", block.get("level")))
                if has_explicit:
                    self.groups = previous_groups
                if kind == "toc_entry" and not previous_active:
                    self.active = False
                if len(self.result["entries"]) > first:
                    parsed_blocks[block.get("id")] = self.result["entries"][first:]
                self.parent_resolution = previous_resolution


def read_toc(*, text: str | None = None, blocks: list[dict[str, Any]] | None = None,
             cells: list[dict[str, Any]] | None = None, source: dict[str, Any], context: tuple | list = (),
             text_format: str = "markdown") -> dict[str, Any]:
    """Read exactly one saved representation; no expected/filename role hints."""
    if sum(value is not None for value in (text, blocks, cells)) != 1:
        raise ValueError("provide exactly one of text, blocks or cells")
    reader = _Reader(source, context)
    if text is not None:
        reader.result["source_fragments"].append({"source": copy.deepcopy(source), "text": text})
        reader.text(text, source, representation=text_format)
    elif cells is not None:
        reader.cells(cells, source)
    else:
        reader.blocks(blocks)
    result = reader.result
    result["recognized"] = result["matched"]
    result["complete"] = bool(result["matched"] and not result["blockers"])
    result["consumed_spans"] = [{**copy.deepcopy(atom), "role": atom.get("role", "control")} for atom in [*result["text_atoms"], *result["controls"]]]
    return result


def project_toc_text(result: dict[str, Any]) -> dict[str, Any]:
    """Project only consumed sources, with finite aliases of printed labels.

    Logical ``fact.attribute`` is never a text source. Every alias must use
    the exact printed origin and an independently present candidate page slot.
    """
    from .text_projection import _alias, _key, _literal, _projection
    from .text_projection import _origin as text_origin

    projection = _projection()
    projection["complete"] = bool(result.get("text_projection_complete"))
    handled = set(result.get("handled_block_ids", []))

    def consumed(source):
        return source.get("block") is None or source.get("block") in handled

    def base_key(source):
        return _key({key: value for key, value in source.items() if key not in {"text_span", "cell_text_span"}})

    snapshots = {}
    for field in ("source_cells", "source_fragments"):
        projection[field] = [copy.deepcopy(item) for item in result.get(field, []) if consumed(item["source"])]
        for item in projection[field]:
            snapshots.setdefault(base_key(item["source"]), []).append(item)
    projection["controls"] = [copy.deepcopy(item) for item in result.get("controls", []) if consumed(item["source"])]
    entries = {entry["id"]: entry for entry in result.get("entries", [])}

    def block(reason, source):
        projection["complete"] = False
        projection["blockers"].append({"reason": reason, "source": copy.deepcopy(source)})

    for atom in result.get("text_atoms", []):
        source = atom["source"]
        if not consumed(source):
            continue
        origin = None
        for snapshot in snapshots.get(base_key(source), []):
            raw = snapshot["text"]
            span = source.get("cell_text_span", source.get("text_span"))
            offset = (snapshot["source"].get("text_span") or [0])[0]
            begin, end = (span[0] - offset, span[1] - offset) if span is not None else (0, len(raw))
            if not 0 <= begin <= end <= len(raw):
                continue
            if raw[begin:end] == atom["text"]:
                origin = text_origin(atom["text"], atom["role"], source)
                break
            relative = raw[begin:end].find(atom["text"])
            if relative >= 0:
                lo, hi = begin + relative, begin + relative + len(atom["text"])
                prefix, suffix = raw[begin:lo], raw[hi:end]
                if re.fullmatch(r"[\s*_`~]*", prefix + suffix):
                    adjusted = copy.deepcopy(source)
                    adjusted["cell_text_span" if "cell_text_span" in source else "text_span"] = [offset + lo, offset + hi]
                    origin = text_origin(atom["text"], atom["role"], adjusted)
                    for a, b in ((begin, lo), (hi, end)):
                        if a < b:
                            syntax_source = copy.deepcopy(source)
                            syntax_source["cell_text_span" if "cell_text_span" in source else "text_span"] = [offset + a, offset + b]
                            projection["controls"].append({"text": raw[a:b], "source": syntax_source,
                                                           "reason": "explicit_markdown_inline_syntax"})
                    break
        if origin is None:
            block("toc_text_origin_not_proven_by_original_snapshot", source)
            continue
        aliases = atom.get("aliases", [])
        if not aliases:
            _literal(projection, origin)
            continue
        seen = set()
        for alias in aliases:
            entry = entries.get(alias.get("entry_id"))
            if (alias.get("text") != atom["text"] or alias.get("origin") != source or entry is None
                    or alias.get("data_source") != entry["page_evidence"]["source"] or alias["entry_id"] in seen):
                block("toc_header_alias_not_proven_by_own_origin_and_page_object", source)
                continue
            seen.add(alias["entry_id"])
            obj = {"id": "data:" + _key(alias["data_source"]), "source": copy.deepcopy(alias["data_source"])}
            _alias(projection, origin, obj)
    return projection
