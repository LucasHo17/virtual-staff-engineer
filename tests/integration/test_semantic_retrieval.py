import hashlib
import os
import threading
import unittest
import uuid
from types import SimpleNamespace

import psycopg

from virtual_staff_engineer.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
)
from virtual_staff_engineer.retrieval.semantic import semantic_search


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


class FakeEmbeddingModels:
    def __init__(self, values):
        self.values = values
        self.calls = []
        self._lock = threading.Lock()

    def embed_content(self, **kwargs):
        with self._lock:
            self.calls.append(kwargs)
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=self.values)]
        )


class SemanticRetrievalIntegrationTests(unittest.TestCase):
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
        self._filenames = []
        self.category = f"semantic-test-{uuid.uuid4().hex}"

    def tearDown(self):
        self._delete_test_documents()

    def _basis_vector(self, index):
        vector = [0.0] * EMBEDDING_DIMENSION
        vector[index] = 1.0
        return vector

    def _vector_literal(self, vector):
        return "[" + ",".join(str(value) for value in vector) + "]"

    def _create_document(self, category=None, archived=False):
        filename = f"semantic-{uuid.uuid4().hex}.md"
        self._filenames.append(filename)

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO playbook_documents (
                        filename,
                        category,
                        archived_at
                    )
                    VALUES (
                        %s,
                        %s,
                        CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END
                    )
                    RETURNING document_id;
                    """,
                    (filename, category or self.category, archived),
                )
                return cur.fetchone()[0]

    def _create_version(
        self,
        document_id,
        version,
        chunks,
        embedding_model=DEFAULT_EMBEDDING_MODEL,
    ):
        checksum = hashlib.sha256(
            f"{document_id}:{version}:{embedding_model}".encode("utf-8")
        ).hexdigest()

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO playbook_versions (
                        document_id,
                        version,
                        checksum,
                        embedding_model,
                        embedding_dimension
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING playbook_version_id;
                    """,
                    (
                        document_id,
                        version,
                        checksum,
                        embedding_model,
                        EMBEDDING_DIMENSION,
                    ),
                )
                playbook_version_id = cur.fetchone()[0]

                for chunk_index, (rule_key, content, vector) in enumerate(chunks):
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
                            playbook_version_id,
                            rule_key,
                            chunk_index,
                            f"Rule {rule_key}",
                            content,
                            self._vector_literal(vector),
                        ),
                    )

        return playbook_version_id

    def _search(self, vector, **search_options):
        fake_models = FakeEmbeddingModels(vector)
        fake_client = SimpleNamespace(models=fake_models)
        return semantic_search(
            "test query",
            database_url=TEST_DATABASE_URL,
            ai_client=fake_client,
            **search_options,
        )

    def _delete_test_documents(self):
        if not self._filenames:
            return

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
                        WHERE pd.filename = ANY(%s)
                    );
                    """,
                    (self._filenames,),
                )
                cur.execute(
                    """
                    DELETE FROM playbook_versions
                    WHERE document_id IN (
                        SELECT document_id
                        FROM playbook_documents
                        WHERE filename = ANY(%s)
                    );
                    """,
                    (self._filenames,),
                )
                cur.execute(
                    """
                    DELETE FROM playbook_documents
                    WHERE filename = ANY(%s);
                    """,
                    (self._filenames,),
                )

    def test_cosine_search_ranks_chunks_and_returns_citations(self):
        document_id = self._create_document()
        self._create_version(
            document_id,
            version=1,
            chunks=[
                (
                    "SEC-01",
                    "Never write credentials to logs.",
                    self._basis_vector(0),
                ),
                (
                    "CACHE-02",
                    "Every cached value requires a TTL.",
                    self._basis_vector(1),
                ),
            ],
        )

        results = self._search(
            self._basis_vector(0),
            category=self.category,
            top_k=2,
        )

        self.assertEqual(
            [result.rule_key for result in results],
            ["SEC-01", "CACHE-02"],
        )
        self.assertAlmostEqual(results[0].similarity_score, 1.0)
        self.assertAlmostEqual(results[1].similarity_score, 0.0)
        self.assertTrue(results[0].playbook_chunk_id)
        self.assertTrue(results[0].playbook_version_id)
        self.assertEqual(results[0].version, 1)
        self.assertEqual(results[0].category, self.category)

    def test_search_excludes_archived_old_and_other_category_content(self):
        active_document_id = self._create_document()
        self._create_version(
            active_document_id,
            version=1,
            chunks=[("OLD-01", "Old content.", self._basis_vector(0))],
        )
        self._create_version(
            active_document_id,
            version=2,
            chunks=[("NEW-02", "Current content.", self._basis_vector(1))],
        )

        archived_document_id = self._create_document(archived=True)
        self._create_version(
            archived_document_id,
            version=1,
            chunks=[("ARCH-01", "Archived content.", self._basis_vector(0))],
        )

        other_document_id = self._create_document(
            category=f"other-{self.category}"
        )
        self._create_version(
            other_document_id,
            version=1,
            chunks=[("OTHER-01", "Other category.", self._basis_vector(0))],
        )

        results = self._search(
            self._basis_vector(0),
            category=self.category,
            top_k=10,
        )

        self.assertEqual([result.rule_key for result in results], ["NEW-02"])
        self.assertEqual(results[0].version, 2)

    def test_search_never_falls_back_to_stale_model_version(self):
        replacement_model = "models/integration-test-embedding"
        document_id = self._create_document()
        self._create_version(
            document_id,
            version=1,
            chunks=[("OLD-01", "Old model.", self._basis_vector(0))],
        )
        self._create_version(
            document_id,
            version=2,
            chunks=[("NEW-02", "New model.", self._basis_vector(0))],
            embedding_model=replacement_model,
        )

        default_model_results = self._search(
            self._basis_vector(0),
            category=self.category,
        )
        replacement_model_results = self._search(
            self._basis_vector(0),
            category=self.category,
            embedding_model=replacement_model,
        )

        self.assertEqual(default_model_results, [])
        self.assertEqual(
            [result.rule_key for result in replacement_model_results],
            ["NEW-02"],
        )


if __name__ == "__main__":
    unittest.main()
