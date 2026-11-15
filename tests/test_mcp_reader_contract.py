from __future__ import annotations

import copy
import json
from types import SimpleNamespace
import unittest

from scripts import verify_local_mcp


FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")
PROJECT = "reader_contract_project"
FILENAME = "cad-exchange.json"


def valid_payload() -> dict:
    return {
        "proyecto": PROJECT,
        "archivo": FILENAME,
        "encoding": "utf-8",
        "status": "DRAFT_NOT_FOR_CUTTING",
        "contenido": '{"review": true}',
        **{flag: False for flag in FLAGS},
    }


class TextContent:
    type = "text"

    def __init__(self, text: object) -> None:
        self.text = text


class ImageContent:
    type = "image"

    def __init__(self) -> None:
        self.data = b"image-bytes-not-for-reader"


class ToolSession:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, arguments: dict) -> object:
        self.calls.append((name, arguments))
        return self.result


class MCPReaderContractTests(unittest.IsolatedAsyncioTestCase):
    async def read_payload(self, result: object) -> dict:
        session = ToolSession(result)
        payload = await verify_local_mcp._read_payload_via_mcp(
            session, PROJECT, FILENAME,
        )
        self.assertEqual(
            session.calls,
            [("carpinova_leer_entregable", {
                "proyecto": PROJECT,
                "archivo": FILENAME,
            })],
        )
        return payload

    async def assert_read_fails(self, result: object) -> AssertionError:
        session = ToolSession(result)
        with self.assertRaises(AssertionError) as raised:
            await verify_local_mcp._read_payload_via_mcp(
                session, PROJECT, FILENAME,
            )
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0][0], "carpinova_leer_entregable")
        return raised.exception

    async def test_structured_aliases_return_validated_object(self) -> None:
        expected = valid_payload()
        expected["book_evidence_status"] = "BOOK_UNVERIFIED"
        for attribute in ("structured_content", "structuredContent"):
            with self.subTest(attribute=attribute):
                result = SimpleNamespace(**{attribute: copy.deepcopy(expected)})
                self.assertEqual(await self.read_payload(result), expected)

    async def test_text_json_and_equivalent_dual_channels_are_accepted(self) -> None:
        expected = valid_payload()
        text = json.dumps(expected, ensure_ascii=False)
        text_only = SimpleNamespace(
            structuredContent=None,
            structured_content=None,
            content=[TextContent(text)],
        )
        self.assertEqual(await self.read_payload(text_only), expected)

        both = SimpleNamespace(
            structured_content=copy.deepcopy(expected),
            structuredContent=copy.deepcopy(expected),
            content=[TextContent(text)],
        )
        self.assertEqual(await self.read_payload(both), expected)

    async def test_contradictory_structured_or_text_channels_fail(self) -> None:
        expected = valid_payload()
        other = copy.deepcopy(expected)
        other["contenido"] = "different"

        aliases = SimpleNamespace(
            structured_content=expected,
            structuredContent=other,
        )
        self.assertIn("aliases", str(await self.assert_read_fails(aliases)))

        text_conflict = SimpleNamespace(
            structured_content=expected,
            content=[TextContent(json.dumps(other))],
        )
        self.assertIn(
            "contradict", str(await self.assert_read_fails(text_conflict)).lower(),
        )

        non_dict_alias = SimpleNamespace(
            structured_content=expected,
            structuredContent="not a structured object",
        )
        error = await self.assert_read_fails(non_dict_alias)
        self.assertIn("BLOCKED_PROTOCOL_SHAPE", str(error))

    async def test_mcp_error_aliases_never_return_payload(self) -> None:
        payload = valid_payload()
        results = (
            SimpleNamespace(isError=True, is_error=False, structured_content=payload),
            SimpleNamespace(isError=False, is_error=True, structured_content=payload),
            SimpleNamespace(isError=True, is_error=False, content=[TextContent("secret")]),
        )
        for index, result in enumerate(results):
            with self.subTest(index=index):
                error = await self.assert_read_fails(result)
                self.assertIn("MCP tool error", str(error))
                self.assertNotIn("secret", str(error))

    async def test_unrecognized_content_shapes_fail_with_safe_metadata(self) -> None:
        responses = (
            SimpleNamespace(content=[]),
            SimpleNamespace(content=[TextContent("{}"), TextContent("{}")]),
            SimpleNamespace(content=[ImageContent()]),
            SimpleNamespace(content=[TextContent(None)]),
            SimpleNamespace(),
        )
        for result in responses:
            with self.subTest(result=type(result).__name__):
                error = await self.assert_read_fails(result)
                self.assertIn("BLOCKED_PROTOCOL_SHAPE", str(error))
                self.assertIn("content_count", str(error))
                self.assertIn("block_types", str(error))
                self.assertIn("text_length", str(error))
                self.assertNotIn("image-bytes", str(error))

    async def test_text_channel_requires_strict_json_object(self) -> None:
        payload_text = json.dumps(valid_payload())
        duplicate_key = payload_text[:-1] + ',"archivo":"cad-exchange.json"}'
        variants = (
            "{",
            duplicate_key,
            payload_text.replace('"cutting_ready": false', '"cutting_ready": NaN'),
            payload_text.replace('"cutting_ready": false', '"cutting_ready": Infinity'),
            "[]",
            "7",
            "true",
            '"scalar"',
        )
        for index, text in enumerate(variants):
            with self.subTest(index=index):
                error = await self.assert_read_fails(
                    SimpleNamespace(content=[TextContent(text)]),
                )
                self.assertNotIn(text, str(error))

    async def test_project_file_encoding_status_and_schema_are_exact(self) -> None:
        mutations = (
            ("proyecto", "another_project"),
            ("archivo", "manifest.json"),
            ("encoding", "UTF-8"),
            ("status", "APPROVED"),
        )
        for key, value in mutations:
            with self.subTest(key=key):
                payload = valid_payload()
                payload[key] = value
                await self.assert_read_fails(
                    SimpleNamespace(structured_content=payload),
                )

        missing_content = valid_payload()
        del missing_content["contenido"]
        await self.assert_read_fails(
            SimpleNamespace(structured_content=missing_content),
        )
        non_text_content = valid_payload()
        non_text_content["contenido"] = 7
        await self.assert_read_fails(
            SimpleNamespace(structured_content=non_text_content),
        )

        invented_authority = valid_payload()
        invented_authority["fabrication_authorized"] = True
        await self.assert_read_fails(
            SimpleNamespace(structured_content=invented_authority),
        )

    async def test_all_four_flags_must_be_present_and_strict_false(self) -> None:
        for flag in FLAGS:
            for value in (True, 0, "false", None):
                with self.subTest(flag=flag, value=value):
                    payload = valid_payload()
                    payload[flag] = value
                    await self.assert_read_fails(
                        SimpleNamespace(structured_content=payload),
                    )
            with self.subTest(flag=flag, value="missing"):
                payload = valid_payload()
                del payload[flag]
                await self.assert_read_fails(
                    SimpleNamespace(structured_content=payload),
                )


if __name__ == "__main__":
    unittest.main()
