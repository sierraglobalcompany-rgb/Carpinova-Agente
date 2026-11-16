from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from carpinova_agent.cad_exchange import cad_exchange, validate_exchange
from carpinova_agent.maestro import consult_maestro
from carpinova_agent.pilot_cli import verify_pilot_bundle, write_pilot_bundle
from test_m2_mixed_kitchen import BASE_SPEC_JSON, mixed_spec

EXPECTED_GEOMETRY_SHA256 = "28845f0e3ec430af001eaec252625042ff13381e80a3a073caba81dc15f0edb6"
EXPECTED_FIXTURE_SHA256 = "3b044d5321d97275926cf20a5583bdc64d06a12beeed4bcf5075e93d27442f6b"
FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")
DOOR_ROLES = {"front_left", "front_right", "front_single"}


def _normalized_fixture_bytes(payload: bytes) -> bytes:
    normalized = payload.replace(b"\r\n", b"\n")
    if b"\r" in normalized:
        raise ValueError("fixture contains a nonstandard carriage return")
    return normalized


def _request(spec: dict | None = None) -> dict:
    return {"action": "modular", "module_spec": spec or mixed_spec()}


def _prepared_exchange(request: dict) -> dict:
    answer = consult_maestro(request)
    if answer.get("status") != "DRAFT_NOT_FOR_CUTTING":
        raise AssertionError("Maestro did not return a nominal draft")
    return validate_exchange(cad_exchange(answer["modular"]))


def _opening_input(exchange: dict) -> dict:
    elements = []
    for box in exchange["boxes"]:
        role = box.get("role")
        if role in DOOR_ROLES or role == "drawer_facade":
            elements.append({
                "piece_id": box["piece_id"],
                "module_id": box["module_id"],
                "element_type": "drawer" if role == "drawer_facade" else "door",
                "opening_system": "handle",
            })
    return {
        "schema_version": "1.0",
        "source": "CLIENT_DECLARED_NOT_AUTHENTICATED",
        "geometry_sha256": exchange["geometry_sha256"],
        "elements": sorted(elements, key=lambda item: item["piece_id"]),
    }


class MixedKitchenDrawerFixtureTests(unittest.TestCase):
    def test_fixture_matches_existing_mixed_spec_and_maestro_geometry(self) -> None:
        fixture_path = ROOT / "examples" / "modular-mixed-kitchen-b5.json"
        fixture_bytes = fixture_path.read_bytes()
        fixture = json.loads(fixture_bytes.decode("utf-8"))
        self.assertEqual(fixture, mixed_spec())
        self.assertEqual(fixture, json.loads(BASE_SPEC_JSON))
        normalized_bytes = _normalized_fixture_bytes(fixture_bytes)
        self.assertEqual(
            hashlib.sha256(normalized_bytes).hexdigest(), EXPECTED_FIXTURE_SHA256,
        )

        reply = consult_maestro(_request(fixture))
        exchange = validate_exchange(cad_exchange(reply["modular"]))
        self.assertEqual(reply["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(len(exchange["boxes"]), 29)
        self.assertEqual(exchange["geometry_sha256"], EXPECTED_GEOMETRY_SHA256)
        openings = _opening_input(exchange)["elements"]
        self.assertEqual(
            sorted(item["element_type"] for item in openings),
            ["door", "door", "drawer", "drawer", "drawer"],
        )
        drawer_ids = {d["drawer_id"] for m in fixture["modules"]
                      if isinstance(m.get("drawers"), list)
                      for d in m["drawers"]}
        self.assertEqual(drawer_ids, {"D1", "D2", "D3"})
        self.assertEqual(len({item["piece_id"] for item in openings}), 5)

    def test_fixture_hash_normalizes_lf_and_crlf_but_rejects_corruption(self) -> None:
        fixture_path = ROOT / "examples" / "modular-mixed-kitchen-b5.json"
        lf_bytes = _normalized_fixture_bytes(fixture_path.read_bytes())
        crlf_bytes = lf_bytes.replace(b"\n", b"\r\n")
        lf_normalized = _normalized_fixture_bytes(lf_bytes)
        crlf_normalized = _normalized_fixture_bytes(crlf_bytes)
        self.assertEqual(lf_normalized, crlf_normalized)
        self.assertEqual(
            hashlib.sha256(lf_normalized).hexdigest(), EXPECTED_FIXTURE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(crlf_normalized).hexdigest(), EXPECTED_FIXTURE_SHA256,
        )

        altered_fixture = json.loads(lf_normalized.decode("utf-8"))
        altered_fixture["width_mm"] += 1
        changed = _normalized_fixture_bytes(json.dumps(
            altered_fixture, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8"))
        self.assertNotEqual(
            hashlib.sha256(changed).hexdigest(), EXPECTED_FIXTURE_SHA256,
        )
        with self.assertRaisesRegex(ValueError, "nonstandard carriage return"):
            _normalized_fixture_bytes(lf_bytes + b"\rvalue")

    def test_pilot_bundle_binds_cad_and_both_review_sidecars(self) -> None:
        request = _request()
        exchange = _prepared_exchange(request)
        opening_input = _opening_input(exchange)
        self.assertEqual(set(opening_input), {
            "schema_version", "source", "geometry_sha256", "elements",
        })
        self.assertEqual(len(opening_input["elements"]), 5)
        self.assertEqual(
            [item["element_type"] for item in opening_input["elements"]].count("door"), 2,
        )
        self.assertEqual(
            [item["element_type"] for item in opening_input["elements"]].count("drawer"), 3,
        )

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "cocina_mixta_b5"
            manifest = write_pilot_bundle(
                request, folder,
                opening_review_json=json.dumps(opening_input, ensure_ascii=False),
            )
            verified = verify_pilot_bundle(folder)
            self.assertEqual(verified, exchange)
            self.assertEqual(manifest["piece_count"], 29)
            self.assertEqual(manifest["geometry_sha256"], EXPECTED_GEOMETRY_SHA256)
            self.assertTrue(all(manifest[flag] is False for flag in FLAGS))
            self.assertIn("opening-intents-review.json", manifest["files"])
            self.assertIn("hardware-reference-review.json", manifest["files"])

            answer = json.loads((folder / "maestro-review.json").read_text(encoding="utf-8"))
            cad = json.loads((folder / "cad-exchange.json").read_text(encoding="utf-8"))
            opening_bytes = (folder / "opening-intents-review.json").read_bytes()
            hardware_bytes = (folder / "hardware-reference-review.json").read_bytes()
            opening = json.loads(opening_bytes.decode("utf-8"))
            hardware = json.loads(hardware_bytes.decode("utf-8"))
            saved_manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(cad, exchange)
            self.assertEqual(answer["status"], "DRAFT_NOT_FOR_CUTTING")
            self.assertTrue(all(answer[flag] is False for flag in FLAGS))
            self.assertTrue(all(answer["modular"][flag] is False for flag in FLAGS))
            self.assertEqual(opening["status"], "NOT_APPROVED_NOT_FOR_FABRICATION")
            self.assertIs(opening["hardware_selected"], False)
            self.assertEqual(
                hashlib.sha256(opening_bytes).hexdigest(),
                saved_manifest["opening_intents_review_sha256"],
            )
            self.assertEqual(
                hashlib.sha256(hardware_bytes).hexdigest(),
                saved_manifest["hardware_reference_review_sha256"],
            )
            expected = {item["piece_id"]: item for item in opening_input["elements"]}
            self.assertEqual(
                {item["piece_id"]: item for item in opening["elements"]}, expected,
            )
            rows = {item["piece_id"]: item for item in hardware["elements"]}
            self.assertEqual(set(rows), set(expected))
            self.assertEqual(hardware["geometry_sha256"], exchange["geometry_sha256"])
            self.assertEqual(hardware["status"], "REFERENCE_ONLY_NOT_SELECTED")
            self.assertIs(hardware["hardware_selected"], False)
            self.assertTrue(all(hardware[flag] is False for flag in FLAGS))

            doors = [row for row in rows.values() if row["element_type"] == "door"]
            self.assertEqual(len(doors), 2)
            for row in doors:
                self.assertEqual(row["f4_status"], "BLOCKED_HARDWARE_SPEC")
                self.assertIsNone(row["candidate_plate_sku"])
                self.assertIs(row["hardware_selected"], False)
                self.assertTrue(all(
                    source["evidence"] == "HISTORICAL_MANUFACTURER_REFERENCE_NOT_COMPATIBILITY"
                    for source in row["sources"]
                ))

            drawers = [row for row in rows.values() if row["element_type"] == "drawer"]
            self.assertEqual(len(drawers), 3)
            self.assertEqual({row["drawer_id"] for row in drawers}, {"D1", "D2", "D3"})
            for row in drawers:
                self.assertIsNone(row["slide_sku"])
                self.assertEqual(row["slide_compatibility"], "NOT_VERIFIED")
                self.assertEqual(row["slide_clearance_reading"], {
                    "status": "DECLARED_REVIEW_ONLY",
                    "left_mm": 0,
                    "right_mm": 0,
                    "installation_status": "PENDING_EXACT_SKU_DATASHEET_AND_MOUNTING",
                })
                self.assertIn(
                    "ZERO_MM_CLEARANCES_ARE_PLACEHOLDERS_NOT_INSTALLABLE",
                    row["blockers"],
                )
                self.assertIs(row["hardware_selected"], False)
                self.assertIs(row["drilling_ready"], False)
                self.assertIs(row["purchase_ready"], False)

    def test_runner_adds_b5_to_existing_session_without_third_case(self) -> None:
        runner_path = ROOT / "scripts" / "verify_local_mcp.py"
        source = runner_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        cases = next(
            node.value for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "CASES"
                    for target in node.targets)
        )
        self.assertEqual(ast.literal_eval(cases), (
            ("primer_mueble", "pilot-open-kitchen-800.json", 4),
            ("cocina_dos_modulos", "modular-kitchen-door-fronts.json", 13),
        ))
        self.assertEqual(source.count("MCP_B5_MIXED_DRAWERS_PASS=cocina_mixta_b5"), 1)
        b3_end = source.index("MCP_B3_OPENING_NEGATIVE_PASS=")
        b5_start = source.index("B5_MIXED_DRAWERS")
        marker = source.index("MCP_B5_MIXED_DRAWERS_PASS=cocina_mixta_b5")
        self.assertGreater(b5_start, b3_end)
        self.assertGreater(marker, b5_start)
        b5_block = source[b5_start:marker]
        self.assertIn("session.call_tool(\n                \"carpinova_generar_borrador\"", b5_block)
        self.assertIn("_read_payload_via_mcp", b5_block)
        for filename in (
            "cad-exchange.json", "manifest.json",
            "opening-intents-review.json", "hardware-reference-review.json",
        ):
            self.assertIn(filename, b5_block)
        self.assertIn('"carpinova_leer_entregable"', source)
        self.assertNotIn("ClientSession(", b5_block)
        after_marker = source[marker:source.index("def validate_artifacts", marker)]
        self.assertNotIn("session.call_tool", after_marker)
        self.assertIn("carpinova_agent.cad_exchange import cad_exchange, validate_exchange", source)
        self.assertIn("from carpinova_agent.maestro import consult_maestro", source)


if __name__ == "__main__":
    unittest.main()
