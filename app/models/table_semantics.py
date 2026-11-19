"""Source references and relations for a derived Markdown view, never new values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SemanticKind = Literal["fields", "records", "comparison", "mixed", "unknown"]


@dataclass(frozen=True, slots=True, order=True)
class CellRef:
    table_id: str
    row: int
    column: int

    @property
    def token(self) -> str:
        return f"{self.table_id}.r{self.row}c{self.column}"


@dataclass(frozen=True, slots=True)
class TextRef:
    """A literal native text slice and its independently bounded table scope."""

    table_id: str
    page: int
    block_id: str
    text: str
    kind: Literal["unit", "period", "note", "title", "group"]
    start: int
    end: int
    body_rows: tuple[int, ...]
    columns: tuple[int, ...]

    @property
    def token(self) -> str:
        return f"{self.table_id}.text.{self.block_id}.{self.start}:{self.end}"

    @property
    def source_cell(self) -> CellRef | None:
        """Cell-backed slices share an anchor, never a whole-cell literal."""
        parts = self.block_id.split(".")
        if len(parts) == 3 and parts[0] == "cell" and all(p.isdecimal() for p in parts[1:]):
            return CellRef(self.table_id, int(parts[1]), int(parts[2]))
        return None


@dataclass(frozen=True, slots=True)
class ValueRelation:
    """Explicit cell bindings; an empty literal makes no source-blank claim."""

    value: CellRef
    row_headers: tuple[CellRef | TextRef, ...] = ()
    column_headers: tuple[CellRef, ...] = ()
    unit_refs: tuple[CellRef | TextRef, ...] = ()
    period_refs: tuple[CellRef | TextRef, ...] = ()
    note_refs: tuple[CellRef | TextRef, ...] = ()
    value_state: Literal["literal", "source_blank"] = "literal"


@dataclass(frozen=True, slots=True)
class SemanticRecord:
    source_table_id: str
    source_row: int
    values: tuple[ValueRelation, ...]
    subject: CellRef | None = None
    subject_headers: tuple[CellRef, ...] = ()
    row_groups: tuple[CellRef | TextRef, ...] = ()
    scope_refs: tuple[TextRef, ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticTableView:
    view_id: str
    source_tables: tuple[str, ...]
    status: Literal["converted", "partial", "retained"]
    kind: SemanticKind
    records: tuple[SemanticRecord, ...] = ()
    reason_codes: tuple[str, ...] = ()
    source_cell_count: int = 0
    covered_source_cells: int = 0
    policy: str = "source-scoped-relations"
    retained_cells: tuple[CellRef, ...] = ()
    retained_rows: tuple[tuple[str, int], ...] = ()
    row_issues: tuple[tuple[str, int, str], ...] = ()
    rendering: Literal["record_lines", "nested_lists"] = "record_lines"
