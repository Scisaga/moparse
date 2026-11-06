"""Independent raw-source omission oracles; no production syntax answers."""

from copy import deepcopy

import pytest

from moparse_eval.authorized_source_inventory import (
    AuthorizedSourceError,
    plan_authorized_source_inventory,
)
from moparse_eval.packaging import write_json

PATH = "<independent-authorized-expected>"


def segment(raw, *, start=1, path=PATH):
    return {"id": "raw:0", "raw": raw, "source": {"path": path, "lines": [start, start + len(raw.splitlines()) - 1]}}


def target(raw, text, *, start=1, path=PATH, cells=None):
    return {"id": f"target:{start}", "raw": raw, "raw_text": text, "text": text,
            "reference": {"path": path, "lines": [start, start + len(raw.splitlines()) - 1]}, "cells": cells or []}


def pending(inventory):
    return [row for row in inventory["obligations"] if row["status"] == "pending"]


def test_all_selected_raw_lines_exist_before_any_target_classification():
    raw = "# Published measures\n\nName: Delta\n\n- Revenue: 17\n"
    targets = [target("# Published measures\n", "Published measures"),
               target("Name: Delta\n", "Name: Delta", start=3),
               target("- Revenue: 17\n", "Revenue: 17", start=5)]
    before = deepcopy((raw, targets))
    inventory = plan_authorized_source_inventory([segment(raw)], targets)
    assert inventory["scope"] == "canonical_authorized_raw"
    assert inventory["source_complete"] is True and not pending(inventory)
    assert [row["source"]["lines"] for row in inventory["obligations"]] == [[n, n] for n in range(1, 6)]
    assert (raw, targets) == before


def test_a_completely_dropped_target_remains_an_original_raw_obligation():
    raw = "Name: Delta\n\nRevenue: 17\n"
    inventory = plan_authorized_source_inventory([segment(raw)], [target("Name: Delta\n", "Name: Delta")])
    [missing] = pending(inventory)
    assert missing["text"] == "Revenue: 17" and missing["source"]["lines"] == [3, 3]
    assert inventory["source_complete"] is False


@pytest.mark.parametrize("shortened", ["Board approves dividends.", "Board approves dividends and reviews."])
def test_retaining_whole_target_raw_cannot_explain_an_omitted_same_line_clause(shortened):
    raw = "Board approves dividends and reviews risks.\n"
    inventory = plan_authorized_source_inventory([segment(raw)], [target(raw, shortened)])
    [missing] = pending(inventory)
    assert missing["text"] == raw.strip() and missing["reason"] == "raw_payload_missing_or_altered_in_target_text"


def gfm():
    raw = "| Metric | 2027 |\n| --- | ---: |\n| Revenue | 17 |\n| Profit | |\n"
    cells = [{"id": f"cell:{row}:{column}", "row": row, "col": column,
              "row_span": 1, "col_span": 1, "text": text}
             for row, values in enumerate([["Metric", "2027"], ["Revenue", "17"], ["Profit", ""]])
             for column, text in enumerate(values)]
    return raw, cells


def test_gfm_source_cells_are_independent_of_target_raw_and_reader_cell_counts():
    raw, cells = gfm()
    inventory = plan_authorized_source_inventory([segment(raw)], [target(raw, "", cells=cells)])
    assert inventory["source_complete"] is True
    assert [(row["row"], row["column"], row["text"]) for row in inventory["obligations"] if row["kind"] == "gfm_cell"] == [
        (0, 0, "Metric"), (0, 1, "2027"), (1, 0, "Revenue"), (1, 1, "17"), (2, 0, "Profit"), (2, 1, "")]


@pytest.mark.parametrize("position", range(6))
def test_every_original_gfm_cell_including_empty_cells_survives_reader_omission(position):
    raw, cells = gfm()
    removed = cells.pop(position)
    inventory = plan_authorized_source_inventory([segment(raw)], [target(raw, "", cells=cells)])
    [missing] = pending(inventory)
    assert missing["kind"] == "gfm_cell"
    assert (missing["row"], missing["column"], missing["text"]) == (removed["row"], removed["col"], removed["text"])
    assert inventory["source_complete"] is False


@pytest.mark.parametrize("mutation", ["value", "position", "duplicate"])
def test_wrong_gfm_literal_or_binding_does_not_hide_behind_retained_table_markup(mutation):
    raw, cells = gfm()
    if mutation == "value":
        cells[3]["text"] = "19"
    elif mutation == "position":
        cells[3]["col"] = 0
    else:
        cells.append(deepcopy(cells[3]))
    inventory = plan_authorized_source_inventory([segment(raw)], [target(raw, "", cells=cells)])
    assert inventory["source_complete"] is False
    assert any(row.get("row") == 1 and row.get("column") == 1 and row["text"] == "17" for row in pending(inventory))


def test_independent_gfm_escapes_code_and_emphasis_keep_actual_literals():
    raw = "| **Metric** | `Value` |\n| --- | --- |\n| A\\|B | 17 &amp; 5 |\n"
    cells = [{"id": f"cell:{r}:{c}", "row": r, "col": c, "text": text}
             for r, values in enumerate([["Metric", "Value"], ["A|B", "17 & 5"]]) for c, text in enumerate(values)]
    inventory = plan_authorized_source_inventory([segment(raw)], [target(raw, "", cells=cells)])
    assert inventory["source_complete"] is True
    assert [row["text"] for row in inventory["obligations"] if row["kind"] == "gfm_cell"] == ["Metric", "Value", "A|B", "17 & 5"]


@pytest.mark.parametrize("raw,corrupted", [("Status_Code_Value\n", "StatusCodeValue"), ("*Risk *\n", "Risk")])
def test_literal_underscores_and_unmatched_emphasis_cannot_be_silently_removed(raw, corrupted):
    valid = plan_authorized_source_inventory([segment(raw)], [target(raw, raw.strip())])
    assert valid["source_complete"] is True
    invalid = plan_authorized_source_inventory([segment(raw)], [target(raw, corrupted)])
    assert invalid["source_complete"] is False


def test_ambiguous_nested_inline_syntax_remains_pending_instead_of_authoring_a_literal():
    raw = "***Revenue***\n"
    inventory = plan_authorized_source_inventory([segment(raw)], [target(raw, "*Revenue*")])
    assert inventory["source_complete"] is False


@pytest.mark.parametrize("raw,text", [
    ("<table><tr><td>Revenue</td><td>17</td></tr></table>\n", "Revenue17"),
    ("<statement subject=\"Delta\">Revenue 17</statement>\n", "Revenue 17"),
    (":::business\n", ":::business"),
    ("[Revenue](https://example.invalid/value)\n", "Revenue"),
])
def test_unknown_markdown_html_and_xml_keep_raw_pending_even_if_target_raw_survives(raw, text):
    inventory = plan_authorized_source_inventory([segment(raw)], [target(raw, text)])
    assert inventory["source_complete"] is False and pending(inventory)


@pytest.mark.parametrize("mutation", ["target_path", "raw_path", "raw_literal", "unselected_line", "overlap"])
def test_source_provenance_cannot_be_forged_by_retaining_correct_text(mutation):
    raw, derived = segment("Revenue: 17\n"), target("Revenue: 17\n", "Revenue: 17")
    segments = [raw]
    if mutation == "target_path":
        derived["reference"]["path"] = "<another-source>"
    elif mutation == "raw_path":
        raw["source"]["path"] = "<another-source>"
    elif mutation == "raw_literal":
        derived["raw"] = "Revenue: 19\n"
    elif mutation == "unselected_line":
        derived["reference"]["lines"] = [2, 2]
    else:
        segments.append(deepcopy(raw))
    with pytest.raises(AuthorizedSourceError, match="source|raw"):
        plan_authorized_source_inventory(segments, [derived])


def test_comment_and_spacing_controls_do_not_hide_neighboring_payload():
    raw = "<!-- declared navigation comment -->\n\nRevenue: 17\n"
    inventory = plan_authorized_source_inventory([segment(raw)], [])
    assert [row["status"] for row in inventory["obligations"]] == ["explicitly_not_applicable", "explicitly_not_applicable", "pending"]
    assert pending(inventory)[0]["text"] == "Revenue: 17"


def test_absent_raw_is_only_a_controlled_fixture_scope_and_empty_real_scope_is_incomplete():
    controlled = plan_authorized_source_inventory(None, [target("Revenue: 17\n", "Revenue: 17")])
    assert controlled["scope"] == "controlled_supplied_target_fixture"
    assert controlled["canonical_authorized_source_complete"] is False
    actual = plan_authorized_source_inventory([], [])
    assert actual["scope"] == "canonical_authorized_raw" and actual["source_complete"] is False


def test_read_expected_keeps_authorized_raw_even_when_upstream_elements_omit_a_target(tmp_path, monkeypatch):
    from moparse_eval import expected_readback

    document = tmp_path / "invented"
    document.mkdir()
    raw = "Name: Delta\n\nRevenue: 17\n"
    (document / "expected.md").write_text(raw)
    write_json(document / "manifest.json", {"markdown": {"path": "expected.md"}, "source_map": {
        "entries": [{"source_pages": [1], "markdown_lines": [1, 3]}]}})
    original = expected_readback.elements
    monkeypatch.setattr(expected_readback, "elements", lambda text: [element for element in original(text) if "Revenue" not in element.text])
    expected = expected_readback.read_expected({"id": "fixture", "document_id": "invented", "source_pages": [1]}, tmp_path)
    assert len(expected["targets"]) == 1
    assert expected["authorized_raw_segments"][0]["raw"] == raw
    inventory = plan_authorized_source_inventory(expected["authorized_raw_segments"], expected["targets"])
    assert inventory["source_complete"] is False and pending(inventory)[0]["text"] == "Revenue: 17"


def media_target(raw="![Board](assets/board.png \"Printed title\")\n", text="Board"):
    derived = target(raw, text)
    derived["inline_references"] = [{"kind": "image", "destination": "assets/board.png", "text": "Board", "title": "Printed title"}]
    return derived


def test_image_source_reference_and_caption_have_separate_literal_evidence_without_semantics():
    derived = media_target()
    inventory = plan_authorized_source_inventory([segment(derived["raw"])], [derived])
    assert inventory["source_complete"] is True
    [reference] = [row for row in inventory["obligations"] if row["kind"] == "media_reference"]
    assert reference["text"] == "assets/board.png" and reference["caption"] == "Board"
    assert reference["title"] == "Printed title" and reference["status"] == "explained"
    assert reference["interpretation_rule"] == "independently_bound_source_reference_and_caption"


@pytest.mark.parametrize("mutation", ["caption", "destination", "title", "delete_reference", "delete_target"])
def test_image_raw_alone_cannot_hide_lost_caption_destination_or_title(mutation):
    derived = media_target()
    raw = derived["raw"]
    targets = [derived]
    if mutation == "caption":
        derived["raw_text"] = derived["text"] = "Another board"
    elif mutation == "destination":
        derived["inline_references"][0]["destination"] = "assets/other-board.png"
    elif mutation == "title":
        derived["inline_references"][0]["title"] = "Another title"
    elif mutation == "delete_reference":
        derived["inline_references"] = []
    else:
        targets.clear()
    inventory = plan_authorized_source_inventory([segment(raw)], targets)
    assert inventory["source_complete"] is False
    assert any(row["kind"] == "media_reference" and row["status"] == "pending" for row in inventory["obligations"])


def test_reference_caption_does_not_explain_missing_neighboring_business_text():
    raw = "Revenue: 17; ![Board](assets/board.png \"Printed title\"); Profit: 5\n"
    derived = media_target(raw, "Revenue: 17; Board")
    inventory = plan_authorized_source_inventory([segment(raw)], [derived])
    assert inventory["source_complete"] is False
    assert any(row["kind"] == "text_payload" and row["status"] == "pending" for row in inventory["obligations"])


def test_same_caption_different_reference_positions_require_complete_sequence_and_multiplicity():
    raw = "![Board](assets/a.png) ![Board](assets/b.png)\n"
    derived = target(raw, "Board Board")
    refs = [{"kind": "image", "destination": path, "text": "Board", "title": None} for path in ["assets/a.png", "assets/b.png"]]
    derived["inline_references"] = refs
    assert plan_authorized_source_inventory([segment(raw)], [derived])["source_complete"] is True
    derived["inline_references"] = [refs[0], refs[0]]
    assert plan_authorized_source_inventory([segment(raw)], [derived])["source_complete"] is False


def test_link_reference_in_a_gfm_cell_is_bound_to_its_own_actual_cell():
    raw = "| Kind | Link |\n|---|---|\n| Policy | [Current policy](policy.md) |\n"
    cells = [{"id": f"cell:{r}:{c}", "row": r, "col": c, "text": text}
             for r, values in enumerate([["Kind", "Link"], ["Policy", "Current policy"]]) for c, text in enumerate(values)]
    refs = [{"kind": "link", "destination": "policy.md", "text": "Current policy", "title": None}]
    cells[3]["inline_references"] = refs
    assert plan_authorized_source_inventory([segment(raw)], [target(raw, "", cells=cells)])["source_complete"] is True
    cells[2]["inline_references"] = cells[3].pop("inline_references")
    assert plan_authorized_source_inventory([segment(raw)], [target(raw, "", cells=cells)])["source_complete"] is False


@pytest.mark.parametrize("raw,wanted", [
    ("**Metric:**2027\n", "**Metric:**2027"),
    ("Board________Director\n", "Board________Director"),
    ("Signature: ________\n", "Signature: ________"),
    ("Value < 17; Other > 5; $$x+1$$\n", "Value < 17; Other > 5; $$x+1$$"),
])
def test_literal_punctuation_form_blanks_and_math_are_preserved_without_interpretation(raw, wanted):
    assert plan_authorized_source_inventory([segment(raw)], [target(raw, wanted)])["source_complete"] is True
    assert plan_authorized_source_inventory([segment(raw)], [target(raw, wanted.replace(wanted[0], "", 1))])["source_complete"] is False


def test_complete_multiline_literal_code_is_bound_without_executing_or_reinterpreting_it():
    raw = "```text\nName: Delta\n![Literal code](assets/never-open.png)\n```\n"
    text = "Name: Delta\n![Literal code](assets/never-open.png)"
    inventory = plan_authorized_source_inventory([segment(raw)], [target(raw, text)])
    assert inventory["source_complete"] is True
    assert [row["kind"] for row in inventory["obligations"]] == ["syntax", "code_literal", "syntax"]
    changed = target(raw, "Name: Delta")
    assert plan_authorized_source_inventory([segment(raw)], [changed])["source_complete"] is False


def test_supported_hard_breaks_do_not_remove_a_final_literal_backslash():
    raw = "Director\\\n*Chair*\\\n2027\n"
    assert plan_authorized_source_inventory([segment(raw)], [target(raw, "Director\nChair\n2027")])["source_complete"] is True
    final = "Literal final backslash\\\n"
    assert plan_authorized_source_inventory([segment(final)], [target(final, "Literal final backslash\\")])["source_complete"] is True
    assert plan_authorized_source_inventory([segment(final)], [target(final, "Literal final backslash")])["source_complete"] is False


def test_unimplemented_source_syntax_and_missing_payload_are_distinct_pending_reasons():
    unknown = plan_authorized_source_inventory([segment("<table><tr><td>17</td></tr></table>\n")], [])
    missing = plan_authorized_source_inventory([segment("Revenue: 17\n")], [])
    assert {row["failure_kind"] for row in pending(unknown)} == {"unimplemented_syntax"}
    assert {row["failure_kind"] for row in pending(missing)} == {"parser_transport_loss"}


def test_raw_heading_scope_survives_upstream_selected_context_omission():
    raw = "# North\n\nRevenue: 17\n"
    heading = target("# North\n", "North")
    body = target("Revenue: 17\n", "Revenue: 17", start=3)
    heading["selected_heading_context"] = body["selected_heading_context"] = []
    inventory = plan_authorized_source_inventory([segment(raw)], [heading, body])
    # Text transport is intact; the separate raw scope still requires North.
    assert inventory["source_complete"] is True
    [scope] = inventory["heading_scope_obligations"]
    assert scope["source"] == {"path": PATH, "lines": [3, 3]}
    assert scope["required_scope"] == [{"text": "North", "reference": {"path": PATH, "lines": [1, 1]}}]
    assert scope["scope_status"] == "known"
    [payload] = [row for row in inventory["obligations"] if row["source"]["lines"] == [3, 3]]
    assert payload["required_scope"] == scope["required_scope"] and payload["scope_status"] == "known"


def test_nested_raw_atx_headings_pop_by_physical_depth_and_do_not_scope_themselves():
    raw = "# North\nA\n## Retail\nB\n### Direct\nC\n## Wholesale\nD\n# South\nE\n"
    texts = ["North", "A", "Retail", "B", "Direct", "C", "Wholesale", "D", "South", "E"]
    targets = [target(line, text, start=number) for number, (line, text) in enumerate(zip(raw.splitlines(keepends=True), texts, strict=True), 1)]
    inventory = plan_authorized_source_inventory([segment(raw)], targets)
    scopes = inventory["heading_scope_obligations"]
    assert [[heading["text"] for heading in row["required_scope"]] for row in scopes] == [
        ["North"], ["North", "Retail"], ["North", "Retail", "Direct"], ["North", "Wholesale"], ["South"]]
    assert [row["source"]["lines"] for row in scopes] == [[2, 2], [4, 4], [6, 6], [8, 8], [10, 10]]


def test_gfm_cells_inherit_the_same_independently_lexed_raw_heading_scope():
    table_raw, cells = gfm()
    raw = "# North\n\n" + table_raw
    inventory = plan_authorized_source_inventory([segment(raw)], [target("# North\n", "North"), target(table_raw, "", start=3, cells=cells)])
    scopes = inventory["heading_scope_obligations"]
    assert len(scopes) == 6
    assert {(row["row"], row["column"]) for row in scopes} == {(row, column) for row in range(3) for column in range(2)}
    assert all(row["required_scope"] == [{"text": "North", "reference": {"path": PATH, "lines": [1, 1]}}] for row in scopes)


def test_headings_in_literal_code_and_comments_never_change_following_raw_scope():
    code = "```text\n# Fake code heading\n```\n"
    comment = "<!--\n# Fake comment heading\n-->\n"
    raw = "# North\n" + code + comment + "Revenue: 17\n"
    inventory = plan_authorized_source_inventory([segment(raw)], [
        target("# North\n", "North"), target(code, "# Fake code heading", start=2),
        target("Revenue: 17\n", "Revenue: 17", start=8)])
    assert inventory["source_complete"] is True
    scopes = inventory["heading_scope_obligations"]
    assert len(scopes) == 2  # One literal body and one following business body.
    assert all([heading["text"] for heading in row["required_scope"]] == ["North"] for row in scopes)
    assert scopes[-1]["source"]["lines"] == [8, 8]


def test_each_authorized_gap_resets_raw_scope_without_importing_unseen_ancestors():
    first, second = "# North\nRevenue: 17\n", "Revenue: 19\n"
    inventory = plan_authorized_source_inventory([segment(first), segment(second, start=10)], [
        target("# North\n", "North"), target("Revenue: 17\n", "Revenue: 17", start=2),
        target(second, "Revenue: 19", start=10)])
    first_scope, second_scope = inventory["heading_scope_obligations"]
    assert [heading["text"] for heading in first_scope["required_scope"]] == ["North"]
    assert second_scope["required_scope"] == [] and second_scope["scope_status"] == "unclaimed"
    assert inventory["source_complete"] is True


def test_unknown_raw_heading_retains_pending_scope_instead_of_reusing_a_previous_child():
    raw = "# North\n## Retail\nA\n## <x>Unknown</x>\nB\n# South\nC\n"
    targets = [target(line, text, start=number) for number, (line, text) in enumerate(zip(
        raw.splitlines(keepends=True), ["North", "Retail", "A", "Unknown", "B", "South", "C"], strict=True), 1)]
    inventory = plan_authorized_source_inventory([segment(raw)], targets)
    first_scope, pending_scope, final_scope = inventory["heading_scope_obligations"]
    assert [heading["text"] for heading in first_scope["required_scope"]] == ["North", "Retail"]
    assert pending_scope["required_scope"] == [{"text": "North", "reference": {"path": PATH, "lines": [1, 1]}}]
    assert pending_scope["scope_status"] == "pending"
    assert pending_scope["unresolved_heading_sources"] == [{"path": PATH, "lines": [4, 4]}]
    assert [heading["text"] for heading in final_scope["required_scope"]] == ["South"]
    assert final_scope["scope_status"] == "known" and inventory["source_complete"] is False


@pytest.mark.parametrize("opening", ["<!--\n", "```text\n"])
def test_unclosed_comment_or_literal_does_not_create_headings_from_unknown_contents(opening):
    raw = "# North\n" + opening + "# Fake\nRevenue: 17\n"
    inventory = plan_authorized_source_inventory([segment(raw)], [target("# North\n", "North")])
    assert inventory["source_complete"] is False
    assert len(inventory["heading_scope_obligations"]) == 1
    [scope] = inventory["heading_scope_obligations"]
    assert [heading["text"] for heading in scope["required_scope"]] == ["North"]
    assert scope["scope_status"] == "pending"
    assert scope["source"]["lines"] == [2, 4]


def test_controlled_target_fixture_never_claims_canonical_heading_scope():
    inventory = plan_authorized_source_inventory(None, [target("# North\n", "North")])
    assert inventory["scope"] == "controlled_supplied_target_fixture"
    assert inventory["heading_scope_obligations"] == []
