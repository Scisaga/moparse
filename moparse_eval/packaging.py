"""Materialize an authored selection without interpreting or reviewing corpus content.

This module copies references verbatim. It does not select pages, extract text,
infer source mappings, verify hashes or return corpus acceptance judgments.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("operation path escapes its declared root")
    return path


def _document(
    item: str | dict[str, Any], selection: dict[str, Any], source_root: Path
) -> dict[str, Any]:
    declaration: dict[str, Any] = {"document_id": item} if isinstance(item, str) else dict(item)
    if "authoring_file" in declaration:
        declaration = read_json(inside(source_root, declaration["authoring_file"]))
    document_id = str(declaration["document_id"])
    declaration.setdefault(
        "source_pdf",
        str(selection.get("source_pdf_template", "pdf_sample/pdf/{document_id}.pdf")).format(
            document_id=document_id
        ),
    )
    declaration.setdefault(
        "reference_dir",
        str(
            selection.get(
                "reference_dir_template", "pdf_sample/parsing/expected/{document_id}"
            )
        ).format(document_id=document_id),
    )
    return declaration


def extract_declared_pages(source: Path, destination: Path, pages: list[int]) -> None:
    """Copy exactly the authored page sequence, retaining PDF page objects.

    Accessing the PDF is necessary materialization, not an automated review.
    No text, OCR, geometry heuristics or inferred page ranges are used.
    """
    import pymupdf

    destination.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(source) as original, pymupdf.open() as selected:
        for physical_page in pages:
            selected.insert_pdf(original, from_page=physical_page - 1, to_page=physical_page - 1)
        selected.save(destination)


def read_selection(path: Path, source_root: Path) -> dict[str, Any]:
    """Concatenate named author declarations; never discover or choose samples."""
    def entries(authored: dict[str, Any], section: str) -> list[Any]:
        base = authored.get("authoring_base")
        values = list(authored.get(section, []))
        if base is None:
            return values
        # This is a declared lexical base, never a filesystem search/fallback.
        return [
            {**value, "authoring_file": str(Path(base) / value["authoring_file"])}
            if isinstance(value, dict) and "authoring_file" in value else value
            for value in values
        ]

    selection = read_json(path)
    combined = {**selection, "documents": entries(selection, "documents"),
                "samples": entries(selection, "samples"),
                "suites": {name: list(items) for name, items in selection.get("suites", {}).items()}}
    for relative in selection.get("includes", []):
        authored = read_json(inside(source_root, relative))
        combined["documents"].extend(entries(authored, "documents"))
        combined["samples"].extend(entries(authored, "samples"))
        for name, items in authored.get("suites", {}).items():
            combined["suites"].setdefault(name, []).extend(items)
    return combined


def package_dataset(selection_path: Path, output: Path, *, source_root: Path) -> dict[str, Any]:
    """Execute an explicit authored selection; never claim its contents correct.

    A package is deliberately not overwritable: changing a frozen reference
    requires a separately named snapshot, not in-place scorer side effects.
    """
    selection = read_selection(selection_path, source_root)
    if output.exists():
        raise FileExistsError(f"package destination already exists: {output}")
    documents = [_document(item, selection, source_root) for item in selection["documents"]]
    document_by_id = {item["document_id"]: item for item in documents}
    output.mkdir(parents=True)
    packaged_documents: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    for document in documents:
        document_id = document["document_id"]
        reference_source = inside(source_root, document["reference_dir"])
        reference_destination = output / "references" / document_id
        shutil.copytree(reference_source, reference_destination)
        # Existing metadata is copied provenance, not an independent finding.
        source_metadata = read_json(reference_source / "manifest.json").get("source", {})
        packaged_documents.append(
            {
                "document_id": document_id,
                "reference_dir": f"references/{document_id}",
                "source_metadata": source_metadata,
                "family_id": document.get("family_id"),
                "tags": document.get("tags", []),
                "review_status": document.get("review_status", "historical_reference"),
                "review_record": document.get("review_record", selection.get("review_record")),
            }
        )
    if selection.get("kind") == "full":
        for document in documents:
            document_id = document["document_id"]
            destination = output / "inputs" / f"{document_id}.pdf"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(inside(source_root, document["source_pdf"]), destination)
            samples.append(
                {
                    "id": document_id,
                    "document_id": document_id,
                    "input": f"inputs/{document_id}.pdf",
                    "input_scope": "complete_original",
                    "reference_dir": f"references/{document_id}",
                    "family_id": document.get("family_id"),
                    "tags": document.get("tags", []),
                    "review_status": document.get("review_status", "historical_reference"),
                    "evaluation": None,
                }
            )
    else:
        for authored in selection["samples"]:
            # This is a supplied declaration, never inferred from a file count.
            sample = (
                read_json(inside(source_root, authored["authoring_file"]))
                if "authoring_file" in authored
                else dict(authored)
            )
            sample_id = sample["id"]
            document = document_by_id[sample["document_id"]]
            pages = list(sample["source_pages"])
            destination = output / "inputs" / f"{sample_id}.pdf"
            extract_declared_pages(inside(source_root, document["source_pdf"]), destination, pages)
            sample["input"] = f"inputs/{sample_id}.pdf"
            sample["input_scope"] = "authored_page_selection"
            sample["reference_dir"] = f"references/{sample['document_id']}"
            evaluation = sample.pop("evaluation", None)
            if isinstance(evaluation, str):
                evaluation = read_json(inside(source_root, evaluation))
            if evaluation is not None:
                evaluation_path = f"evaluation/{sample_id}.json"
                write_json(output / evaluation_path, evaluation)
                sample["evaluation"] = evaluation_path
            else:
                sample["evaluation"] = None
            samples.append(sample)
    manifest = {
        "name": selection["name"],
        "kind": selection["kind"],
        "state": selection.get("state", "draft"),
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "declared_input_pages": selection.get("declared_input_pages"),
        "review_record": selection.get("review_record"),
        "freeze_record": selection.get("freeze_record"),
        "preflight_confirmed": selection.get("preflight_confirmed", False),
        "documents": packaged_documents,
        "samples": samples,
        "suites": selection.get("suites", {}),
        "scoring_policy": "mo-parse-eval-text-v1",
        "reference_scope": selection.get("reference_scope", "explicit_authored_scope"),
        "corpus_acceptance": "not_performed_by_packaging",
    }
    write_json(output / "manifest.json", manifest)
    for relative, authored_path in selection.get("supplementary_files", {}).items():
        destination = inside(output, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(inside(source_root, authored_path), destination)
    (output / "README.md").write_text(
        f"# {selection['name']}\n\n"
        "本目录包含独立运行所需的输入PDF、现有参考与图片副本、manifest和评分索引。"
        "运行路径以本包manifest为准；原参考manifest及处理说明按历史字节保留，"
        "其中编辑工作区导航不作为运行路径。\n\n"
        f"制作状态：{manifest['state']}。包装只执行人工清单，没有机械复核或验收语料。"
        "Full不因复制完成而成为新验收Gold；未知与历史复核范围以参考记录为准。\n\n"
        "评分程序只读冻结且目视确认的参考，不能用于检查或改写语料。"
        "评分协议由MO-Parse的benchmark/evaluation-tasks.md维护；本包不复制其规则。\n\n"
        "命令：`python -m moparse_eval run --dataset <本目录> --suite lite`；"
        "Full本轮不启动推理。未冻结的Lite不能形成正式对照。\n\n"
        "原件来源与许可沿用原资料声明；本地打包不提供新的再分发许可。\n",
        encoding="utf-8",
    )
    return manifest
