from __future__ import annotations

import hashlib
import json
import os
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from carpinova_agent.mcp_bridge import carpinova_generar_borrador, carpinova_leer_entregable
from carpinova_agent.cad_exchange import validate_exchange
from carpinova_agent.maestro import consult_maestro as maestro_consult
from carpinova_agent.pilot_cli import (
    PilotError, _hardware_reference_review, pilot_review, verify_pilot_bundle,
)
from test_m2_mixed_kitchen import FULL_UTTERANCE, guided, mixed_spec


FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")
GEOMETRY_SHA = "28845f0e3ec430af001eaec252625042ff13381e80a3a073caba81dc15f0edb6"
B3_NO_SIDECAR_SHA256 = {
    "maestro-review.json": "ced7dcb972076f294b98193ed71be47e211c50d89f5fe04fad796c32a81bed12",
    "front-review.svg": "da3dc1f01f84a38eee9bafa78554aa37568b330bc0f0d48b0e47453a28358471",
    "parts-review.csv": "91d372811c179f482148983c9bc18eb7d29606626db64b6a134229c422f66bcf",
    "cad-exchange.json": "df17b7c3752b78c71a58d7aaf442d08871c39a08fa27b778b50ed3c610137a59",
    "manifest.json": "d49e5060bb1df015e5be8fcd203cc93e8b8fa66bbaf608dad662d679802f5066",
}


def _request() -> dict:
    return {"action": "modular", "module_spec": mixed_spec()}


def _sidecar(review: dict, opening_system: str = "handle") -> str:
    source = review["nominal_draft_opening_review"]
    value = {
        "schema_version": "1.0",
        "source": "CLIENT_DECLARED_NOT_AUTHENTICATED",
        "geometry_sha256": review["nominal_draft_geometry_sha256"],
        "elements": [{
            "piece_id": item["piece_id"],
            "module_id": item["module_id"],
            "element_type": item["element_type"],
            "opening_system": opening_system,
        } for item in source["elements"]],
    }
    return json.dumps(value, ensure_ascii=False)


def _artifact(folder: Path) -> dict:
    result = carpinova_leer_entregable(
        folder.name, "hardware-reference-review.json",
    )
    return json.loads(result["contenido"])


class B4HardwareReferenceTests(unittest.TestCase):
    def test_empty_sidecar_preserves_exact_b3_bundle_bytes(self):
        result = pilot_review(_request())
        observed = {
            name: hashlib.sha256(content.encode("utf-8")).hexdigest()
            for name, content in result.items()
        }
        self.assertEqual(observed, B3_NO_SIDECAR_SHA256)
        self.assertEqual(list(result), list(B3_NO_SIDECAR_SHA256))
        manifest = json.loads(result["manifest.json"])
        self.assertNotIn("hardware-reference-review.json", manifest["files"])
        self.assertNotIn("hardware_reference_review_sha256", manifest)

    def test_mixed_bundle_links_five_rows_to_the_same_cad_and_blocks_release(self):
        review = guided(FULL_UTTERANCE, mixed_spec())
        sidecar = _sidecar(review)
        request = _request()
        with TemporaryDirectory() as root, patch.dict(
            os.environ, {"CARPINOVA_OUTPUT_ROOT": root},
        ):
            generated = carpinova_generar_borrador(
                json.dumps(request), "mixed_b4", opening_review_json=sidecar,
            )
            folder = Path(root) / "mixed_b4"
            hardware = _artifact(folder)
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            cad = json.loads((folder / "cad-exchange.json").read_text(encoding="utf-8"))
            sidecar_value = json.loads(
                (folder / "opening-intents-review.json").read_text(encoding="utf-8")
            )

            self.assertEqual(generated["geometry_sha256"], GEOMETRY_SHA)
            self.assertEqual(generated["piece_count"], 29)
            self.assertEqual(hardware["geometry_sha256"], cad["geometry_sha256"])
            self.assertEqual(hardware["status"], "REFERENCE_ONLY_NOT_SELECTED")
            self.assertEqual(hardware["approval_status"], "NOT_APPROVED_NOT_FOR_FABRICATION")
            self.assertIs(hardware["hardware_selected"], False)
            self.assertTrue(all(hardware[flag] is False for flag in FLAGS))
            self.assertEqual(manifest["geometry_sha256"], hardware["geometry_sha256"])
            self.assertIn("hardware-reference-review.json", manifest["files"])
            self.assertEqual(
                manifest["hardware_reference_contract"], "B4_DECLARED_SOURCE_V1",
            )
            self.assertEqual(
                manifest["hardware_reference_source_request"], request,
            )
            hardware_bytes = (folder / "hardware-reference-review.json").read_bytes()
            self.assertEqual(
                hashlib.sha256(hardware_bytes).hexdigest(),
                manifest["hardware_reference_review_sha256"],
            )
            self.assertEqual(sidecar_value["status"], "NOT_APPROVED_NOT_FOR_FABRICATION")
            self.assertEqual(len(hardware["elements"]), 5)

            expected = {
                item["piece_id"]: item
                for item in sidecar_value["elements"]
            }
            self.assertEqual(
                [row["piece_id"] for row in hardware["elements"]],
                sorted(expected),
            )
            self.assertEqual(
                {row["piece_id"] for row in hardware["elements"]}, set(expected),
            )
            for row in hardware["elements"]:
                source = expected[row["piece_id"]]
                self.assertEqual(
                    tuple(row[key] for key in (
                        "piece_id", "module_id", "element_type", "opening_system",
                    )),
                    tuple(source[key] for key in (
                        "piece_id", "module_id", "element_type", "opening_system",
                    )),
                )
                self.assertEqual(row["status"], "REFERENCE_ONLY_NOT_SELECTED")
                self.assertEqual(row["approval_status"], "NOT_APPROVED_NOT_FOR_FABRICATION")
                self.assertIs(row["hardware_selected"], False)
                self.assertTrue(all(row[flag] is False for flag in FLAGS))

            doors = [row for row in hardware["elements"] if row["element_type"] == "door"]
            drawers = [row for row in hardware["elements"] if row["element_type"] == "drawer"]
            self.assertEqual((len(doors), len(drawers)), (2, 3))
            for row in doors:
                self.assertEqual(row["candidate_hinge_sku"], "71B3550")
                self.assertIsNone(row["candidate_plate_sku"])
                self.assertEqual(row["f4_status"], "BLOCKED_HARDWARE_SPEC")
                self.assertTrue(all(
                    source["evidence"] == "HISTORICAL_MANUFACTURER_REFERENCE_NOT_COMPATIBILITY"
                    for source in row["sources"]
                ))
            for row in drawers:
                self.assertIn(row["drawer_id"], {"D1", "D2", "D3"})
                self.assertEqual(row["opening_system"], "handle")
                self.assertIsNone(row["slide_sku"])
                self.assertEqual(row["slide_compatibility"], "NOT_VERIFIED")
                self.assertIn("drawer_front_style_and_position", row["required_inputs"])
                self.assertNotIn("DRAWER_SOURCE_NOT_FOUND", row["blockers"])
                self.assertEqual(row["slide_clearance_reading"], {
                    "status": "DECLARED_REVIEW_ONLY",
                    "left_mm": 0,
                    "right_mm": 0,
                    "installation_status":
                        "PENDING_EXACT_SKU_DATASHEET_AND_MOUNTING",
                })
                self.assertIn(
                    "ZERO_MM_CLEARANCES_ARE_PLACEHOLDERS_NOT_INSTALLABLE",
                    row["blockers"],
                )
                self.assertTrue(row["required_inputs"])

            verified = verify_pilot_bundle(folder)
            self.assertEqual(verified["geometry_sha256"], GEOMETRY_SHA)
            self.assertTrue(all(generated[flag] is False for flag in FLAGS))

    def test_synthetic_legacy_b3_opening_only_reads_unchanged(self):
        review = guided(FULL_UTTERANCE, mixed_spec())
        package = pilot_review(_request(), opening_review_json=_sidecar(review))
        with TemporaryDirectory() as root, patch.dict(
            os.environ, {"CARPINOVA_OUTPUT_ROOT": root},
        ):
            folder = Path(root) / "legacy_b3"
            folder.mkdir()
            for name, content in package.items():
                if name == "hardware-reference-review.json":
                    continue
                if name == "manifest.json":
                    manifest = json.loads(content)
                    manifest["files"].remove("hardware-reference-review.json")
                    manifest.pop("hardware_reference_contract")
                    manifest.pop("hardware_reference_review_sha256")
                    manifest.pop("hardware_reference_source_request")
                    content = json.dumps(
                        manifest, indent=2, ensure_ascii=False,
                    ) + "\n"
                (folder / name).write_bytes(content.encode("utf-8"))

            opening_path = folder / "opening-intents-review.json"
            original_bytes = opening_path.read_bytes()
            original_sha = hashlib.sha256(original_bytes).hexdigest()
            self.assertEqual(len(json.loads(
                (folder / "manifest.json").read_text(encoding="utf-8")
            )["files"]), 6)
            self.assertEqual(
                verify_pilot_bundle(folder)["geometry_sha256"], GEOMETRY_SHA,
            )
            delivered = carpinova_leer_entregable(
                "legacy_b3", "opening-intents-review.json",
            )
            self.assertEqual(delivered["contenido"].encode("utf-8"), original_bytes)
            self.assertEqual(
                hashlib.sha256(delivered["contenido"].encode("utf-8")).hexdigest(),
                original_sha,
            )
            self.assertFalse((folder / "hardware-reference-review.json").exists())

    def test_missing_clearance_is_unknown_not_zero(self):
        package = pilot_review(
            _request(),
            opening_review_json=_sidecar(guided(FULL_UTTERANCE, mixed_spec())),
        )
        answer = json.loads(package["maestro-review.json"])
        cad = validate_exchange(json.loads(package["cad-exchange.json"]))
        opening = json.loads(package["opening-intents-review.json"])
        source_request = copy.deepcopy(_request())
        for drawer in source_request["module_spec"]["modules"][1]["drawers"]:
            drawer.pop("slide_clearance_left_mm")
            drawer.pop("slide_clearance_right_mm")

        # Isolate the review serializer branch. A real Maestro replay still
        # rejects missing geometry inputs before a package can be generated.
        hardware = _hardware_reference_review(
            opening, answer["modular"], cad, source_request,
        )
        rows = [
            row for row in hardware["elements"]
            if row["element_type"] == "drawer"
        ]
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row["slide_clearance_reading"], {
                "status": "UNKNOWN",
                "left_mm": "UNKNOWN",
                "right_mm": "UNKNOWN",
                "installation_status":
                    "PENDING_EXACT_SKU_DATASHEET_AND_MOUNTING",
            })
            self.assertIn("SLIDE_CLEARANCES_NOT_VERIFIED", row["blockers"])
            self.assertNotIn(
                "ZERO_MM_CLEARANCES_ARE_PLACEHOLDERS_NOT_INSTALLABLE",
                row["blockers"],
            )

    def test_verifier_replays_persisted_hardware_source_request(self):
        review = guided(FULL_UTTERANCE, mixed_spec())
        with TemporaryDirectory() as root, patch.dict(
            os.environ, {"CARPINOVA_OUTPUT_ROOT": root},
        ):
            carpinova_generar_borrador(
                json.dumps(_request()), "source_tampered_b4",
                opening_review_json=_sidecar(review),
            )
            folder = Path(root) / "source_tampered_b4"
            manifest_path = folder / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["hardware_reference_source_request"]["module_spec"][
                "modules"
            ][0]["width_mm"] += 1
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(PilotError, "HARDWARE_SOURCE_REPLAY_"):
                verify_pilot_bundle(folder)

    def test_b4_hardware_requires_explicit_contract_and_source(self):
        review = guided(FULL_UTTERANCE, mixed_spec())
        package = pilot_review(_request(), opening_review_json=_sidecar(review))
        cases = (
            ("contract_missing", "hardware_reference_contract",
             "B4_HARDWARE_CONTRACT_INVALID"),
            ("source_missing", "hardware_reference_source_request",
             "B4_HARDWARE_SOURCE_MISSING"),
        )
        with TemporaryDirectory() as root:
            for name, field, message in cases:
                folder = Path(root) / name
                folder.mkdir()
                for filename, content in package.items():
                    if filename == "manifest.json":
                        manifest = json.loads(content)
                        manifest.pop(field)
                        content = json.dumps(
                            manifest, indent=2, ensure_ascii=False,
                        ) + "\n"
                    (folder / filename).write_bytes(content.encode("utf-8"))
                with self.assertRaisesRegex(PilotError, message):
                    verify_pilot_bundle(folder)

    def test_book_query_is_reused_without_duplicate_hardware_source(self):
        request = {**_request(), "query": "bisagras puertas"}
        answer = maestro_consult(_request())
        answer["knowledge"] = {
            "coverage": "FULL_BOOK", "knowledge_version": "1.2.0",
            "results": [{}], "total_matches": 1,
        }
        answer["source_provenance"] = [{}]
        metadata = {"book_id": "synthetic-contract-test"}
        review = guided(FULL_UTTERANCE, mixed_spec())
        with (
            patch("carpinova_agent.pilot_cli._book_bundle", return_value={}),
            patch("carpinova_agent.pilot_cli._book_source_metadata",
                  return_value=metadata),
            patch("carpinova_agent.pilot_cli.consult_maestro", return_value=answer),
        ):
            package = pilot_review(request, opening_review_json=_sidecar(review))
            manifest = json.loads(package["manifest.json"])
            self.assertEqual(manifest["book_source_request"], request)
            self.assertNotIn("hardware_reference_source_request", manifest)
            self.assertEqual(
                manifest["hardware_reference_contract"], "B4_DECLARED_SOURCE_V1",
            )

            with TemporaryDirectory() as root:
                folder = Path(root) / "book_query_b4"
                folder.mkdir()
                for name, content in package.items():
                    (folder / name).write_bytes(content.encode("utf-8"))
                verified = verify_pilot_bundle(folder)
                self.assertEqual(
                    verified["geometry_sha256"], GEOMETRY_SHA,
                )

    def test_handle_to_push_changes_only_intent_not_geometry_or_piece_identity(self):
        review = guided(FULL_UTTERANCE, mixed_spec())
        request = _request()
        with TemporaryDirectory() as root, patch.dict(
            os.environ, {"CARPINOVA_OUTPUT_ROOT": root},
        ):
            handle = carpinova_generar_borrador(
                json.dumps(request), "handle_b4", opening_review_json=_sidecar(review, "handle"),
            )
            push = carpinova_generar_borrador(
                json.dumps(request), "push_b4",
                opening_review_json=_sidecar(review, "push_to_open"),
            )
            self.assertEqual(handle["geometry_sha256"], GEOMETRY_SHA)
            self.assertEqual(push["geometry_sha256"], GEOMETRY_SHA)
            handle_folder, push_folder = Path(root) / "handle_b4", Path(root) / "push_b4"
            handle_cad = json.loads((handle_folder / "cad-exchange.json").read_text())
            push_cad = json.loads((push_folder / "cad-exchange.json").read_text())
            self.assertEqual(handle_cad, push_cad)
            handle_rows = _artifact(handle_folder)["elements"]
            push_rows = _artifact(push_folder)["elements"]
            self.assertEqual(
                [item["piece_id"] for item in handle_rows],
                [item["piece_id"] for item in push_rows],
            )
            self.assertEqual({item["opening_system"] for item in handle_rows}, {"handle"})
            self.assertEqual({item["opening_system"] for item in push_rows}, {"push_to_open"})
            self.assertTrue(all(item["hardware_selected"] is False for item in push_rows))
            self.assertTrue(all(
                item[flag] is False for item in push_rows for flag in FLAGS
            ))

    def test_changed_id_is_rejected_before_creating_output(self):
        review = guided(FULL_UTTERANCE, mixed_spec())
        invalid = json.loads(_sidecar(review))
        invalid["elements"][0]["piece_id"] = "CARPN-B4-FAKE-ID"
        with TemporaryDirectory() as root, patch.dict(
            os.environ, {"CARPINOVA_OUTPUT_ROOT": root},
        ):
            with self.assertRaises(PilotError):
                carpinova_generar_borrador(
                    json.dumps(_request()), "invalid_b4",
                    opening_review_json=json.dumps(invalid),
                )
            self.assertFalse((Path(root) / "invalid_b4").exists())

    def test_verifier_rejects_missing_or_rehashed_tampered_artifact(self):
        review = guided(FULL_UTTERANCE, mixed_spec())
        with TemporaryDirectory() as root, patch.dict(
            os.environ, {"CARPINOVA_OUTPUT_ROOT": root},
        ):
            for name in ("missing_b4", "tampered_b4", "hash_tampered_b4"):
                carpinova_generar_borrador(
                    json.dumps(_request()), name, opening_review_json=_sidecar(review),
                )
            missing = Path(root) / "missing_b4" / "hardware-reference-review.json"
            missing.unlink()
            with self.assertRaisesRegex(PilotError, "ausente|no coinciden exactamente"):
                verify_pilot_bundle(missing.parent)

            folder = Path(root) / "tampered_b4"
            artifact_path = folder / "hardware-reference-review.json"
            altered = json.loads(artifact_path.read_text(encoding="utf-8"))
            altered["elements"][0]["piece_id"] = "UNVERIFIED-PIECE-ID"
            artifact_path.write_text(
                json.dumps(altered, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            manifest_path = folder / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["hardware_reference_review_sha256"] = hashlib.sha256(
                artifact_path.read_bytes()
            ).hexdigest()
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(PilotError, "íntegramente"):
                verify_pilot_bundle(folder)

            hash_folder = Path(root) / "hash_tampered_b4"
            manifest_path = hash_folder / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["hardware_reference_review_sha256"] = "0" * 64
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(PilotError, "Hash de revisión de herrajes"):
                verify_pilot_bundle(hash_folder)

    def test_no_sidecar_rejects_an_orphan_hardware_artifact(self):
        with TemporaryDirectory() as root, patch.dict(
            os.environ, {"CARPINOVA_OUTPUT_ROOT": root},
        ):
            carpinova_generar_borrador(json.dumps(_request()), "legacy_b4")
            folder = Path(root) / "legacy_b4"
            (folder / "hardware-reference-review.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(PilotError, "no declarada|no coinciden exactamente"):
                verify_pilot_bundle(folder)

    def test_missing_f4_candidate_stays_unknown_without_invented_sku(self):
        from carpinova_agent import conversation_flow

        review = guided(FULL_UTTERANCE, mixed_spec())
        blocked = {
            "hardware": {
                "status": "BLOCKED_HARDWARE_SPEC",
                "candidate_hinge_sku": None,
                "sources": [],
                "blockers": ["OFFICIAL_SKU_MISSING"],
                "missing_inputs": ["current_official_SKU_datasheet"],
            },
        }
        with patch.object(conversation_flow, "consult_maestro", return_value=blocked):
            package = pilot_review(
                _request(), opening_review_json=_sidecar(review),
            )
        hardware = json.loads(package["hardware-reference-review.json"])
        doors = [row for row in hardware["elements"] if row["element_type"] == "door"]
        self.assertTrue(doors)
        self.assertTrue(all(row["candidate_hinge_sku"] is None for row in doors))
        self.assertTrue(all(row["candidate_plate_sku"] is None for row in doors))

    def test_existing_helper_marks_known_zero_clearance_as_noninstallable(self):
        review = guided(FULL_UTTERANCE, mixed_spec())
        drawers = [
            row for row in review["hardware_review"]["elements"]
            if row["element_type"] == "drawer"
        ]
        self.assertEqual(len(drawers), 3)
        self.assertTrue(all(
            "ZERO_MM_CLEARANCES_ARE_PLACEHOLDERS_NOT_INSTALLABLE" in row["blockers"]
            for row in drawers
        ))
        self.assertTrue(all(
            "drawer_front_style_and_position" in row["required_inputs"]
            for row in drawers
        ))


if __name__ == "__main__":
    unittest.main()
