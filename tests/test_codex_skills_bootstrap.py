"""Tests for the Codex skill installer, with synthetic sources (no network or IDE)."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "install_codex_skills.py"
spec = importlib.util.spec_from_file_location("install_codex_skills", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InstallerTests(unittest.TestCase):
    def make_repo(self, p: Path) -> Path:
        repo = p / "repo"
        for name in module.SKILLS:
            skill = repo / "skills" / name
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: Synthetic test.\n---\n# Test\n",
                encoding="utf-8")
        return repo

    def test_installs_four_skills_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo = self.make_repo(base)
            target = base / "home" / ".agents" / "skills"
            self.assertEqual(set(module.install(repo, target).values()), {"INSTALLED"})
            self.assertEqual(set(module.install(repo, target).values()), {"ALREADY_IDENTICAL"})
            for name in module.SKILLS:
                self.assertEqual(
                    (repo / "skills" / name / "SKILL.md").read_bytes(),
                    (target / name / "SKILL.md").read_bytes())

    def test_conflicting_skill_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo = self.make_repo(base)
            target = base / "skills-installed"
            module.install(repo, target)
            conflict = target / module.SKILLS[0] / "SKILL.md"
            conflict.write_text("Do not overwrite", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                module.install(repo, target)
            self.assertEqual(conflict.read_text(), "Do not overwrite")

    def test_conflict_is_detected_before_any_other_skill_install(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo = self.make_repo(base)
            target = base / "skills-installed"
            conflicted = target / module.SKILLS[-1]
            conflicted.mkdir(parents=True)
            (conflicted / "SKILL.md").write_text("different", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                module.install(repo, target)
            self.assertFalse((target / module.SKILLS[0]).exists())

    def test_shipped_skill_docs_work_after_global_relocation(self):
        """Installed SKILL.md files must not rely on ../../docs outside the clone."""
        import re
        from urllib.parse import unquote
        canonical = SCRIPT.parents[1]
        prefix = (
            "https://github.com/sierraglobalcompanyv2/"
            "Carpinova-Agente/blob/main/docs/"
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "different-home" / ".agents" / "skills"
            statuses = module.install(canonical, target)
            self.assertEqual(len(statuses), 4)
            self.assertEqual(set(statuses.values()), {"INSTALLED"})
            document_count = 0
            for name in module.SKILLS:
                skill_path = target / name / "SKILL.md"
                text = skill_path.read_text(encoding="utf-8")
                self.assertNotIn("](../../docs/", text)
                for reference in re.findall(r"\\]\\(([^)]+)\\)", text):
                    if reference.startswith(prefix):
                        relative = unquote(reference[len(prefix):])
                        self.assertNotIn("..", Path(relative).parts)
                        self.assertTrue(
                            (canonical / "docs" / relative).is_file(),
                            f"Missing referenced CarpiNova document: {relative}"
                        )
                        document_count += 1
            self.assertGreaterEqual(document_count, 8)

    def test_rejects_mismatched_skill_name(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo = self.make_repo(base)
            (repo / "skills" / module.SKILLS[0] / "SKILL.md").write_text(
                "---\nname: changed-name\n---\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                module.install(repo, base / "out")


if __name__ == "__main__":
    unittest.main()