"""Serve the pinned SDK with its packaged defaults and local connection overrides."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import multiprocessing
import os
from pathlib import Path
from urllib.parse import urlsplit

from glmocr.config import GlmOcrConfig


def selected_config() -> GlmOcrConfig:
    """Load official YAML completely; do not inherit historical task overrides."""

    config = GlmOcrConfig.from_yaml()
    endpoint = os.environ.get("GLMOCR_OCR_API_URL", "http://glm-ocr:8000/v1/chat/completions")
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("GLMOCR_OCR_API_URL must be an absolute HTTP(S) endpoint")
    port = int(os.environ.get("GLMOCR_SERVER_PORT", "5002"))
    if not 1 <= port <= 65535:
        raise ValueError("GLMOCR_SERVER_PORT is outside the valid port range")
    config.pipeline.maas.enabled = False
    config.pipeline.ocr_api.api_url = endpoint
    config.pipeline.ocr_api.model = os.environ.get("GLMOCR_OCR_MODEL", "zai-org/GLM-OCR")
    config.pipeline.layout.device = "cpu"
    config.server.host = "0.0.0.0"
    config.server.port = port
    return config


def configuration_record(config: GlmOcrConfig) -> dict[str, object]:
    packaged = Path(GlmOcrConfig.default_path())
    effective = config.model_dump(mode="json")
    canonical = json.dumps(effective, ensure_ascii=False, sort_keys=True).encode()
    return {
        "sdk_version": importlib.metadata.version("glmocr"),
        "packaged_config_path": str(packaged),
        "packaged_config_sha256": hashlib.sha256(packaged.read_bytes()).hexdigest(),
        "effective_config_sha256": hashlib.sha256(canonical).hexdigest(),
        "overrides": [
            "pipeline.maas.enabled",
            "pipeline.ocr_api.api_url",
            "pipeline.ocr_api.model",
            "pipeline.layout.device",
            "server.host",
            "server.port",
        ],
        "configuration": effective,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-config", action="store_true")
    args = parser.parse_args()
    config = selected_config()
    record = configuration_record(config)
    if args.print_config:
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return

    # Retain normal proxy support for CPU model loading; private OCR requests
    # use the deployment's NO_PROXY setting. No secondary inference provider.
    for upper, lower in (("HTTP_PROXY", "http_proxy"), ("HTTPS_PROXY", "https_proxy")):
        if upper in os.environ:
            os.environ[lower] = os.environ[upper]
    from glmocr.server import configure_logging, create_app

    multiprocessing.set_start_method("spawn", force=True)
    configure_logging(level=config.logging.level)
    print(
        json.dumps({key: value for key, value in record.items() if key != "configuration"}),
        flush=True,
    )
    app = create_app(config)
    pipeline = app.config["pipeline"]
    try:
        pipeline.start()
        app.run(
            debug=config.server.debug,
            host=config.server.host,
            port=config.server.port,
        )
    finally:
        pipeline.stop()


if __name__ == "__main__":
    main()
