"""Terminal interview regression for actual input sequences."""
import unittest

from carpinova_agent.dialogue import parse_answer, run_interview
from carpinova_agent.core import DesignError


def simulate(inputs):
    answers = iter(inputs)
    messages = []
    def ask(prompt):
        messages.append(prompt)
        return next(answers)
    code, result = run_interview(ask, messages.append)
    return code, result, messages


class DialogTests(unittest.TestCase):
    def test_complete_cabinet(self):
        code, result, messages = simulate([
            "gabinete", "600", "720", "560", "18", "costados completos"
        ])
        self.assertEqual(code, 0)
        self.assertEqual(result["phase"], "GEOMETRY_DRAFT")
        self.assertEqual(result["design"]["dimensions"]["clear_width_mm"], 564)
        self.assertIn("NO apto", messages[0])

    def test_non_numeric_asks_again(self):
        code, result, messages = simulate([
            "gabinete", "ancho", "600 mm", "720", "560", "18", "sides_full"
        ])
        self.assertEqual(code, 0)
        self.assertTrue(any("milímetros enteros" in message for message in messages))
        self.assertEqual(result["design"]["dimensions"]["external_width_mm"], 600)

    def test_drawer_requires_explicit_slide_clearances(self):
        code, result, messages = simulate([
            "cajón", "564", "240", "500", "150", "15", "6",
            "13", "13", "5", "5",
        ])
        self.assertEqual(code, 0)
        self.assertEqual(result["phase"], "GEOMETRY_DRAFT")
        self.assertTrue(any("corredera" in msg for msg in messages))
        self.assertTrue(result["release_blockers"])

    def test_concept_only_closet(self):
        code, result, _ = simulate(["clóset", "2000", "2400", "600"])
        self.assertEqual(code, 0)
        self.assertEqual(result["phase"], "CONCEPT_ONLY")
        self.assertIsNone(result["design"])

    def test_cancel(self):
        code, result, transcript = simulate(["salir"])
        self.assertEqual(code, 1)
        self.assertIsNone(result)
        self.assertTrue(any("cancelada" in x for x in transcript))

    def test_ambiguous_construction_repeats(self):
        code, result, transcript = simulate([
            "gabinete", "600", "720", "560", "18", "tapa interna",
            "top_bottom_full",
        ])
        self.assertEqual(code, 0)
        self.assertTrue(any("Elige sides_full" in t for t in transcript))
        self.assertEqual(result["design"]["parts"][1]["face_x_mm"], 600)

    def test_invalid_type_repeats(self):
        code, result, transcript = simulate([
            "estantería alienígena", "gabinete", "600",
            "720", "560", "18", "sides_full",
        ])
        self.assertEqual(code, 0)
        self.assertTrue(any("Mueble no reconocido" in t for t in transcript))

    def test_geometry_failure_fails_closed(self):
        code, result, transcript = simulate([
            "gabinete", "30", "720", "560", "18", "sides_full",
        ])
        self.assertEqual(code, 2)
        self.assertEqual(result["phase"], "INVALID_GEOMETRY")
        self.assertTrue(any("Bloqueado" in t for t in transcript))

    def test_parse_non_numeric(self):
        with self.assertRaises(DesignError):
            parse_answer("width_mm", "600.5")

    def test_no_hidden_default(self):
        with self.assertRaises(DesignError):
            parse_answer("width_mm", " ")

    def test_parse_full_construction(self):
        self.assertEqual(parse_answer("construction", "tapas completas"),
                         "top_bottom_full")

    def test_not_wild_guessing(self):
        with self.assertRaises(DesignError):
            parse_answer("construction", "pata externa")


if __name__ == "__main__":
    unittest.main()
