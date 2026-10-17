"""Record additional source-confirmed observations, outside the frozen matrix.

Reads original bytes and existing raw inference/HTTP captures only. It never
changes parser results, source references, or gold used by another system.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evidence(path):
    return {
        "path": str(Path(path).relative_to(HERE)),
        "sha256": sha(path),
        "bytes": Path(path).stat().st_size,
    }


def save_crop(page, bbox, filename):
    path = HERE / "additional-source-observations" / filename
    page.get_pixmap(matrix=pymupdf.Matrix(4, 4), clip=pymupdf.Rect(bbox), alpha=False).save(path)
    return {**evidence(path), "source_bbox_PDF_points": bbox}


def eos(call):
    tokens = call["eos_token_id"]
    return call["last_token_id"] in (tokens if isinstance(tokens, list) else [tokens])


def main():
    out = HERE / "additional-source-observations" / "source-confirmed-extra-observations.json"
    if out.exists():
        raise ValueError("Refusing to overwrite additional observation evidence")
    out.parent.mkdir(exist_ok=True)
    reference = json.loads((HERE / "source-reference.json").read_text())
    p40 = pymupdf.open(REPO / "pdf_sample/1225474739.pdf")[39]
    trial40 = HERE / "mineru-trial/remaining-pages-gpu/1225474739-p40"
    blocks40 = json.loads((trial40 / "official-blocks.json").read_text())
    calls40 = json.loads((trial40 / "generation-calls.json").read_text())
    prior = HERE / "user-prior-job_01M54S6SZB4PH061X16NW8TVCQ/result.md"
    raw = prior.read_text()
    match = re.search(r"<!-- page: 40 -->", raw)
    end = re.search(r"<!-- page: \d+ -->", raw[match.end() :])
    page40 = raw[match.start() : match.end() + end.start()]
    excerpt = out.parent / "user-prior-job-page40-original.md"
    excerpt.write_text(page40)
    heading = "持股 5%以上股东、前 10 名股东及前 10 名无限售流通股股东参与转融通业务出借股份情况"
    position = page40.find(heading)
    assert position >= 0
    prior_lines = page40[position:].split("\n\n")[:2]
    assert "□适用 \uf052不适用" in "\n\n".join(prior_lines)
    assert blocks40[3]["content"] == "□适用 □不适用"
    assert calls40[4]["raw_generation"] == ["□适用 □不适用<|im_end|>"] and eos(calls40[4])
    assert blocks40[5]["content"] == "□适用 ☑不适用"
    crop40 = trial40 / "sdk-calls/004/image-0.png"
    observations = [
        {
            "id": "134p40-first-post-table-checkbox-state",
            "source_pdf": "pdf_sample/1225474739.pdf",
            "source_sha256": reference["source_documents"]["1225474739"]["sha256"],
            "source_page": 40,
            "source_crop": save_crop(
                p40, [53, 730, 131, 747], "1225474739-p40-checkbox-source.png"
            ),
            "source_visible_state": "Applicability unchecked; not-applicable checked",
            "source_native_checkbox": {
                "character": "\uf052",
                "font": "Wingdings 2",
                "visible_meaning": "checked checkbox",
            },
            "prior_user_job_baseline": {
                "job": "job_01M54S6SZB4PH061X16NW8TVCQ",
                "origin": "Existing user job, GET-only this turn; not a new POST of this experiment",
                "job_time_deployment_build": "unknown",
                "raw_MD": evidence(prior),
                "unmodified_page_excerpt": evidence(excerpt),
                "actual_raw_lines": prior_lines,
                "correct_checked_state_retained": True,
            },
            "MinerU_transformers": {
                "official_blocks": evidence(trial40 / "official-blocks.json"),
                "block_pointer": "/3/content",
                "actual": blocks40[3]["content"],
                "raw_generation": evidence(trial40 / "generation-calls.json"),
                "raw_generation_pointer": "/4/raw_generation/0",
                "actual_generation": calls40[4]["raw_generation"][0],
                "ended_EOS": True,
                "actual_model_crop": evidence(crop40),
                "actual_model_crop_dimensions": [192, 31],
                "crop_checked_mark_visually_present": True,
                "status": "fail",
            },
            "same_page_second_checkbox_control": {
                "source_checked_not_applicable": True,
                "blocks_pointer": "/5/content",
                "actual": blocks40[5]["content"],
                "status": "pass",
            },
            "classification": "Confirmed local loss of a visible choice state relative to this specific prior raw baseline; not a whole-model quality ranking.",
        }
    ]
    p74 = pymupdf.open(REPO / "pdf_sample/1225475375.pdf")[73]
    trial74 = HERE / "mineru-trial/remaining-pages-gpu/1225475375-p74"
    blocks74 = json.loads((trial74 / "official-blocks.json").read_text())
    calls74 = json.loads((trial74 / "generation-calls.json").read_text())
    original = reference["1225475375"]["page74"]["negative_business_conclusion"]["text"]
    assert original.startswith("—") and blocks74[11]["content"] == "一" + original[1:]
    assert eos(calls74[11])
    observations.append(
        {
            "id": "119p74-negative-conclusion-restored-with-leading-glyph-error",
            "source_pdf": "pdf_sample/1225475375.pdf",
            "source_sha256": reference["source_documents"]["1225475375"]["sha256"],
            "source_page": 74,
            "source_crop": save_crop(
                p74, [99, 692, 392, 718], "1225475375-p74-negative-conclusion-source.png"
            ),
            "source_original": original,
            "model_actual": blocks74[11]["content"],
            "official_blocks": evidence(trial74 / "official-blocks.json"),
            "raw_pointer": "/11/content",
            "raw_generation": evidence(trial74 / "generation-calls.json"),
            "raw_generation_pointer": "/11/raw_generation/0",
            "ended_EOS": True,
            "conclusion_body_restored": True,
            "literal_character_exact": False,
            "status": "fail_literal_first_character",
            "classification": "Business negation and complete statement present; original em dash misrecognized as Chinese numeral one. Not a continuing whole-sentence omission.",
        }
    )
    assert blocks74[13]["type"] == "footer" and blocks74[13]["content"] == "验证码"
    assert eos(calls74[13])
    observations.append(
        {
            "id": "119p74-QR-inferred-label-output-as-footer-text",
            "source_pdf": "pdf_sample/1225475375.pdf",
            "source_sha256": reference["source_documents"]["1225475375"]["sha256"],
            "source_page": 74,
            "source_crop": save_crop(p74, [522, 770, 587, 833], "1225475375-p74-QR-source.png"),
            "source_visual": "QR graphic only; no printed 验证码 caption in this crop",
            "model_type": blocks74[13]["type"],
            "model_actual": blocks74[13]["content"],
            "official_blocks": evidence(trial74 / "official-blocks.json"),
            "raw_pointer": "/13/content",
            "raw_generation_pointer": "/13/raw_generation/0",
            "ended_EOS": True,
            "status": "fail_as_verbatim_source_text",
            "classification": "Model produces an inferred QR description as footer text; not a verbatim character present in the original. No historical-baseline regression claimed.",
        }
    )
    result = {
        "schema": "mosaicparse-additional-source-observations/1",
        "created_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "scope": "Additional reviewed observations, outside the fixed targeted content reference; not a full-document semantic score.",
        "source_reference_modified": False,
        "inference_or_HTTP_started": False,
        "observations": observations,
    }
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"observations": len(observations), "output": str(out)}))


if __name__ == "__main__":
    main()
