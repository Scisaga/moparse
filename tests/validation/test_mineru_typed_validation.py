"""Official integration tests: real 0.5.16, invented JSON, no parser or media.

Run explicitly in the pinned isolated image. Missing/wrong dependencies are
errors, never skips or a successful substitute for an official call.
"""

from __future__ import annotations

import argparse
import copy
import inspect
import json
import resource
import sys
import unittest
from pathlib import Path

from app.adapters.mineru_native import read_middle_page
from moparse_eval.mineru_typed_validation import (
    DependencyUnavailable,
    OfficialAPI,
    TextOnlyBoundary,
    attempt_projection,
    compare_common,
    differences,
    require_pinned_version,
    validate_native,
)


def text(value, index, **fields):
    return {
        "type": "text",
        "index": index,
        "bbox": [0.1, 0.1, 0.9, 0.2],
        "content": [{"type": "text", "content": value, "styles": []}],
        **fields,
    }


def native(blocks):
    return {
        "pipeline": "P06",
        "documents": [
            {
                "schema": "docvortex.middle",
                "schema_version": "2.0",
                "is_full_document": False,
                "metadata": {
                    "file_suffix": "pdf",
                    "producer": {"name": "controlled-fixture", "version": "1"},
                },
                "extensions": {"mineru": {"tier": "standard", "parse_mode": "txt"}},
                "pages": [{"page_idx": 0, "blocks": blocks}],
            }
        ],
        "pages": [
            {
                "page": 1,
                "branch": "mineru",
                "raw": {"page_idx": 0, "native_document": "#/documents/0"},
            }
        ],
    }


class OfficialValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = OfficialAPI()
        cls.diagnostics = {}

    def validate(self, source):
        before = copy.deepcopy(source)
        result = validate_native(source, "controlled-fixture-not-real-artifact", "P06", self.api)
        self.assertEqual(source, before)
        self.assertTrue(result["input_unchanged"])
        return result

    def test_actual_version_and_official_type_paths(self):
        require_pinned_version(self.api.distribution.version)
        self.assertEqual(self.api.distribution.version, "0.5.16")
        typed = self.api.page_block.validate_python(text("Real official class", 0))
        self.assertEqual(type(typed).__module__, "docvortex.schema")
        self.assertTrue(
            Path(inspect.getfile(type(typed))).is_relative_to(
                Path(self.api.distribution.locate_file("docvortex"))
            )
        )
        self.assertNotIn("native_worker.server", sys.modules)

    def test_wrong_version_is_refused_without_metadata_patching(self):
        with self.assertRaisesRegex(DependencyUnavailable, "found 0.5.17"):
            require_pinned_version("0.5.17")

    def test_bad_block_keeps_original_slot_and_good_siblings(self):
        source = native(
            [text("Same literal", 0), {"type": "unregistered", "index": 1}, text("Same literal", 2)]
        )
        result = self.validate(source)
        rows = result["objects"]
        self.assertEqual(
            [r["path"] for r in rows], [f"#/documents/0/pages/0/blocks/{i}" for i in range(3)]
        )
        self.assertEqual(
            [r["schema"]["status"] for r in rows], ["accepted", "rejected", "accepted"]
        )
        self.assertEqual(rows[1]["raw_payload"], source["documents"][0]["pages"][0]["blocks"][1])
        self.assertEqual(rows[2]["projection"]["text"], "Same literal")

    def test_bad_nested_block_keeps_valid_children(self):
        block = {
            "type": "list",
            "index": 0,
            "bbox": [0.1, 0.1, 0.9, 0.5],
            "content": [
                text("1、First", 1),
                {"type": "unregistered", "index": 2},
                text("3、Last", 3),
            ],
        }
        rows = self.validate(native([block]))["objects"]
        self.assertEqual(
            [r["schema"]["status"] for r in rows], ["rejected", "accepted", "rejected", "accepted"]
        )
        self.assertEqual(rows[-1]["path"], "#/documents/0/pages/0/blocks/0/content/2")
        self.assertEqual(rows[-1]["projection"]["text"], "3、Last")

    def test_defaults_and_compact_omissions_are_observed(self):
        row = self.validate(native([text("Default fields", 0)]))["objects"][0]
        full, compact = row["serialization"]["full"], row["serialization"]["to_dict"]
        self.assertIsNone(full["continues_prev"])
        self.assertNotIn("continues_prev", compact)
        self.assertNotIn("styles", compact["content"][0])
        self.assertTrue(
            any(
                r["path"] == "/continues_prev" and r["operation"] == "added"
                for r in row["serialization"]["full_diff"]
            )
        )
        self.assertFalse(row["serialization"]["derived_fields_are_native_observations"])

    def test_none_false_zero_empty_and_missing_stay_distinct(self):
        self.assertEqual(len(differences({"x": None}, {})), 1)
        self.assertEqual(len(differences({"x": False}, {"x": 0})), 1)
        self.assertEqual(len(differences({"x": ""}, {"x": None})), 1)
        row = self.validate(native([text("Zero index", 0, continues_prev=False)]))["objects"][0]
        self.assertEqual(row["serialization"]["to_dict"]["index"], 0)
        self.assertIs(row["serialization"]["to_dict"]["continues_prev"], False)

    def test_strict_types_and_unknown_fields_are_rejected(self):
        for source in [text("Strict", "0"), text("Unknown", 0, unrecognized=0)]:
            with self.subTest(source=source):
                with self.assertRaises(self.api.validation_error):
                    self.api.page_block.validate_python(source)

    def test_lists_keep_container_members_printed_numbers_and_parentage(self):
        child = {"type": "list", "index": 3, "content": [text("a) Nested", 4)]}
        source = native(
            [
                {
                    "type": "list",
                    "index": 0,
                    "bbox": [0.1, 0.1, 0.9, 0.6],
                    "content": [text("1、First", 1), text("2、Second", 2), child],
                }
            ]
        )
        result = self.validate(source)
        self.assertEqual(result["summary"]["common_comparison"], {"retained": 5})
        self.assertEqual(result["summary"]["text_comparison"], {"retained": 5})
        rows = result["objects"]
        self.assertEqual(len(rows[0]["original_children"]), 3)
        self.assertEqual(rows[-1]["parent_path"], rows[-2]["path"])
        self.assertIn("a) Nested", rows[0]["projection"]["text"])

    def test_same_literal_and_sorted_indices_do_not_supply_identity(self):
        source = native([text("Same", 2), text("Same", 1)])
        blocks, _, _ = read_middle_page(source, source["pages"][0])
        self.assertTrue(blocks[0]["native_path"].endswith("/1"))
        result = self.validate(source)
        self.assertEqual(result["summary"]["common_comparison"], {"retained": 2})
        a, b = result["objects"]
        self.assertNotEqual(a["path"], b["path"])
        wrong = compare_common(
            source["documents"][0]["pages"][0]["blocks"][0], blocks[0], None, a["path"]
        )
        self.assertEqual(wrong["status"], "different")
        self.assertFalse(wrong["checks"]["native_path"])

    def test_rich_inline_normalization_is_not_an_occurrence_mapping(self):
        block = text("unused", 0)
        block["content"] = [
            {"type": "text", "content": "Bold", "styles": ["italic", "bold", "italic"]},
            {"type": "text", "content": " continuation", "styles": ["bold", "italic"]},
            {
                "type": "hyperlink",
                "url": "https://example.invalid/info",
                "content": [{"type": "text", "content": " link", "styles": []}],
            },
        ]
        row = self.validate(native([block]))["objects"][0]
        self.assertEqual(row["common"]["status"], "retained")
        self.assertEqual(row["text_comparison"]["status"], "retained")
        self.assertEqual(len(row["inline_occurrences"]), 3)
        self.assertEqual(len(row["serialization"]["full"]["content"]), 2)
        self.assertEqual(row["serialization"]["full"]["content"][0]["styles"], ["bold", "italic"])
        self.assertTrue(
            any(
                r.get("operation") == "official_list_normalization"
                for r in row["serialization"]["construction_changes"]
            )
        )
        links = [
            a for a in row["common"]["projection"]["inline_annotations"] if a["type"] == "link"
        ]
        self.assertEqual(links[0]["target"], "https://example.invalid/info")

    def test_table_html_spans_caption_and_note_keep_own_sources(self):
        html = '<table><tr><td rowspan="2">Group</td><td>A</td></tr><tr><td>17</td></tr></table>'
        box = [0.1, 0.1, 0.9, 0.5]
        source = native(
            [
                {
                    "type": "table",
                    "index": 0,
                    "bbox": box,
                    "content": [
                        text("Caption", 1, type="table_caption"),
                        {"type": "table_body", "index": 0, "bbox": box, "content": html},
                        text("Printed note", 2, type="table_footnote"),
                    ],
                }
            ]
        )
        rows = self.validate(source)["objects"]
        self.assertEqual(rows[0]["original_children"], [r["path"] for r in rows[1:]])
        body = next(r for r in rows if r["native_type"] == "table_body")
        cells = body["common"]["projection"]["cells"]
        self.assertEqual(
            [(c["row"], c["col"], c["row_span"], c["text"]) for c in cells],
            [(0, 0, 2, "Group"), (0, 1, 1, "A"), (1, 1, 1, "17")],
        )
        self.assertEqual(body["serialization"]["full"]["content"], html)
        self.assertEqual(rows[-1]["projection"]["text"], "Printed note")

    def test_media_callback_has_no_io_and_never_delivers_assets(self):
        box = [0.1, 0.1, 0.9, 0.5]
        source = native(
            [
                {
                    "type": "image",
                    "index": 0,
                    "bbox": box,
                    "content": [
                        {
                            "type": "image_body",
                            "index": 0,
                            "bbox": box,
                            "content": "",
                            "image_base64": "intentionally-not-image-data",
                            "image_path": "unavailable.png",
                        },
                    ],
                }
            ]
        )
        result = self.validate(source)
        calls = result["objects"][0]["media_callback_calls"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["delivery"], "declaration_only_not_delivered")
        self.assertIn("no asset delivered", result["objects"][0]["projection"]["text"])
        self.assertTrue(sys.getprofile() is not None)

    def test_projection_failure_upstream_state_and_engineering_error_are_separate(self):
        body = self.api.block.validate_python({"type": "table_body", "index": 0, "content": ""})
        failed = attempt_projection(
            lambda: self.api.renderer(
                body,
                delimiters=self.api.delimiters,
                asset_base_url="",
                image_renderer=lambda _: "declaration",
            )
        )
        self.assertEqual(failed["reason"], "official_text_projection_failed")
        source = native(
            [
                text("Still available", 0, status="failed", error="upstream marker"),
                text("Legal sibling", 1),
            ]
        )
        result = self.validate(source)
        self.assertEqual(result["objects"][0]["upstream_state"]["status"], "failed")
        self.assertEqual(result["objects"][0]["schema"]["status"], "rejected")
        self.assertEqual(result["objects"][1]["projection"]["status"], "rendered")

        def engineering_error():
            raise RuntimeError("controlled implementation exception")

        self.assertEqual(attempt_projection(engineering_error)["reason"], "engineering_exception")

    def test_full_dump_nested_null_is_rejected_but_compact_roundtrip_accepts(self):
        source = native(
            [
                {
                    "type": "list",
                    "index": 0,
                    "bbox": [0.1, 0.1, 0.9, 0.5],
                    "content": [text("1、Printed member", 1)],
                }
            ]
        )
        typed = self.api.schema.MiddleJson.from_dict(source["documents"][0])
        full, compact = typed.model_dump(mode="json"), typed.to_dict()
        self.assertIsNone(full["pages"][0]["blocks"][0]["content"][0]["continues_prev"])
        with self.assertRaisesRegex(
            self.api.validation_error, "nested blocks must not contain continues_prev"
        ):
            self.api.schema.MiddleJson.from_dict(full)
        self.api.schema.MiddleJson.from_dict(compact)
        source["documents"][0] = full
        result = self.validate(source)
        self.assertEqual(result["summary"]["document_schema"], {"rejected": 1})
        self.assertEqual(result["summary"]["object_schema"], {"accepted": 2})
        self.assertEqual(result["summary"]["object_projection"], {"rendered": 2})
        self.diagnostics["synthetic_full_dump_roundtrip"] = {
            "purpose": "synthetic_only; not a repaired real input",
            "full_dump": full,
            "compact": compact,
            "original_full_dump_schema": result["documents"][0]["schema"],
            "compact_synthetic_roundtrip": "accepted_by_actual_MiddleJson.from_dict",
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("historical test evidence cannot be overwritten")
    boundary = TextOnlyBoundary()
    boundary.install()
    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OfficialValidationTests)

    class Executed(unittest.TextTestResult):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.executed = []

        def startTest(self, test):
            self.executed.append(test.id())
            super().startTest(test)

    result = unittest.TextTestRunner(verbosity=2, resultclass=Executed).run(suite)
    record = {
        "interpreter": sys.executable,
        "tests_run": result.testsRun,
        "executed": result.executed,
        "failures": [(t.id(), message) for t, message in result.failures],
        "errors": [(t.id(), message) for t, message in result.errors],
        "skipped": [(t.id(), message) for t, message in result.skipped],
        "boundary_violations": boundary.violations,
        "official_dependency": getattr(
            getattr(OfficialValidationTests, "api", None), "distribution", None
        ).version
        if hasattr(OfficialValidationTests, "api")
        else "not_executed",
        "synthetic_diagnostics": getattr(OfficialValidationTests, "diagnostics", {}),
    }
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return int(not result.wasSuccessful() or bool(result.skipped) or bool(boundary.violations))


if __name__ == "__main__":
    raise SystemExit(main())
