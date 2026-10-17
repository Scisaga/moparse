"""Diagnostic visible-native-span coverage on independently reviewed PDF pages.

Coverage is not reading-order, row/column binding, or semantic accuracy. Pure
numeric spans require token boundaries, so 6,606.571 cannot cover 6,606.57.
Checkbox state is compared with its preceding printed context, independently
of text presence. No model output, source, or historical gold is changed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
spec = importlib.util.spec_from_file_location(
    "mineru_evaluator", HERE / "evaluate-mineru-source.py"
)
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(text):
    # Interpret only visible representation, without altering inferred content.
    # Preserve physical HTML cell boundaries before compacting whitespace;
    # otherwise adjacent exact numbers would falsely look like one token.
    text = re.sub(r"</(?:td|th)\s*>", " ⟦CELL⟧ ", text or "", flags=re.I)
    text = evaluator.visible(text)
    for old, new in [
        (r"\(", ""),
        (r"\)", ""),
        (r"\%", "%"),
        ("☑", "⟦CHECKED⟧"),
        ("✓", "⟦CHECKED⟧"),
        ("☒", "⟦CHECKED⟧"),
        ("\uf052", "⟦CHECKED⟧"),
        ("□", "⟦EMPTY⟧"),
        ("☐", "⟦EMPTY⟧"),
    ]:
        text = text.replace(old, new)
    return evaluator.prose(text)


def covered(source, output):
    wanted = canonical(source)
    if re.fullmatch(r"[-+]?\d[\d,]*(?:\.\d+)?%?", wanted):
        return bool(re.search(r"(?<![\d,.%+-])" + re.escape(wanted) + r"(?![\d,.%])", output))
    return wanted in output.replace("⟦CELL⟧", "")


def choice_states(text):
    return re.findall(r"⟦(CHECKED|EMPTY)⟧", text)


def source_spans(page):
    spans, lines = [], []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"])
            if text.strip():
                lines.append({"text": text, "bbox": list(line["bbox"])})
            spans.extend(
                {"text": s["text"], "bbox": list(s["bbox"]), "font": s["font"], "size": s["size"]}
                for s in line["spans"]
                if s["text"].strip()
            )
    lines.sort(key=lambda line: (round(line["bbox"][1], 1), line["bbox"][0]))
    return spans, lines


def audit(stem, page_no, source_pdf, output_segments, origin):
    page = pymupdf.open(source_pdf)[page_no - 1]
    spans, lines = source_spans(page)
    output = canonical("\n".join(output_segments))
    matched = [span for span in spans if covered(span["text"], output)]
    unmatched = [span for span in spans if not covered(span["text"], output)]
    states = []
    normalized_segments = [canonical(segment) for segment in output_segments]
    for i, line in enumerate(lines):
        expected = choice_states(canonical(line["text"]))
        if len(expected) < 2:
            continue
        context = lines[i - 1] if i else None
        context_text = canonical(context["text"]) if context else ""
        candidates = []
        for index, segment in enumerate(normalized_segments):
            position = segment.find(context_text) if context_text else -1
            if position < 0:
                continue
            tail = segment[position + len(context_text) :] + "".join(
                normalized_segments[index + 1 : index + 4]
            )
            observed = choice_states(tail)[: len(expected)]
            if observed:
                candidates.append({"segment_index": index, "observed_states": observed})
        status = (
            "pass"
            if any(c["observed_states"] == expected for c in candidates)
            else "fail"
            if candidates
            else "unknown_context_not_found"
        )
        states.append(
            {
                "source_context": context,
                "source_choice_line": line,
                "expected_states": expected,
                "status": status,
                "candidates": candidates,
            }
        )
    return {
        "source": stem,
        "source_page": page_no,
        "source_PDF": str(source_pdf),
        "source_SHA256": sha(source_pdf.read_bytes()),
        "origin": origin,
        "nonempty_native_spans": len(spans),
        "covered_native_spans": len(matched),
        "unmatched_source_spans_requiring_review": unmatched,
        "choice_state_context_checks": states,
        "scope": "Diagnostic source-span coverage only; not whole-page or whole-document semantic accuracy. Exact numeric and source-context choice-state checks are separate from prose typography.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-run", type=Path, action="append", default=[])
    parser.add_argument(
        "--public-case",
        action="append",
        default=[],
        help="STEM=PATH; uses existing public source-page comments without inventing them",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite diagnostic evidence")
    reference = json.loads((HERE / "source-reference.json").read_text())
    out = {
        "schema": "mosaicparse-reviewed-source-visible-span-diagnostic/1",
        "created_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "audit_script_SHA256": sha(Path(__file__).read_bytes()),
        "source_reference_SHA256": sha((HERE / "source-reference.json").read_bytes()),
        "source_reference_modified": False,
        "source_text_is_never_inserted_in_results": True,
        "pages": [],
    }
    for run in args.model_run:
        for page_dir in sorted(run.glob("*-p*")):
            request_path, blocks_path = page_dir / "request.json", page_dir / "official-blocks.json"
            if not request_path.exists() or not blocks_path.exists():
                continue
            request, blocks = (
                json.loads(request_path.read_text()),
                json.loads(blocks_path.read_text()),
            )
            source = Path(request["source_pdf"])
            if sha(source.read_bytes()) != request["source_pdf_SHA256"]:
                raise ValueError(f"Source identity mismatch: {source}")
            segments = [block["content"] for block in blocks if block.get("content")]
            out["pages"].append(
                audit(
                    request["id"],
                    request["page"],
                    source,
                    segments,
                    {
                        "type": "official_model_blocks",
                        "path": str(blocks_path),
                        "SHA256": sha(blocks_path.read_bytes()),
                    },
                )
            )
    for assignment in args.public_case:
        stem, path = assignment.split("=", 1)
        source_spec = reference["source_documents"][stem]
        source = REPO / source_spec["path"]
        if sha(source.read_bytes()) != source_spec["sha256"]:
            raise ValueError(f"Source identity mismatch: {source}")
        content = Path(path).read_text()
        page_map = evaluator.source_verifier.pages(content)
        for page_no in source_spec["inspected_pages"]:
            if page_no not in page_map:
                continue
            segments = page_map[page_no].split("\n\n")
            out["pages"].append(
                audit(
                    stem,
                    page_no,
                    source,
                    segments,
                    {
                        "type": "captured_public_markdown",
                        "path": path,
                        "SHA256": sha(Path(path).read_bytes()),
                    },
                )
            )
    out["page_count"] = len(out["pages"])
    out["diagnostic_unmatched_span_count"] = sum(
        len(page["unmatched_source_spans_requiring_review"]) for page in out["pages"]
    )
    out["choice_context_status_counts"] = {
        status: sum(
            c["status"] == status
            for page in out["pages"]
            for c in page["choice_state_context_checks"]
        )
        for status in ["pass", "fail", "unknown_context_not_found"]
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "pages": out["page_count"],
                "unmatched_native_spans_for_review": out["diagnostic_unmatched_span_count"],
                "choice_context_status_counts": out["choice_context_status_counts"],
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
