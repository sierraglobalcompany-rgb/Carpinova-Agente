"""Runtime MCP schema contract; run only in the SDK-enabled MCP workflow."""
import unittest

from carpinova_agent.mcp_bridge import create_server


class McpRuntimeContractTests(unittest.TestCase):
    def test_six_tools_and_optional_bounded_flow_review_argument(self):
        server = create_server()
        expected = {
            "carpinova_estado", "carpinova_consultar", "carpinova_generar_borrador",
            "carpinova_renderizar_lamina", "carpinova_exportar_3d",
            "carpinova_leer_entregable",
        }
        self.assertEqual(set(server._tool_manager._tools), expected)
        params = server._tool_manager._tools["carpinova_generar_borrador"].parameters
        prop = params["properties"]["flow_review_json"]
        self.assertEqual(prop["type"], "string")
        self.assertEqual(prop["default"], "")
        self.assertNotIn("flow_review_json", params["required"])


if __name__ == "__main__":
    unittest.main()
