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
class ValueRelation:
    value: CellRef
    row_headers: tuple[CellRef, ...] = ()
    column_headers: tuple[CellRef, ...] = ()
    unit_refs: tuple[CellRef, ...] = ()
    period_refs: tuple[CellRef, ...] = ()
    note_refs: tuple[CellRef, ...] = ()
    value_state: Literal["literal", "source_blank"] = "literal"


@dataclass(frozen=True, slots=True)
class SemanticRecord:
    source_table_id: str
    source_row: int
    values: tuple[ValueRelation, ...]
    subject: CellRef | None = None
    subject_headers: tuple[CellRef, ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticTableView:
    view_id: str
    source_tables: tuple[str, ...]
    status: Literal["converted", "retained"]
    kind: SemanticKind
    records: tuple[SemanticRecord, ...] = ()
    reason_codes: tuple[str, ...] = ()
    source_cell_count: int = 0
    covered_source_cells: int = 0
    policy: str = "source-scoped-relations"
