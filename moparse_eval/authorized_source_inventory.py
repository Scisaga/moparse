"""Independent raw-text inventory for an existing authorized expected selection.

The bounded lexer below does not import the Markdown reader, its adapters, or
semantic compilers. It checks whether their target view actually retains every
authorized raw payload. Unknown syntax remains pending. These are evaluation
input transport obligations, never corpus review or acceptance judgments.
"""

from __future__ import annotations

import copy
import html
import re
import string
import unicodedata
from collections import Counter
from typing import Any


class AuthorizedSourceError(ValueError):
    """A derived target does not originate in its declared raw selection."""


def _punctuation(char: str) -> bool:
    return bool(char) and (char in string.punctuation or unicodedata.category(char).startswith(("P", "S")))


def _flanking(raw: str, start: int, size: int) -> tuple[bool, bool]:
    previous = raw[start - 1] if start else ""
    following = raw[start + size] if start + size < len(raw) else ""
    left = bool(following and not following.isspace() and (not _punctuation(following) or not previous or previous.isspace() or _punctuation(previous)))
    right = bool(previous and not previous.isspace() and (not _punctuation(previous) or not following or following.isspace() or _punctuation(following)))
    if raw[start] == "_":
        return left and (not right or _punctuation(previous)), right and (not left or _punctuation(following))
    return left, right


def _reference(raw: str, start: int) -> tuple[dict[str, Any] | None, int, str | None]:
    kind = "image" if raw.startswith("![", start) else "link"
    first = start + (2 if kind == "image" else 1)
    index, depth = first, 1
    while index < len(raw):
        if raw[index] == "\\" and index + 1 < len(raw):
            index += 2
            continue
        if raw[index] == "[":
            depth += 1
        elif raw[index] == "]":
            depth -= 1
            if depth == 0:
                break
        index += 1
    if depth or index + 1 >= len(raw) or raw[index + 1] != "(":
        return None, start, None
    label = raw[first:index]
    cursor, opening = index + 2, index + 2
    depth, quote = 1, None
    while cursor < len(raw):
        char = raw[cursor]
        if char == "\\" and cursor + 1 < len(raw):
            cursor += 2
            continue
        if quote:
            if char == quote:
                quote = None
        elif char in {'"', "'"} and cursor > opening and raw[cursor - 1].isspace():
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                break
        cursor += 1
    if depth:
        return None, start, "unclosed_inline_reference"
    content = raw[opening:cursor].strip()
    match = re.fullmatch(r'''(?P<destination><[^<>\n]*>|(?:\\.|[^\s])+)?(?:\s+(?P<quote>["'])(?P<title>.*)(?P=quote))?''', content)
    if match is None:
        return None, start, "unsupported_inline_reference_destination_or_title"
    destination = match["destination"] or ""
    if destination.startswith("<"):
        destination = destination[1:-1]
    destination = html.unescape(re.sub(r"\\([" + re.escape(string.punctuation) + r"])", r"\1", destination))
    text, error, nested = _inline_details(label)
    if error or nested:
        return None, start, error or "nested_reference_binding_unsupported"
    return {"kind": kind, "destination": destination, "text": text,
            "title": html.unescape(match["title"]) if match["title"] is not None else None}, cursor + 1, None


def _inline_details(raw: str) -> tuple[str, str | None, list[dict[str, Any]]]:
    """A finite display-syntax lexer; unsupported constructs remain explicit."""
    output, references, index = [], [], 0
    while index < len(raw):
        char = raw[index]
        if char == "\\" and index + 1 < len(raw) and raw[index + 1] in string.punctuation:
            output.append(raw[index + 1])
            index += 2
        elif char == "&" and (entity := re.match(r"&(?:#[0-9]+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);", raw[index:])):
            value = html.unescape(entity[0])
            if value == entity[0]:
                return "", "unknown_character_entity", []
            output.append(value)
            index += len(entity[0])
        elif char == "`":
            size = len(raw[index:]) - len(raw[index:].lstrip("`"))
            closing = re.search(r"(?<!`)`{" + str(size) + r"}(?!`)", raw[index + size:])
            if closing is None:
                return "", "unclosed_inline_code", []
            close = index + size + closing.start()
            value = raw[index + size:close].replace("\n", " ")
            if value.startswith(" ") and value.endswith(" ") and value.strip():
                value = value[1:-1]
            output.append(value)
            index = close + size
        elif raw.startswith(("![", "["), index):
            reference, stop, error = _reference(raw, index)
            if error:
                return "", error, []
            if reference is None:
                output.append(char)
                index += 1
            else:
                output.append(reference["text"])
                references.append({**reference, "raw_span": [index, stop], "raw": raw[index:stop]})
                index = stop
        elif char == "<" and re.match(r"<(?:/?[A-Za-z!?]|[A-Za-z][A-Za-z0-9+.-]*:)[^>]*>", raw[index:]):
            return "", "unsupported_html_or_autolink_syntax", []
        elif char in "*_":
            size = len(raw[index:]) - len(raw[index:].lstrip(char))
            opens, _closes = _flanking(raw, index, size)
            closing = next((match for match in re.finditer(r"(?<!" + re.escape(char) + ")" + re.escape(char) + "{" + str(size) + r"}(?!" + re.escape(char) + ")", raw[index + size:])
                            if _flanking(raw, index + size + match.start(), size)[1]), None) if opens else None
            if opens and closing is None and any(_flanking(raw, index + size + match.start(), len(match[0]))[1]
                    for match in re.finditer(re.escape(char) + "+", raw[index + size:])):
                return "", "unsupported_emphasis_run_interaction", []
            if size > 2 and closing is not None:
                return "", "unsupported_nested_emphasis", []
            if closing is not None:
                close = index + size + closing.start()
                value, error, inner_refs = _inline_details(raw[index + size:close])
                if error:
                    return "", error, []
                output.append(value)
                references.extend({**reference, "raw_span": [reference["raw_span"][0] + index + size,
                                                             reference["raw_span"][1] + index + size]} for reference in inner_refs)
                index = close + size
            else:
                output.append(char * size)
                index += size
        else:
            output.append(char)
            index += 1
    return "".join(output), None, references


def _inline(raw: str) -> tuple[str, str | None]:
    text, error, _references = _inline_details(raw)
    return text, error


def _payload(raw: str, *, hard_break_continues: bool = False) -> tuple[str, str | None, str]:
    text = raw.rstrip("\r\n")
    if re.match(r"\s*(?::::|\[\^|<[/!?A-Za-z])", text):
        return "", "unsupported_block_syntax", "unknown"
    role = "plain_line"
    heading = re.match(r"^ {0,3}#{1,6}(?:[ \t]+|$)", text)
    item = re.match(r"^[ \t]*(?:[-+*]|[0-9]{1,9}[.)])[ \t]+", text)
    quote = re.match(r"^ {0,3}(?:>[ \t]?)+", text)
    if heading:
        role, text = "atx_heading_payload", text[heading.end():]
        text = re.sub(r"[ \t]+#+[ \t]*$", "", text)
    elif item:
        role, text = "list_item_payload", text[item.end():]
    elif quote:
        role, text = "blockquote_payload", text[quote.end():]
    if hard_break_continues and raw.endswith(("\r", "\n")) and (len(text) - len(text.rstrip("\\"))) % 2 == 1:
        text = text[:-1]
    literal, error = _inline(text.strip())
    return literal, error, role


def _pipe_cells(line: str) -> list[tuple[int, int]] | None:
    """Lex unescaped GFM pipes while retaining each original cell span."""
    text = line.rstrip("\r\n")
    pipes, index = [], 0
    while index < len(text):
        if text[index] == "\\" and index + 1 < len(text):
            index += 2
        else:
            if text[index] == "|":
                pipes.append(index)
            index += 1
    if not pipes:
        return None
    spans = list(zip([0, *(position + 1 for position in pipes)], [*pipes, len(text)], strict=True))
    if not text[:pipes[0]].strip():
        spans.pop(0)
    if not text[pipes[-1] + 1:].strip():
        spans.pop()
    return spans


def _delimiter(line: str, width: int) -> bool:
    cells = _pipe_cells(line)
    return bool(cells and len(cells) == width and all(
        re.fullmatch(r"[ \t]*:?-{3,}:?[ \t]*", line[a:b]) for a, b in cells))


def _target_payload(target: dict[str, Any]) -> tuple[str, str | None]:
    lines = target["raw"].splitlines()
    if lines and (fence := re.fullmatch(r" {0,3}(`{3,}|~{3,})[^`]*", lines[0])):
        mark = fence[1]
        if len(lines) < 2 or not re.fullmatch(r" {0,3}" + re.escape(mark[0]) + "{" + str(len(mark)) + r",}[ \t]*", lines[-1]):
            return "", "unclosed_fenced_literal"
        return "\n".join(lines[1:-1]).strip(), None
    values = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        value, error, _role = _payload(line + ("\n" if index + 1 < len(lines) else ""),
                                       hard_break_continues=index + 1 < len(lines))
        if error:
            return "", error
        values.append(value)
    return "\n".join(values).strip(), None


def plan_authorized_source_inventory(raw_segments: list[dict[str, Any]] | None,
                                     targets: list[dict[str, Any]]) -> dict[str, Any]:
    """Bind original selected raw text to independently enumerated payloads.

    ``None`` is reserved for controlled target-only software fixtures. An empty
    real raw selection is incomplete. External canonical binding must compare
    these raw segments with a fresh read of the authorized selected source.
    """
    if raw_segments is None:
        return {"purpose": "authorized_expected_raw_source_transport_not_corpus_review",
                "scope": "controlled_supplied_target_fixture", "segments": [], "obligations": [],
                "heading_scope_obligations": [],
                "source_complete": True, "canonical_authorized_source_complete": False,
                "status_counts": {}, "basis": "supplied_target_scope_only_no_canonical_source_claim"}
    if not isinstance(raw_segments, list):
        raise AuthorizedSourceError("authorized raw segments must be a source-supplied list")
    segments, bound, bound_refs, occupied = [], {}, {}, set()
    for original in raw_segments:
        segment = copy.deepcopy(original)
        source, raw = segment.get("source", {}), segment.get("raw")
        bounds = source.get("lines")
        if (not isinstance(source.get("path"), str) or not source["path"] or not isinstance(raw, str)
                or not isinstance(bounds, list) or len(bounds) != 2
                or any(type(value) is not int for value in bounds) or not 1 <= bounds[0] <= bounds[1]):
            raise AuthorizedSourceError("authorized raw source has no exact path, lines and literal")
        lines = raw.splitlines(keepends=True)
        if len(lines) != bounds[1] - bounds[0] + 1:
            raise AuthorizedSourceError("authorized raw literal differs from its physical line span")
        keys = {(source["path"], line) for line in range(bounds[0], bounds[1] + 1)}
        if occupied & keys:
            raise AuthorizedSourceError("authorized raw segments overlap or duplicate a physical source line")
        occupied.update(keys)
        segment["lines"] = lines
        segment["bound_targets"] = []
        segments.append(segment)
    for target in targets:
        source = target.get("reference", {})
        bounds, raw = source.get("lines"), target.get("raw")
        if (not isinstance(bounds, (list, tuple)) or len(bounds) != 2
                or any(type(value) is not int for value in bounds) or not isinstance(raw, str)):
            raise AuthorizedSourceError("target has no exact raw source span")
        owners = [segment for segment in segments if source.get("path") == segment["source"]["path"]
                  and segment["source"]["lines"][0] <= bounds[0] <= bounds[1] <= segment["source"]["lines"][1]]
        if len(owners) != 1:
            raise AuthorizedSourceError("target raw source path or lines are outside the authorized raw selection")
        owner = owners[0]
        start = bounds[0] - owner["source"]["lines"][0]
        if "".join(owner["lines"][start:start + bounds[1] - bounds[0] + 1]) != raw:
            raise AuthorizedSourceError("target raw literal does not cut its actual authorized source")
        owner["bound_targets"].append(target)
        bound[target["id"]] = _target_payload(target)
        _payload_text, ref_error, refs = _inline_details(raw)
        bound_refs[target["id"]] = (refs, ref_error)
    obligations, heading_scopes, heading_stack = [], [], []

    def add(segment, start, end, kind, literal, rule, *, status="pending", reason="authorized_source_payload_unrepresented", evidence=(), **detail):
        obligations.append({"id": f"authorized-raw-obligation:{len(obligations)}", "kind": kind,
            "source": {"path": segment["source"]["path"], "lines": [start, end]},
            "text": literal, "interpretation_rule": rule, "status": status, "reason": reason,
            "evidence": copy.deepcopy(list(evidence)), **detail})
        if status == "pending":
            obligations[-1]["failure_kind"] = ("unimplemented_syntax" if reason.startswith(("unsupported", "unclosed", "unknown_"))
                                               else "parser_transport_loss")
        if kind in {"text_payload", "gfm_cell", "code_literal", "unknown"} and rule != "atx_heading_payload":
            known = [{"text": heading["text"], "reference": copy.deepcopy(heading["reference"])}
                     for heading in heading_stack if heading["text"] is not None]
            unknown = [copy.deepcopy(heading["reference"]) for heading in heading_stack if heading["text"] is None]
            scope_status = "pending" if unknown or kind == "unknown" else "known" if heading_stack else "unclaimed"
            absolute = bool(heading_stack and heading_stack[0]["level"] == 1 and not unknown)
            obligations[-1].update(required_scope=copy.deepcopy(known), scope_status=scope_status, scope_is_absolute=absolute)
            heading_scopes.append({"id": f"authorized-raw-heading-scope:{len(heading_scopes)}",
                "payload_obligation_id": obligations[-1]["id"], "source": copy.deepcopy(obligations[-1]["source"]),
                "required_scope": known, "scope_status": scope_status, "scope_is_absolute": absolute,
                "rule_id": "contiguous_raw_atx_heading_stack",
                "scope_basis": "contiguous_authorized_raw_atx_headings_only",
                **({"unresolved_heading_sources": unknown} if unknown else {}),
                **{key: copy.deepcopy(detail[key]) for key in ("row", "column") if key in detail}})

    def references_equal(required, actual):
        return ([{key: reference[key] for key in ("kind", "destination", "text", "title")} for reference in required]
                == actual)

    def add_reference(segment, number, reference, evidence, *, raw_offset=0):
        add(segment, number, number, "media_reference" if reference["kind"] == "image" else "link_reference",
            reference["destination"], "independently_bound_source_reference_and_caption",
            status="explained" if evidence else "pending",
            reason="source_reference_and_complete_caption_retained" if evidence else "reference_destination_caption_or_title_missing_or_altered",
            evidence=evidence, caption=reference["text"], title=reference["title"], raw=reference["raw"],
            raw_span=[raw_offset + value for value in reference["raw_span"]])

    for segment in segments:
        # A gap never imports an ancestor that was not in this selected raw
        # stream. Existing outside-selection declarations remain separate.
        heading_stack = []
        lines, start = segment["lines"], segment["source"]["lines"][0]
        index = 0
        while index < len(lines):
            line, number = lines[index], start + index
            if not line.strip():
                add(segment, number, number, "syntax", line, "explicit_blank_line", status="explicitly_not_applicable", reason="raw_blank_spacing_has_no_payload")
                index += 1
                continue
            if re.fullmatch(r" {0,3}(?:>[ \t]?)+", line.rstrip("\r\n")):
                add(segment, number, number, "syntax", line, "explicit_empty_quote_continuation",
                    status="explicitly_not_applicable", reason="raw_empty_quote_line_has_no_literal_payload")
                index += 1
                continue
            fence = re.fullmatch(r" {0,3}(`{3,}|~{3,})([^`\r\n]*)[\r\n]*", line)
            if fence:
                marker = fence[1]
                closing = next((stop for stop in range(index + 1, len(lines)) if re.fullmatch(
                    r" {0,3}" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}[ \t]*[\r\n]*", lines[stop])), None)
                if closing is not None:
                    literal = "".join(lines[index + 1:closing]).strip()
                    owners = [target for target in segment["bound_targets"]
                              if list(target["reference"]["lines"]) == [number, start + closing]
                              and target.get("raw_text", target.get("text")) == literal]
                    add(segment, number, number, "syntax", line, "explicit_literal_fence_open",
                        status="explicitly_not_applicable", reason="fence_declares_literal_display", language=fence[2].strip())
                    if closing > index + 1:
                        add(segment, number + 1, start + closing - 1, "code_literal", literal, "exact_fenced_literal_body",
                            status="explained" if owners else "pending",
                            reason="complete_fenced_literal_retained" if owners else "fenced_literal_body_missing_or_altered",
                            evidence=[{"target_id": target["id"], "source": copy.deepcopy(target["reference"])} for target in owners])
                    add(segment, start + closing, start + closing, "syntax", lines[closing], "explicit_literal_fence_close",
                        status="explicitly_not_applicable", reason="fence_closes_literal_display")
                    index = closing + 1
                    continue
                add(segment, number, start + len(lines) - 1, "unknown", "".join(lines[index:]),
                    "unclosed_literal_fence_has_unknown_remaining_scope", reason="unclosed_fenced_literal")
                break
            if line.lstrip().startswith("<!--"):
                stop = index
                while stop < len(lines) and "-->" not in lines[stop]:
                    stop += 1
                literal = "".join(lines[index:min(stop + 1, len(lines))])
                if stop < len(lines) and re.fullmatch(r"\s*<!--(?:(?!-->).)*-->\s*", literal, re.S):
                    add(segment, number, start + stop, "syntax", literal, "explicit_comment_block", status="explicitly_not_applicable", reason="raw_comment_has_no_display_payload")
                    index = stop + 1
                    continue
                if stop == len(lines):
                    add(segment, number, start + len(lines) - 1, "unknown", literal,
                        "unclosed_comment_has_unknown_remaining_scope", reason="unclosed_comment_block")
                    break
            header = _pipe_cells(line)
            if header and index + 1 < len(lines) and _delimiter(lines[index + 1], len(header)):
                stop = index + 2
                while stop < len(lines) and lines[stop].strip() and _pipe_cells(lines[stop]):
                    stop += 1
                owners = [target for target in segment["bound_targets"]
                          if list(target["reference"]["lines"]) == [number, start + stop - 1]]
                add(segment, number + 1, number + 1, "syntax", lines[index + 1], "explicit_gfm_column_separator", status="explicitly_not_applicable", reason="gfm_separator_declares_source_columns")
                table_lines = [index, *range(index + 2, stop)]
                for row, position in enumerate(table_lines):
                    cells = _pipe_cells(lines[position]) or []
                    if len(cells) != len(header):
                        add(segment, start + position, start + position, "unknown", lines[position], "gfm_row_width_must_be_explicit", reason="gfm_row_width_requires_unsupported_padding_or_truncation")
                    for column, (a, b) in enumerate(cells):
                        raw_cell = lines[position][a:b]
                        literal, error, refs = _inline_details(raw_cell.strip())
                        if "`" in raw_cell and "\\|" in raw_cell:
                            error = "unsupported_gfm_escaped_code_pipe"
                        matches = [(target, cell) for target in owners for cell in target.get("cells", [])
                                   if cell.get("row") == row and cell.get("col") == column
                                   and cell.get("row_span", 1) == cell.get("col_span", 1) == 1
                                   and cell.get("text") == literal]
                        explained = error is None and len(matches) == 1
                        add(segment, start + position, start + position, "gfm_cell", literal if error is None else raw_cell,
                            "each_original_gfm_cell_payload", status="explained" if explained else "pending",
                            reason="exact_original_cell_retained" if explained else error or "original_gfm_cell_missing_altered_or_duplicated",
                            evidence=[{"target_id": target["id"], "cell_id": cell.get("id"), "row": row, "column": column}
                                      for target, cell in matches], raw=raw_cell, raw_span=[a, b], row=row, column=column)
                        for reference in refs:
                            evidence = [{"target_id": target["id"], "cell_id": cell.get("id"), "row": row, "column": column}
                                        for target, cell in matches if explained and references_equal(refs, cell.get("inline_references", []))]
                            add_reference(segment, start + position, reference, evidence,
                                          raw_offset=a + len(raw_cell) - len(raw_cell.lstrip()))
                index = stop
                continue
            if re.fullmatch(r" {0,3}(?:\*[ \t]*){3,}| {0,3}(?:-[ \t]*){3,}| {0,3}(?:_[ \t]*){3,}", line.rstrip("\r\n")):
                add(segment, number, number, "syntax", line, "explicit_thematic_rule", status="explicitly_not_applicable", reason="raw_thematic_separator_has_no_literal_payload")
                index += 1
                continue
            continues = any(target["reference"]["lines"][0] <= number < target["reference"]["lines"][1]
                            for target in segment["bound_targets"])
            payload, error, role = _payload(line, hard_break_continues=continues)
            matches = []
            for target in segment["bound_targets"]:
                a, b = target["reference"]["lines"]
                expected_payload, target_error = bound[target["id"]]
                actual_payload = target.get("raw_text", target.get("text"))
                if a <= number <= b and target_error is None and expected_payload == actual_payload:
                    matches.append({"target_id": target["id"], "source": copy.deepcopy(target["reference"]),
                                    "payload": actual_payload})
            explained = error is None and bool(matches)
            add(segment, number, number, "text_payload" if error is None else "unknown", payload if error is None else line,
                role, status="explained" if explained else "pending",
                reason="complete_independent_raw_payload_retained" if explained else error or "raw_payload_missing_or_altered_in_target_text", evidence=matches,
                raw=line, raw_span=[0, len(line.rstrip("\r\n"))])
            if role == "atx_heading_payload":
                stripped = line.lstrip(" ")
                level = len(stripped) - len(stripped.lstrip("#"))
                heading_stack = [heading for heading in heading_stack if heading["level"] < level]
                heading_stack.append({"level": level, "text": payload if error is None else None,
                                      "reference": {"path": segment["source"]["path"], "lines": [number, number]}})
            _text, reference_error, refs = _inline_details(line)
            if reference_error is None:
                for reference in refs:
                    evidence = []
                    for target in segment["bound_targets"]:
                        required_refs, target_error = bound_refs[target["id"]]
                        if (any(proof["target_id"] == target["id"] for proof in matches) and target_error is None
                                and references_equal(required_refs, target.get("inline_references", []))):
                            evidence.append({"target_id": target["id"], "source": copy.deepcopy(target["reference"]),
                                             "reference": {key: reference[key] for key in ("kind", "destination", "text", "title")}})
                    add_reference(segment, number, reference, evidence)
            index += 1
    if not obligations:
        obligations.append({"id": "authorized-raw-obligation:0", "kind": "unknown", "source": {}, "text": "",
                            "status": "pending", "reason": "authorized_raw_selection_empty",
                            "interpretation_rule": "authorized_source_scope_must_be_present", "evidence": []})
    complete = all(row["status"] != "pending" for row in obligations)
    return {"purpose": "authorized_expected_raw_source_transport_not_corpus_review",
            "scope": "canonical_authorized_raw", "segments": copy.deepcopy(raw_segments),
            "obligations": obligations, "heading_scope_obligations": heading_scopes, "source_complete": complete,
            "canonical_authorized_source_complete": complete,
            "status_counts": dict(Counter(row["status"] for row in obligations))}
