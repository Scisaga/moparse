# Benchmark guide

The maintained dataset, method registry, evaluation CLI and comparison report now
live in [`benchmark/`](../benchmark/README.md). The current comparison is
[`benchmark/report.md`](../benchmark/report.md); the earlier report under
`benchmark-results/clean-model-comparison-20261015/` is historical evidence.

Run `python -m benchmark validate --require-sources`, `python -m benchmark compare`
and `python -m benchmark.tools.render_report` from the repository root. Use `run-http` to retain
whole-document requests, final Markdown, public assets and resource samples, then
`evaluate` to score the received output. See the benchmark README for exact commands.

Parsing quality is evaluated at the content level, not by exact whole-document string
equality. Docling and model upgrades can make harmless Markdown formatting
changes.

## Corpus policy

The committed fixtures are small, original documents and are suitable for CI.
Real GPU regression tests should use an access-controlled corpus whose license,
retention, and confidentiality are documented. Do not commit customer reports
or copyrighted research PDFs.

Private page-level truth can be recorded in a local manifest using
`tests/fixtures/quality-manifest.example.json` as the schema. The manifest and
PDFs stay outside Git; it records SHA-256, target pages, text/order anchors,
dates, numbers, table shapes, allowed warnings, and performance budgets. Run it
with:

```bash
uv run python scripts/evaluate_quality.py pdf_sample/regression.local.json \
  --base-url http://127.0.0.1:12303 \
  --json-output pdf_sample/results/latest.json
```

## Metrics

Record at least:

- document and page success rates;
- exact preservation of numbers, signs, decimal places, and units;
- heading/paragraph reading order;
- table cell and row/column structure;
- empty-page and repeated-text rates;
- full HTTP wall time (upload through saved final Markdown), model inference time, and per-page mean/p95;
- CPU utilization, peak parser RAM, GPU utilization, GPU memory, and sampling interval/coverage;
- GLM/SDK request count, OCR-page rate, unresolved structural conflicts, and budget exhaustion;
- trusted/degraded/untrusted counts and candidate adoption/rejection reasons;
- native repair, logical cross-page merge, rotation, and timeout counts.

Unknown route counts are not zeros. Report them as unavailable when the parser
or upstream component cannot observe them reliably.

The earlier Docling rollout used page-level budget targets: native numeric pages p95
within 10% of its fixed baseline, and automatically routed complex pages p95 within
about 2x. The current method comparison measures complete-document HTTP latency and
does not establish those page-level targets; keep missing p95 measurements unknown.
Its selection prioritizes the source-backed body/header/span acceptance requested for
Advanced＋TXT, with the measured time and shared-resource cost reported alongside
quality. Do not present that tradeoff as satisfying the earlier page-level budgets.

A page timeout must stop later candidates while retaining the primary page with
a warning. Do not attribute another process's GPU load or service-resident memory to per-request
inference. Compare complete PDFs with `scan_policy=auto` and no `unit_range`, and retain the
requests, final public Markdown, source hashes, model settings, and actual deployed image.

Only remove cross-page repeated headers when their complete text, multi-level structure, and
column meanings agree. Validate changed-header continuations and genuine same-header
continuations against the original PDFs. Check units, merged cells, and source-page associations.

## Comparison evidence

The single maintained report is [benchmark/report.md](../benchmark/report.md).
It separates new full-HTTP runs, saved full-HTTP results, and rescoring of existing final Markdown.
All displayed configurations must use the same gold and public-output scoring rules; neither
component timing nor offline output scoring substitutes for complete service acceptance.

## HTTP smoke benchmark

Start the service, then run:

```bash
uv run python scripts/benchmark.py \
  tests/fixtures/native-report.pdf \
  tests/fixtures/table-report.pdf \
  --scan-policy auto \
  --json-output benchmark-results/standard.json
```

For the GPU path:

```bash
uv run python scripts/benchmark.py \
  tests/fixtures/scanned-report.pdf \
  tests/fixtures/sample-image.png \
  --scan-policy auto \
  --json-output benchmark-results/glm-ocr.json
```

The helper records transport status and elapsed time. It is intentionally not a
load generator. Use a controlled tool and fixed concurrency for capacity tests.

## Golden assertions

Prefer focused assertions such as:

- native fixture contains `12,345.67` and `18.25%`;
- mixed fixture preserves the native first page and obtains non-empty OCR text
  for the second page;
- column headings precede their respective bodies;
- table output contains all expected cells in row order;
- no unexpected Unicode replacement characters or repeated short blocks.

Record parser version, Docling/plugin versions, model identity/revision, scan
policy, hardware, and all non-secret tuning values with every comparison.
For CPU runs also record `DOCLING_NUM_THREADS`, `DOCLING_PAGE_WORKERS`, startup
warm-up state, and whether native-page parallelism was selected. Compare at
least two consecutive requests so startup model loading is not mistaken for
steady-state conversion time.
