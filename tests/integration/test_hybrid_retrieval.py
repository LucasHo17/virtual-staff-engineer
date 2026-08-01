import hashlib
import os
import unittest
import uuid
from types import SimpleNamespace

import psycopg

from virtual_staff_engineer.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
)
from virtual_staff_engineer.retrieval.hybrid import hybrid_search


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


class FakeEmbeddingModels:
    def __init__(self, values):
        self.values = values

    def embed_content(self, **kwargs):
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=self.values)]
        )


class HybridRetrievalIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TEST_DATABASE_URL:
            raise unittest.SkipTest(
                "Set TEST_DATABASE_URL or DATABASE_URL to run PostgreSQL "
                "integration tests."
            )

        try:
            with psycopg.connect(TEST_DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT to_regclass('public.playbook_chunks');")
                    schema_exists = cur.fetchone()[0] is not None
        except psycopg.Error as error:
            raise unittest.SkipTest(
                f"PostgreSQL integration database is unavailable: {error}"
            )

        if not schema_exists:
            raise unittest.SkipTest(
                "Database schema is missing. Run python scripts/migrate.py first."
            )

    def setUp(self):
        self.filename = f"hybrid-{uuid.uuid4().hex}.md"
        self.category = f"hybrid-test-{uuid.uuid4().hex}"

    def tearDown(self):
        self._delete_document()

    def _basis_vector(self, index):
        vector = [0.0] * EMBEDDING_DIMENSION
        vector[index] = 1.0
        return vector

    def _vector_literal(self, vector):
        return "[" + ",".join(str(value) for value in vector) + "]"

    def _insert_fixture(self):
        checksum = hashlib.sha256(self.filename.encode("utf-8")).hexdigest()
        semantic_only_vector = self._basis_vector(0)
        overlapping_vector = [0.0] * EMBEDDING_DIMENSION
        overlapping_vector[0] = 0.8
        overlapping_vector[1] = 0.6

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO playbook_documents (filename, category)
                    VALUES (%s, %s)
                    RETURNING document_id;
                    """,
                    (self.filename, self.category),
                )
                document_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO playbook_versions (
                        document_id,
                        version,
                        checksum,
                        embedding_model,
                        embedding_dimension
                    )
                    VALUES (%s, 1, %s, %s, %s)
                    RETURNING playbook_version_id;
                    """,
                    (
                        document_id,
                        checksum,
                        DEFAULT_EMBEDDING_MODEL,
                        EMBEDDING_DIMENSION,
                    ),
                )
                version_id = cur.fetchone()[0]

                chunks = [
                    (
                        "VECTOR-99",
                        "Unrelated Vector Rule",
                        "This content has no matching lexical terms.",
                        semantic_only_vector,
                    ),
                    (
                        "SEC-01",
                        "Sensitive Data Restriction",
                        "Never write credentials to logs.",
                        overlapping_vector,
                    ),
                ]
                for index, (rule_key, section, content, vector) in enumerate(chunks):
                    cur.execute(
                        """
                        INSERT INTO playbook_chunks (
                            playbook_version_id,
                            rule_key,
                            chunk_index,
                            section,
                            content,
                            embedding
                        )
                        VALUES (%s, %s, %s, %s, %s, %s::vector);
                        """,
                        (
                            version_id,
                            rule_key,
                            index,
                            section,
                            content,
                            self._vector_literal(vector),
                        ),
                    )

        return semantic_only_vector

    def _delete_document(self):
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM playbook_chunks
                    WHERE playbook_version_id IN (
                        SELECT pv.playbook_version_id
                        FROM playbook_versions AS pv
                        JOIN playbook_documents AS pd
                          ON pd.document_id = pv.document_id
                        WHERE pd.filename = %s
                    );
                    """,
                    (self.filename,),
                )
                cur.execute(
                    """
                    DELETE FROM playbook_versions
                    WHERE document_id IN (
                        SELECT document_id
                        FROM playbook_documents
                        WHERE filename = %s
                    );
                    """,
                    (self.filename,),
                )
                cur.execute(
                    """
                    DELETE FROM playbook_documents
                    WHERE filename = %s;
                    """,
                    (self.filename,),
                )

    def test_overlap_is_promoted_above_semantic_only_candidate(self):
        query_vector = self._insert_fixture()
        fake_client = SimpleNamespace(
            models=FakeEmbeddingModels(query_vector)
        )

        results = hybrid_search(
            "SEC-01",
            top_k=2,
            candidate_k=2,
            category=self.category,
            fuzzy_threshold=0.8,
            database_url=TEST_DATABASE_URL,
            ai_client=fake_client,
        )

        self.assertEqual(
            [result.rule_key for result in results],
            ["SEC-01", "VECTOR-99"],
        )
        self.assertEqual(results[0].semantic_rank, 2)
        self.assertEqual(results[0].lexical_rank, 1)
        self.assertEqual(results[1].semantic_rank, 1)
        self.assertIsNone(results[1].lexical_rank)
        self.assertGreater(results[0].rrf_score, results[1].rrf_score)


if __name__ == "__main__":
    unittest.main()
