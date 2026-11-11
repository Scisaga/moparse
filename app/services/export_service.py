"""Deterministic Markdown/Text normalization and page joining."""

from __future__ import annotations

import hashlib
import html
import re
from collections.abc import Sequence
from difflib import SequenceMatcher
from html.parser import HTMLParser

from markdown_it import MarkdownIt
from markdown_it.rules_inline.backticks import backtick
from markdown_it.rules_inline.state_inline import StateInline

from app.models.parse_result import DocumentParseResult, PageParseResult
from app.models.source_evidence import SourceRegionEvidence
from app.services.table_service import (
    PageFurnitureFragment,
    TableFragment,
    TableSourceView,
    assemble_logical_tables,
)

_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_FENCE_RE = re.compile(r"^\s*```[^\n]*\n|^\s*```\s*$", re.MULTILINE)
_EMPHASIS_RE = re.compile(r"(?<!\\)(?:\*\*|__|~~|`)(.*?)(?<!\\)(?:\*\*|__|~~|`)", re.DOTALL)


class _PlainHTMLText(HTMLParser):
    """Strip actual HTML markup without consuming ordinary comparison text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.parts.append(f"&#{name};")

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"sup", "sub"}:
            # Explicit typographic boundaries are evidence, not permission to
            # reinterpret the item as a footnote, exponent or adjacent digit.
            self.parts.append(self.get_starttag_text() or f"<{tag}>")
        elif tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"sup", "sub"}:
            self.parts.append(f"</{tag}>")


def _protect_code(content: str) -> tuple[str, list[tuple[str, str]]]:
    """Protect actual fenced/indented blocks and inline code before cleanup."""
    protected: list[tuple[str, str]] = []
    original = content

    def replace_spans(spans: list[tuple[int, int, str]]) -> None:
        nonlocal content
        for start, end, literal in reversed(spans):
            token = f"MOPARSECODE{len(protected)}TOKEN"
            while token in content or token in original:
                token += "X"
            content = content[:start] + token + content[end:]
            protected.append((token, literal))

    parser = MarkdownIt("commonmark")
    offsets = [0]
    # CommonMark maps CR/LF lines. str.splitlines also splits form feeds and
    # Unicode separators, which shifts spans after the real page separator.
    offsets.extend(match.end() for match in re.finditer(r"\r\n|\r|\n", content))
    if offsets[-1] != len(content):
        offsets.append(len(content))
    blocks = []
    for token in parser.parse(content):
        if token.type in {"fence", "code_block"} and token.map is not None:
            start, end = token.map
            finish = offsets[end]
            # Keep the original separator after the block outside its token.
            # Otherwise a following paragraph would join the last code line.
            if content[:finish].endswith("\r\n"):
                finish -= 2
            elif finish and content[finish - 1] in "\r\n":
                finish -= 1
            blocks.append((offsets[start], finish, token.content.removesuffix("\n")))
    replace_spans(blocks)
    state = StateInline(content, parser, {}, [])
    spans = []
    position = 0
    while position < len(content):
        if content[position] == "\\":
            position += 2
        elif content[position] == "`":
            state.pos = position
            before = len(state.tokens)
            backtick(state, False)
            tokens = state.tokens[before:]
            if tokens and tokens[-1].type == "code_inline":
                # Inline parsing cannot cross a Markdown paragraph boundary.
                if not re.search(r"\n[ \t]*\n", content[position:state.pos]):
                    spans.append((position, state.pos, tokens[-1].content))
            position = state.pos
        else:
            position += 1
    replace_spans(spans)
    return content, protected


class ExportService:
    def apply_document(self, result: DocumentParseResult, *, merge_cross_page_tables: bool = True) -> None:
        """Assemble the same source-owned document for live and saved inputs."""
        views: list[TableSourceView] = []
        for page in result.pages:
            page.plain_text = self.markdown_to_text(page.content or "", source_regions=result._source_regions)
        before = (self.join_pages(result.pages, preserve_page_breaks=True, source_regions=result._source_regions)[0]
                  if "saved_p01" in result._source_verification else None)
        result.markdown, result.plain_text = self.join_document(
            result.pages, preserve_page_breaks=True, table_fragments=result._table_fragments,
            page_furniture=result._page_furniture, source_regions=result._source_regions,
            merge_cross_page_tables=merge_cross_page_tables, public_views=views,
        )
        result._table_views = [*views]
        result.processed_pages = sum(page.status.value != "failed" for page in result.pages)
        if before is not None:
            refs = [fragment.native_evidence.get("native_path", fragment.fragment_id)
                    for fragment in result._table_fragments if isinstance(fragment, TableFragment)]
            result._source_verification["saved_exported_edits"] = {
                "input": before, "output": result.markdown,
                "edits": [{"before_span": [a, b], "after_span": [c, d], "before": before[a:b],
                           "after": result.markdown[c:d], "reason": "source_table_assembly_and_page_export",
                           "source_refs": refs}
                          for operation, a, b, c, d in SequenceMatcher(None, before, result.markdown, autojunk=False).get_opcodes()
                          if operation != "equal"],
            }

    @staticmethod
    def _protect_source_regions(
        content: str, source_regions: list[object] | None
    ) -> tuple[str, list[tuple[str, SourceRegionEvidence]]]:
        protected = []
        for region in source_regions or []:
            if not isinstance(region, SourceRegionEvidence) or region.rendered not in content:
                continue
            if content.count(region.rendered) != 1:
                raise ValueError("source-region evidence has no unique rendering position")
            digest = hashlib.sha256(region.rendered.encode()).hexdigest()
            token = f"MOPARSESOURCEREGION{digest}"
            while token in content:
                token += "X"
            content = content.replace(region.rendered, token, 1)
            protected.append((token, region))
        return content, protected

    @staticmethod
    def normalize_markdown(content: str, *, source_regions: list[object] | None = None) -> str:
        content, protected = ExportService._protect_source_regions(content, source_regions)
        content = content.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
        content = "\n".join(line.rstrip() for line in content.splitlines())
        content = re.sub(r"\n{4,}", "\n\n\n", content)
        content = content.strip()
        for token, region in protected:
            content = content.replace(token, region.rendered, 1)
        return content

    @staticmethod
    def markdown_to_text(markdown: str, *, source_regions: list[object] | None = None) -> str:
        markdown, protected = ExportService._protect_source_regions(markdown, source_regions)
        markdown, code = _protect_code(markdown)
        text = _FENCE_RE.sub("", markdown)
        text = _LINK_RE.sub(lambda match: match.group(1), text)
        text = _HEADING_RE.sub("", text)
        text = re.sub(r"^[ \t]{0,3}>[ \t]?", "", text, flags=re.MULTILINE)
        text = re.sub(r"^[ \t]*[-+*][ \t]+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^[ \t]*\d+[.)][ \t]+", "", text, flags=re.MULTILINE)
        text = _EMPHASIS_RE.sub(lambda match: match.group(1), text)
        html_text = _PlainHTMLText()
        html_text.feed(text)
        html_text.close()
        text = "".join(html_text.parts)
        text = html.unescape(text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()
        for token, literal in code:
            text = text.replace(token, literal, 1)
        for token, region in protected:
            text = text.replace(token, region.literal_text, 1)
        return text

    def join_pages(
        self,
        pages: Sequence[PageParseResult],
        *,
        preserve_page_breaks: bool,
        source_regions: list[object] | None = None,
    ) -> tuple[str, str]:
        markdown_parts: list[str] = []
        text_parts: list[str] = []
        protected_regions: list[tuple[str, SourceRegionEvidence]] = []
        for page in pages:
            source, protected = self._protect_source_regions(page.content or "", source_regions)
            protected_regions.extend(protected)
            markdown = self.normalize_markdown(source)
            plain = (
                (page.plain_text if not protected else None) or self.markdown_to_text(markdown)
            ).strip()
            if preserve_page_breaks:
                markdown_parts.append(f"<!-- page: {page.page_number} -->\n\n{markdown}".rstrip())
                text_parts.append(f"--- Page {page.page_number} ---\n\n{plain}".rstrip())
            else:
                markdown_parts.append(markdown)
                text_parts.append(plain)
        separator = "\n\n\f\n\n" if preserve_page_breaks else "\n\n"
        markdown = separator.join(markdown_parts).strip()
        plain = separator.join(text_parts).strip()
        for token, region in protected_regions:
            markdown = markdown.replace(token, region.rendered, 1)
            plain = plain.replace(token, region.literal_text, 1)
        return markdown, plain

    def join_document(
        self,
        pages: Sequence[PageParseResult],
        *,
        preserve_page_breaks: bool,
        table_fragments: list[object] | None = None,
        merge_cross_page_tables: bool = True,
        page_furniture: list[object] | None = None,
        source_regions: list[object] | None = None,
        public_views: list[TableSourceView] | None = None,
    ) -> tuple[str, str]:
        fragments = [item for item in table_fragments or [] if isinstance(item, TableFragment)]
        content_by_page = assemble_logical_tables(
            list(pages),
            fragments,
            enabled=merge_cross_page_tables,
            page_furniture=[
                item for item in page_furniture or [] if isinstance(item, PageFurnitureFragment)
            ],
            public_views=public_views,
        )
        canonical = [
            page.model_copy(
                update={
                    "content": content_by_page.get(page.page_number, page.content or ""),
                    "plain_text": None,
                }
            )
            for page in pages
        ]
        return self.join_pages(
            canonical,
            preserve_page_breaks=preserve_page_breaks,
            source_regions=source_regions,
        )
