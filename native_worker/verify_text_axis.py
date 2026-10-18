"""CPU-only source regression of the pinned character-matching patch.

Replays the actual source PDFs and observed model span geometry. It runs no OCR,
VLM requests or output text replacements, and never edits an installed package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path

from native_worker.patch_dependency import ORIGINAL_SHA256, PATCHED_SHA256, source_path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project(box, angle):
    cosine, sine = math.cos(angle), math.sin(angle)
    points = [
        (x * cosine - y * sine, x * sine + y * cosine)
        for x in (box[0], box[2])
        for y in (box[1], box[3])
    ]
    return (
        min(p[0] for p in points),
        min(p[1] for p in points),
        max(p[0] for p in points),
        max(p[1] for p in points),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    original_path = source_path()
    original = original_path.read_text()
    if digest(original_path) != ORIGINAL_SHA256:
        raise SystemExit("This verifier compares against the unchanged supported upstream source")
    with tempfile.TemporaryDirectory(prefix="moparse-axis-verify-") as directory:
        root = Path(directory)
        destination = root / "mineru/backend/analysis/pdf/text/native.py"
        destination.parent.mkdir(parents=True)
        destination.write_text(original)
        patch = Path(__file__).parent / "patches/mineru-4.0.12-text-axis.patch"
        subprocess.run(
            ["patch", "--batch", "--fuzz=0", "-p1", "-d", str(root), "-i", str(patch.resolve())],
            check=True,
            capture_output=True,
        )
        assert digest(destination) == PATCHED_SHA256
        namespace = {
            "__name__": "mineru.backend.analysis.pdf.text.native_axis_reference",
            "__package__": "mineru.backend.analysis.pdf.text",
        }
        exec(compile(destination.read_text(), str(destination), "exec"), namespace)

    import mineru.backend.analysis.pdf.text.native as upstream
    from docvortex.document.pdf import PDFDocument, PDFPage
    from mineru.backend.analysis.pdf.text.models import _AnalyzeSpan
    from mineru.types import BlockType
    from PIL import Image

    synthetic = []
    for degrees in range(0, 360, 45):
        angle = math.radians(degrees)
        span = project((100.0, 100.0, 300.0, 112.0), angle)
        left, right = [
            project(box, angle)
            for box in ((101.0, 101.0, 110.0, 111.0), (290.0, 101.0, 299.0, 111.0))
        ]
        outside = project((150.0, 170.0, 160.0, 180.0), angle)
        assert namespace["calculate_char_in_span"](left, span, "A", writing_angle=angle)
        assert namespace["calculate_char_in_span"](right, span, "Z", writing_angle=angle)
        assert not namespace["calculate_char_in_span"](outside, span, "X", writing_angle=angle)
        synthetic.append(
            {"writing_degrees": degrees, "both_ends_retained": True, "outside_line_rejected": True}
        )

    base = (
        args.repo
        / "benchmark-results/clean-model-comparison-20261015/followup/20261017/content-preservation-mineru/mineru-trial"
    )
    plans = json.loads((base / "first-pages.json").read_text()) + json.loads(
        (base / "remaining-pages.json").read_text()
    )
    plans.append({"id": "1225475375", "page": 62})
    rows = []
    for plan in plans:
        folder = base / "official-native-advanced" / f"{plan['id']}-p{plan['page']}"
        events = json.loads((folder / "official-stage-observations.json").read_text())
        event = next(item for item in events if item["stage"] == "native_PDF_text_fill")
        page_path = folder / "prepared-by-official-page-selection.pdf"
        result = {
            "id": plan["id"],
            "source_page": plan["page"],
            "selected_pdf_sha256": digest(page_path),
            "cohort": "additional_p62" if plan["page"] == 62 else "original_14",
        }
        with PDFDocument(str(page_path)) as pdf:
            page = PDFPage(pdf, 0)
            width, height = pdf.page_size(0)
            geometry = pdf.get_page_chars_with_geometry(0)
            source_chars = geometry.chars
            native_snapshot = page.get_text_snapshot()
            fill_kwargs = {
                "page_chars": source_chars,
                "tight_bboxes": geometry.tight_bboxes,
                "origins": geometry.origins,
                "_native_text": native_snapshot,
            }
            result["native_snapshot_available"] = native_snapshot is not None
            result["nonhorizontal_source_characters"] = sum(
                abs(math.sin(float(char.get("writing_angle", 0)))) > 1e-6
                or math.cos(float(char.get("writing_angle", 0))) < 0
                for char in source_chars
            )
            outputs = {}
            for label, function in (
                ("upstream", upstream.txt_spans_extract),
                ("patched", namespace["txt_spans_extract"]),
            ):
                spans = [_AnalyzeSpan(item["type"], tuple(item["bbox"])) for item in event["spans"]]
                started = time.perf_counter()
                filled = function(
                    page,
                    spans,
                    Image.new("RGB", (int(width), int(height))),
                    1,
                    [(0, 0, width, height, None, None, None, BlockType.TEXT)],
                    [],
                    detect_scripts=False,
                    **fill_kwargs,
                )
                result[label + "_seconds"] = time.perf_counter() - started
                outputs[label] = {tuple(span.bbox): span.content for span in filled}
            changes = []
            for box, previous in outputs["upstream"].items():
                current = outputs["patched"].get(box, "")
                assert not (
                    Counter(previous.replace(" ", "")) - Counter(current.replace(" ", ""))
                ), (plan, previous, current)
                if previous != current:
                    changes.append({"bbox": box, "before": previous, "after": current})
            result["changed_spans"] = changes
            result["existing_source_characters_lost"] = 0
            if plan["id"] == "1225475375" and plan["page"] == 87:
                values = list(outputs["patched"].values())
                # Original rendered PDF was inspected; these are test ground truth,
                # not a phrase used by the production matcher or model prompt.
                assert "—其他债权投资公允价值变动源于应收款项融资。" in values
                assert "（三十四）其他综合收益" in values
                # Changing other spans must no longer alter this span's text.
                spans = [_AnalyzeSpan(item["type"], tuple(item["bbox"])) for item in event["spans"]]
                spans.extend(
                    [_AnalyzeSpan("text", (0, 0, 1, 1)), _AnalyzeSpan("text", (0, 0, 1, 1))]
                )
                filled = namespace["txt_spans_extract"](
                    page,
                    spans,
                    Image.new("RGB", (int(width), int(height))),
                    1,
                    [(0, 0, width, height, None, None, None, BlockType.TEXT)],
                    [],
                    detect_scripts=False,
                    **fill_kwargs,
                )
                assert "—其他债权投资公允价值变动源于应收款项融资。" in [
                    span.content for span in filled
                ]
                result["independent_of_other_spans_height"] = True
        rows.append(result)
    evidence = {
        "schema": "native-text-matching-axis-verification/1",
        "GPU_requests": 0,
        "input_boundary": "Original PDF characters plus unchanged captured VLM span geometry; no output overwrite",
        "upstream_native_sha256": ORIGINAL_SHA256,
        "patched_native_sha256": PATCHED_SHA256,
        "patch_sha256": digest(Path(__file__).parent / "patches/mineru-4.0.12-text-axis.patch"),
        "angles": synthetic,
        "cases": rows,
        "original14_existing_source_characters_lost": 0,
        "p87_footnote_original_characters": 22,
        "p87_footnote_recovered_characters": 22,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "native-axis-source-replay.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "cases": len(rows),
                "angles": len(synthetic),
                "existing_source_characters_lost": 0,
                "changed_spans": [
                    dict(id=row["id"], page=row["source_page"], changes=row["changed_spans"])
                    for row in rows
                    if row["changed_spans"]
                ],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
