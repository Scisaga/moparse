# Independent 7-page source addendum

This addendum keeps the original `moparse-v1` 1.1.0 manifest and prior gold
unchanged. Its three complete public originals were source-reviewed before any
candidate inference on these documents.

| Original / source family | Pages | Source properties |
| --- | ---: | --- |
| NASA-hosted MAAX mission factsheet | 2 | Native text, dense visual layout, prose, units and small tables |
| GSA / DOJ Standard Form 95, revision 2/2007 | 2 | Native text, blank form controls and two-column instructions |
| NARA JFK record 32171186, released State Department telegram | 3 | Historical scans; all three pages have zero native text characters and one page image |

The **28 source assertions** comprise 14 text assertions, 11 ordered-text
assertions, one complete 10-by-4 cost grid and two independently visible merged
spans. All seven pages were rendered at 300 DPI and visually inspected, with
three additional detail views. This is partial source coverage, reviewed by one
agent; it does not establish whole-document accuracy or absence from model
pretraining.

The final gold was sealed at **2026-10-17 19:31:24 UTC** (2026-10-18 03:31:24
Asia/Shanghai), before any model call, with SHA256
`8da34499ea3ed33cadcb044a352671010207c4fd30819bdafe2201303168b40c`.
[The seal](annotations/fresh7/gold-seal.json) and
[closure hashes](annotations/fresh7/closure.json) record the original identities.
An earlier provisional seal and an explicit path-only relocation proof are
retained; every scoring predicate and every original PDF byte is unchanged.

The source review did not access candidate runs, model outputs or scores. An
initial broad code search inadvertently displayed some old holdout builder
lines; this is disclosed in the review metadata. Those lines were not used to
choose the three new families or to write their assertions. The prior
IRS/Census/NIST families are excluded.

Text and ordered-text checks may collapse source line-wrap whitespace. No case,
punctuation, numerical, width, unit or mathematical equivalence is enabled. NASA
raised footnote markers retain the actual source ASCII `1` and `2` characters;
they are not rewritten into mathematical exponents. Empty source form controls
remain empty; check labels do not assert a selected state.

The PDF originals and 300 DPI images are private local evidence and ignored by
Git. Download URLs, UTC timestamps, source SHA256, page properties, image hashes
and source-specific rights observations are retained in
[the source records](annotations/fresh7/source-records.json). NASA's third-party
photo credits are retained without assigning a new license. SF95 explicitly
authorizes local reproduction. No broader license is inferred from government
hosting or public accessibility. USCIS I-9 was considered but its official
download returned HTTP 403; that failed acquisition is recorded in the download
provenance and the document is not an input.

Validate the independent manifest and all local source identities:

```bash
python -m benchmark validate \
  --dataset benchmark/datasets/moparse-addon-20261018/dataset.json \
  --require-sources
```

Use `--dataset` with this manifest and cohort `fresh7-20261018` for the complete
seven-page HTTP capture. Evaluate only against
`annotations/fresh7.assertions.json` with the unchanged assertions reader. Once
candidate results are viewed, this first-use holdout role is consumed; later
repairs require a new independent source set for a new first-use claim.
