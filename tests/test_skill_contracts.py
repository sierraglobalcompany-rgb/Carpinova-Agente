"""Verify that shipped CarpiNova skills resolve local docs and advertise real contracts.

These are static metadata/link regressions, not an LLM or fabrication QA.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "skills"
EXPECTED_SKILLS = {
    "diseno-muebles",
    "maestro-carpintero",
    "seleccion-herrajes",
    "tecnicas-constructivas",
}
LINK = re.compile(r"!?(?:\[[^\]\n]*\])\(([^)]+)\)")


class SkillContractTest(unittest.TestCase):
    def test_exact_skill_directories_and_readable_instructions(self) -> None:
        observed = {p.name for p in SKILLS_ROOT.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()}
        self.assertEqual(observed, EXPECTED_SKILLS)
        for name in sorted(EXPECTED_SKILLS):
            with self.subTest(skill=name):
                content = (SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertTrue(content.startswith("---\nname: " + name + "\n"))
                self.assertIn("\ndescription: ", content.split("\n---\n", 1)[0])

    def test_local_markdown_links_exist_in_shipped_skills(self) -> None:
        for name in sorted(EXPECTED_SKILLS):
            source = SKILLS_ROOT / name / "SKILL.md"
            content = source.read_text(encoding="utf-8")
            for raw in LINK.findall(content):
                target = raw.split()[0].strip("<>")
                url = urlsplit(target)
                if url.scheme in {"http", "https", "mailto"} or target.startswith("#"):
                    continue
                self.assertEqual(url.scheme, "", f"Unsupported link scheme in {source}: {raw}")
                self.assertFalse(target.startswith("/"), f"Absolute local link in {source}: {raw}")
                resolved = (source.parent / unquote(url.path)).resolve()
                with self.subTest(skill=name, link=raw):
                    self.assertTrue(resolved.is_relative_to(ROOT), f"Link escapes repository: {raw}")
                    self.assertTrue(resolved.is_file(), f"Broken skill link: {source}: {raw}")

    def test_maestro_skill_mentions_all_existing_actions(self) -> None:
        skill = (SKILLS_ROOT / "maestro-carpintero" / "SKILL.md").read_text(encoding="utf-8")
        from carpinova_agent.maestro import ACTIONS
        advertised = set()
        for line in skill.splitlines():
            if "entrada unificada con" in line:
                match = re.search(r"action=([a-z|]+)", line)
                if match:
                    advertised = set(match.group(1).split("|"))
        self.assertEqual(advertised, ACTIONS)

    def test_maestro_skill_keeps_nonfabrication_and_mcp_disclosures(self) -> None:
        skill = (SKILLS_ROOT / "maestro-carpintero" / "SKILL.md").read_text(encoding="utf-8")
        for required in (
            "fabrication_ready=false",
            "drilling_ready=false",
            "cutting_ready=false",
            "purchase_ready=false",
            "Ningún MCP interactivo",
            "pruebas nativas reales en CI",
        ):
            with self.subTest(required=required):
                self.assertIn(required, skill)


if __name__ == "__main__":
    unittest.main()
