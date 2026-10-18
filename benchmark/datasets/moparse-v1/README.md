# moparse-v1 dataset card

Version **1.1.0** contains 14 inputs and 543 physical PDF pages. Source files remain
local; [dataset.json](dataset.json) and [documents.jsonl](documents.jsonl) lock
their identity and describe the registered evaluation cohorts.

| Split / source group | Inputs | Pages | Role |
| --- | ---: | ---: | --- |
| Previously inspected financial PDFs | 10 | 502 | Fixed regression set |
| Previously inspected Office-derived PDF | 1 | 2 | Conversion / source-content regression |
| IRS 2025 Form 1040 | 1 | 2 | New form family |
| US Census 1930 American Samoa bulletin | 1 | 12 | New historical scanned-statistics family |
| NIST Technical Note 2354 | 1 | 25 | New scientific prose / units / tables family |

The existing 502 pages have 433 native, 66 scanned and 3 mixed source-page routes;
these counts describe the frozen source routing, not model predictions. The Office
PDF has two native pages. New-source route decisions remain based on source
properties, never on annotation answers or a document-ID success list.

The initial 11 inputs have already been used repeatedly for debugging. They are
**regression data**, including their 14 difficult selected pages and the extra
119-page-report page 62. The three new original documents were source-reviewed
before their first candidate output; their 36 assertions were sealed with SHA256
`cef9ea7229d722e66ae4403fa8f337295534f89e6e6c5ac983e8c77523dccafc`.
The seal and source review are in [annotations/holdout-20261018/](annotations/holdout-20261018/).
Source families, full documents, selected pages, crops and derived scans stay in
the same leakage group. Looking at a holdout result consumes its holdout role for
future tuning; a subsequent independent claim needs newly acquired documents.

| Annotation suite | Fixed scope | Interpretation |
| --- | --- | --- |
| core209 / period209 | 209 nonempty numeric source-column bindings | Original values and source-backed periods |
| supplement402 | 402 atomic source fields | Literal + unique row, and complete column meaning separately |
| content14-fixed46 | 46 reviewed content / structural conditions | Original 14 difficult pages, not whole-document accuracy |
| additional4 | Four source-state / character observations | A separate denominator |
| extra-p62 | 99 grid positions and 9 merged spans | A separate complex-table grid |
| holdout-20261018 | 36 source assertions across 3 new originals | 17 text, 10 ordered text, 4 regex, 3 full small grids, 2 merged spans |

These suites overlap in source documents and pages. Their denominators are never
added to produce a global accuracy. Unlabelled content is unscored, not presumed
correct. Existing annotations are provisional single-reviewer source transcriptions;
the new gold also has **partial** coverage and does not establish complete
paragraph fidelity or whole-document semantic accuracy.

The new original URLs and download SHA256 values are recorded in each document's
`origin`. Government source links are retained for provenance. Redistribution
rights for the existing financial/Office inputs have not been established, so raw
documents and large proof images are ignored by Git. This repository contains
source references, necessary assertions and evidence hashes; it does not grant a
new license for the underlying source documents.

Validate local identities with:

```bash
uv run python -m benchmark validate --require-sources
```

See [the benchmark guide](../../README.md) for complete HTTP capture, fixed-source
scoring, importing a new document group and registering reproducible method runs.
