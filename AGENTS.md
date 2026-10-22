# MO-Parse project instructions

The formal project name is **MO-Parse**. Keep existing `moparse` package names, configuration identifiers and public APIs compatible.

## Markdown

Write each ordinary Markdown paragraph on one physical line, with a blank line between paragraphs. Preserve syntax-required line breaks in lists, tables, code blocks and HTML. Configure prose formatters to preserve paragraphs.

Authored Markdown and documentation generators must not contain U+FF0F. Use ASCII `/` or plain words. Run `python scripts/check_markdown_policy.py` before delivering documentation changes.

Keep each rule in its owning document: execution constraints here, final text and image-package requirements in [the output contract](docs/specs/moparse-output-spec.md), source evidence in [table-source](docs/specs/table-source.md), interface behavior in [API](docs/specs/api.md), per-pipeline native formats and adapter logic in [pipeline outputs and adapters](docs/pipelines/README.md), implementation structure in [architecture](docs/engineering/architecture.md), research questions in [the research framework](docs/research/research-framework.md), work sequence in [the technical route](docs/engineering/technical-route.md), and deployment/configuration in [runtime recipes](docs/operations/runtime-recipes.md). Link to those definitions instead of recreating project-spec documents or repeating complete requirements. Separate target behavior from implemented and verified behavior; documentation changes do not authorize inference, measurements or deployment.

## Benchmark reset

The research questions, evidence requirements, methods and decision sequence are defined in [the research framework](docs/research/research-framework.md). Establish source categories and cheap observable features, then compare category-specific parsing quality and actual parsing cost before selecting methods or a routing policy. Existing code, model names, parser disagreement and isolated failures do not establish method superiority. Predeclared native/visual branching belongs to each fixed configuration; a new method-selection policy requires comparison evidence. The [technical route](docs/engineering/technical-route.md) separates parser research from MO-Parse integration, conversion and API delivery. Research documentation does not authorize experiments or deployment.

Candidate pipelines may return their native Markdown, HTML, XML, JSON or SDK structures, including tables and page furniture. Preserve native outputs and use faithful research-side Markdown export for comparison. Do not require candidates to implement MO-Parse's final semantic format, a common semantic interface or service conversion components before comparison. Readback must not drop available information or repair parser answers; pure-visual parsing and export must not use native text or other parsers to complete results.

The benchmark currently contains exactly three planning documents: [evaluation tasks](benchmark/evaluation-tasks.md), [pipelines to test](benchmark/pipelines-to-test.md) and [MinerU tuning](benchmark/mineru-tuning.md). Keep task definitions, the eight concrete main comparison configurations, and MinerU tuning experiments in their respective documents.

The previous benchmark reports, measurements, figures, archives, generators and dedicated evaluation tooling have been removed at the user's request. Do not restore them, recreate compatibility entry points, or use their scores to describe the new benchmark. No new comparison results exist until the declared configurations have been measured again under the same protocol.

The main comparison evaluates complete PDF parsing pipelines on the same source bytes, annotations, faithful export rules, declared common processing and resource budget. Measure directly from worker processing start to native parsing results, faithful research-side Markdown and necessary assets being ready, including required PDF rendering and parsing/export work. Exclude MO-Parse semantic conversion, page-furniture cleanup and API document assembly, as well as HTTP transport, API queues, polling, downloads and pure persistence. Measure service conversion separately; do not estimate removed overhead or sum overlapping stage durations as total elapsed time. Record initialization and warm-up separately.

The current service entry point and its duration fields are not ready-made benchmark boundaries. `ParserService.parse` includes MO-Parse source supplementation, assets and semantic conversion; turning off the semantic flag does not remove those other stages. The native worker duration omits its earlier PDF metadata reads and covers only one branch. Preserve field meanings and prepare direct measurement of the declared full pipeline; do not subtract local fields to invent compliant elapsed time. See [the inspected code boundaries](docs/engineering/architecture.md#现有调用与计时字段).

Keep unannotated content, missing measurements, failed runs and unknown structure distinct from correct output and zero cost. State task coverage and document-family exposure. Use an explicit character-width policy with strict character diagnostics; width equivalence cannot repair numbers, signs, units, headers or source bindings.

Predeclare task-specific adoption criteria and compare paired original documents before selecting a method. Preserve quality/cost tradeoffs instead of inventing a weighted winner; repeated runs do not create independent document samples. Source classification and method selection are different questions. Learn routing only when measured differences and runtime-observable features support it; include switching, context loss and repeated processing in actual routed results.

Keep MinerU concurrency, thread, execution-mode and verification experiments in the tuning document. They are not additional main pipelines or cross-framework quality results. Do not launch inference, change parser behavior or restart services as a side effect of documentation cleanup.

## Task autonomy

Complete authorized inspection, implementation, scoped verification and deployment work without asking the user to enumerate routine steps. Preserve unrelated work and processes. Respect explicit scope, resource, timing and cancellation limits.

A request to list or organize planned experiments does not itself start them. For authorized performance measurements, separate warm-up and use at least three measured repetitions of representative workloads. Run proportionate checks for code changes without repeatedly broadening successful validation.

Parsing expected results and corpus generation are being carried out in other projects. Do not recreate the removed local sample directory or duplicate corpus and gold generation here. Future PDF workloads require an explicitly scoped handoff of versioned originals and independent annotations; no replacement corpus is currently declared. The six public PDFs in `pdf_sample_extra/` are retained locally and temporarily out of scope for parsing, benchmarks, tuning, warm-up, regression acceptance and deployment decisions. Resume them only on explicit user instruction; do not add more documents or source-specific handling as part of another task.

Keep development and evaluation splits at complete-document and document-family level, and record development exposure. Review preannotations before accepting them as Gold; online corrections remain candidates until reviewed rather than feeding directly into training or evaluation. These constraints do not authorize training, corpus generation or new workloads.

## Runtime and GPU execution

Deployment steps and actual configuration keys belong in [runtime recipes](docs/operations/runtime-recipes.md). Read live image and model identities when reporting a current deployment; a software version or planned recipe is not proof of deployment acceptance.

Enable CUDA Graphs on supported GPU inference backends within their allocated resources. Verify uncertain support with a bounded capture and inference trial. Disable graphs only for an explicit eager control or a demonstrated failure, memory-budget violation or output regression, recording the condition for re-enablement. Keep torch.compile separate from CUDA Graphs. Do not silently restore slower eager execution after a successful trial.

## Table, diagram and final-output handling

The [output contract](docs/specs/moparse-output-spec.md) owns the final Markdown, image assets and ZIP delivery requirements. Before designing a pipeline adapter, verify and document that complete pipeline's actual native output, fields, order, coordinates, media, failures and limitations in [pipeline outputs and adapters](docs/pipelines/README.md). Each P01–P08 configuration's document keeps its native format definitions, fields, media, verification evidence and adaptation logic together, including all declared branches; same-family readers may be shared in code. Design common MO-Parse assembly from this inventory, without imposing the current limited IR or a common Markdown intermediate on backends. Distinguish documentation/source inspection from fixed-version sample verification and implemented acceptance. It applies after MO-Parse service conversion, not to candidate pipelines. Read selected backends' native results faithfully; distinguish parser defects from integration, conversion and assembly defects. Preserve business headings, notes, units, signatures and dates while cleaning page furniture from final text; retain original content and physical locations for audit.

Image semantic interpretation is explicitly out of scope. Do not implement or plan flowchart/organizational-chart relation recovery, graph descriptions, chart interpretation, scene descriptions, related annotations or acceptance tests. Preserve images, source captions, Markdown references and package delivery; existing optional OCR remains text recognition only. Image preservation is valid final delivery and the absence of image semantics is not a failure or a pending feature.

Classify content before table conversion. Grid lines, rectangular cells, alignment, coordinates, matching glyphs and backend `table` labels do not prove a semantic data table. Separate source-backed fields/records/data relations from grid-based prose or image layout and unknown uses; mixed grids require region-level treatment. Restore layout content in its supported reading order without inventing field/value or header relations. Add independent layout-grid and mixed-region cases before claiming classification or conversion coverage. The output contract defines how confirmed data tables are expressed.

Keep source reconstruction, semantic binding and final conversion separate. Intermediate Markdown, HTML, XML and native SDK structures are allowed. Preserve source evidence, valid neighboring content and images when a region is unresolved; report classification uncertainty, unsupported methods, recognition gaps, conflicts and source ambiguity separately. Screenshots of confirmed data tables do not prove completed table conversion.

Cross-page joining requires complete source-backed headers, spans, units and continuation scope. Similar first-row text, equal column counts or visual proximity do not authorize header deletion or merging. Retain complete physical tables in the evidence layer when their relation is uncertain; the final conversion must express confirmed content and explicitly account for unresolved scope.

Do not run an independent Docling parser after MinerU for header or source-conflict verification. Docling remains a separately selected native backend. Use direct PDF evidence for source handling; do not treat parser disagreement as proof of correctness or add a second parser without page-category quality and cost evidence.

Bind confirmed table values to complete row and column header paths, units, periods, notes and source cells before verbalization. Copy labels and values from source evidence; business normalization, entity disambiguation, fact deduplication, event orchestration and inferred facts belong downstream. Do not apply table role or display-row mappings to prose laid out inside grids.

The table semantics in `app/models/table_semantics.py` and `app/services/table_semantics_service.py` remain limited; see the output contract's current implementation gaps. Extend source categories and independent annotations before broadening conversion methods. Test service functions with controlled structures and actual parser outputs separately; these tests are not prerequisites or quality results for the eight-pipeline comparison.

Follow [the table-source evidence rules](docs/specs/table-source.md). Maintain one current definition for table sources, semantic relations and their audit data; edit it directly without internal protocol versions, old-format compatibility branches or automatic migrations. Read each backend's native results; GFM is only a display format, not a required common intermediate model. Preserve source rows, cells, spans and provenance internally. For confirmed data tables, unknown first rows remain data. When a display needs synthetic headers, strip only explicitly declared, all-empty synthetic rows when reconstructing source rows. A reconstructed grid does not prove header semantics or completeness. Do not apply display row mappings to prose or expose physical page markers in the target final text. Preserve historical evidence bytes and distinguish processing completion from complete semantic conversion. This rule does not change generic document IR, asset index or ZIP formats, public HTTP routes, model identities or software release versions.

Isolate malformed SDK regions without losing valid neighbors or original source images. Do not retry received-response or execution-unknown failures without a verified idempotency contract. Keep cancellation and shared-deadline cleanup owned until the original requests return or remote acknowledgement confirms cleanup. Do not infer remote completion from local counters.

## Brand and figure typography

Use an independently designed document-related everyday object as the mascot, with a simple silhouette, restrained expression and loose slender limbs. Preserve application status colors. Do not copy a named character's recognizable silhouette, face panel or controls.

Use sans-serif fonts in maintained charts and diagrams, including mathematical text. Use DejaVu Sans for Latin text and Noto Sans CJK for Chinese, an explicit SVG `sans-serif` fallback, `mathtext.fontset=dejavusans`, and no TeX or serif fallback. Embed fonts in exported PDFs and verify SVG font stacks and PDF font names. Generate any future measurement charts only from the new referenced measurements with their actual resource and timing conditions.
