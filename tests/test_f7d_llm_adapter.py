"""F7D opt-in LLM interpreter: offline mocks; zero live API calls."""
from __future__ import annotations

import io
import json
import os
import unittest
from unittest.mock import patch

from carpinova_agent.llm_adapter import (
    API_URL, SCHEMA, _decode_response, _ground_type, interpret_openai_request,
)
from carpinova_agent.maestro import MaestroError


def answer(intent="project", furniture="gabinete"):
    return {"status": "completed", "output": [
        {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": json.dumps(
                {"intent": intent, "project_type": furniture}, ensure_ascii=False)}
        ]}
    ]}


class FakeHandle(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class FakeOpener:
    def __init__(self, result):
        self.result = result
        self.calls = 0
        self.request = None

    def open(self, request, timeout=0):
        self.calls += 1
        self.request = request
        assert timeout == 20
        return FakeHandle(json.dumps(self.result).encode("utf-8"))


class ResponsesInterpreterTests(unittest.TestCase):
    def _invoke(self, words="Quiero un gabinete", result=None, model="test-model"):
        opener = FakeOpener(result if result is not None else answer())
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret-for-test"}):
            with patch("carpinova_agent.llm_adapter.urllib.request.build_opener",
                       return_value=opener):
                value = interpret_openai_request(
                    words, model=model, consent_send_text=True)
        return value, opener

    def test_explicit_consent_required_before_network(self):
        with patch("carpinova_agent.llm_adapter.urllib.request.build_opener") as network:
            with self.assertRaisesRegex(MaestroError, "consentimiento"):
                interpret_openai_request("gabinete", model="test-model", consent_send_text=False)
            network.assert_not_called()

    def test_key_required_before_network(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            with patch("carpinova_agent.llm_adapter.urllib.request.build_opener") as net:
                with self.assertRaisesRegex(MaestroError, "OPENAI_API_KEY"):
                    interpret_openai_request(
                        "gabinete", model="test-model", consent_send_text=True)
                net.assert_not_called()

    def test_fixed_endpoint_no_tools_and_only_user_text(self):
        candidate, network = self._invoke()
        self.assertEqual(network.calls, 1)
        self.assertEqual(network.request.full_url, API_URL)
        body = json.loads(network.request.data)
        self.assertEqual(body["input"], "Quiero un gabinete")
        self.assertFalse(body["store"])
        self.assertEqual(body["tools"], [])
        self.assertEqual(body["text"]["format"]["schema"], SCHEMA)
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertNotIn("secret-for-test", network.request.data.decode())
        self.assertEqual(candidate, {"action": "project",
                                     "project": {"project_type": "gabinete"}})

    def test_knowledge_keeps_original_question(self):
        words = "¿Qué es una bisagra y cómo se instala?"
        result, _ = self._invoke(words, answer("knowledge", None))
        self.assertEqual(result, {"action": "knowledge", "query": words})

    def test_unclear_causes_no_candidate(self):
        value, _ = self._invoke("Hola", answer("unclear", None))
        self.assertIsNone(value)

    def test_no_type_requests_more_details(self):
        value, _ = self._invoke("Quiero un mueble", answer("project", None))
        self.assertEqual(value, {"action": "project", "project": {}})

    def test_fabricated_type_rejected(self):
        value, _ = self._invoke("Quiero algo para mi habitación")
        self.assertEqual(value, {"action": "project", "project": {}})

    def test_ambiguous_multiple_furniture_terms_not_inferred(self):
        value, _ = self._invoke("Una cocina con cajones", answer("project", "cocina"))
        self.assertEqual(value, {"action": "project", "project": {}})

    def test_reuses_existing_f3_aliases(self):
        self.assertEqual(_ground_type("Diseñar un armario", "clóset"), "clóset")
        self.assertIsNone(_ground_type("Diseñar una mesa", "clóset"))

    def test_rejects_incomplete_refused_and_multi_message(self):
        bads = [
            {"status": "incomplete", "output": answer()["output"]},
            {"status": "completed", "output": []},
            {"status": "completed", "output": answer()["output"] * 2},
            {"status": "completed", "output": [
                {"type": "message", "role": "assistant",
                 "content": [{"type": "refusal", "refusal": "No"}]}
            ]},
        ]
        for bad in bads:
            with self.subTest(bad=bad), self.assertRaises(MaestroError):
                _decode_response(bad)

    def test_rejects_out_of_schema_or_bad_fields(self):
        bads = [
            {"intent": "manufacture", "project_type": "gabinete"},
            {"intent": "knowledge", "project_type": "gabinete"},
            {"intent": "project", "project_type": "fabricable"},
            {"intent": "project", "project_type": "gabinete", "cutting_ready": True},
        ]
        for data in bads:
            result = answer()
            result["output"][0]["content"][0]["text"] = json.dumps(data)
            with self.subTest(value=data), self.assertRaises(MaestroError):
                _decode_response(result)

    def test_invalid_model_has_no_network(self):
        for bad in ("", "bad/name", "../model", None, "x" * 200):
            with self.subTest(bad=bad), self.assertRaises(MaestroError):
                self._invoke(model=bad)

    def test_never_accepts_dimensions_from_llm(self):
        value, _ = self._invoke("Gabinete de 600 mm con bisagra Blum")
        self.assertEqual(value, {"action": "project",
                                  "project": {"project_type": "gabinete"}})

    def test_cli_missing_consent_has_no_network(self):
        from carpinova_agent.maestro_cli import main
        with patch("sys.argv", ["maestro_cli", "--utterance", "Gabinete",
                                "--interpret-openai", "--interpret-model", "test-model"]):
            with patch("carpinova_agent.llm_adapter.urllib.request.build_opener") as net:
                self.assertEqual(main(), 2)
                net.assert_not_called()

    def test_cli_cannot_mix_candidate_and_llm(self):
        from carpinova_agent.maestro_cli import main
        with patch("sys.argv", ["maestro_cli", "--utterance", "Gabinete",
                                "--candidate", "missing.json", "--interpret-openai",
                                "--interpret-model", "test-model",
                                "--consent-send-text"]):
            with patch("carpinova_agent.llm_adapter.urllib.request.build_opener") as net:
                self.assertEqual(main(), 2)
                net.assert_not_called()

    def test_cli_llm_utterance_generates_preview_without_execution(self):
        from carpinova_agent.maestro_cli import main
        with patch("sys.argv", ["maestro_cli", "--utterance", "Gabinete",
                                "--interpret-openai", "--consent-send-text",
                                "--interpret-model", "test-model"]):
            with patch("carpinova_agent.maestro_cli.interpret_openai_request",
                       return_value={"action": "project",
                                     "project": {"project_type": "gabinete"}}):
                with patch("carpinova_agent.maestro_cli.consult_maestro") as engine:
                    output = io.StringIO()
                    with patch("sys.stdout", output):
                        self.assertEqual(main(), 0)
                    parsed = json.loads(output.getvalue())
                    self.assertEqual(parsed["status"], "NEEDS_USER_CONFIRMATION")
                    self.assertEqual(parsed["interpreter"]["authority"], "proposal_only")
                    engine.assert_not_called()


    def test_malformed_types_fail_as_maestro_error(self):
        # An untrusted JSON model can return lists/objects despite its schema.
        for invalid in (
            {"intent": [], "project_type": "gabinete"},
            {"intent": {"action": "fabricar"}, "project_type": None},
            {"intent": "project", "project_type": []},
            {"intent": "project", "project_type": {"width_mm": 600}},
        ):
            out = answer()
            out["output"][0]["content"][0]["text"] = json.dumps(invalid)
            with self.subTest(invalid=invalid), self.assertRaises(MaestroError):
                _decode_response(out)

    def test_cli_remote_confirmation_still_requires_tty(self):
        from carpinova_agent.maestro_cli import main
        argv = ["maestro_cli", "--utterance", "Gabinete",
                "--interpret-openai", "--consent-send-text",
                "--interpret-model", "test-model", "--confirm-execute"]
        with patch("sys.argv", argv):
            with patch("carpinova_agent.maestro_cli.interpret_openai_request",
                       return_value={"action": "project", "project": {}}):
                with patch("carpinova_agent.maestro_cli.consult_maestro") as engine:
                    with patch("sys.stdin", io.StringIO()):
                        with patch("sys.stderr", io.StringIO()):
                            self.assertEqual(main(), 2)
                    engine.assert_not_called()

if __name__ == "__main__":
    unittest.main()
