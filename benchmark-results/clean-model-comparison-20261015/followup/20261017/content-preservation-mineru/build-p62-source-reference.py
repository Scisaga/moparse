"""Independent additional p62 source grid; separate from the fixed 14-page set."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
PDF = REPO / "pdf_sample/1225475375.pdf"
EXPECTED_SHA = "5eef30b5c544d76df917d56df76a665ed13b5e6ffebdc54ab0eea0a47b7589d6"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    output = HERE / "source-reference-p62.json"
    if output.exists():
        raise ValueError("Refusing to overwrite independent source evidence")
    if sha(PDF) != EXPECTED_SHA:
        raise ValueError("Original PDF bytes differ")
    doc = pymupdf.open(PDF)
    page = doc[61]
    evidence_dir = HERE / "source-reference-p62"
    evidence_dir.mkdir(exist_ok=True)
    original = evidence_dir / "original-page-rotation.png"
    page.get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6), alpha=False).save(original)
    original_rotation = page.rotation
    page.set_rotation(0)
    upright = evidence_dir / "upright.png"
    page.get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6), alpha=False).save(upright)
    candidates = [t for t in page.find_tables().tables if (t.row_count, t.col_count) == (9, 11)]
    if len(candidates) != 1:
        raise ValueError("The reviewed original vector grid is not uniquely 9x11")
    table = candidates[0]
    crop = evidence_dir / "original-table.png"
    page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=pymupdf.Rect(table.bbox), alpha=False).save(
        crop
    )
    xs = sorted({round(c[0], 2) for c in table.cells} | {round(c[2], 2) for c in table.cells})
    ys = sorted({round(c[1], 2) for c in table.cells} | {round(c[3], 2) for c in table.cells})
    physical = []
    for row, source_row in enumerate(table.rows):
        for column, bbox in enumerate(source_row.cells):
            if bbox:
                rowspan = min(range(len(ys)), key=lambda i: abs(ys[i] - bbox[3])) - row
                colspan = min(range(len(xs)), key=lambda i: abs(xs[i] - bbox[2])) - column
                physical.append(
                    {
                        "row_zero_based": row,
                        "column_zero_based": column,
                        "rowspan": rowspan,
                        "colspan": colspan,
                        "bbox_PDF_points_upright": list(bbox),
                        "text": table.extract()[row][column] or "",
                    }
                )
    rows = [[value or "" for value in row] for row in table.extract()]
    spans = [
        [c["row_zero_based"], c["column_zero_based"], c["rowspan"], c["colspan"]]
        for c in physical
        if c["rowspan"] > 1 or c["colspan"] > 1
    ]
    raw = page.get_text("rawdict")
    raw["blocks"] = [b for b in raw["blocks"] if b["type"] == 0]
    (evidence_dir / "source-native-characters.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2) + "\n"
    )
    result = {
        "schema": "mosaicparse-additional-original-p62-table-reference/1",
        "created_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "builder_SHA256": sha(Path(__file__)),
        "source_pdf": "pdf_sample/1225475375.pdf",
        "source_SHA256": EXPECTED_SHA,
        "source_total_pages": len(doc),
        "source_physical_page": 62,
        "printed_page": "55",
        "source_page_rotation": original_rotation,
        "source_review_rotation": 0,
        "independence": {
            "model_or_parser_output_read": False,
            "old_gold_or_main_reference_modified": False,
            "scope": "Extra p62-only original-PDF evidence, explicitly outside the fixed 14-page trial denominator.",
        },
        "source_title": page.get_text(sort=True).splitlines()[0].strip(),
        "grid_rows": 9,
        "grid_columns": 11,
        "header_rows_zero_based": [0, 1, 2],
        "body_rows_zero_based": [3, 4, 5, 6, 7, 8],
        "rows_raw": rows,
        "spans": spans,
        "physical_cells": physical,
        "table_bbox_upright": list(table.bbox),
        "column_boundaries_upright": xs,
        "row_boundaries_upright": ys,
        "source_positions": 99,
        "body_positions": 66,
        "body_nonempty_physical_anchors": sum(bool(v.strip()) for row in rows[3:] for v in row),
        "explicit_unit_on_this_page": None,
        "acceptance": "Require the actual eleven-column table, three-level header topology, all six source body rows with exact cell bindings and blanks. Picture/text character coverage alone cannot pass table restoration.",
        "source_evidence": [
            {"path": str(p.relative_to(HERE)), "SHA256": sha(p), "bytes": p.stat().st_size}
            for p in sorted(evidence_dir.iterdir())
            if p.is_file()
        ],
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "reference": str(output),
                "grid": [9, 11],
                "header_rows": 3,
                "body_rows": 6,
                "body_nonempty_cells": result["body_nonempty_physical_anchors"],
                "spans": spans,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
