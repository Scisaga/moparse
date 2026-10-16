#!/usr/bin/env python3
"""Prefetch the pinned official CPU document-orientation classifier."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from huggingface_hub import snapshot_download

MODEL = "PaddlePaddle/PP-LCNet_x1_0_doc_ori_safetensors"
REVISION = "b2716954d2e321dd4436400b37584fab641027ab"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    path = Path(
        snapshot_download(
            repo_id=MODEL,
            revision=REVISION,
            local_dir=args.output_dir,
            allow_patterns=["*.json", "model.safetensors"],
        )
    )
    model = path / "model.safetensors"
    print(
        json.dumps(
            {
                "model": MODEL,
                "revision": REVISION,
                "directory": str(path.resolve()),
                "model_SHA256": hashlib.sha256(model.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
