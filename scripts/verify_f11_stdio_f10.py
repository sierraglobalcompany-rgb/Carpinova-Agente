from __future__ import annotations
import csv, hashlib, importlib.metadata, io, json, os, re, sys, tempfile, unittest
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
TOOLS = {
    "carpinova_estado", "carpinova_consultar", "carpinova_generar_borrador",
    "carpinova_renderizar_lamina", "carpinova_exportar_3d", "carpinova_leer_entregable",
}
FILES = {
    "LEER_PRIMERO.txt", "01-visor-3d.html", "02-planta.svg", "03-seccion.svg",
    "04-habitacion.json", "05-solicitud.json", "06-paneles-en-escena.csv",
}
FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready", "can_generate_f7c")


def _module_spec(module_id: str, width: int, *, corner: bool) -> dict:
    module = {
        "module_id": module_id, "width_mm": width, "panel_thickness_mm": 18,
        "material_id": "MELAMINA_18", "construction": "sides_full", "support": "floor",
        "fronts": "none", "back": "none", "drawers": "none",
    }
    if corner:
        module["corner_blind"] = {
            "side": "right", "blind_width_mm": 420,
            "access_door": {
                "material_id": "MELAMINA_18", "thickness_mm": 18,
                "gap_left_mm": 3, "gap_right_mm": 3, "gap_top_mm": 3,
                "gap_bottom_mm": 3, "hinge_side": "left",
            },
        }
    return {
        "type": "modular_run", "application": "kitchen", "width_mm": width,
        "height_mm": 720, "depth_mm": 560, "installation": "freestanding",
        "modules": [module],
    }


def _request() -> dict:
    return {
        "review_kind": "room_layout_v1",
        "assemblies": [
            {"group_id": "CIEGO", "module_spec": _module_spec("CIEGO", 900, corner=True),
             "origin_xyz_mm": [0, 0, 0], "rotation_deg": 0},
            {"group_id": "RECTO", "module_spec": _module_spec("RECTO", 600, corner=False),
             "origin_xyz_mm": [900, 0, 0], "rotation_deg": 90},
        ],
        "service_zones": [],
    }


def _json_object(text: str) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    value = json.loads(text, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid JSON constant")))
    if type(value) is not dict:
        raise AssertionError("MCP JSON content must be an object")
    return value


def _schema(tool) -> tuple[str, dict]:
    name = getattr(tool, "name", None)
    schema = getattr(tool, "inputSchema", getattr(tool, "input_schema", None))
    if schema is None and hasattr(tool, "model_dump"):
        dumped = tool.model_dump(by_alias=True, mode="json")
        schema = dumped.get("inputSchema", dumped.get("input_schema"))
    if hasattr(schema, "model_dump"):
        schema = schema.model_dump(by_alias=True, mode="json")
    if type(name) is not str or type(schema) is not dict:
        raise AssertionError("tool name/inputSchema missing")
    return name, schema


def _decode(response) -> tuple[dict, str]:
    err = getattr(response, "isError", None)
    if err is None:
        err = getattr(response, "is_error", False)
    if err is True:
        raise AssertionError("MCP tool returned isError=true")
    structured = []
    for key in ("structuredContent", "structured_content"):
        value = getattr(response, key, None)
        if value is not None:
            if type(value) is not dict:
                raise AssertionError(f"{key} is not an object")
            structured.append((key, value))
    if len(structured) > 1 and any(x != structured[0][1] for _, x in structured[1:]):
        raise AssertionError("structuredContent aliases contradict")
    texts = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text" and type(getattr(block, "text", None)) is str:
            try:
                texts.append(_json_object(block.text))
            except (json.JSONDecodeError, ValueError):
                pass
    if structured:
        value, source = structured[0][1], structured[0][0]
        if any(text != value for text in texts):
            raise AssertionError("structured response contradicts JSON text")
        return value, source
    if len(texts) != 1:
        raise AssertionError("expected one structured object or one JSON text object")
    return texts[0], "single_json_text"


def _false_flags(test: unittest.TestCase, obj: dict) -> None:
    for flag in FLAGS:
        test.assertIs(type(obj.get(flag)), bool, f"{flag} must be a boolean")
        test.assertIs(obj[flag], False, f"{flag} must be false")


class F11RealMcpStdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_f10_generar_paquete_por_stdio_real(self):
        evidence_setting = os.environ.get("CARPINOVA_F11_EVIDENCE_DIR")
        self.assertTrue(evidence_setting, "external evidence directory not configured")
        evidence = Path(evidence_setting).resolve(strict=True)
        self.assertFalse(evidence.is_relative_to(ROOT.resolve()))

        with tempfile.TemporaryDirectory(prefix="carpinova-f11-") as temp:
            output = Path(temp).resolve(strict=True)
            required_env = ("SystemRoot", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP")
            child_env = {}
            for key in required_env:
                self.assertTrue(os.environ.get(key), f"missing Windows variable {key}")
                child_env[key] = os.environ[key]
            child_env.update({
                "PYTHONPATH": str(ROOT), "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1", "CARPINOVA_OUTPUT_ROOT": str(output),
                "CARPINOVA_NATIVE_EXECUTION_ENABLED": "0",
            })
            self.assertNotIn("CARPINOVA_NATIVE_APPROVAL_DIR", child_env)
            params = StdioServerParameters(
                command=sys.executable, args=["-m", "carpinova_agent.mcp_bridge"], env=child_env,
            )
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    available = list((await session.list_tools()).tools)
                    names = [getattr(t, "name", None) for t in available]
                    self.assertEqual(len(available), 6)
                    self.assertEqual(len(set(names)), 6)
                    self.assertEqual(set(names), TOOLS)
                    schemas = dict(_schema(tool) for tool in available)
                    tool_schema = schemas["carpinova_generar_borrador"]
                    props = tool_schema.get("properties")
                    self.assertIs(type(props), dict)
                    self.assertIn("seccion_y_mm", props)
                    section_schema = props["seccion_y_mm"]
                    self.assertTrue(Draft202012Validator(section_schema).is_valid(350))
                    self.assertTrue(Draft202012Validator(section_schema).is_valid(None))
                    request = _request()
                    args = {
                        "solicitud_json": json.dumps(request, ensure_ascii=False),
                        "proyecto": "F11_ROOM", "seccion_y_mm": 350, "incluir_planos": False,
                    }
                    response = await session.call_tool("carpinova_generar_borrador", args)
                    result, result_source = _decode(response)

            self.assertEqual(result.get("status"), "REVIEW_ONLY")
            self.assertEqual(result.get("proyecto"), "F11_ROOM")
            self.assertIs(type(result.get("piece_count")), int)
            self.assertEqual(result.get("piece_count"), 10)
            self.assertIs(type(result.get("section_y_mm")), int)
            self.assertEqual(result.get("section_y_mm"), 350)
            self.assertEqual(result.get("release"), "NO_GO")
            _false_flags(self, result)
            self.assertRegex(result.get("zip_sha256", ""), r"^[0-9a-f]{64}$")
            self.assertRegex(result.get("layout_sha256", ""), r"^[0-9a-f]{64}$")
            self.assertIs(type(result.get("files")), list)
            self.assertEqual(len(result["files"]), 7)
            self.assertEqual(len(set(result["files"])), 7)
            self.assertEqual(set(result["files"]), FILES)
            self.assertTrue(any("LOCAL_PATH_NOT_BINARY_MCP" in w for w in result.get("warnings", [])))
            self.assertFalse(any("zip_bytes" in str(k).lower() or "base64" in str(k).lower() for k in result))

            product_path = Path(result["room_package_path"])
            expected_path = (output / "F11_ROOM-room-review.zip").resolve(strict=True)
            self.assertFalse(product_path.is_symlink())
            self.assertEqual(product_path.resolve(strict=True), expected_path)
            self.assertEqual([p.name for p in output.iterdir()], [expected_path.name])
            zip_bytes = expected_path.read_bytes()
            product_sha = hashlib.sha256(zip_bytes).hexdigest()
            self.assertEqual(product_sha, result["zip_sha256"])

            with ZipFile(io.BytesIO(zip_bytes)) as archive:
                self.assertIsNone(archive.testzip())
                names_in_zip = archive.namelist()
                self.assertEqual(len(names_in_zip), 8)
                self.assertEqual(len(set(names_in_zip)), 8)
                self.assertEqual(set(names_in_zip), FILES | {"MANIFEST.json"})
                for name in names_in_zip:
                    path = PurePosixPath(name)
                    self.assertFalse(path.is_absolute())
                    self.assertNotIn("..", path.parts)
                    self.assertNotIn("\\", name)
                manifest_bytes = archive.read("MANIFEST.json")
                manifest = _json_object(manifest_bytes.decode("utf-8"))
                self.assertEqual(manifest.get("piece_count"), 10)
                self.assertEqual(manifest.get("section_y_mm"), 350)
                self.assertEqual(manifest.get("room_status"), "REVIEW_ONLY")
                self.assertEqual(manifest.get("release"), "NO_GO")
                self.assertEqual(manifest.get("layout_sha256"), result["layout_sha256"])
                listed = manifest.get("files")
                self.assertIs(type(listed), dict)
                self.assertEqual(set(listed), FILES)
                contents = {name: archive.read(name) for name in sorted(FILES)}
                for name, data in contents.items():
                    self.assertEqual(listed[name].get("bytes"), len(data), name)
                    self.assertEqual(listed[name].get("sha256"), hashlib.sha256(data).hexdigest(), name)

            room = _json_object(contents["04-habitacion.json"].decode("utf-8"))
            self.assertEqual(room.get("piece_count"), 10)
            self.assertEqual(room.get("layout_sha256"), result["layout_sha256"])
            self.assertEqual(room.get("status"), "REVIEW_ONLY")
            _false_flags(self, room)
            boxes = room.get("world_boxes")
            self.assertIs(type(boxes), list)
            self.assertEqual(len(boxes), 10)
            access = [b for b in boxes if b.get("role") == "front_corner_access"]
            blind = [b for b in boxes if b.get("role") == "front_corner_blind"]
            self.assertEqual(len(access), 1)
            self.assertEqual(len(blind), 1)
            self.assertEqual((access[0]["group_id"], access[0]["origin_xyz_mm"], access[0]["size_xyz_mm"]), ("CIEGO", [21, 21, 0], [456, 678, 18]))
            self.assertEqual((blind[0]["group_id"], blind[0]["origin_xyz_mm"], blind[0]["size_xyz_mm"]), ("CIEGO", [480, 0, 0], [420, 720, 18]))
            groups = {g["group_id"]: g for g in room.get("groups", [])}
            self.assertEqual(groups["CIEGO"]["piece_count"], 6)
            self.assertEqual(groups["RECTO"]["piece_count"], 4)
            self.assertFalse(room.get("panel_collisions"))
            self.assertFalse(room.get("envelope_collisions"))
            self.assertIn("CORNER_JOINT_AND_FILLER_NOT_DESIGNED", room.get("warnings", []))

            rows = list(csv.DictReader(io.StringIO(contents["06-paneles-en-escena.csv"].decode("utf-8"))))
            self.assertEqual(len(rows), 10)
            self.assertTrue(all(row.get("NOT_FOR_CUTTING") == "TRUE" for row in rows))
            svg = ET.fromstring(contents["03-seccion.svg"])
            svg_roles = {node.attrib.get("data-role") for node in svg.iter()}
            self.assertTrue({"front_corner_access", "front_corner_blind"}.issubset(svg_roles))
            html = contents["01-visor-3d.html"].decode("utf-8")
            self.assertIn("front_corner_access", html)
            self.assertIn("front_corner_blind", html)
            self.assertIn("NO CORTAR NI FABRICAR", html)
            self.assertNotRegex(html, r"(?i)(?:src|href)=[\"']https?://")

            safe_result = dict(result)
            safe_result["room_package_path"] = "<TEMP_ROOT>/F11_ROOM-room-review.zip"
            (evidence / "F11_RESPUESTA_MCP.json").write_text(
                json.dumps({"result_source": result_source, "result": safe_result}, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8", newline="\n",
            )
            tools_evidence = {
                "tools": sorted(names), "count": 6,
                "carpinova_generar_borrador": {"name": "carpinova_generar_borrador", "inputSchema": tool_schema},
            }
            (evidence / "F11_MCP_TOOLS.json").write_text(
                json.dumps(tools_evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8", newline="\n",
            )
            (evidence / "F11_PRODUCTO_MANIFEST.json").write_bytes(manifest_bytes)
            (evidence / "F11_PRODUCTO_SHA256.txt").write_text(product_sha + "\n", encoding="ascii", newline="\n")
            unpacked = evidence / "PRODUCTO_DESCOMPRIMIDO"
            unpacked.mkdir(parents=True, exist_ok=False)
            for name, data in contents.items():
                (unpacked / name).write_bytes(data)
            (unpacked / "MANIFEST.json").write_bytes(manifest_bytes)
            self.assertEqual(len(list(unpacked.iterdir())), 8)
            print(json.dumps({"stdio":"PASS","tools":6,"productive_tool_calls":1,"pieces":10,"section_y_mm":350,"product_zip_sha256":product_sha,"result_source":result_source}))


if __name__ == "__main__":
    unittest.main()