"""Known image references are distinct from unreviewed output identity."""

from moparse_eval.reporting import aggregate_reports
from moparse_eval.scoring import score_case


def test_different_asset_name_is_not_a_missing_image_judgment():
    case = {"sample_id": "synthetic", "review_status": "confirmed", "units": [
        {"id": "picture", "kind": "image", "status": "confirmed", "pages": [1],
         "reference": {"path": "references/source-picture.png"}}]}
    output = {"sample_id": "synthetic", "status": "completed", "pages": [{"page": 1, "blocks": [
        {"id": "native-picture", "kind": "image", "text": "", "asset": "assets/different-name.png"}]}]}
    scored = score_case(case, output)
    assert scored["coverage"]["known_image_targets"] == 1
    assert scored["coverage"]["image_automatic_identity_targets"] == 0
    assert scored["metrics"]["image_reference_presence"]["value"] is None
    assert scored["metrics"]["image_fidelity"]["value"] is None
    assert scored["units"][0]["reference_status"] == "confirmed"
    summary = aggregate_reports([scored])["groups"][0]["quality"]
    assert summary["coverage"]["known_image_targets"] == 1


def test_timing_only_outputs_do_not_claim_completed_quality_scoring():
    report = aggregate_reports([{"pipeline": "P01", "sample_id": "synthetic", "scorer_status": "not_scored",
                                 "phase": "preflight", "status": "completed", "metrics": {}}])
    assert report["groups"][0]["quality"]["status"] == "not_scored"
