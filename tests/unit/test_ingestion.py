import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from virtual_staff_engineer.ingestion.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    generate_embeddings,
)
from virtual_staff_engineer.ingestion.markdown import (
    derive_rule_key,
    parse_markdown,
)


class FakeEmbeddingModels:
    def __init__(self):
        self.calls = []

    def embed_content(self, **kwargs):
        self.calls.append(kwargs)
        values = [0.25] * EMBEDDING_DIMENSION
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=values)]
        )


class IngestTests(unittest.TestCase):
    def test_parse_markdown_skips_empty_general_section(self):
        markdown = """# Engineering Standards

## Rule SEC-01: Sensitive Data
Do not log secrets.

## Rule CACHE-02: Cache TTL
All cached values require a TTL.
"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            playbook_path = Path(temporary_directory) / "playbook.md"
            playbook_path.write_text(markdown, encoding="utf-8")

            chunks = parse_markdown(playbook_path)

        self.assertEqual(
            chunks,
            [
                ("Rule SEC-01: Sensitive Data", "Do not log secrets."),
                ("Rule CACHE-02: Cache TTL", "All cached values require a TTL."),
            ],
        )

    def test_derive_rule_key_prefers_explicit_identifier(self):
        self.assertEqual(
            derive_rule_key("Rule sec-01: Sensitive Data"),
            "SEC-01",
        )

    def test_derive_rule_key_falls_back_to_heading_slug(self):
        self.assertEqual(
            derive_rule_key("General API Standards"),
            "GENERAL-API-STANDARDS",
        )

    def test_generate_embeddings_preserves_chunk_metadata(self):
        fake_models = FakeEmbeddingModels()
        fake_client = SimpleNamespace(models=fake_models)

        chunks = generate_embeddings(
            [("Rule CACHE-02: Cache TTL", "Use a TTL.")],
            fake_client,
        )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["chunk_index"], 0)
        self.assertEqual(chunks[0]["rule_key"], "CACHE-02")
        self.assertEqual(
            len(chunks[0]["embedding"]),
            EMBEDDING_DIMENSION,
        )
        self.assertEqual(
            fake_models.calls[0]["model"],
            DEFAULT_EMBEDDING_MODEL,
        )


if __name__ == "__main__":
    unittest.main()
