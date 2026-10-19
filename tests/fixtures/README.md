# Test fixtures

The document, image and video fixtures in this directory are generated from original test text by [`scripts/generate_fixtures.py`](../../scripts/generate_fixtures.py). They contain no company report, article or third-party logo.

`mineru-4.0.12-pp-formulanet-plus-m-onnx.py.txt` is an unmodified upstream Python source fixture from the installed `mineru==4.0.12` distribution, originally at `mineru/model/mfr/pp_formulanet_plus_m_onnx.py`. Its SHA256 is `06f787c9414b99388a89b75a9c8a6c752058146d4538725e4afb2451829f1c1f`. The CPU microbatch tests apply our patch to this pinned source and replace the ONNX session with a fake; they do not load weights or run model inference. The Opendatalab copyright notice is retained. This fixture is governed by the [MinerU Open Source License](LICENSE.MinerU.md), copied from that exact installed distribution, rather than the repository's Apache-2.0 license alone. Upstream: [Opendatalab/MinerU](https://github.com/opendatalab/MinerU).

| File | Purpose |
|---|---|
| `native-report.pdf` | One-page PDF with an extractable text layer and exact numbers |
| `scanned-report.pdf` | One-page image-only PDF for OCR routing |
| `mixed-report.pdf` | Native first page plus scanned second page |
| `multi-column-research.pdf` | Two text columns for reading-order checks |
| `table-report.pdf` | Ruled numeric table for table-structure checks |
| `field-observation-report.pdf` | Embedded raster image plus a ruled numeric table for mixed-layout checks |
| `sample-image.png` | Standalone image upload and OCR fixture |
| `natural-scene.{png,webp,bmp,tiff}` | Pure visual image routing in supported raster formats |
| `mixed-screenshot.png` | Text plus chart image for mixed routing |
| `embedded-image.docx` | DOCX body plus an embedded image |
| `embedded-image.pptx` | PPTX slide plus an embedded image |
| `embedded-video.pptx` | Embedded video and poster; video relationships must be ignored |
| `scene-switch.mp4` | Six-second, three-scene, silent video for deterministic keyframes |

Regenerate and validate:

```bash
uv run python scripts/generate_fixtures.py
uv run python scripts/generate_fixtures.py --check
```

The fixtures are deliberately tiny and validate mocked routing and component contracts, not model quality or the complete [final semantic output contract](../../docs/output-contract.md). Parsing expected results and corpus generation are being carried out in other projects; real PDF inference and deployment acceptance require an explicitly scoped handoff of versioned originals and independent annotations. Complete table descriptions, flowchart and organizational relations, and page-furniture cleanup require source annotations and full-document evidence.

Fixtures created before the 2026-10-18 rename retain their original MosaicParse text and metadata. Those strings are test data, not a current service or repository name; the existing fixture bytes and hashes are preserved.
