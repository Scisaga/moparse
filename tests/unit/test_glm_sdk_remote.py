from __future__ import annotations

import asyncio
import base64
import io
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from app.models import (
    BackendState,
    ContentParseOptions,
    StoredSource,
)
from app.models.parse_result import PageParseResult
from app.parsers.glm_sdk_remote import GlmSdkRemoteParser, _html_table_layout, _html_table_rows
from app.services.export_service import ExportService
from app.services.ir_service import DocumentIRService
from app.services.table_service import TableFragment


def _source(path: Path, *, page_count: int = 1) -> StoredSource:
    return StoredSource(
        path=path,
        filename=path.name,
        mime_type="application/pdf",
        size_bytes=path.stat().st_size,
        page_count=page_count,
    )


async def test_sdk_adapter_renders_region_json_and_table_spans(native_pdf: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(
            200,
            json={
                "layout_details": [
                    [
                        {
                            "index": 0,
                            "label": "text",
                            "native_label": "doc_title",
                            "content": "测试报告",
                            "bbox_2d": [10, 10, 990, 80],
                        },
                        {
                            "index": 1,
                            "label": "table",
                            "native_label": "table",
                            "content": (
                                "<table><tr><th rowspan='2'>项目</th><th colspan='2'>金额</th></tr>"
                                "<tr><th>本期</th><th>上期</th></tr>"
                                "<tr><td>收入</td><td>100</td><td>90</td></tr></table>"
                            ),
                            "bbox_2d": [50, 100, 950, 800],
                        },
                        {
                            "index": 2,
                            "label": "image",
                            "native_label": "seal",
                            "content": "",
                            "bbox_2d": [700, 700, 950, 900],
                        },
                    ]
                ],
                "md_results": "unused",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    parser = GlmSdkRemoteParser(
        SimpleNamespace(
            glm_ocr_enabled=True,
            glm_sdk_enabled=True,
            glm_sdk_orientation_enabled=False,
            glm_sdk_url="http://sdk:5002/glmocr/parse",
            glm_sdk_max_retries=0,
            glm_sdk_max_concurrency=1,
        ),
        http_client=client,
    )
    assert (await parser.probe()).state == BackendState.READY

    result = await parser.parse(
        _source(native_pdf),
        ContentParseOptions(unit_range="1"),
        document_id="doc_sdk_test",
    )

    assert result.pages[0].backend == "glm-sdk-remote"
    assert result.pages[0].content is not None
    assert result.pages[0].content.startswith("# 测试报告")
    assert "<!-- image -->" in result.pages[0].content
    assert len(result._table_fragments) == 1
    table = result._table_fragments[0]
    assert isinstance(table, TableFragment)
    assert table.rows == [
        ["项目", "金额", ""],
        ["", "本期", "上期"],
        ["收入", "100", "90"],
    ]
    assert table.has_column_header is True
    assert table.header_row_indices == (0, 1)
    internal = DocumentIRService._table(table)
    assert internal.header_rows == [0, 1]
    assert internal.source_units == [1]
    assert len(internal.cells) == 7
    project = next(cell for cell in internal.cells if cell.text == "项目")
    amount = next(cell for cell in internal.cells if cell.text == "金额")
    assert (project.row_span, project.column_span, project.is_column_header) == (2, 1, True)
    assert (amount.row_span, amount.column_span, amount.is_column_header) == (1, 2, True)
    assert all(cell.provenance.selected_source.value == "glm" for cell in internal.cells)
    assert table.visual_obstructions == [(0.7, 0.7, 0.95, 0.9)]
    assert result.route_summary.ocr_regions == 3
    await client.aclose()


def _html_fragment(content: str) -> TableFragment | None:
    return GlmSdkRemoteParser._table_fragment(
        {"content": content, "bbox_2d": [50, 100, 950, 800]}, page_number=7, ordinal=1
    )


@pytest.mark.parametrize("opening,closing", [("th", "td"), ("td", "th")])
def test_explicit_cell_end_marker_preserves_opening_role_and_multilevel_spans(
    opening: str, closing: str
) -> None:
    content = (
        f"<table><tr><{opening} rowspan='2' scope='row'>Group</{closing}>"
        "<th colspan='2'>Band (kg)</th></tr>"
        "<tr><th>Prior</th><th>Current</th></tr>"
        "<tr><td>Alpha</td><td>-2.50</td><td>0.2907</td></tr></table>"
    )
    paired = content.replace(f"Group</{closing}>", f"Group</{opening}>")
    rows, has_header, cells = _html_table_layout(content)

    assert (rows, has_header, cells) == _html_table_layout(paired)
    assert rows == [
        ["Group", "Band (kg)", ""],
        ["", "Prior", "Current"],
        ["Alpha", "-2.50", "0.2907"],
    ]
    assert has_header is True
    assert len(cells) == 7
    assert (cells[0].row_span, cells[0].column_span) == (2, 1)
    assert cells[0].is_column_header is False
    assert cells[0].is_row_header is (opening == "th")
    assert (cells[1].row, cells[1].column, cells[1].column_span) == (0, 1, 2)
    assert cells[1].is_column_header is True


def test_mismatched_explicit_header_end_exports_complete_gfm_and_source_rows() -> None:
    content = (
        "<table><tr><th rowspan='2'>Label</td><th colspan='2'>Values (kg)</th></tr>"
        "<tr><th>Prior</th><th>Current</th></tr>"
        "<tr><td>Alpha</th><td>-2.50</td><td>0.2907</td></tr></table>"
    )
    markup, fragments = GlmSdkRemoteParser._render_regions(
        [{"label": "table", "content": content, "bbox_2d": [50, 100, 950, 800]}], 1
    )

    assert len(fragments) == 1
    fragment = fragments[0]
    assert fragment.header_row_indices == (0, 1)
    assert fragment.markdown == (
        "| Label | Values (kg) |  |\n"
        "| --- | --- | --- |\n"
        "|  | Prior | Current |\n"
        "| Alpha | -2.50 | 0.2907 |"
    )
    internal = DocumentIRService._table(fragment)
    assert internal.header_rows == [0, 1]
    assert len(internal.cells) == 7
    assert internal.source_units == [1]
    assert internal.cells[0].is_column_header is True
    assert internal.cells[-3].is_column_header is False
    joined, _plain = ExportService().join_document(
        [PageParseResult(page_number=1, content=markup)],
        preserve_page_breaks=True,
        table_fragments=fragments,
    )
    assert "<table" not in joined.casefold()
    assert fragment.markdown in joined
    assert (
        "<!-- table-source: sdk_p1_t1; source-page: 1; source-rows: 1-3; "
        "logical-rows: 1-3; repeated-header-rows: 0 -->"
    ) in joined


@pytest.mark.parametrize(
    "content",
    [
        "<table><tr><th>Outer<td>Inner</th></td></tr></table>",
        "<table><tr><td>Outer<tr><th>Inner</td></tr></td></tr></table>",
        "<table><tr><th>Outer<table><tr><td>Inner</th></tr></table></td></tr></table>",
        "<table><tr><th>A</td><td rowspan='2'>B</td></tr>"
        "<tr><td colspan='2'>Collision</th></tr></table>",
        "<table><tr><th colspan='2001'>Too wide</td></tr></table>",
    ],
)
def test_explicit_end_marker_recovery_does_not_relax_topology_rejection(content: str) -> None:
    assert _html_table_layout(content) == ([], False, [])


def test_html_spans_survive_in_ir_with_units_and_signed_values() -> None:
    fragment = _html_fragment(
        "<table><tr><th colspan='2'>筹资方式（万元）</th><th>金额</th></tr>"
        "<tr><td rowspan='3' colspan='2'>发行<br/>股票</td><td>12.30</td></tr>"
        "<tr><td>-5.00</td></tr><tr><td>7.30</td></tr></table>"
    )

    assert fragment is not None
    assert fragment.rows == [
        ["筹资方式（万元）", "", "金额"],
        ["发行 股票", "", "12.30"],
        ["", "", "-5.00"],
        ["", "", "7.30"],
    ]
    table = DocumentIRService._table(fragment)
    merged = next(cell for cell in table.cells if cell.text == "发行 股票")
    assert (merged.row, merged.column, merged.row_span, merged.column_span) == (1, 0, 3, 2)
    assert table.source_units == [7]
    assert [cell.text for cell in table.cells] == [
        "筹资方式（万元）",
        "金额",
        "发行 股票",
        "12.30",
        "-5.00",
        "7.30",
    ]
    assert "筹资方式（万元）" in fragment.markdown
    assert fragment.markdown.count("发行 股票") == 1
    assert fragment.markdown.count("-5.00") == 1


def test_html_empty_explicit_rows_do_not_shift_later_cell_ownership() -> None:
    content = (
        "<table><tr><th colspan='2'>事项</th></tr>"
        "<tr><td rowspan='3' colspan='2'>事项甲</td></tr>"
        "<tr></tr><tr></tr><tr><td>事项乙</td><td>17</td></tr>"
        "<tr></tr></table>"
    )
    fragment = _html_fragment(content)

    assert fragment is not None
    assert (fragment.num_rows, fragment.num_cols) == (6, 2)
    assert fragment.rows == [
        ["事项", ""],
        ["事项甲", ""],
        ["", ""],
        ["", ""],
        ["事项乙", "17"],
        ["", ""],
    ]
    table = DocumentIRService._table(fragment)
    later = next(cell for cell in table.cells if cell.text == "事项乙")
    assert (later.row, later.column) == (4, 0)
    assert not any(cell.row in (2, 3) for cell in table.cells)
    # The legacy helper still returns the same two-value text/header view.
    assert _html_table_rows(content) == (fragment.rows, True)


def test_html_explicit_row_header_scope_does_not_expand_column_header_band() -> None:
    fragment = _html_fragment(
        "<table><tr><th>类别</th><th>金额（元）</th></tr>"
        "<tr><th scope='rowgroup' rowspan='2'>类别甲</th><td>0.2907</td></tr>"
        "<tr><td>0.3042</td></tr></table>"
    )

    assert fragment is not None
    assert fragment.header_row_indices == (0,)
    table = DocumentIRService._table(fragment)
    row_header = next(cell for cell in table.cells if cell.text == "类别甲")
    assert (row_header.row_span, row_header.is_row_header, row_header.is_column_header) == (
        2,
        True,
        False,
    )
    assert [cell.text for cell in table.cells if not cell.is_column_header] == [
        "类别甲",
        "0.2907",
        "0.3042",
    ]


def test_html_colspan_collision_with_prior_rowspan_cannot_leak_raw_html() -> None:
    content = (
        "<table><tr><td>甲</td><td rowspan='2'>乙</td></tr><tr><td colspan='2'>丙</td></tr></table>"
    )

    assert _html_table_rows(content) == ([], False)
    assert _html_fragment(content) is None
    warnings = []
    markdown, fragments = GlmSdkRemoteParser._render_regions(
        [{"label": "table", "content": content, "bbox_2d": [50, 100, 950, 800]}], 7,
        warnings=warnings,
    )
    assert not fragments and "structure: unknown" in markdown and "<table" not in markdown
    assert all(value in markdown for value in ("甲", "乙", "丙"))
    assert [warning.code for warning in warnings] == ["glm_sdk_unusable_table_structure"]


async def test_unusable_sdk_html_marks_page_failed_without_publishing_raw_table(
    native_pdf: Path,
) -> None:
    from app.models.parse_result import PageStatus, WarningSeverity

    content = (
        "<table><tr><td>First</td><td rowspan='2'>Owner</td></tr>"
        "<tr><td colspan='2'>Conflicting anchor</td></tr></table>"
    )

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "layout_details": [[{
                    "label": "table", "native_label": "table", "content": content,
                    "bbox_2d": [50, 100, 950, 800],
                }]],
                "md_results": content,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        parser = GlmSdkRemoteParser(
            SimpleNamespace(
                glm_ocr_enabled=True, glm_sdk_enabled=True, glm_sdk_orientation_enabled=False,
                glm_sdk_url="http://sdk:5002/glmocr/parse", glm_sdk_max_retries=0,
            ),
            http_client=client,
        )
        result = await parser.parse(
            _source(native_pdf), ContentParseOptions(), document_id="doc_bad_structure"
        )

    page = result.pages[0]
    assert page.status == PageStatus.FAILED
    assert page.content and "structure: unknown" in page.content
    assert all(value in page.content for value in ("First", "Owner", "Conflicting anchor"))
    assert result._table_fragments == []
    assert [warning.code for warning in page.warnings] == ["glm_sdk_unusable_table_structure"]
    assert page.warnings[0].severity == WarningSeverity.ERROR
    assert "<table" not in (result.markdown or "").casefold()


@pytest.mark.parametrize(
    "content",
    [
        "<table><tr><td rowspan='2001'>甲</td></tr></table>",
        "<table><tr><td colspan='2001'>甲</td></tr></table>",
        "<table><tr><td>甲</td></tr><tr><td rowspan='2000'>乙</td></tr></table>",
        "<table><tr><td rowspan='0'>甲</td></tr></table>",
        "<table><tr><td colspan='-1'>甲</td></tr></table>",
        "<table><tr><td rowspan='unknown'>甲</td></tr></table>",
        "<table>" + "<tr><td>甲</td></tr>" * 2_001 + "</table>",
    ],
)
def test_html_unproved_or_oversized_spans_are_not_clamped_into_false_topology(content: str) -> None:
    assert _html_table_rows(content) == ([], False)
    assert _html_fragment(content) is None


def test_wide_source_grid_retains_every_anchor_and_span_without_column_clamping() -> None:
    content = (
        "<table><tr><th colspan='101'>Complete source header</th><th>Last</th></tr>"
        "<tr><td colspan='101'>Original source value</td><td>9.25</td></tr></table>"
    )
    rows, has_header, cells = _html_table_layout(content)
    assert has_header and len(rows) == 2 and len(rows[0]) == 102
    assert rows[0][0] == "Complete source header" and rows[0][101] == "Last"
    assert rows[1][0] == "Original source value" and rows[1][101] == "9.25"
    assert [(c.row, c.column, c.column_span, c.text) for c in cells] == [
        (0, 0, 101, "Complete source header"),
        (0, 101, 1, "Last"),
        (1, 0, 101, "Original source value"),
        (1, 101, 1, "9.25"),
    ]


@pytest.mark.parametrize("rows,columns", [(1, 2000), (2000, 1), (100, 2000)])
def test_source_grid_axis_and_area_boundary_is_accepted(rows: int, columns: int) -> None:
    source = f"<table><tr><td rowspan='{rows}' colspan='{columns}'>All source</td></tr></table>"
    matrix, _, cells = _html_table_layout(source)
    assert len(matrix) == rows and len(matrix[0]) == columns
    assert len(cells) == 1 and cells[0].text == "All source"
    assert (cells[0].row_span, cells[0].column_span) == (rows, columns)


def test_large_sparse_grid_is_rejected_by_full_projected_area_without_clamping() -> None:
    # Each individual axis/span is legal, but the implied grid exceeds the
    # former 100*2000 allocation budget even though only one cell is nonempty.
    source = "<table><tr><td rowspan='101' colspan='2000'>Original</td></tr></table>"
    assert _html_table_layout(source) == ([], False, [])
    warnings = []
    markdown, fragments = GlmSdkRemoteParser._render_regions(
        [{"label": "table", "content": source, "bbox_2d": [50, 100, 950, 800]}], 7,
        warnings=warnings,
    )
    assert not fragments and "structure: unknown" in markdown and "Original" in markdown
    assert [warning.code for warning in warnings] == ["glm_sdk_unusable_table_structure"]


def test_wide_colspan_still_cannot_cross_an_active_rowspan() -> None:
    source = (
        "<table><tr><td colspan='101'>First</td><td rowspan='2'>Owner</td></tr>"
        "<tr><td colspan='102'>Conflicting source cell</td></tr></table>"
    )
    assert _html_table_layout(source) == ([], False, [])


def test_wide_markdown_grid_uses_the_same_total_allocation_budget() -> None:
    from app.parsers.glm_sdk_remote import _markdown_table_rows

    wide = "|" + "|".join(["source"] * 101) + "|"
    separator = "|" + "|".join(["---"] * 101) + "|"
    assert _markdown_table_rows(wide + "\n" + separator) == [["source"] * 101]
    assert _markdown_table_rows("\n".join([wide, separator] + [wide] * 1980)) == []


async def test_pdf_page_is_physically_rotated_before_glm_submission(native_pdf: Path) -> None:
    parser = GlmSdkRemoteParser(
        SimpleNamespace(
            glm_ocr_enabled=True,
            glm_sdk_enabled=True,
            glm_sdk_orientation_enabled=False,
            glm_sdk_url="http://sdk:5002/glmocr/parse",
            glm_sdk_render_scale=1,
        )
    )

    normal_uri = parser._render_page(_source(native_pdf), 1, 0)
    rotated_uri = parser._render_page(_source(native_pdf), 1, 90)
    with Image.open(io.BytesIO(base64.b64decode(normal_uri.partition(",")[2]))) as normal:
        normal_size = normal.size
    with Image.open(io.BytesIO(base64.b64decode(rotated_uri.partition(",")[2]))) as rotated:
        rotated_size = rotated.size

    assert rotated_size == (normal_size[1], normal_size[0])
    await parser.close()


async def test_sdk_adapter_timeout_stops_later_page_calls(native_pdf: Path, monkeypatch) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return httpx.Response(200, json={"layout_details": [[]]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    parser = GlmSdkRemoteParser(
        SimpleNamespace(
            glm_ocr_enabled=True,
            glm_sdk_enabled=True,
            glm_sdk_orientation_enabled=False,
            glm_sdk_url="http://sdk:5002/glmocr/parse",
            glm_sdk_timeout_seconds=0.01,
            glm_sdk_max_retries=1,
            glm_sdk_max_concurrency=1,
        ),
        http_client=client,
    )
    monkeypatch.setattr(
        parser,
        "_render_page",
        lambda source, page_number, rotation_degrees=0: "data:image/png;base64,eA==",
    )

    result = await parser.parse(
        _source(native_pdf, page_count=2),
        ContentParseOptions(unit_range="1-2"),
        document_id="doc_sdk_timeout",
    )

    assert calls == 1
    assert result.route_summary.failed_pages == 2
    assert result.pages[0].duration_ms == 10
    assert [warning.code for warning in result.pages[0].warnings] == ["glm_sdk_timeout"]
    assert result.pages[1].duration_ms == 0
    assert [warning.code for warning in result.pages[1].warnings] == [
        "glm_sdk_skipped_after_timeout"
    ]
    await client.aclose()


@pytest.mark.parametrize(
    ("rotation", "upright_bbox"),
    [
        (0, [100, 200, 400, 600]),
        (90, [400, 100, 800, 400]),
        (180, [600, 400, 900, 800]),
        (270, [200, 600, 600, 900]),
    ],
)
def test_orientation_inverse_maps_all_regions_without_mutating_sdk_payload(
    rotation: int,
    upright_bbox: list[int],
) -> None:
    regions = [
        {
            "index": index,
            "label": label,
            "native_label": label,
            "content": f"原件{label}",
            "bbox_2d": list(upright_bbox),
        }
        for index, label in enumerate(("text", "table", "image"))
    ]
    before = deepcopy(regions)

    mapped = GlmSdkRemoteParser._map_regions_to_source(regions, rotation)

    assert regions == before
    assert len(mapped) == len(regions)
    for before_region, after_region in zip(regions, mapped, strict=True):
        assert after_region["bbox_2d"] == pytest.approx([100, 200, 400, 600])
        assert after_region["index"] == before_region["index"]
        assert after_region["content"] == before_region["content"]
        assert after_region["label"] == before_region["label"]


@pytest.mark.parametrize(
    ("rotation", "upright_bbox"),
    [(90, [400, 100, 800, 400]), (180, [600, 400, 900, 800]), (270, [200, 600, 600, 900])],
)
async def test_orientation_precedes_sdk_http_and_preserves_source_table_geometry(
    native_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
    rotation: int,
    upright_bbox: list[int],
) -> None:
    events: list[str] = []
    image = Image.new("RGB", (6, 10), "white")
    image.putpixel((0, 0), (255, 0, 0))
    image.putpixel((5, 9), (0, 0, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image_uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    expected_pixels = image.rotate(-rotation, expand=True)

    class Orientation:
        def orient(self, raw: str) -> tuple[str, int, float]:
            events.append("orientation")
            assert raw == image_uri
            encoded = io.BytesIO()
            expected_pixels.save(encoded, format="PNG")
            return (
                "data:image/png;base64," + base64.b64encode(encoded.getvalue()).decode("ascii"),
                rotation,
                0.999,
            )

    async def handler(request: httpx.Request) -> httpx.Response:
        events.append("sdk_http")
        assert request.method == "POST"
        payload = json.loads(request.content)
        with Image.open(
            io.BytesIO(base64.b64decode(payload["images"][0].partition(",")[2]))
        ) as sent:
            assert sent.size == expected_pixels.size
            assert sent.convert("RGB").tobytes() == expected_pixels.tobytes()
        return httpx.Response(
            200,
            json={
                "layout_details": [
                    [
                        {
                            "index": 0,
                            "label": "text",
                            "content": "原件文字",
                            "bbox_2d": upright_bbox,
                        },
                        {
                            "index": 1,
                            "label": "table",
                            "content": (
                                "<table><tr><th>原件期间</th><th>金额</th></tr>"
                                "<tr><td rowspan='2'>合并单元格原文</td><td>0.2907</td></tr>"
                                "<tr><td>0.3042</td></tr></table>"
                            ),
                            "bbox_2d": upright_bbox,
                        },
                        {
                            "index": 2,
                            "label": "image",
                            "native_label": "seal",
                            "content": "",
                            "bbox_2d": upright_bbox,
                        },
                    ]
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    parser = GlmSdkRemoteParser(
        SimpleNamespace(
            glm_ocr_enabled=True,
            glm_sdk_enabled=True,
            glm_sdk_orientation_enabled=True,
            glm_sdk_max_retries=0,
            glm_sdk_url="http://sdk:5002/glmocr/parse",
        ),
        http_client=client,
        orientation_service=Orientation(),
    )
    monkeypatch.setattr(parser, "_render_page", lambda *_args: image_uri)

    parsed = await parser.parse(_source(native_pdf), ContentParseOptions(), document_id="rotation")

    assert events == ["orientation", "sdk_http"]
    assert parsed.processed_pages == 1
    [fragment] = parsed._table_fragments
    assert fragment.normalized_bbox == pytest.approx((0.1, 0.2, 0.4, 0.6))
    assert fragment.visual_obstructions[0] == pytest.approx((0.1, 0.2, 0.4, 0.6))
    table = DocumentIRService._table(fragment)
    assert next(cell for cell in table.cells if cell.text == "合并单元格原文").row_span == 2
    assert table.source_units == [1]
    assert "0.2907" in parsed.pages[0].content
    assert "0.3042" in parsed.pages[0].content
    assert "原件文字" in parsed.pages[0].content
    await client.aclose()


async def test_sdk_request_count_measures_actual_retry_posts(native_pdf: Path) -> None:
    posts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal posts
        assert request.method == "POST"
        posts += 1
        if posts == 1:
            raise httpx.ConnectError("connection not established", request=request)
        return httpx.Response(
            200,
            json={
                "layout_details": [
                    [{"label": "text", "content": "原件文字", "bbox_2d": [0, 0, 1000, 1000]}]
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    parser = GlmSdkRemoteParser(
        SimpleNamespace(
            glm_ocr_enabled=True,
            glm_sdk_enabled=True,
            glm_sdk_orientation_enabled=False,
            glm_sdk_max_retries=1,
        ),
        http_client=client,
    )

    parsed = await parser.parse(
        _source(native_pdf), ContentParseOptions(), document_id="retry-count"
    )

    assert posts == 2
    assert parsed.pages[0]._sdk_requests == posts
    assert parsed.pages[0].content == "原件文字"
    await client.aclose()


async def test_orientation_failure_reports_zero_sdk_posts(native_pdf: Path) -> None:
    class FailedOrientation:
        def orient(self, _image: str):
            # The real initializer reports missing local model files with an
            # OSError subtype. Unexpected RuntimeError/OOM must propagate.
            raise FileNotFoundError("orientation unavailable")

    posts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal posts
        posts += 1
        raise AssertionError("SDK must not receive an image whose orientation stage failed")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    parser = GlmSdkRemoteParser(
        SimpleNamespace(
            glm_ocr_enabled=True,
            glm_sdk_enabled=True,
            glm_sdk_orientation_enabled=True,
            glm_sdk_max_retries=0,
        ),
        http_client=client,
        orientation_service=FailedOrientation(),
    )

    parsed = await parser.parse(
        _source(native_pdf), ContentParseOptions(), document_id="orientation-fail"
    )

    assert posts == 0
    assert parsed.pages[0]._sdk_requests == 0
    assert parsed.pages[0].status.value == "failed"
    await client.aclose()


@pytest.mark.parametrize("pdf_rotation", [0, 90, 180, 270])
async def test_default_pdf_render_matches_200_dpi_and_pdf_rotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pdf_rotation: int
) -> None:
    import pymupdf

    from app.config import Settings

    monkeypatch.delenv("GLM_SDK_RENDER_SCALE", raising=False)
    assert Settings(_env_file=None).glm_sdk_render_scale == pytest.approx(200 / 72)
    path = tmp_path / "rotated-source.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=360, height=720)
        page.insert_text((24, 48), "Visible source text at the original top-left")
        page.draw_rect(pymupdf.Rect(40, 100, 90, 160), color=(1, 0, 0), fill=(1, 0, 0))
        page.set_rotation(pdf_rotation)
        document.save(path)
    parser = GlmSdkRemoteParser(SimpleNamespace(glm_ocr_enabled=False))
    try:
        assert parser.scale == pytest.approx(200 / 72)
        image_uri = parser._render_page(_source(path), 1)
        with Image.open(io.BytesIO(base64.b64decode(image_uri.partition(",")[2]))) as rendered:
            expected_size = (1000, 2000) if pdf_rotation in {0, 180} else (2000, 1000)
            assert rendered.size == expected_size
            with pymupdf.open(path) as document:
                expected = document[0].get_pixmap(dpi=200, alpha=False)
            assert rendered.convert("RGB").tobytes() == expected.samples
    finally:
        await parser.close()


@pytest.mark.parametrize("pdf_rotation", [0, 90])
async def test_200_dpi_pdf_render_still_respects_maximum_image_pixels(
    tmp_path: Path, pdf_rotation: int
) -> None:
    import pymupdf

    path = tmp_path / "limited-source.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=360, height=720)
        page.insert_text((24, 48), "Source with a configured image-pixel budget")
        page.set_rotation(pdf_rotation)
        document.save(path)
    parser = GlmSdkRemoteParser(
        SimpleNamespace(glm_ocr_enabled=False, glm_sdk_max_image_pixels=500_000)
    )
    try:
        image_uri = parser._render_page(_source(path), 1)
        with Image.open(io.BytesIO(base64.b64decode(image_uri.partition(",")[2]))) as rendered:
            expected_size = (500, 1000) if pdf_rotation == 0 else (1000, 500)
            assert rendered.size == expected_size
            assert rendered.width * rendered.height <= parser.max_pixels
    finally:
        await parser.close()
