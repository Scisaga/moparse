"""Read official MinerU native TXT exports without repairing their content.

The default Markdown, public FULL Markdown and raw model JSON are independent
views. GFM tokens are decoded into an in-memory grid; no model results, spans,
source comments, typography or malformed HTML attributes are rewritten.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path

from markdown_it import MarkdownIt

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


shared = load("native_source_shared", "evaluate-mineru-source.py")
extra = load("native_source_extra", "evaluate-docling-component.py")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_blocks(data, filename):
    blocks = []

    def inline(value):
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "".join(inline(item.get("content")) for item in value if isinstance(item, dict))
        return ""

    for page_index, page in enumerate(data["pages"]):
        for block_index, block in enumerate(page):
            blocks.append(
                {
                    "type": block.get("type"),
                    "bbox": block.get("bbox"),
                    "angle": block.get("angle"),
                    "content": inline(block.get("content")),
                    "raw_pointer": f"{filename}#/pages/{page_index}/{block_index}/content",
                }
            )
    tables, errors = shared.read_tables(blocks)
    for table in tables:
        table["raw_pointer"] = blocks[table["block_index"]]["raw_pointer"]
    return blocks, tables, errors


def markdown_tables(content, filename):
    """Read actual HTML tables and explicit GFM cells; never infer a span."""
    parser = MarkdownIt("commonmark", {"html": True}).enable("table")
    tokens = parser.parse(content)
    tables, errors = [], []
    current, start_line = None, None
    for token in tokens:
        if token.type == "html_block" and "<table" in token.content.lower():
            parsed, local_errors = shared.read_tables([{"content": token.content}])
            for table in parsed:
                table["raw_pointer"] = f"{filename}#line-{token.map[0] + 1}/HTML-table"
            tables.extend(parsed)
            errors.extend(local_errors)
        elif token.type == "table_open":
            current, start_line = ["<table>"], token.map[0] + 1
        elif current is not None:
            if token.type in {"thead_open", "thead_close", "tbody_open", "tbody_close"}:
                continue
            if token.type == "inline":
                current.append(parser.renderer.renderInline(token.children, parser.options, {}))
            elif token.type in {
                "tr_open",
                "tr_close",
                "td_open",
                "td_close",
                "th_open",
                "th_close",
            }:
                current.append(f"<{('/' if token.nesting == -1 else '')}{token.tag}>")
            elif token.type == "table_close":
                current.append("</table>")
                parsed, local_errors = shared.read_tables([{"content": "".join(current)}])
                for table in parsed:
                    table["raw_pointer"] = f"{filename}#line-{start_line}/GFM-table"
                tables.extend(parsed)
                errors.extend(local_errors)
                current = None
    for index, table in enumerate(tables):
        table["table_index"] = index
    return tables, errors


def evaluate_view(stem, page, blocks, tables, errors, reference, old_reference, termination):
    checks = shared.model_checks(stem, page, blocks, tables, reference, old_reference)
    for check in checks:
        check["status"] = (
            "pass"
            if check["observed_pass"]
            else "unknown"
            if errors
            or termination["status"] not in {"all_calls_server_stop", "native_no_VLM_calls"}
            else "fail"
        )
        if check["status"] == "unknown":
            check["qualification"] = (
                "Actual emitted output differs; malformed HTML or termination requires diagnosis before a model-capability conclusion. No attribute repair was applied."
            )
    return {
        "checks": checks,
        "counts": {
            status: sum(c["status"] == status for c in checks)
            for status in ["pass", "fail", "unknown"]
        },
        "table_shapes": [[t["num_rows"], t["num_cols"]] for t in tables],
        "HTML_reader_errors": errors,
        "_segments": [b.get("content") or "" for b in blocks],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite evaluation evidence")
    manifest = json.loads((args.run / "run-manifest.json").read_text())
    reference = json.loads((HERE / "source-reference.json").read_text())
    old_reference = json.loads(shared.BASELINE_REFERENCE.read_text())
    result = {
        "schema": "mosaicparse-official-native-source-evaluation/1",
        "created_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "evaluator_SHA256": sha(Path(__file__)),
        "shared_model_reader_SHA256": sha(HERE / "evaluate-mineru-source.py"),
        "shared_extra_checker_SHA256": sha(HERE / "evaluate-docling-component.py"),
        "reference_SHA256": sha(HERE / "source-reference.json"),
        "prior_independent_reference_SHA256": sha(shared.BASELINE_REFERENCE),
        "run_manifest": str(args.run / "run-manifest.json"),
        "run_manifest_SHA256": sha(args.run / "run-manifest.json"),
        "scope": "Original fourteen source pages; three actual output views scored separately. Additional p62 excluded; no MosaicParse public API provenance or full-document HTTP claim.",
        "main_comparison_view": "FULL",
        "views": {key: {"pages": []} for key in ["FULL", "DEFAULT", "raw_model_JSON"]},
    }
    for item in manifest["cases"]:
        if item.get("cohort") != "original_14" or item.get("status") != "completed":
            continue
        page_dir = args.run / f"{item['id']}-p{item['page']}"
        request = json.loads((page_dir / "request.json").read_text())
        expected_sha = reference["source_documents"].get(item["id"], {}).get("sha256")
        if expected_sha is None:
            expected_sha = next(
                s["SHA256"]
                for s in old_reference["source_documents"]
                if Path(s["path"]).stem == item["id"]
            )
        if request["source_pdf_SHA256"] != expected_sha:
            raise ValueError(f"Original PDF identity differs: {page_dir}")
        termination = (
            shared.assess_generation(page_dir)
            if item["model_HTTP_calls"]
            else {
                "status": "native_no_VLM_calls",
                "calls": [],
                "reason": "Official native TXT path; no chat generation invoked.",
            }
        )
        for view, filename in [
            ("FULL", "result-full.md"),
            ("DEFAULT", "result.md"),
            ("raw_model_JSON", "official-saved/model_output.json"),
        ]:
            path = page_dir / filename
            if view == "raw_model_JSON":
                blocks, tables, errors = raw_blocks(json.loads(path.read_text()), path)
            else:
                text = path.read_text()
                tables, errors = markdown_tables(text, path)
                blocks = [
                    {
                        "content": shared.source_verifier.visible_markdown(text),
                        "raw_pointer": f"{path}#rendered-visible-body",
                    }
                ]
            page = evaluate_view(
                item["id"],
                item["page"],
                blocks,
                tables,
                errors,
                reference,
                old_reference,
                termination,
            )
            page.update(
                source=item["id"],
                source_page=item["page"],
                source_SHA256=expected_sha,
                actual_output=str(path),
                actual_output_SHA256=sha(path),
                generation_integrity=termination,
                public_interface_source_mapping={
                    "status": "unknown",
                    "reason": "Source input page lineage only; MosaicParse table-source and cross-page assembly not integrated.",
                },
            )
            result["views"][view]["pages"].append(page)
    for view in result["views"].values():
        view["additional_four_source_observations"] = extra.extra_checks(view["pages"])
        view["fixed_condition_counts"] = {
            status: sum(p["counts"][status] for p in view["pages"])
            for status in ["pass", "fail", "unknown"]
        }
        view["additional_observation_counts"] = {
            status: sum(c["status"] == status for c in view["additional_four_source_observations"])
            for status in ["pass", "fail", "unknown"]
        }
        for page in view["pages"]:
            text = "\n".join(page.pop("_segments"))
            private_chars = sorted({f"U+{ord(c):04X}" for c in text if 0xE000 <= ord(c) <= 0xF8FF})
            page["private_use_character_display"] = {
                "codepoints": private_chars,
                "ordinary_Markdown_font_readability": "unknown"
                if private_chars
                else "no PUA characters observed",
                "reason": "Matching source private-use characters does not carry the original PDF font into ordinary Markdown.",
            }
    args.output.parent.mkdir(exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: {
                    "pages": len(value["pages"]),
                    "fixed": value["fixed_condition_counts"],
                    "extra": value["additional_observation_counts"],
                }
                for key, value in result["views"].items()
            }
        )
    )


if __name__ == "__main__":
    main()
