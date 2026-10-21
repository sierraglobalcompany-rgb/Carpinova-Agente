"""Native CAD: human host approval, no silent model-granted permission."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from carpinova_agent.native_export import (
    NativeExportError, REVIEW_CONFIRMATION, export_native_project,
    issue_native_approval, main,
)
from carpinova_agent.pilot_cli import write_pilot_bundle

ROOT = Path(__file__).resolve().parents[1]
REQUEST = json.loads(
    (ROOT / "examples/pilot-open-kitchen-800.json").read_text(encoding="utf-8")
)


class NativeHostApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.approval_tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.approval_tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.approvals = Path(self.approval_tmp.name)
        self.project = self.root / "mueble"
        write_pilot_bundle(REQUEST, self.project)
        self.freecad = self.root / "FreeCADCmd.exe"
        self.blender = self.root / "blender.exe"
        self.freecad.write_bytes(b"fixture")
        self.blender.write_bytes(b"fixture")
        self.invocations = []

    def attempt(self):
        def runner(command, **kwargs):
            self.invocations.append(command)
            raise AssertionError("Native CAD must not have launched")
        return export_native_project(
            self.project, confirmation=REVIEW_CONFIRMATION,
            enabled=True, approval_dir=self.approvals,
            freecad_executable=str(self.freecad),
            blender_executable=str(self.blender), runner=runner,
        )

    def test_phrase_and_opt_in_cannot_run_without_separate_owner_approval(self):
        with self.assertRaisesRegex(NativeExportError, "aprobación local"):
            self.attempt()
        self.assertEqual(self.invocations, [])

    def test_approval_is_bound_to_exact_project_and_cad_sha(self):
        record = issue_native_approval(self.project, self.approvals)
        self.assertTrue(record.is_file())
        with self.assertRaisesRegex(NativeExportError, "pendiente"):
            issue_native_approval(self.project, self.approvals)
        json_record = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual(json_record["geometry_sha256"],
                         json.loads((self.project / "cad-exchange.json").read_text())["geometry_sha256"])
        json_record["geometry_sha256"] = "0" * 64
        record.write_text(json.dumps(json_record), encoding="utf-8")
        with self.assertRaisesRegex(NativeExportError, "incompatible"):
            self.attempt()
        self.assertEqual(self.invocations, [])

    def test_expired_approval_fails_closed(self):
        record = issue_native_approval(self.project, self.approvals, ttl_seconds=1)
        approval = json.loads(record.read_text(encoding="utf-8"))
        approval["expires_at"] = 1
        record.write_text(json.dumps(approval), encoding="utf-8")
        with self.assertRaisesRegex(NativeExportError, "vencida"):
            self.attempt()
        self.assertEqual(self.invocations, [])

    def test_approval_cannot_be_stored_with_generated_projects(self):
        with self.assertRaisesRegex(NativeExportError, "salida"):
            issue_native_approval(self.project, self.root)
        self.assertEqual(self.invocations, [])

    def test_tampered_review_must_not_be_approved(self):
        original = self.project / "parts-review.csv"
        original.write_bytes(original.read_bytes() + b"tampered")
        with self.assertRaisesRegex(NativeExportError, "inconsistente"):
            issue_native_approval(self.project, self.approvals)

    def test_issuer_cli_requires_real_terminal(self):
        with patch("sys.stdin") as fake_stdin:
            fake_stdin.isatty.return_value = False
            with self.assertRaises(SystemExit):
                main(["--approve-project", str(self.project),
                      "--approval-dir", str(self.approvals)])
        self.assertEqual(list(self.approvals.iterdir()), [])

    def test_valid_owner_terminal_issues_one_sha_bound_approval(self):
        cad = json.loads((self.project / "cad-exchange.json").read_text(encoding="utf-8"))
        answer = "AUTORIZO " + cad["geometry_sha256"][-8:]
        with patch("sys.stdin") as terminal, patch("builtins.input", return_value=answer):
            terminal.isatty.return_value = True
            self.assertEqual(main(["--approve-project", str(self.project),
                                   "--approval-dir", str(self.approvals)]), 0)
        tickets = list(self.approvals.glob("native-*.json"))
        self.assertEqual(len(tickets), 1)
        approval = json.loads(tickets[0].read_text(encoding="utf-8"))
        self.assertEqual(approval["project"], str(self.project.resolve()))
        self.assertEqual(approval["geometry_sha256"], cad["geometry_sha256"])

    def test_native_failure_consumes_approval_and_prevents_replay(self):
        ticket = issue_native_approval(self.project, self.approvals)
        with self.assertRaisesRegex(AssertionError, "must not have launched"):
            self.attempt()
        self.assertEqual(len(self.invocations), 1)
        self.assertFalse(ticket.exists())
        with self.assertRaisesRegex(NativeExportError, "aprobación local"):
            self.attempt()
        self.assertEqual(len(self.invocations), 1)

    def test_rejects_long_lived_approval(self):
        with self.assertRaisesRegex(NativeExportError, "Ventana"):
            issue_native_approval(self.project, self.approvals, ttl_seconds=3600)
        self.assertEqual(list(self.approvals.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
