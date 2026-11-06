"""Relation features use production authored-text compilation, not filled answers."""

import json
from copy import deepcopy

import pytest

from moparse_eval.expected_readback import read_expected
from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    evaluation_projection,
    validate_requirement_graph,
)
from moparse_eval.three_layer import grade_layers, read_candidate_markdown

REFERENCE = "# North\n\nLumen owns Kappa.\n\nSee Note 03 for more information.\n"
ENUMERATION = "- 2028年，Lumen的合作进展包括：\n  - 批准Kappa。\n  - 披露Sigma。\n"
COMPOSITION = "Notes on pages 21 to 34 are part of this statement.\n"
QUOTED = 'Lumen owns "Kappa and Sigma".\n'
CJK = "2028年，工业产值超过137万元，同比增长4.3%。\n"


def production(tmp_path, text):
    """Invent one actual selected Markdown source, then call the owning reader."""
    document = tmp_path / "invented-document"
    document.mkdir(exist_ok=True)
    (document / "expected.md").write_text(text, encoding="utf-8")
    (document / "manifest.json").write_text(json.dumps({
        "markdown": {"path": "expected.md"},
        "source_map": {"entries": [{"source_pages": [1], "markdown_lines": [1, len(text.splitlines())]}]},
    }), encoding="utf-8")
    selected = {"id": "invented-represented-feature", "document_id": "invented-document", "source_pages": [1]}
    expected = read_expected(selected, tmp_path)
    graph = compile_requirement_graph(expected)
    validate_requirement_graph(graph, expected=expected)
    assert graph["semantic_complete"], graph["unresolved"]
    return graph, evaluation_projection(graph)


@pytest.mark.parametrize("text,feature,oracle", [
    (REFERENCE, "explicit_reference_binding", [("Lumen", "own", "Kappa")]),
    (ENUMERATION, "enumeration_context_scope", [("Lumen", "批准", "Kappa"), ("Lumen", "披露", "Sigma")]),
])
def test_relation_only_features_reach_final_votes_without_fabricating_ast(tmp_path, text, feature, oracle):
    # The hand-written oracle precedes production compilation and is never
    # obtained by copying parser-created facts.
    graph, required = production(tmp_path, text)
    assert [(f["subject"], f["attribute"], f["value"]) for f in required["business"]] == oracle
    result = grade_layers(required, read_candidate_markdown(text, sample_id="invented-represented-feature"))
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["numerator"] == len(oracle)
    assert result["layers"]["L"]["numerator"] == len(graph["projections"]["L"])
    assert result["layers"]["L"]["score"] == 100
    check = result["semantic_comparison"]["feature_checks"]["expected"][feature]
    assert check["equivalent"] and check["proof"]["representation"] == "source_bound_relations"
    assert not any(tree.get("kind") in {feature, "explicit_reference", "enumeration"}
                   for tree in required["logical_statements"])
    validate_evidence(result)


@pytest.mark.parametrize("text,variation", [
    (REFERENCE, REFERENCE.replace("Note 03", "NOTE 03")),
    (ENUMERATION, ENUMERATION.replace("  - ", "    - ")),
])
def test_supported_surface_changes_keep_relation_and_business_votes(tmp_path, text, variation):
    _, required = production(tmp_path, text)
    result = grade_layers(required, read_candidate_markdown(variation, sample_id="invented-represented-feature"))
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["score"] == result["layers"]["L"]["score"] == 100
    validate_evidence(result)


@pytest.mark.parametrize("changed", [
    REFERENCE.replace("Note 03", "Note 04"),
    REFERENCE.replace("# North", "# South"),
    REFERENCE.replace("See Note 03 for more information.\n", ""),
])
def test_reference_target_owner_and_omitted_reference_are_actual_relation_losses(tmp_path, changed):
    _, required = production(tmp_path, REFERENCE)
    result = grade_layers(required, read_candidate_markdown(changed, sample_id="invented-represented-feature"))
    assert result["layers"]["L"]["numerator"] < result["layers"]["L"]["denominator"]
    assert result["layers"]["B"]["denominator"] == 1
    validate_evidence(result)


@pytest.mark.parametrize("changed", [
    ENUMERATION.replace("2028年", "2029年"),
    ENUMERATION.replace("Lumen", "Vega"),
    ENUMERATION.replace("  - 披露Sigma。\n", ""),
])
def test_collection_period_owner_and_member_loss_do_not_disappear_from_denominators(tmp_path, changed):
    _, required = production(tmp_path, ENUMERATION)
    result = grade_layers(required, read_candidate_markdown(changed, sample_id="invented-represented-feature"))
    assert result["layers"]["L"]["numerator"] < result["layers"]["L"]["denominator"]
    assert result["layers"]["B"]["denominator"] == 2
    assert result["layers"]["B"]["numerator"] < 2
    validate_evidence(result)


@pytest.mark.parametrize("text,feature,relation", [
    (REFERENCE, "explicit_reference_binding", "explicit_reference_target"),
    (ENUMERATION, "enumeration_context_scope", "enumeration_membership"),
])
@pytest.mark.parametrize("mutation", ["feature_deleted", "relation_kind_changed", "relation_deleted", "borrowed_source"])
def test_representation_mutations_block_even_when_flat_text_survives(tmp_path, text, feature, relation, mutation):
    _, required = production(tmp_path, text)
    candidate = read_candidate_markdown(text, sample_id="invented-represented-feature")
    original_text = deepcopy(candidate["text"])
    edge = next(edge for edge in candidate["relations"] if edge["type"] == relation)
    if mutation == "feature_deleted":
        candidate["required_matcher_features"].remove(feature)
    elif mutation == "relation_kind_changed":
        edge["type"] = "field_binding"
    elif mutation == "relation_deleted":
        candidate["relations"].remove(edge)
    elif feature == "enumeration_context_scope":
        evidence = edge["binding_evidence"]
        evidence["introduction_source"] = deepcopy(evidence["member_source"])
    else:
        edge["binding_evidence"]["target_source"] = deepcopy(edge["binding_evidence"]["directive_source"])
    result = grade_layers(required, candidate)
    assert candidate["text"] == original_text
    assert not result["publishable"]
    check = result["semantic_comparison"]["feature_checks"]["candidate"][feature]
    assert not check["equivalent"]
    assert result["layers"]["L"]["score"] is None
    with pytest.raises(ValueError, match="incomplete software judgments"):
        validate_evidence(result)


@pytest.mark.parametrize("text,oracle", [
    (COMPOSITION, ("Notes", "part of", "this statement")),
    ("第21页至第34页所载的附注为本财务报表的组成部分。\n", ("附注", "组成部分", "本财务报表")),
])
def test_native_document_composition_and_page_range_reach_final_votes(tmp_path, text, oracle):
    graph, required = production(tmp_path, text)
    assert [(f["subject"], f["attribute"], f["value"]) for f in required["business"]] == [oracle]
    result = grade_layers(required, read_candidate_markdown(text, sample_id=required["sample_id"]))
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["numerator"] == result["layers"]["B"]["denominator"] == 1
    assert result["layers"]["L"]["numerator"] == result["layers"]["L"]["denominator"] == len(graph["projections"]["L"]) == 2
    assert result["semantic_comparison"]["decisions"]["B"]["equivalent"]
    assert result["semantic_comparison"]["decisions"]["L"]["equivalent"]
    validate_evidence(result)


def test_composition_spacing_variation_preserves_page_endpoints_and_owner(tmp_path):
    _, required = production(tmp_path, COMPOSITION)
    candidate = read_candidate_markdown(COMPOSITION.replace("21 to 34", "21  to  34"), sample_id=required["sample_id"])
    result = grade_layers(required, candidate)
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["score"] == result["layers"]["L"]["score"] == 100
    assert any("21  to  34" in atom["text"] for atom in result["text_evidence"]["candidate_atoms"])
    validate_evidence(result)


@pytest.mark.parametrize("change", ["endpoints_reversed", "document", "component", "missing_range", "condition"])
def test_composition_changed_identity_scope_or_omitted_range_never_passes(tmp_path, change):
    _, required = production(tmp_path, COMPOSITION)
    text = {"endpoints_reversed": COMPOSITION.replace("21 to 34", "34 to 21"),
            "document": COMPOSITION.replace("this statement", "this report"),
            "component": COMPOSITION.replace("Notes", "Accompanying notes"),
            "missing_range": COMPOSITION.replace(" on pages 21 to 34", ""),
            "condition": COMPOSITION.rstrip(".\n") + " if the board approves.\n"}[change]
    result = grade_layers(required, read_candidate_markdown(text, sample_id=required["sample_id"]))
    assert not result["publishable"] or result["layers"]["B"]["numerator"] < 1 or result["layers"]["L"]["numerator"] < 2
    if result["publishable"]:
        validate_evidence(result)


@pytest.mark.parametrize("mutation", ["dependency", "kind", "endpoint_source", "document_source", "relation"])
def test_document_composition_retained_text_cannot_hide_missing_or_borrowed_structure(tmp_path, mutation):
    _, required = production(tmp_path, COMPOSITION)
    candidate = read_candidate_markdown(COMPOSITION, sample_id=required["sample_id"])
    [tree] = candidate["logical_statements"]
    if mutation == "dependency":
        candidate["required_matcher_features"].remove("page_reference_binding")
    elif mutation == "kind":
        tree["kind"] = "proposition"
    elif mutation == "endpoint_source":
        tree["page_reference"]["end"]["source"] = deepcopy(tree["page_reference"]["start"]["source"])
    elif mutation == "document_source":
        tree["document_identity"]["source"] = deepcopy(tree["subject_source"])
    else:
        candidate["relations"] = [edge for edge in candidate["relations"] if edge["type"] != "document_part_of"]
    result = grade_layers(required, candidate)
    assert not result["publishable"]
    assert result["layers"]["B"]["score"] is None and result["layers"]["L"]["score"] is None


@pytest.mark.parametrize("text,oracle,features", [
    (QUOTED, [("Lumen", "own", '"Kappa and Sigma"')], {"quoted_nominal_scope"}),
    (CJK, [("工业产值", "超过", "137"), ("工业产值", "同比增长", "4.3")],
     {"shared_period_scope", "year_on_year_comparison", "same_subject_relative_clause"}),
])
def test_existing_nominal_and_measurement_representations_own_final_judgments(tmp_path, text, oracle, features):
    graph, required = production(tmp_path, text)
    assert [(f["subject"], f["attribute"], f["value"]) for f in required["business"]] == oracle
    result = grade_layers(required, read_candidate_markdown(text, sample_id=required["sample_id"]))
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["numerator"] == len(oracle)
    assert result["layers"]["L"]["numerator"] == len(graph["projections"]["L"])
    assert result["layers"]["B"]["score"] == result["layers"]["L"]["score"] == 100
    assert all(result["semantic_comparison"]["feature_checks"]["expected"][feature]["equivalent"] for feature in features)
    validate_evidence(result)


@pytest.mark.parametrize("text,variation", [
    (QUOTED, QUOTED.replace("Kappa and Sigma", "Kappa  and Sigma")),
    (CJK, CJK.replace("137万元", "1370000元").replace("4.3%", "43‰")),
])
def test_nominal_spacing_and_exact_measurement_scale_equivalence_reach_final_votes(tmp_path, text, variation):
    _, required = production(tmp_path, text)
    result = grade_layers(required, read_candidate_markdown(variation, sample_id=required["sample_id"]))
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["score"] == result["layers"]["L"]["score"] == 100
    assert result["layers"]["B"]["denominator"] == len(required["business"])
    if text == CJK:
        assert result["layers"]["T"]["score"] < 100
    validate_evidence(result)


@pytest.mark.parametrize("changed,wrong_layer", [
    (QUOTED.replace("Kappa and Sigma", "Kappa or Sigma"), "B"),
    (QUOTED.replace("Lumen", "Vega"), "B"),
    ('"Kappa and Sigma" owns Lumen.\n', "L"),
    (QUOTED.replace('"', ''), "B"),
])
def test_quoted_nominal_owner_content_attachment_and_delimiter_loss_do_not_pass(tmp_path, changed, wrong_layer):
    _, required = production(tmp_path, QUOTED)
    result = grade_layers(required, read_candidate_markdown(changed, sample_id=required["sample_id"]))
    assert not result["publishable"] or result["layers"][wrong_layer]["numerator"] < result["layers"][wrong_layer]["denominator"]
    assert result["layers"]["B"]["denominator"] == 1
    if result["publishable"]:
        validate_evidence(result)


@pytest.mark.parametrize("changed,wrong_layer", [
    (CJK.replace("137", "138"), "B"),
    (CJK.replace("2028年", "2029年"), "L"),
    (CJK.replace("2028年，", ""), "L"),
    (CJK.replace("，同比增长4.3%", ""), "B"),
    (CJK.replace("同比增长4.3%", "港口吞吐量同比增长4.3%"), "L"),
    (CJK.replace("同比增长", "环比增长"), "B"),
    (CJK.replace("4.3%", "4.3个百分点"), "B"),
])
def test_cjk_scope_basis_member_and_value_changes_keep_their_own_layer_losses(tmp_path, changed, wrong_layer):
    _, required = production(tmp_path, CJK)
    result = grade_layers(required, read_candidate_markdown(changed, sample_id=required["sample_id"]))
    assert not result["publishable"] or result["layers"][wrong_layer]["numerator"] < result["layers"][wrong_layer]["denominator"]
    assert result["layers"]["B"]["denominator"] == 2 and result["layers"]["L"]["denominator"] == 10
    if changed == CJK.replace("137", "138"):
        assert result["layers"]["B"]["numerator"] == 1
        assert result["layers"]["L"]["score"] == 100, "wrong scalar must not erase independent relation votes"
    if result["publishable"]:
        validate_evidence(result)


@pytest.mark.parametrize("feature", ["quoted_nominal_scope", "shared_period_scope", "same_subject_relative_clause", "year_on_year_comparison"])
@pytest.mark.parametrize("mutation", ["feature_deleted", "relation_kind", "relation_deleted", "neighbor_source"])
def test_nominal_and_cjk_source_mutations_cannot_bypass_feature_checks(tmp_path, feature, mutation):
    text = QUOTED if feature == "quoted_nominal_scope" else CJK
    _, required = production(tmp_path, text)
    candidate_text = (text + '\nVega owns "Kappa and Sigma".\n' if text == QUOTED else text + "\n# 2028年\n")
    candidate = read_candidate_markdown(candidate_text, sample_id=required["sample_id"])
    own_type = {"quoted_nominal_scope": "narrative_quoted_nominal_scope", "shared_period_scope": "qualifier_scope",
                "same_subject_relative_clause": "cjk_year_on_year_subject_binding",
                "year_on_year_comparison": "cjk_year_on_year_subject_binding"}[feature]
    edges = [edge for edge in candidate["relations"] if edge["type"] == own_type]
    edge = next((edge for edge in edges if edge.get("left", {}).get("type") == "period"), edges[0])
    if mutation == "feature_deleted":
        candidate["required_matcher_features"].remove(feature)
    elif mutation == "relation_kind":
        edge["type"] = "field_binding"
    elif mutation == "relation_deleted":
        candidate["relations"].remove(edge)
    elif text == QUOTED:
        proof = candidate["business"][0]["quoted_nominals"][0]
        proof["content_source"] = deepcopy(candidate["business"][1]["quoted_nominals"][0]["content_source"])
    else:
        heading = next(node for node in candidate["syntax"] if node["kind"] == "heading")
        candidate["business"][0]["qualifier_sources"]["period"] = {**deepcopy(heading["source"]), "text_span": [0, 5]}
    result = grade_layers(required, candidate)
    assert not result["publishable"]
    assert not result["semantic_comparison"]["feature_checks"]["candidate"][feature]["equivalent"]
    assert result["layers"]["B"]["score"] is None and result["layers"]["L"]["score"] is None
