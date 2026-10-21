"""No Codex process, machine settings or real user home is changed by these tests."""
from pathlib import Path
import importlib.util
import tempfile
import tomllib
import unittest

s=Path(__file__).resolve().parents[1]/'scripts'/'install_codex_skills.py'
spec=importlib.util.spec_from_file_location('cinstall',s)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MCPConfigTests(unittest.TestCase):
    def make_data(self,root):
        repo=root/'src'
        repo.mkdir()
        runtime=repo/'.venv'/'Scripts'/'python.exe'
        runtime.parent.mkdir(parents=True)
        runtime.write_bytes(b'fake-exe-test-only')
        projects=repo/'work'/'muebles'
        projects.mkdir(parents=True)
        approval=root/'host-approvals'
        approval.mkdir()
        example=repo/'work'/'configuracion-local'/'codex-config.toml.example'
        example.parent.mkdir(parents=True)
        txt=(f'[mcp_servers.carpinova]\ncommand = "{runtime}"\n'
             f'args = ["-m", "carpinova_agent.mcp_bridge"]\n'
             f'[mcp_servers.carpinova.env]\nPYTHONPATH = "{repo}"\n'
             f'CARPINOVA_OUTPUT_ROOT = "{projects}"\n'
             f'CARPINOVA_NATIVE_APPROVAL_DIR = "{approval}"\n')
        example.write_text(txt)
        return repo

    def test_preserves_existing_config_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); repo=self.make_data(root); c=root/'user'/'config.toml'
            c.parent.mkdir()
            c.write_text('model = "gpt-6"\n[mcp_servers.existing]\nurl = "https://example.org/mcp"\n')
            self.assertEqual(m.configure_mcp(repo,c),'CONFIGURED')
            parsed=tomllib.loads(c.read_text())
            self.assertEqual(parsed['model'],'gpt-6')
            self.assertIn('existing',parsed['mcp_servers'])
            self.assertIn('carpinova',parsed['mcp_servers'])
            orig=c.read_bytes()
            self.assertEqual(m.configure_mcp(repo,c),'ALREADY_CONFIGURED')
            self.assertEqual(orig,c.read_bytes())

    def test_different_existing_stanza_fails_without_touching_file(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);repo=self.make_data(root);c=root/'config.toml'
            c.write_text('[mcp_servers.carpinova]\ncommand = "other"\n')
            before=c.read_bytes()
            with self.assertRaises(FileExistsError):m.configure_mcp(repo,c)
            self.assertEqual(before,c.read_bytes())

    def test_reject_unexpected_host_execution_flag(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);repo=self.make_data(root);c=root/'config.toml'
            sample=repo/'work'/'configuracion-local'/'codex-config.toml.example'
            sample.write_text(sample.read_text()+ 'CARPINOVA_NATIVE_EXECUTION_ENABLED = "1"\n')
            with self.assertRaises(ValueError):m.configure_mcp(repo,c)
            self.assertFalse(c.exists())

    def test_dry_run_has_no_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);repo=self.make_data(root);c=root/'config.toml'
            self.assertEqual(m.configure_mcp(repo,c,write=False),'READY_TO_CONFIGURE')
            self.assertFalse(c.exists())

    def test_invalid_existing_toml_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);repo=self.make_data(root);c=root/'config.toml'
            c.write_text('= invalid')
            with self.assertRaises(tomllib.TOMLDecodeError):m.configure_mcp(repo,c)
            self.assertEqual(c.read_text(),'= invalid')

if __name__=='__main__':unittest.main()