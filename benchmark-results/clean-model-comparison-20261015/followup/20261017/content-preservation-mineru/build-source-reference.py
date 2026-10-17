"""Build independent test evidence from original PDF bytes only; no model IO read.

Rectangles below are physical grid/text regions reviewed in rendered originals.
They select source evidence and are never used by the MosaicParse application.
No absent model text is inserted into a parser result or a historical gold file.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
SOURCE_SPECS = {
    "1225474739": {
        "path": "pdf_sample/1225474739.pdf",
        "sha256": "1c99c450a8efefe77c9ca02a6f670c958298f661e5ad8d30d6ba01aa0742cda9",
        "pages": 134,
        "inspected_pages": [19, 40, 74, 130, 131],
    },
    "1225475375": {
        "path": "pdf_sample/1225475375.pdf",
        "sha256": "5eef30b5c544d76df917d56df76a665ed13b5e6ffebdc54ab0eea0a47b7589d6",
        "pages": 119,
        "inspected_pages": [74, 87],
    },
    "1225474139": {
        "path": "pdf_sample/1225474139.pdf",
        "sha256": "dc69826976c576302ee4156642039b790693202a611922dda647eb006e6d5c18",
        "pages": 36,
        "inspected_pages": [28, 30],
    },
    "1206337604": {
        "path": str(HERE.relative_to(REPO) / "sources/1206337604/source-converted.pdf"),
        "sha256": "ccff40771d75e9412b65f364a1c72c1733c37b4d8f232f49cf639621f0ba165f",
        "pages": 2,
        "inspected_pages": [1, 2],
    },
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def compact(text):
    return re.sub(r"\s+", "", text)


def source_region(page, bbox):
    region = pymupdf.Rect(bbox)
    lines = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            spans = []
            for span in line["spans"]:
                chars = [
                    char
                    for char in span["chars"]
                    if region.contains(
                        pymupdf.Point(
                            (char["bbox"][0] + char["bbox"][2]) / 2,
                            (char["bbox"][1] + char["bbox"][3]) / 2,
                        )
                    )
                ]
                if chars:
                    spans.append(
                        {
                            "text": "".join(c["c"] for c in chars),
                            "size": span["size"],
                            "color": span["color"],
                            "font": span["font"],
                            "origin": list(chars[0]["origin"]),
                            "chars": chars,
                        }
                    )
            if spans:
                lines.append(
                    {
                        "bbox": list(line["bbox"]),
                        "dir": list(line["dir"]),
                        "spans": spans,
                        "text": "".join(s["text"] for s in spans),
                    }
                )
    lines.sort(key=lambda line: (round(line["bbox"][1], 1), line["bbox"][0]))
    return {
        "bbox": list(bbox),
        "text": "\n".join(line["text"] for line in lines),
        "source_lines": lines,
    }


def grid(page, xs, ys):
    return [
        [
            source_region(page, [xs[c] + 0.2, ys[r] + 0.2, xs[c + 1] - 0.2, ys[r + 1] - 0.2])[
                "text"
            ]
            for c in range(len(xs) - 1)
        ]
        for r in range(len(ys) - 1)
    ]


def build(output):
    if output.exists():
        raise ValueError(f"Refusing to overwrite independent source evidence: {output}")
    documents, opened = {}, {}
    for stem, spec in SOURCE_SPECS.items():
        path = REPO / spec["path"]
        data = path.read_bytes()
        if sha(data) != spec["sha256"]:
            raise ValueError(f"Input bytes differ: {path}")
        doc = pymupdf.open(path)
        if len(doc) != spec["pages"]:
            raise ValueError(f"Page count differs: {path}")
        opened[stem] = doc
        documents[stem] = {
            **spec,
            "bytes": len(data),
            "page_rotation": {str(n): doc[n - 1].rotation for n in spec["inspected_pages"]},
        }
    a, b, c, office = (opened[s] for s in ["1225474739", "1225475375", "1225474139", "1206337604"])
    p19 = a[18]
    long_risk = source_region(p19, [179.4, 484.9, 533.0, 772.8])
    amount = source_region(p19, [426.4, 335.3, 479.5, 347.2])
    amount_spans = [
        span for line in amount["source_lines"] for span in line["spans"] if span["text"].strip()
    ]
    normal_amount = "".join(s["text"] for s in amount_spans if s["size"] > 8)
    footnote = "".join(s["text"] for s in amount_spans if s["size"] < 8)
    assert compact(normal_amount) == "6,606.57" and compact(footnote) == "1"
    p40 = a[39]
    accounts = source_region(p40, [149.0, 542.4, 533.0, 710.3])
    paragraphs = [m.group() for m in re.finditer(r"\d、.*?(?=\d、|$)", compact(accounts["text"]))]
    account_bindings = []
    for paragraph in paragraphs:
        match = re.fullmatch(
            r"(\d)、(.+?)通过(.+?)客户信用交易担保证券账户持有公司([\d,]+)股[，,]通过普通证券账户持有公司([\d,]+)股，共计持有公司([\d,]+)股。",
            paragraph,
        )
        if not match:
            raise ValueError(f"Unexpected original account paragraph: {paragraph}")
        account_bindings.append(
            {
                "number": int(match[1]),
                "person": match[2],
                "broker": match[3],
                "credit_shares": match[4],
                "ordinary_shares": match[5],
                "total_shares": match[6],
                "raw_source_paragraph": paragraph,
            }
        )
    assert len(account_bindings) == 7
    continuation_x = [51.24, 131.54, 217.01, 307.27, 386.38, 453.58, 533.28]
    continuation_y = [72.12, 84.38, 100.70]
    p87 = b[86]
    p87.set_rotation(0)  # The actual /Rotate=270 visually turns text sideways.
    table87 = p87.find_tables().tables[0]
    assert (table87.row_count, table87.col_count) == (10, 9)
    xs87 = sorted(
        set(round(cell[0], 2) for cell in table87.cells if cell)
        | set(round(cell[2], 2) for cell in table87.cells if cell)
    )
    ys87 = sorted(
        set(round(cell[1], 2) for cell in table87.cells if cell)
        | set(round(cell[3], 2) for cell in table87.cells if cell)
    )
    spans87 = []
    for row, row_object in enumerate(table87.rows):
        for column, rect in enumerate(row_object.cells):
            if rect:
                rowspan = min(range(len(ys87)), key=lambda i: abs(ys87[i] - rect[3])) - row
                colspan = min(range(len(xs87)), key=lambda i: abs(xs87[i] - rect[2])) - column
                if rowspan > 1 or colspan > 1:
                    spans87.append([row, column, rowspan, colspan])
    office_pages = {}
    for page in office:
        spans = []
        lines = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(s["text"] for s in line["spans"])
                if text.strip():
                    lines.append({"text": text, "bbox": list(line["bbox"])})
                spans.extend(
                    {"text": s["text"], "bbox": list(s["bbox"]), "size": s["size"]}
                    for s in line["spans"]
                    if s["text"].strip()
                )
        office_pages[str(page.number + 1)] = {"nonempty_native_spans": spans, "native_lines": lines}
    out = {
        "schema": "mosaicparse-independent-original-content-reference/1",
        "created_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "builder_SHA256": sha(Path(__file__).read_bytes()),
        "independence": {
            "source": "matching original PDF bytes only",
            "parser_output_read": False,
            "old_gold_modified": False,
            "scope": "Only explicitly inspected pages/regions; not a whole-document semantic gold",
        },
        "source_documents": documents,
        "1225474739": {
            "page19": {
                "risk_control_merged_cell": long_risk,
                "risk_label": source_region(p19, [51.4, 484.9, 179.0, 772.8]),
                "source_cell_colspan": 8,
                "base_column_count": 9,
                "amount_and_footnote_source": amount,
                "amount": compact(normal_amount),
                "footnote_reference": compact(footnote),
                "actual_profit_loss_cell": source_region(p19, [179.4, 416.1, 533.0, 452.0]),
            },
            "page40": {
                "financing_explanation_label": source_region(p40, [51.4, 542.4, 148.6, 710.3]),
                "financing_explanation_cell": accounts,
                "account_bindings": account_bindings,
                "independent_explanation_label": source_region(p40, [51.4, 478.0, 148.6, 542.0]),
                "independent_explanation_text": source_region(p40, [149.0, 478.0, 533.0, 542.0]),
                "source_horizontal_boundary_y": [477.91, 542.26, 710.52],
                "shareholder_rows_4cols": grid(
                    p40,
                    [51.24, 148.82, 357.62, 432.34, 533.28],
                    [
                        355.37,
                        367.73,
                        379.99,
                        392.23,
                        404.47,
                        416.71,
                        428.95,
                        441.19,
                        453.43,
                        465.67,
                        477.91,
                    ],
                ),
                "top_chenqingliang_9cols": grid(
                    p40,
                    [51.24, 92.064, 148.82, 182.69, 241.01, 294.07, 360.43, 432.34, 482.04, 533.28],
                    [84.38, 96.62],
                )[0],
            },
            "page74": {
                "policy_heading": source_region(a[73], [51, 625, 540, 640]),
                "policy_sentence": source_region(a[73], [51, 641, 540, 657]),
                "all_source_sorted_text": a[73].get_text(sort=True),
            },
            "page130_131": {
                "column_count": 6,
                "column_boundaries_x": continuation_x,
                "page131_rows_raw": grid(a[130], continuation_x, continuation_y),
                "page130_table_bbox": [51.24, 617.0, 533.28, 778.8],
                "page130_header_source": source_region(a[129], [51.4, 617.0, 533.0, 658.0]),
            },
        },
        "1225475375": {
            "page74": {
                "negative_business_conclusion": source_region(b[73], [45, 695, 555, 715]),
                "all_source_sorted_text": b[73].get_text(sort=True),
            },
            "page87": {
                "source_rotation": 270,
                "reference_rotation": 0,
                "rows_raw": table87.extract(),
                "grid_rows": 10,
                "grid_columns": 9,
                "spans": spans87,
                "header_rows": [0, 1],
                "current_period_group_anchor": [0, 2, 1, 6],
                "source_bbox_upright": list(table87.bbox),
                "footnote": source_region(p87, [65, 389, 785, 420]),
            },
        },
        "1225474139": {
            "page28": {"ordered_paragraph": source_region(c[27], [60, 110, 540, 156])},
            "page30": {
                "blank_date": source_region(c[29], [370, 425, 545, 445]),
                "all_source_sorted_text": c[29].get_text(sort=True),
            },
        },
        "1206337604": {
            "pages": office_pages,
            "identity_line": source_region(office[0], [70, 65, 530, 95]),
            "title": source_region(office[0], [150, 129, 530, 155]),
            "record_date": source_region(office[1], [150, 710, 530, 733]),
            "fragment_policy": "Independently extracted 117 native spans and 65 lines; Eventrail original 71-fragment segmentation was not supplied and is not falsely reproduced.",
        },
    }
    output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "reference": str(output),
                "SHA256": sha(output.read_bytes()),
                "source_documents": len(documents),
                "Office_native_spans": sum(
                    len(v["nonempty_native_spans"]) for v in office_pages.values()
                ),
                "p87_spans": spans87,
                "p131_total_row": out["1225474739"]["page130_131"]["page131_rows_raw"][1],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "source-reference.json")
    build(parser.parse_args().output)
