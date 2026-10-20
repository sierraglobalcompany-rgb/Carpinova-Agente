"""Regression tests for the F4/F5 known README conflict rehearsal."""
from __future__ import annotations

import unittest

from scripts.reconcile_stack_readme import reconcile


HARDWARE = "## Catálogo de herrajes (desarrollo F4)"
MAESTRO = "## CarpiNova Maestro — interfaz unificada (F5)"


class ReadmeReconciliationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.f4 = (
            "# CarpiNova Agente\n\nIntro original\n\n"
            + HARDWARE + "\nFicha F4 exacta\nNo autoriza perforaciones.\n"
        )
        self.f5 = (
            "# CarpiNova Agente\n\nIntro original\n\n"
            + MAESTRO + "\nIntegración F5 exacta\nNo autoriza fabricación.\n"
        )
        self.final = (
            "# CarpiNova Agente\n\nIntro actualizada con estado F7C.\n\n"
            + HARDWARE + "\nFicha F4 exacta\nNo autoriza perforaciones.\n\n"
            + MAESTRO + "\nIntegración F5 exacta\nNo autoriza fabricación.\n\n"
            + "## F6 — módulos\nHay geometría nominal.\n"
        )

    def test_allows_updated_introduction_but_defers_it_until_f7c(self) -> None:
        resolved = reconcile(self.f4, self.f5, self.final)
        self.assertEqual(
            resolved,
            self.f5.replace(
                MAESTRO,
                HARDWARE + "\nFicha F4 exacta\nNo autoriza perforaciones.\n\n" + MAESTRO,
                1,
            ),
        )
        self.assertIn("Intro original", resolved)
        self.assertNotIn("Intro actualizada con estado F7C", resolved)
        self.assertNotIn("## F6", resolved)

    def test_rejects_changed_f4_section(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact F4"):
            reconcile(self.f4, self.f5, self.final.replace("No autoriza perforaciones.", "Sí autoriza perforaciones."))

    def test_rejects_changed_f5_section(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact F5"):
            reconcile(self.f4, self.f5, self.final.replace("No autoriza fabricación.", "Sí autoriza fabricación."))

    def test_rejects_missing_f4_or_f5_section(self) -> None:
        for heading in (HARDWARE, MAESTRO):
            with self.subTest(heading=heading), self.assertRaises(ValueError):
                reconcile(self.f4, self.f5, self.final.replace(heading, "## Sección perdida"))

    def test_rejects_duplicate_headings(self) -> None:
        with self.assertRaises(ValueError):
            reconcile(self.f4, self.f5, self.final + "\n" + HARDWARE + "\nDuplicado\n")

    def test_rejects_reordered_sections(self) -> None:
        reversed_final = (
            "# CarpiNova Agente\n\n"
            + MAESTRO + "\nIntegración F5 exacta\nNo autoriza fabricación.\n\n"
            + HARDWARE + "\nFicha F4 exacta\nNo autoriza perforaciones.\n"
        )
        with self.assertRaisesRegex(ValueError, "reversed"):
            reconcile(self.f4, self.f5, reversed_final)

    def test_rejects_unsupported_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unexpected source"):
            reconcile(self.f4.replace(HARDWARE, "## Eliminado"), self.f5, self.final)

    def test_rejects_conflict_markers(self) -> None:
        with self.assertRaisesRegex(ValueError, "conflict markers"):
            reconcile(self.f4, self.f5, self.final + "\n<<<<<<< HEAD\n")

    def test_rejects_renamed_final_document(self) -> None:
        with self.assertRaisesRegex(ValueError, "identity"):
            reconcile(self.f4, self.f5, self.final.replace("# CarpiNova Agente", "# Otro proyecto", 1))


if __name__ == "__main__":
    unittest.main()
