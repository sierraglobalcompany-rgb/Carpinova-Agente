"""F7D web-review boundary: no real HTTP, login, LLM or CAD."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from carpinova_agent.maestro import MaestroError, consult_maestro
from carpinova_agent.web_review import ReviewGate

CABINET = {
    "action": "project",
    "project": {
        "project_type": "gabinete", "width_mm": 600,
        "height_mm": 720, "depth_mm": 560,
        "panel_thickness_mm": 18, "construction": "sides_full",
    },
}


class WebReviewTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.identities = {
            "a": ("user-1", "session-a"),
            "b": ("user-1", "session-b"),
            "other": ("user-2", "session-other"),
        }

        def identity(context):
            if context == "anonymous":
                raise PermissionError("not logged in")
            return self.identities[context]

        self.gate = ReviewGate(
            authenticated_identity=identity,
            clock=lambda: self.now, ttl_seconds=30,
        )

    def stage(self):
        return self.gate.stage("a", "Gabinete de 600 mm", CABINET)

    def consume(self, item, ctx="a", **overrides):
        options = {
            "review_id": item["review_id"],
            "confirmation_challenge": item["confirmation_challenge"],
            "fingerprint": item["fingerprint"],
        }
        options.update(overrides)
        return self.gate.consume(ctx, **options)

    def test_stage_never_calculates_or_executes(self):
        with patch("carpinova_agent.maestro.guide_project",
                   side_effect=AssertionError("geometry executed")):
            record = self.stage()
        self.assertEqual(record["status"], "NEEDS_USER_CONFIRMATION")
        self.assertEqual(record["executed_tools"], [])
        self.assertEqual(record["proposed_request"], CABINET)
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
            self.assertFalse(record[flag])

    def test_session_isolation_even_for_same_user(self):
        record = self.stage()
        for context in ("b", "other"):
            with self.subTest(context=context):
                with self.assertRaisesRegex(MaestroError, "otra sesión"):
                    self.consume(record, context)
        self.assertEqual(self.consume(record)["approved_request"], CABINET)

    def test_ticket_cannot_be_used_twice(self):
        record = self.stage()
        self.consume(record)
        with self.assertRaisesRegex(MaestroError, "ya utilizada"):
            self.consume(record)

    def test_expiration_removes_review(self):
        record = self.stage()
        self.now += 30
        with self.assertRaisesRegex(MaestroError, "caducada"):
            self.consume(record)

    def test_wrong_challenge_blocks_but_valid_one_still_works(self):
        record = self.stage()
        with self.assertRaisesRegex(MaestroError, "diferente"):
            self.consume(record, confirmation_challenge="falso")
        self.assertEqual(self.consume(record)["approved_request"], CABINET)

    def test_wrong_fingerprint_does_not_approve(self):
        record = self.stage()
        with self.assertRaisesRegex(MaestroError, "diferente"):
            self.consume(record, fingerprint="0" * 64)
        self.assertEqual(self.consume(record)["approved_request"], CABINET)

    def test_missing_host_authentication_is_fail_closed(self):
        with self.assertRaisesRegex(MaestroError, "identidad autenticada"):
            self.gate.stage("anonymous", "Gabinete", CABINET)
        record = self.stage()
        with self.assertRaisesRegex(MaestroError, "identidad autenticada"):
            self.consume(record, "anonymous")

    def test_returned_preview_cannot_mutate_server_snapshot(self):
        record = self.stage()
        record["proposed_request"]["project"]["width_mm"] = 999
        approved = self.consume(record)
        self.assertEqual(approved["approved_request"]["project"]["width_mm"], 600)

    def test_model_cannot_override_fabrication_state(self):
        with self.assertRaises(MaestroError):
            self.gate.stage("a", "Cortar", {**CABINET, "cutting_ready": True})

    def test_cancel_destroys_pending_review(self):
        record = self.stage()
        self.gate.cancel("a", review_id=record["review_id"])
        with self.assertRaisesRegex(MaestroError, "inexistente"):
            self.consume(record)

    def test_cancel_other_session_blocked(self):
        record = self.stage()
        with self.assertRaisesRegex(MaestroError, "otra sesión"):
            self.gate.cancel("b", review_id=record["review_id"])
        self.assertEqual(self.consume(record)["approved_request"], CABINET)

    def test_max_pending_rejects_without_silent_eviction(self):
        gate = ReviewGate(authenticated_identity=lambda _: ("user", "session"),
                          max_pending=1)
        first = gate.stage(None, "Gabinete", CABINET)
        with self.assertRaisesRegex(MaestroError, "Capacidad"):
            gate.stage(None, "Otro gabinete", CABINET)
        result = gate.consume(
            None, review_id=first["review_id"],
            confirmation_challenge=first["confirmation_challenge"],
            fingerprint=first["fingerprint"],
        )
        self.assertEqual(result["approved_request"], CABINET)

    def test_host_identity_callback_is_mandatory(self):
        with self.assertRaises(MaestroError):
            ReviewGate(authenticated_identity=None)

    def test_bad_identity_data_rejected(self):
        for bad in (None, "user", ("", "session"), ("user", ""), (" user", "s"),
                    ("user", "session", "extra")):
            with self.subTest(value=bad):
                gate = ReviewGate(authenticated_identity=lambda _: bad)
                with self.assertRaises(MaestroError):
                    gate.stage(None, "Gabinete", CABINET)

    def test_non_ascii_identity_ids_fail_closed_before_comparison(self):
        # compare_digest is defined only for ASCII text inputs.
        gate = ReviewGate(authenticated_identity=lambda _: ("usuario-ñ", "session"))
        with self.assertRaisesRegex(MaestroError, "inválidas"):
            gate.stage(None, "gabinete", CABINET)

    def test_bad_limits_rejected(self):
        for ttl in (0, True, -1, 3601):
            with self.subTest(ttl=ttl), self.assertRaises(MaestroError):
                ReviewGate(authenticated_identity=lambda _: ("user", "s"),
                           ttl_seconds=ttl)
        with self.assertRaises(MaestroError):
            ReviewGate(authenticated_identity=lambda _: ("user", "s"),
                       max_pending=0)

    def test_actual_maestro_revalidates_after_gate_confirmation(self):
        record = self.stage()
        reviewed = self.consume(record)
        self.assertEqual(reviewed["executed_tools"], [])
        with patch("carpinova_agent.maestro.load_bundle",
                   side_effect=AssertionError("bundle not requested")):
            calculated = consult_maestro(reviewed["approved_request"])
        self.assertEqual(calculated["status"], "DRAFT_NOT_FOR_CUTTING")
        self.assertEqual(calculated["project"]["phase"], "GEOMETRY_DRAFT")
        for flag in ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready"):
            self.assertFalse(calculated[flag])

    def test_concurrent_double_click_has_one_winner(self):
        record = self.stage()

        def attempt(_):
            try:
                self.consume(record)
                return "APPROVED"
            except MaestroError:
                return "BLOCKED"

        with ThreadPoolExecutor(max_workers=4) as workers:
            outcomes = list(workers.map(attempt, range(4)))
        self.assertEqual(outcomes.count("APPROVED"), 1)
        self.assertEqual(outcomes.count("BLOCKED"), 3)

    def test_consume_does_not_call_maestro_by_itself(self):
        record = self.stage()
        with patch("carpinova_agent.maestro.guide_project") as engine:
            reviewed = self.consume(record)
            engine.assert_not_called()
        self.assertEqual(reviewed["executed_tools"], [])

    def test_expiry_frees_capacity(self):
        gate = ReviewGate(
            authenticated_identity=lambda _: ("u", "s"),
            ttl_seconds=5, max_pending=1, clock=lambda: self.now,
        )
        gate.stage(None, "Gabinete", CABINET)
        self.now += 6
        record = gate.stage(None, "Gabinete", CABINET)
        self.assertEqual(record["status"], "NEEDS_USER_CONFIRMATION")


if __name__ == "__main__":
    unittest.main()
