"""Validate observed GLM table geometry without rewriting recognized content."""

from __future__ import annotations

from app.models.parse_result import PipelineWarning
from app.services.table_service import TableFragment


class GlmTableService:
    """Report inconsistent source geometry; never infer missing text or periods."""

    @staticmethod
    def validate_fragments(fragments: list[TableFragment]) -> list[PipelineWarning]:
        warnings: list[PipelineWarning] = []
        for fragment in fragments:
            reasons = list(fragment.invalid_reasons)
            shape_valid = (
                fragment.num_rows > 0
                and fragment.num_cols > 0
                and len(fragment.rows) == fragment.num_rows
                and all(len(row) == fragment.num_cols for row in fragment.rows)
            )
            if not shape_valid:
                reasons.append("table_shape_inconsistent")
            occupied: set[tuple[int, int]] = set()
            for cell in fragment.cells:
                if (
                    cell.row < 0
                    or cell.column < 0
                    or cell.row_span < 1
                    or cell.column_span < 1
                    or cell.row + cell.row_span > fragment.num_rows
                    or cell.column + cell.column_span > fragment.num_cols
                ):
                    reasons.append("table_cell_out_of_bounds")
                    continue
                if (
                    shape_valid
                    and cell.text.strip() != fragment.rows[cell.row][cell.column].strip()
                ):
                    reasons.append("table_cell_anchor_content_conflict")
                positions = {
                    (row, column)
                    for row in range(cell.row, cell.row + cell.row_span)
                    for column in range(cell.column, cell.column + cell.column_span)
                }
                if occupied & positions:
                    reasons.append("table_cell_span_overlap")
                occupied.update(positions)
                if shape_valid and any(
                    fragment.rows[row][column].strip()
                    for row, column in positions - {(cell.row, cell.column)}
                ):
                    reasons.append("table_cell_span_hides_content")
            if reasons or not fragment.valid:
                fragment.valid = False
                fragment.invalid_reasons = list(dict.fromkeys(reasons)) or ["source_table_invalid"]
                warnings.append(
                    PipelineWarning(
                        code="table_structure_invalid",
                        message="GLM table geometry is inconsistent; recognized source content was retained",
                        page_number=fragment.page_number,
                        backend="glm-ocr-sdk",
                        details={
                            "table_id": fragment.fragment_id,
                            "reasons": list(dict.fromkeys(reasons)) or ["source_table_invalid"],
                        },
                    )
                )
        return warnings
