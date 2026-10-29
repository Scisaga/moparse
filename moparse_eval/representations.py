"""Visible-text projections for declared representations, without answer repair."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any


class _VisibleHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"style", "script"}:
            self.hidden += 1
        elif tag == "br" and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"style", "script"}:
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def visible_text(text: str, representation: str = "plain") -> str:
    """Decode display syntax only when the native field declares that syntax."""
    if representation in {"plain", "literal"}:
        return text
    if representation == "html":
        parser = _VisibleHTML()
        parser.feed(text)
        parser.close()
        return "".join(parser.parts).strip("\n")
    if representation != "markdown":
        raise ValueError(f"unsupported declared text representation: {representation}")
    from markdown_it import MarkdownIt

    def visible(tokens: list[Any]) -> str:
        fragments = []
        for token in tokens:
            if token.type in {"text", "code_inline", "fence", "code_block"}:
                fragments.append(token.content)
            elif token.type in {"softbreak", "hardbreak"}:
                fragments.append("\n")
            elif token.type == "html_block":
                fragments.append(visible_text(token.content, "html"))
            elif token.type == "html_inline":
                fragments.append(visible_text(token.content, "html"))
            elif token.children:
                fragments.append(visible(token.children))
            elif token.type in {"paragraph_close", "heading_close"}:
                fragments.append("\n")
        return "".join(fragments)

    return visible(MarkdownIt("commonmark").parse(text)).strip("\n")
