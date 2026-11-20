"""D15: real guided coffee top flight decisions, no second CAD engine."""
from __future__ import annotations

import unittest

from carpinova_agent.conversation_flow import (
    _guided_compose_product_spec, _guided_text_updates,
)


def owner(value):
    return {"value": value, "status": "confirmed", "source": "OWNER_TEXT"}


def reviewed(owner_flights=None, *, use="coffee"):
    decisions = {
        "project_type": owner("gabinete"),
        "dimensions_mm": owner({"width_mm": 890, "height_mm": 770, "depth_mm": 600}),
        "use": owner(use),
        "material": owner("melamina"),
        "thickness_mm": owner(15),
        "construction": owner("sides_full"),
        "wall_contact": owner(True),
        "support": owner({"style": "legs", "height_mm": 100}),
        "internal_layout": owner(["open"]),
        "drawers": owner("none"),
        "doors": owner({"count": 2}),
        "front_style": owner("overlay"),
        "back": owner("none"),
        "countertop": owner({
            "present": True,
            "dimensions_mm": {"width_mm": 940, "depth_mm": 650},
            "thickness_mm": 30,
            "material_id": "MDF_RH_30",
        }),
    }
    if owner_flights is not None:
        decisions["countertop_overhang"] = owner(owner_flights)
    return decisions


class CoffeeV4OwnerOverhangD15(unittest.TestCase):
    def test_owner_text_extracts_exact_50_front_zero_rear(self):
        updates = _guided_text_updates(
            "El mesón tiene vuelo frontal 50 mm y vuelo posterior 0 mm.",
            {}, None,
        )
        pairs = [item for item in updates
                 if item["field"] == "countertop_overhang"]
        self.assertEqual(pairs, [{
            "field": "countertop_overhang",
            "value": {"front_mm": 50, "rear_mm": 0},
            "status": "confirmed",
            "source": "OWNER_TEXT",
        }])

    def test_coffee_v4_preserves_explicit_front_rear_in_f6_request(self):
        spec, _, blockers = _guided_compose_product_spec(
            reviewed({"front_mm": 50, "rear_mm": 0}), "", {},
        )
        self.assertEqual(blockers, [])
        self.assertIsNotNone(spec)
        top = spec["modules"][0]["countertop"]
        self.assertEqual((top["front_overhang_mm"],
                          top["rear_overhang_mm"]), (50, 0))
        self.assertEqual((top["left_overhang_mm"],
                          top["right_overhang_mm"]), (25, 25))

    def test_no_owner_flights_does_not_silently_invent_25_25(self):
        spec, _, blockers = _guided_compose_product_spec(reviewed(), "", {})
        self.assertIsNone(spec)
        self.assertIn(
            "countertop_overhang:confirm_front_and_rear_mm_required", blockers,
        )

    def test_wrong_sum_rejects_even_if_owner_confirmed(self):
        spec, _, blockers = _guided_compose_product_spec(
            reviewed({"front_mm": 40, "rear_mm": 0}), "", {},
        )
        self.assertIsNone(spec)
        self.assertIn(
            "countertop_overhang:front_rear_do_not_match_depth", blockers,
        )

    def test_other_cabinet_applications_retain_previous_behavior(self):
        spec, _, blockers = _guided_compose_product_spec(
            reviewed(use="kitchen"), "", {},
        )
        self.assertEqual(blockers, [])
        top = spec["modules"][0]["countertop"]
        self.assertEqual((top["front_overhang_mm"],
                          top["rear_overhang_mm"]), (25, 25))


if __name__ == "__main__":
    unittest.main()
