"""Read explicit HTML line breaks without joining words or changing cell bounds.

This is a presentation decoder for source assertions, never a parser repair.
Escaped tags and backtick code are literal text and must remain literal.
"""

from __future__ import annotations

import re

_CODE_OR_BREAK = re.compile(r"(`+)[\s\S]*?\1|(?<!\\)<br\s*/?>", re.IGNORECASE)


def html_breaks_as_spaces(markdown: str) -> str:
    return _CODE_OR_BREAK.sub(lambda match: match[0] if match[0].startswith("`") else " ", markdown)
