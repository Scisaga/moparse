"""Request-private evidence for a source region with unresolved structure."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceGlyph:
    character_index: int
    literal_text: str
    bbox_top_left: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class SourceRegionEvidence:
    source_ref: str
    page_number: int
    normalized_bbox: tuple[float, float, float, float]
    literal_text: str
    source_sha256: str
    glyphs: tuple[SourceGlyph, ...]
    page_width: float
    page_height: float
    rotation_degrees: int
    original_table: dict[str, Any]
    raw_model_table_html: str | None = None
    character_observation: dict[str, Any] = field(default_factory=dict)
    independent_evidence: dict[str, Any] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = (
        "source_witnessed_character_excess",
        "independent_region_type_disagreement",
        "source_region_structure_unknown",
    )

    @property
    def image_placeholder(self) -> str:
        return f"<!-- source-region-image: {self.source_ref} -->"

    @property
    def rendered(self) -> str:
        # The source text remains literal, including signs, pipes and apparent
        # Markdown. A longer delimiter also preserves source backtick runs.
        fence = "`" * max(
            3, max((len(run) for run in re.findall(r"`+", self.literal_text)), default=0) + 1
        )
        ending = "" if self.literal_text.endswith(("\n", "\r")) else "\n"
        return (
            f"<!-- source-region: {self.source_ref}; source-page: {self.page_number}; "
            "structure: unknown -->\n\n"
            f"{self.image_placeholder}\n\n"
            f"{fence}text\n{self.literal_text}{ending}{fence}\n\n"
            f"<!-- /source-region: {self.source_ref} -->"
        )


@dataclass(frozen=True, slots=True)
class SourceRegionPictureCandidate:
    page_number: int
    normalized_bbox: tuple[float, float, float, float]
    source_region_ref: str
    placeholder_index: int = 0
    caption: str = ""
    allow_description: bool = False
