"""Synthetic fixture verifies integrity behavior; it is NOT proof against full book."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from knowledge_client import BundleError, load_bundle, search_content
from knowledge_client.reader import SOURCE_SHA256


class KnowledgeReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.meta = {
            "schema_version": "0.1.0",
            "knowledge_version": "0.1.0",
            "book_id": "cpnc-2025",
        }
        self.data = {
            "knowledge.bundle.json": {
                **self.meta,
                "pages": [
                    {"page_id": "PAGE-CPNC-2025-P0110"},
                    {"page_id": "PAGE-CPNC-2025-P0111"},
                ],
                "content": [
                    {
                        "content_id": "CONTENT-1",
                        "page_id": "PAGE-CPNC-2025-P0110",
                        "normalized_text": "La bisagra de cazoleta se instala según ficha.",
                        "tags": ["bisagras", "herrajes"],
                        "source": {
                            "book_id": "cpnc-2025", "pdf_page": 110, "printed_page": 88,
                            "extraction": {"review_status": "VISUALLY_VERIFIED"},
                        },
                    },
                    {
                        "content_id": "CONTENT-2",
                        "page_id": "PAGE-CPNC-2025-P0111",
                        "normalized_text": "Los tarugos unen tableros.",
                        "tags": ["ensamble"],
                        "source": {
                            "book_id": "cpnc-2025", "pdf_page": 111, "printed_page": 89,
                            "extraction": {"review_status": "REVIEW_PENDING"},
                        },
                    },
                ],
                "measurements": [],
                "rules": [],
            },
            "figures.bundle.json": {**self.meta, "figures": []},
            "lessons.bundle.json": {**self.meta, "lessons": []},
        }
        self.manifest = {
            **self.meta,
            "source_manifest_sha256": SOURCE_SHA256,
            "counts": {"pages": 2, "content": 2, "measurements": 0,
                       "rules": 0, "figures": 0, "lessons": 0},
        }
        self.write_fixture()

    def write_fixture(self):
        digests = {}
        for filename, payload in self.data.items():
            raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
            (self.root / filename).write_bytes(raw)
            digests[filename] = hashlib.sha256(raw).hexdigest()
        self.manifest["files"] = digests
        (self.root / "manifest.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )

    def test_search_with_provenance(self):
        output = search_content(load_bundle(self.root), "BISAGRAS", 3)
        self.assertEqual(output["total_matches"], 1)
        first = output["results"][0]
        self.assertEqual(first["pdf_page"], 110)
        self.assertEqual(first["printed_page"], 88)
        self.assertEqual(first["content_id"], "CONTENT-1")
        self.assertEqual(first["review_status"], "VISUALLY_VERIFIED")
        self.assertIs(first["manufacturing_authority"], False)

    def test_partial_scope_is_explicit(self):
        loaded = load_bundle(self.root)
        self.assertEqual(loaded["coverage"], "PARTIAL_CORPUS")
        self.assertIs(loaded["source_pdf_bytes_verified"], False)

    def test_accent_normalization(self):
        result = search_content(load_bundle(self.root), "cazóleta")
        self.assertEqual(result["total_matches"], 1)

    def test_no_match_is_empty_not_inferred(self):
        output = search_content(load_bundle(self.root), "cocinas")
        self.assertEqual(output["results"], [])
        self.assertEqual(output["total_matches"], 0)

    def test_tampering_fails(self):
        with (self.root / "knowledge.bundle.json").open("ab") as stream:
            stream.write(b" ")
        with self.assertRaises(BundleError):
            load_bundle(self.root)

    def test_wrong_book_hash_fails(self):
        self.manifest["source_manifest_sha256"] = "0" * 64
        self.write_fixture()
        with self.assertRaises(BundleError):
            load_bundle(self.root)

    def test_wrong_counts_fails(self):
        self.manifest["counts"]["content"] = 200
        self.write_fixture()
        with self.assertRaises(BundleError):
            load_bundle(self.root)

    def test_broken_page_reference_fails(self):
        self.data["knowledge.bundle.json"]["content"][0]["page_id"] = "FAKE"
        self.write_fixture()
        with self.assertRaises(BundleError):
            load_bundle(self.root)

    def test_claiming_full_book_fails(self):
        self.manifest.update({"scope": "BOOK", "knowledge_version": "1.2.0",
                              "source_page_count": 295, "excluded_page_count": 43})
        for data in self.data.values():
            data["knowledge_version"] = "1.2.0"
        self.write_fixture()
        with self.assertRaises(BundleError):
            load_bundle(self.root)

    def test_reject_invalid_limit(self):
        with self.assertRaises(BundleError):
            search_content(load_bundle(self.root), "bisagras", 0)

    def test_reject_blank_query(self):
        with self.assertRaises(BundleError):
            search_content(load_bundle(self.root), "  ")

    def test_unexpected_bundle_file_fails(self):
        self.manifest["files"]["unexpected.json"] = "1" * 64
        (self.root / "manifest.json").write_text(json.dumps(self.manifest))
        with self.assertRaises(BundleError):
            load_bundle(self.root)


if __name__ == "__main__":
    unittest.main()
