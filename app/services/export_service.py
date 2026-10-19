"""Deterministic Markdown/Text normalization and page joining."""

from __future__ import annotations

import hashlib
import html
import re
from collections.abc import Sequence

from app.models.parse_result import PageParseResult
from app.models.source_evidence import SourceRegionEvidence
from app.services.table_service import (
    PageFurnitureFragment,
    TableFragment,
    TableSourceView,
    assemble_logical_tables,
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_FENCE_RE = re.compile(r"^\s*```[^\n]*\n|^\s*```\s*$", re.MULTILINE)
_EMPHASIS_RE = re.compile(r"(?<!\\)(?:\*\*|__|~~|`)(.*?)(?<!\\)(?:\*\*|__|~~|`)", re.DOTALL)


class ExportService:
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
        text = _FENCE_RE.sub("", markdown)
        text = _LINK_RE.sub(lambda match: match.group(1), text)
        text = _HEADING_RE.sub("", text)
        text = re.sub(r"^[ \t]{0,3}>[ \t]?", "", text, flags=re.MULTILINE)
        text = re.sub(r"^[ \t]*[-+*][ \t]+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^[ \t]*\d+[.)][ \t]+", "", text, flags=re.MULTILINE)
        text = _EMPHASIS_RE.sub(lambda match: match.group(1), text)
        text = _HTML_TAG_RE.sub("", text)
        text = html.unescape(text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()
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
