from __future__ import annotations

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from carpinova_agent.cad_exchange import validate_exchange
from carpinova_agent.mcp_bridge import carpinova_consultar
from carpinova_agent.pilot_cli import verify_pilot_bundle, write_pilot_bundle
from test_b3_product_families import tower_text
from test_m2_mixed_kitchen import FULL_UTTERANCE


FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready",
         "purchase_ready", "can_generate_f7c")
HIGH_UTTERANCE = (
    "Mueble superior de cocina suspendido, 1000 mm ancho × 700 mm alto × "
    "350 mm fondo de carcasa. Melamina de 15 mm, laterales continuos, dos "
    "puertas sobrepuestas, interior abierto, sin cajones ni mesón, fondo "
    "trasero pendiente. Va fijado al muro, pero la instalación y los chazos "
    "los define un instalador."
)
LOWER_CONFIRM = (
    "Sí, confirmo las proporciones iguales, la franja geométrica de 28 mm "
    "y la caja ilustrativa pendiente de revisar con la corredera exacta. "
    "También confirmo las luces nominales de puertas propuestas."
)
LOWER_WIDTH_CONFIRM = (
    "Sí, confirmo las nuevas proporciones y la separación geométrica "
    "propuestas, luces de puertas y placeholders de caja solo ilustrativos."
)


def ask(state: dict | None, group: str, utterance: str) -> dict:
    request = {
        "review_kind": "kitchen_linear_v1", "target_group": group,
        "utterance": utterance, "review_state": copy.deepcopy(state),
    }
    return carpinova_consultar(json.dumps(request, ensure_ascii=False))


def make_l1() -> dict:
    state = None
    for group, utterance in (
        ("BAJO", FULL_UTTERANCE), ("BAJO", LOWER_CONFIRM),
        ("BAJO", "Ubicar BAJO: X=0 mm, Y=0 mm, Z=0 mm"),
        ("ALTO", HIGH_UTTERANCE),
        ("ALTO", "Para este boceto, déjalo sin fondo posterior."),
        ("ALTO", "Ubicar ALTO: X=0 mm, Y=1450 mm, Z=0 mm"),
        ("TORRE", tower_text(reserve=False)),
        ("TORRE", "Ubicar TORRE: X=1100 mm, Y=0 mm, Z=0 mm"),
    ):
        result = ask(state, group, utterance)
        state = result["review_state"]
    return result


class LinearKitchenCoordinatorTests(unittest.TestCase):
    def assert_safe(self, result: dict) -> None:
        for flag in FLAGS:
            self.assertIs(result[flag], False, flag)

    def test_l1_natural_groups_maestro_cad_packages_and_wall_warning(self) -> None:
        result = make_l1()
        self.assertEqual(result["assemblage_status"], "REVIEW_ONLY_VALID")
        self.assertEqual(result["collisions"], [])
        groups = {item["group_id"]: item for item in result["groups"]}
        self.assertEqual(set(groups), {"BAJO", "ALTO", "TORRE"})
        self.assertEqual(groups["BAJO"]["origin_xyz_mm"], [0, 0, 0])
        self.assertEqual(groups["ALTO"]["origin_xyz_mm"], [0, 1450, 0])
        self.assertEqual(groups["TORRE"]["origin_xyz_mm"], [1100, 0, 0])
        self.assertTrue(all(groups[g]["piece_count"] > 0 for g in groups))
        self.assertTrue(all(len(groups[g]["geometry_sha256"]) == 64 for g in groups))
        self.assertEqual(len(result["global_piece_ids"]), len(set(result["global_piece_ids"])))
        self.assertTrue(any("NOT_CERTIFIED_INSTALLATION" in warning
                            for warning in result["warnings"]))
        self.assertTrue(any("NO_ANCHORS_OR_LOAD_CAPACITY_ARE_PROPOSED" in warning
                            for warning in result["warnings"]))
        self.assert_safe(result)

        # Exercise real package writer/verifier from each re-derived group request.
        internal = result["review_state"]["working"]
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for group in ("BAJO", "ALTO", "TORRE"):
                from carpinova_agent.kitchen_linear import _rebuild_group
                review = _rebuild_group(group, internal["groups"][group]["history"])
                # Reconstruct the exact natural-language-to-Maestro handoff.
                from carpinova_agent.conversation_flow import prepare_guided_design_v1
                state = None
                guided = None
                for text in internal["groups"][group]["history"]:
                    guided = prepare_guided_design_v1({
                        "review_kind": "guided_design_v1", "utterance": text,
                        "review_state": state, "review_updates": [],
                        "photo_observations": None,
                    })
                    state = guided["review_state"]
                request = guided["nominal_draft_request"]
                out = root / group
                manifest = write_pilot_bundle(request, out)
                verified = verify_pilot_bundle(out)
                exchange = validate_exchange(json.loads((out / "cad-exchange.json").read_text(encoding="utf-8")))
                self.assertEqual(manifest["status"], "DRAFT_NOT_FOR_CUTTING")
                self.assertEqual(verified["geometry_sha256"], groups[group]["geometry_sha256"])
                self.assertEqual(exchange["geometry_sha256"], groups[group]["geometry_sha256"])

    def test_l2_move_changes_only_layout_digest(self) -> None:
        base = make_l1()
        before = {item["group_id"]: item["geometry_sha256"] for item in base["groups"]}
        moved = ask(base["review_state"], "TORRE",
                    "Mover TORRE: X=1050 mm, Y=0 mm, Z=0 mm")
        after = {item["group_id"]: item["geometry_sha256"] for item in moved["groups"]}
        self.assertEqual(moved["assemblage_status"], "REVIEW_ONLY_VALID")
        self.assertEqual(before, after)
        self.assertNotEqual(base["layout_sha256"], moved["layout_sha256"])
        self.assertIsNone(moved["pending_candidate"])
        self.assert_safe(moved)

    def test_l3_collision_keeps_last_valid_and_reports_intervals(self) -> None:
        valid = ask(make_l1()["review_state"], "TORRE",
                    "Mover TORRE: X=1050 mm, Y=0 mm, Z=0 mm")
        collision = ask(valid["review_state"], "ALTO",
                        "Mover ALTO: X=0 mm, Y=650 mm, Z=0 mm")
        self.assertEqual(collision["assemblage_status"], "NEEDS_USER_CONFIRMATION")
        self.assertEqual(collision["collisions"][0]["groups"], ["BAJO", "ALTO"])
        self.assertEqual({item["axis"] for item in collision["collisions"][0]["overlap_axes"]},
                         {"X", "Y", "Z"})
        self.assertEqual(collision["pending_candidate"]["status"], "PENDING_COLLISION")
        self.assertEqual(collision["last_valid_summary"]["layout_sha256"],
                         valid["layout_sha256"])
        self.assert_safe(collision)

    def test_l4_width_recomposes_only_target_and_resolves_candidate(self) -> None:
        state = make_l1()["review_state"]
        moved = ask(state, "TORRE", "Mover TORRE: X=1050 mm, Y=0 mm, Z=0 mm")
        before = {item["group_id"]: item["geometry_sha256"] for item in moved["groups"]}
        changed = ask(moved["review_state"], "BAJO", "La carcasa ahora tiene 1100 mm de ancho.")
        self.assertEqual(changed["pending_candidate"]["status"], "PENDING_REVIEW")
        self.assertNotEqual(changed["last_valid_summary"]["layout_sha256"],
                            changed["layout_sha256"])
        confirmed = ask(changed["review_state"], "BAJO", LOWER_WIDTH_CONFIRM)
        self.assertEqual(confirmed["pending_candidate"]["status"], "PENDING_COLLISION")
        self.assertTrue(confirmed["collisions"])
        resolved = ask(confirmed["review_state"], "TORRE",
                       "Mover TORRE: X=1200 mm, Y=0 mm, Z=0 mm")
        after = {item["group_id"]: item["geometry_sha256"] for item in resolved["groups"]}
        self.assertEqual(resolved["assemblage_status"], "REVIEW_ONLY_VALID")
        self.assertIsNone(resolved["pending_candidate"])
        self.assertNotEqual(before["BAJO"], after["BAJO"])
        self.assertEqual(before["ALTO"], after["ALTO"])
        self.assertEqual(before["TORRE"], after["TORRE"])
        self.assertNotEqual(moved["layout_sha256"], resolved["layout_sha256"])
        self.assertEqual(resolved["last_valid_summary"]["layout_sha256"],
                         resolved["layout_sha256"])
        self.assert_safe(resolved)

    def test_l5_missing_back_appliance_coordinates_and_tampering_fail_closed(self) -> None:
        missing_back = ask(None, "ALTO", HIGH_UTTERANCE)
        self.assertIn(missing_back["groups"][1]["status"],
                      {"NEEDS_USER_CONFIRMATION", "CONCEPT_ONLY"})
        self.assertEqual(missing_back["groups"][1]["piece_count"], 0)
        self.assertTrue(missing_back["questions"])
        oven = ask(None, "TORRE", tower_text(reserve=True))
        self.assertEqual(oven["groups"][2]["status"], "CONCEPT_ONLY")
        self.assertEqual(oven["groups"][2]["piece_count"], 0)
        self.assert_safe(oven)
        with self.assertRaisesRegex(ValueError, "Ubicación ambigua"):
            ask(None, "BAJO", "Mover BAJO: X=20 mm, Y=0 mm")
        with self.assertRaisesRegex(ValueError, "grupo aún no existe"):
            ask(None, "BAJO", "Ubicar BAJO: X=0 mm, Y=0 mm, Z=0 mm")
        cutting = ask(None, "BAJO", FULL_UTTERANCE + " Déjalo listo para cortar.")
        self.assertEqual(cutting["groups"][0]["status"], "CONCEPT_ONLY")
        self.assertTrue(any("PRODUCTION_REQUEST_BLOCKED" in warning
                            for warning in cutting["groups"][0]["warnings"]))
        self.assert_safe(cutting)
        with self.assertRaisesRegex(ValueError, "campos no permitidos"):
            bad = ask(None, "TORRE", tower_text(reserve=False))["review_state"]
            bad["working"]["groups"]["TORRE"]["pieces"] = []
            ask(bad, "TORRE", "Mover TORRE: X=0 mm, Y=0 mm, Z=0 mm")
        valid = make_l1()["review_state"]
        valid["last_valid"]["layout_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "no pudo revalidarse"):
            ask(valid, "TORRE", "Mover TORRE: X=1100 mm, Y=0 mm, Z=0 mm")
        with self.assertRaisesRegex(ValueError, "JSON válido"):
            carpinova_consultar(
                '{"review_kind":"kitchen_linear_v1",'
                '"review_kind":"kitchen_linear_v1",'
                '"target_group":"BAJO","utterance":"x","review_state":null}'
            )
        with self.assertRaisesRegex(ValueError, "JSON válido"):
            carpinova_consultar(
                '{"review_kind":"kitchen_linear_v1","target_group":"BAJO",'
                '"utterance":"x","review_state":{"schema_version":"kitchen_linear_v1",'
                '"working":{"groups":{"BAJO":{"history":[]},"ALTO":{"history":[]},'
                '"TORRE":{"history":[]}},"positions":{"BAJO":[NaN,0,0],'
                '"ALTO":null,"TORRE":null}},"last_valid":null,"pending_candidate":null}}'
            )


if __name__ == "__main__":
    unittest.main()
