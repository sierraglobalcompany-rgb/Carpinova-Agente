"""P7 book-first, replayable review flow using the real MCP stdio server."""
from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

from knowledge_client.reader import load_bundle
from carpinova_agent.mcp_bridge import (
    carpinova_consultar, carpinova_generar_borrador,
    carpinova_leer_entregable,
)
from carpinova_agent.pilot_cli import (
    BookEvidenceError, verify_pilot_bundle, write_pilot_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
BOOK_DIR = os.environ.get("CARPINOVA_KNOWLEDGE_BUNDLE_DIR")
P6_GEOMETRY_SHA256 = "5c0b8944ba015ef537688afac3ee58b9dd52011267c28278c9134a473cecf947"
LEGACY_BUNDLE_SHA256 = {
    "pilot-open-kitchen-800": "ea7f52ab516f6a1cf2616927f8cfafe6e5ca27cd3ee1bbd0a3091ef52f904c7f",
    "wall-bar-900-review-p5": "368d7f9e686d3414fce7b00be807df7fa04ec5753d8274aff2c4d9280160b361",
    "modular-kitchen-door-fronts": "3afd46e50c3dabccf7eb588b0f5a242da11e39260742a11e9bcfa12cc6c47738",
}


def _book_requests() -> list[tuple[str, dict, int]]:
    bar = json.loads(
        (ROOT / "examples" / "wall-bar-900-review-p5.json").read_text(encoding="utf-8")
    )
    bar["query"] = "correderas telescópicas rieles gaveta"
    kitchen = {
        "action": "modular",
        "module_spec": json.loads(
            (ROOT / "examples" / "modular-kitchen-door-fronts.json").read_text(
                encoding="utf-8"
            )
        ),
        "query": "bisagras puertas sobrepuestas",
    }
    return [("p7_bar_book", bar, 28), ("p7_kitchen_book", kitchen, 13)]


def _legacy_requests() -> dict[str, dict]:
    generic = json.loads(
        (ROOT / "examples" / "pilot-open-kitchen-800.json").read_text(encoding="utf-8")
    )
    generic["action"] = "modular"
    bar = json.loads(
        (ROOT / "examples" / "wall-bar-900-review-p5.json").read_text(encoding="utf-8")
    )
    kitchen = {
        "action": "modular",
        "module_spec": json.loads(
            (ROOT / "examples" / "modular-kitchen-door-fronts.json").read_text(
                encoding="utf-8"
            )
        ),
    }
    return {
        "pilot-open-kitchen-800": generic,
        "wall-bar-900-review-p5": bar,
        "modular-kitchen-door-fronts": kitchen,
    }


def _bundle_digest(folder: Path) -> str:
    records = []
    for path in sorted(
        (item for item in folder.iterdir() if item.is_file()),
        key=lambda item: item.name,
    ):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append(f"{path.name}\0{digest}\n")
    return hashlib.sha256("".join(records).encode("utf-8")).hexdigest()


def _mcp_payload(result):
    if result.structuredContent is not None:
        return result.structuredContent
    text_blocks = [getattr(block, "text", None) for block in result.content]
    text = next((item for item in text_blocks if isinstance(item, str)), None)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


@unittest.skipUnless(BOOK_DIR, "P7 requires a locally validated FULL_BOOK bundle")
class P7BookFirstTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle_dir = Path(BOOK_DIR)
        cls.bundle = load_bundle(cls.bundle_dir)
        cls.assert_bundle_contract()

    @classmethod
    def assert_bundle_contract(cls):
        manifest = cls.bundle["manifest"]
        files = {path.name for path in cls.bundle_dir.iterdir() if path.is_file()}
        if (cls.bundle["coverage"] != "FULL_BOOK"
                or manifest["knowledge_version"] != "1.2.0"
                or manifest["schema_version"] != "0.1.0"
                or manifest["scope"] != "BOOK"
                or manifest["counts"]["pages"] != 252
                or manifest["source_page_count"] != 295
                or manifest["excluded_page_count"] != 43
                or files != {
                    "manifest.json", "knowledge.bundle.json",
                    "figures.bundle.json", "lessons.bundle.json",
                }):
            raise AssertionError("P7 requiere exactamente BOOK 1.2.0 FULL_BOOK validado")

    def test_real_stdio_mcp_book_queries_generation_replay_render_and_read(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        with TemporaryDirectory() as output_root:
            env = dict(os.environ)
            env.update({
                "PYTHONPATH": str(ROOT),
                "CARPINOVA_OUTPUT_ROOT": output_root,
                "CARPINOVA_KNOWLEDGE_BUNDLE_DIR": str(self.bundle_dir),
                "CARPINOVA_NATIVE_EXECUTION_ENABLED": "0",
                "CARPINOVA_FREECADCMD": "",
                "CARPINOVA_BLENDER": "",
            })
            evidence = []

            async def run_mcp():
                parameters = StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "carpinova_agent.mcp_bridge"],
                    env=env,
                )
                async with stdio_client(parameters) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        listed = await session.list_tools()
                        self.assertEqual(
                            {tool.name for tool in listed.tools},
                            {
                                "carpinova_estado", "carpinova_consultar",
                                "carpinova_generar_borrador", "carpinova_renderizar_lamina",
                                "carpinova_exportar_3d", "carpinova_leer_entregable",
                            },
                        )
                        state = _mcp_payload(
                            await session.call_tool("carpinova_estado", {})
                        )
                        self.assertTrue(state["knowledge_bundle_configured"])
                        self.assertEqual(state["status"], "DRAFT_DESIGN_ONLY")
                        for flag in (
                            "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready",
                        ):
                            self.assertIs(state[flag], False)

                        for project, request, expected_pieces in _book_requests():
                            raw = json.dumps(request, ensure_ascii=False)
                            consulted = await session.call_tool(
                                "carpinova_consultar", {"solicitud_json": raw}
                            )
                            self.assertFalse(consulted.isError)
                            answer = _mcp_payload(consulted)
                            self.assertEqual(answer["status"], "DRAFT_NOT_FOR_CUTTING")
                            self.assertEqual(answer["knowledge"]["coverage"], "FULL_BOOK")
                            self.assertEqual(answer["knowledge"]["knowledge_version"], "1.2.0")
                            self.assertGreater(answer["knowledge"]["total_matches"], 0)
                            self.assertGreater(len(answer["source_provenance"]), 0)
                            self.assertEqual(answer["modular"]["piece_count"], expected_pieces)
                            self.assertIsNone(answer["hardware"])
                            self.assertEqual(answer.get("manufacturing_holes", []), [])
                            self.assertEqual(answer.get("drilling_coordinates", []), [])
                            for key in ("hardware_included", "finished_panel_edges_included"):
                                if key in answer:
                                    self.assertIs(answer[key], False)
                                if key in answer["modular"]:
                                    self.assertIs(answer["modular"][key], False)
                            for part in answer["modular"]["parts"]:
                                self.assertEqual(part.get("manufacturing_holes", []), [])
                                self.assertEqual(part.get("drilling_coordinates", []), [])
                            self.assertTrue(all(
                                source["fabrication_authority"] is False
                                for source in answer["source_provenance"]
                            ))

                            generated = await session.call_tool(
                                "carpinova_generar_borrador",
                                {"solicitud_json": raw, "proyecto": project},
                            )
                            self.assertFalse(generated.isError)
                            generated_data = _mcp_payload(generated)
                            self.assertEqual(generated_data["status"], "DRAFT_NOT_FOR_CUTTING")
                            self.assertEqual(generated_data["piece_count"], expected_pieces)
                            for flag in (
                                "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready",
                            ):
                                self.assertIs(generated_data[flag], False)

                            manifest_result = await session.call_tool(
                                "carpinova_leer_entregable",
                                {"proyecto": project, "archivo": "manifest.json"},
                            )
                            manifest_content = _mcp_payload(manifest_result)["contenido"]
                            manifest = json.loads(manifest_content)
                            self.assertEqual(manifest["book_source_request"], request)
                            self.assertEqual(manifest["book_source_status"], "BOOK_EVIDENCE_PASS")
                            self.assertEqual(
                                manifest["book_source_metadata"]["knowledge_version"], "1.2.0"
                            )
                            self.assertIs(
                                manifest["book_source_metadata"]["source_pdf_bytes_verified"], False
                            )
                            self.assertNotIn(
                                "bundle_dir", manifest["book_source_metadata"].keys()
                            )

                            review_result = await session.call_tool(
                                "carpinova_leer_entregable",
                                {"proyecto": project, "archivo": "maestro-review.json"},
                            )
                            self.assertEqual(
                                _mcp_payload(review_result)["book_evidence_status"],
                                "BOOK_EVIDENCE_PASS",
                            )
                            saved_answer = json.loads(
                                _mcp_payload(review_result)["contenido"]
                            )
                            self.assertEqual(saved_answer, answer)

                            cad_result = await session.call_tool(
                                "carpinova_leer_entregable",
                                {"proyecto": project, "archivo": "cad-exchange.json"},
                            )
                            cad = json.loads(_mcp_payload(cad_result)["contenido"])
                            self.assertEqual(cad["geometry_sha256"], generated_data["geometry_sha256"])
                            if project == "p7_bar_book":
                                self.assertEqual(cad["geometry_sha256"], P6_GEOMETRY_SHA256)
                            self.assertEqual(len(cad["boxes"]), expected_pieces)
                            csv_result = await session.call_tool(
                                "carpinova_leer_entregable",
                                {"proyecto": project, "archivo": "parts-review.csv"},
                            )
                            rows = list(csv.DictReader(io.StringIO(
                                _mcp_payload(csv_result)["contenido"]
                            )))
                            self.assertEqual(
                                {row["piece_id"] for row in rows},
                                {box["piece_id"] for box in cad["boxes"]},
                            )
                            self.assertTrue(all(
                                not row.get("manufacturing_holes")
                                and not row.get("drilling_coordinates")
                                for row in rows
                            ))
                            svg_result = await session.call_tool(
                                "carpinova_leer_entregable",
                                {"proyecto": project, "archivo": "front-review.svg"},
                            )
                            ElementTree.fromstring(_mcp_payload(svg_result)["contenido"])

                            rendered = await session.call_tool(
                                "carpinova_renderizar_lamina", {"proyecto": project}
                            )
                            self.assertFalse(rendered.isError)
                            render_data = _mcp_payload(rendered)
                            self.assertEqual(render_data["geometry_sha256"], cad["geometry_sha256"])
                            self.assertEqual(render_data["piece_count"], expected_pieces)
                            for flag in (
                                "fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready",
                            ):
                                self.assertIs(render_data[flag], False)
                            png_result = await session.call_tool(
                                "carpinova_leer_entregable",
                                {"proyecto": project, "archivo": "lamina/three-views.png"},
                            )
                            self.assertFalse(png_result.isError)
                            self.assertTrue(any(
                                getattr(block, "type", None) == "image"
                                for block in png_result.content
                            ))
                            verify_pilot_bundle(
                                Path(output_root) / project, bundle_dir=self.bundle_dir
                            )
                            if project == "p7_bar_book":
                                criteria = await session.call_tool(
                                    "carpinova_leer_entregable",
                                    {
                                        "proyecto": project,
                                        "archivo": "CN-BAR-001-P6-criterios.md",
                                    },
                                )
                                self.assertEqual(
                                    _mcp_payload(criteria)["book_evidence_status"],
                                    "BOOK_UNVERIFIED",
                                )

                            safe_knowledge = answer["knowledge"]
                            evidence.append({
                                "project": project,
                                "request": request,
                                "mcp_query": {
                                    "status": answer["status"],
                                    "coverage": safe_knowledge["coverage"],
                                    "knowledge_version": safe_knowledge["knowledge_version"],
                                    "total_matches": safe_knowledge["total_matches"],
                                    "source_provenance": answer["source_provenance"],
                                    "source_text_omitted": True,
                                },
                                "draft": {
                                    "geometry_sha256": generated_data["geometry_sha256"],
                                    "piece_count": generated_data["piece_count"],
                                    "manifest": manifest,
                                    "csv_row_count": len(rows),
                                    "svg_xml_valid": True,
                                    "render_geometry_sha256": render_data["geometry_sha256"],
                                    "image_content_returned": True,
                                    "verified_against_book_bundle": True,
                                },
                                "manufacturing_flags": {
                                    key: answer[key] for key in (
                                        "fabrication_ready", "cutting_ready",
                                        "drilling_ready", "purchase_ready",
                                    )
                                },
                            })

            asyncio.run(run_mcp())
            evidence_root = os.environ.get("P7_EVIDENCE_DIR")
            if evidence_root:
                evidence_path = Path(evidence_root)
                evidence_path.mkdir(parents=True, exist_ok=True)
                (evidence_path / "real-mcp-book-e2e.json").write_text(
                    json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

    def test_legacy_no_query_packages_remain_byte_identical(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            for label, request in _legacy_requests().items():
                target = root / label
                target.mkdir()
                write_pilot_bundle(request, target / "review")
                manifest = json.loads(
                    (target / "review" / "manifest.json").read_text(encoding="utf-8")
                )
                self.assertNotIn("book_source_request", manifest)
                self.assertNotIn("book_source_metadata", manifest)
                self.assertNotIn("book_source_status", manifest)
                self.assertEqual(
                    _bundle_digest(target / "review"), LEGACY_BUNDLE_SHA256[label]
                )

    def test_no_match_is_explicit_and_has_no_citations(self):
        from carpinova_agent.pilot_cli import pilot_review

        request = {
            "action": "modular",
            "module_spec": json.loads(
                (ROOT / "examples" / "modular-kitchen-door-fronts.json").read_text(
                    encoding="utf-8"
                )
            ),
            "query": "qzxvlaetij",
        }
        result = pilot_review(request, bundle_dir=self.bundle_dir)
        manifest = json.loads(result["manifest.json"])
        answer = json.loads(result["maestro-review.json"])
        self.assertEqual(manifest["book_source_status"], "NO_BOOK_MATCH")
        self.assertEqual(answer["knowledge"]["total_matches"], 0)
        self.assertEqual(answer["knowledge"]["results"], [])
        self.assertEqual(answer["source_provenance"], [])
        self.assertTrue(any("No se encontró evidencia" in blocker
                            for blocker in answer["blockers"]))

    def test_fail_closed_missing_partial_flow_and_oversize_precede_output(self):
        request = _book_requests()[0][1]
        with TemporaryDirectory() as td:
            root = Path(td)
            missing_output = root / "missing_book"
            with patch.dict(os.environ, {
                "CARPINOVA_OUTPUT_ROOT": str(root),
                "CARPINOVA_KNOWLEDGE_BUNDLE_DIR": "",
            }):
                with self.assertRaisesRegex(BookEvidenceError, "BLOCKED_BOOK_BUNDLE"):
                    carpinova_generar_borrador(
                        json.dumps(request, ensure_ascii=False), "missing_book"
                    )
            self.assertFalse(missing_output.exists())

            partial = root / "partial-book"
            shutil.copytree(self.bundle_dir, partial)
            partial_manifest = json.loads(
                (partial / "manifest.json").read_text(encoding="utf-8")
            )
            partial_manifest["scope"] = "PILOT"
            (partial / "manifest.json").write_text(
                json.dumps(partial_manifest, indent=2) + "\n", encoding="utf-8"
            )
            partial_output = root / "partial_blocked"
            with patch.dict(os.environ, {
                "CARPINOVA_OUTPUT_ROOT": str(root),
                "CARPINOVA_KNOWLEDGE_BUNDLE_DIR": str(partial),
            }):
                partial_consult = carpinova_consultar(
                    json.dumps(request, ensure_ascii=False)
                )
                self.assertEqual(
                    partial_consult["knowledge"]["coverage"], "PARTIAL_CORPUS"
                )
                with self.assertRaisesRegex(BookEvidenceError, "BOOK_SCOPE_NOT_FULL"):
                    carpinova_generar_borrador(
                        json.dumps(request, ensure_ascii=False), "partial_blocked"
                    )
            self.assertFalse(partial_output.exists())

            flow_output = root / "query_with_flow"
            with patch.dict(os.environ, {
                "CARPINOVA_OUTPUT_ROOT": str(root),
                "CARPINOVA_KNOWLEDGE_BUNDLE_DIR": str(self.bundle_dir),
            }):
                with self.assertRaisesRegex(
                    BookEvidenceError, "BOOK_FLOW_COMBINATION_UNSUPPORTED"
                ):
                    carpinova_generar_borrador(
                        json.dumps(request, ensure_ascii=False), "query_with_flow",
                        flow_review_json="{}",
                    )
            self.assertFalse(flow_output.exists())

            oversized = json.loads(json.dumps(request))
            oversized["query"] = "q" * 32769
            oversized_output = root / "oversized_blocked"
            with patch.dict(os.environ, {
                "CARPINOVA_OUTPUT_ROOT": str(root),
                "CARPINOVA_KNOWLEDGE_BUNDLE_DIR": str(self.bundle_dir),
            }):
                with self.assertRaisesRegex(
                    BookEvidenceError, "BOOK_SOURCE_REQUEST_TOO_LARGE"
                ):
                    carpinova_generar_borrador(
                        json.dumps(oversized, ensure_ascii=False), "oversized_blocked"
                    )
            self.assertFalse(oversized_output.exists())

    def test_replay_rejects_request_citation_answer_and_manifest_tampering(self):
        request = _book_requests()[1][1]
        mutations = {
            "citation": lambda folder: self._mutate_json(
                folder / "maestro-review.json",
                lambda answer: answer["knowledge"]["results"][0].update(
                    {"content_id": "CONTENT-FAKE"}
                ),
            ),
            "saved_query": lambda folder: self._mutate_json(
                folder / "manifest.json",
                lambda manifest: manifest["book_source_request"].update(
                    {"query": "bisagras con consulta alterada"}
                ),
            ),
            "answer": lambda folder: self._mutate_json(
                folder / "maestro-review.json",
                lambda answer: answer["knowledge"].update(
                    {"query": "consulta alterada en respuesta"}
                ),
            ),
            "manifest_metadata": lambda folder: self._mutate_json(
                folder / "manifest.json",
                lambda manifest: manifest["book_source_metadata"].update(
                    {"scope": "PILOT"}
                ),
            ),
            "removed_binding": lambda folder: self._mutate_json(
                folder / "manifest.json",
                lambda manifest: manifest.pop("book_source_request"),
            ),
        }
        with TemporaryDirectory() as td:
            root = Path(td)
            for label, mutate in mutations.items():
                with self.subTest(mutation=label):
                    folder = root / label
                    folder.mkdir()
                    write_pilot_bundle(request, folder / "review", bundle_dir=self.bundle_dir)
                    mutate(folder / "review")
                    with self.assertRaises(BookEvidenceError):
                        verify_pilot_bundle(folder / "review", bundle_dir=self.bundle_dir)

    @staticmethod
    def _mutate_json(path: Path, mutate):
        data = json.loads(path.read_text(encoding="utf-8"))
        mutate(data)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    def test_bundle_bytes_and_scope_metadata_are_rechecked_on_replay(self):
        request = _book_requests()[1][1]
        with TemporaryDirectory() as td:
            root = Path(td)
            project = root / "review"
            write_pilot_bundle(request, project, bundle_dir=self.bundle_dir)

            with patch.dict(os.environ, {
                "CARPINOVA_OUTPUT_ROOT": str(root),
                "CARPINOVA_KNOWLEDGE_BUNDLE_DIR": "",
            }):
                with self.assertRaisesRegex(BookEvidenceError, "BLOCKED_BOOK_BUNDLE"):
                    carpinova_leer_entregable("review", "maestro-review.json")

            altered_bytes = root / "altered-bytes"
            shutil.copytree(self.bundle_dir, altered_bytes)
            target = altered_bytes / "knowledge.bundle.json"
            target.write_bytes(target.read_bytes() + b"\n")
            with self.assertRaisesRegex(BookEvidenceError, "BLOCKED_BOOK_BUNDLE"):
                verify_pilot_bundle(project, bundle_dir=altered_bytes)

            altered_scope = root / "altered-scope"
            shutil.copytree(self.bundle_dir, altered_scope)
            scope_path = altered_scope / "manifest.json"
            manifest = json.loads(scope_path.read_text(encoding="utf-8"))
            manifest["scope"] = "PILOT"
            scope_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(BookEvidenceError, "BOOK_SCOPE_NOT_FULL"):
                verify_pilot_bundle(project, bundle_dir=altered_scope)

            with self.assertRaisesRegex(BookEvidenceError, "BLOCKED_BOOK_BUNDLE"):
                verify_pilot_bundle(project)


if __name__ == "__main__":
    unittest.main()
