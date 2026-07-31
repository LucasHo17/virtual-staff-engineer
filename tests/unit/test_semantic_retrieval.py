import unittest
from types import SimpleNamespace

from virtual_staff_engineer.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
)
from virtual_staff_engineer.retrieval.semantic import (
    generate_query_embedding,
    search_by_embedding,
    semantic_search,
)


class FakeEmbeddingModels:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def embed_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=self.values)]
        )


class SemanticRetrievalUnitTests(unittest.TestCase):
    def test_generate_query_embedding_trims_and_embeds_query(self):
        values = [0.25] * EMBEDDING_DIMENSION
        fake_models = FakeEmbeddingModels(values)
        fake_client = SimpleNamespace(models=fake_models)

        result = generate_query_embedding(
            "  credentials in logs  ",
            ai_client=fake_client,
        )

        self.assertEqual(result, values)
        self.assertEqual(
            fake_models.calls[0]["contents"],
            "credentials in logs",
        )
        self.assertEqual(
            fake_models.calls[0]["model"],
            DEFAULT_EMBEDDING_MODEL,
        )

    def test_query_embedding_rejects_wrong_dimension(self):
        fake_models = FakeEmbeddingModels([0.25] * 3)
        fake_client = SimpleNamespace(models=fake_models)

        with self.assertRaisesRegex(
            ValueError,
            "Expected 1536 embedding dimensions",
        ):
            generate_query_embedding(
                "credentials in logs",
                ai_client=fake_client,
            )

    def test_semantic_search_rejects_empty_query_before_api_or_database(self):
        with self.assertRaisesRegex(ValueError, "non-empty string"):
            semantic_search("   ")

    def test_semantic_search_rejects_invalid_top_k(self):
        for invalid_top_k in (0, 101, 1.5, True):
            with self.subTest(top_k=invalid_top_k):
                with self.assertRaises(ValueError):
                    semantic_search("credentials", top_k=invalid_top_k)

    def test_search_rejects_dimension_not_supported_by_schema(self):
        with self.assertRaisesRegex(ValueError, "requires 1536 dimensions"):
            search_by_embedding(
                [0.25] * 10,
                embedding_dimension=10,
            )

    def test_search_rejects_non_finite_embedding_values(self):
        invalid_embedding = [0.25] * EMBEDDING_DIMENSION
        invalid_embedding[0] = float("nan")

        with self.assertRaisesRegex(ValueError, "finite numbers"):
            search_by_embedding(invalid_embedding)


if __name__ == "__main__":
    unittest.main()
