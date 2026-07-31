import hashlib
import os
import unittest
import uuid

import psycopg

from virtual_staff_engineer.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
)
from virtual_staff_engineer.retrieval.lexical import lexical_search


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


class LexicalRetrievalIntegrationTests(unittest.TestCase):
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
        self.category = f"lexical-test-{uuid.uuid4().hex}"

    def tearDown(self):
        self._delete_test_documents()

    def _vector_literal(self):
        return "[1" + ",0" * (EMBEDDING_DIMENSION - 1) + "]"

    def _create_document(self, category=None, archived=False):
        filename = f"lexical-{uuid.uuid4().hex}.md"
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

    def _create_version(self, document_id, version, chunks):
        checksum = hashlib.sha256(
            f"{document_id}:{version}".encode("utf-8")
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
                        DEFAULT_EMBEDDING_MODEL,
                        EMBEDDING_DIMENSION,
                    ),
                )
                playbook_version_id = cur.fetchone()[0]

                for chunk_index, (rule_key, section, content) in enumerate(chunks):
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
                            section,
                            content,
                            self._vector_literal(),
                        ),
                    )

    def _search(self, query, **search_options):
        return lexical_search(
            query,
            database_url=TEST_DATABASE_URL,
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

    def test_exact_rule_key_is_boosted_above_text_reference(self):
        document_id = self._create_document()
        self._create_version(
            document_id,
            version=1,
            chunks=[
                (
                    "SEC-01",
                    "Sensitive Data Restriction",
                    "Never write credentials to application logs.",
                ),
                (
                    "LOG-02",
                    "Logging References",
                    "Related requirements include rule SEC-01.",
                ),
            ],
        )

        results = self._search(
            "SEC-01",
            category=self.category,
            top_k=2,
        )

        self.assertEqual(
            [result.rule_key for result in results],
            ["SEC-01", "LOG-02"],
        )
        self.assertTrue(results[0].exact_rule_key_match)
        self.assertFalse(results[1].exact_rule_key_match)
        self.assertGreater(results[0].lexical_score, results[1].lexical_score)

    def test_full_text_and_trigram_search_return_citable_chunks(self):
        document_id = self._create_document()
        self._create_version(
            document_id,
            version=1,
            chunks=[
                (
                    "AUTH-03",
                    "Credential Logging",
                    "Authentication tokens must never be written to logs.",
                )
            ],
        )

        full_text_results = self._search(
            "authentication tokens",
            category=self.category,
        )
        fuzzy_results = self._search(
            "credentail loggin",
            category=self.category,
        )

        self.assertEqual(full_text_results[0].rule_key, "AUTH-03")
        self.assertGreater(full_text_results[0].full_text_rank, 0)
        self.assertEqual(fuzzy_results[0].rule_key, "AUTH-03")
        self.assertGreaterEqual(fuzzy_results[0].trigram_score, 0.2)
        self.assertTrue(fuzzy_results[0].playbook_chunk_id)
        self.assertEqual(fuzzy_results[0].version, 1)

    def test_search_uses_only_active_latest_category_content(self):
        active_document_id = self._create_document()
        self._create_version(
            active_document_id,
            version=1,
            chunks=[("OLD-01", "Obsolete Alpha", "obsoletealpha requirement")],
        )
        self._create_version(
            active_document_id,
            version=2,
            chunks=[("NEW-02", "Current Standard", "current requirement")],
        )

        archived_document_id = self._create_document(archived=True)
        self._create_version(
            archived_document_id,
            version=1,
            chunks=[("ARCH-01", "Obsolete Alpha", "obsoletealpha requirement")],
        )

        other_document_id = self._create_document(
            category=f"other-{self.category}"
        )
        self._create_version(
            other_document_id,
            version=1,
            chunks=[("OTHER-01", "Obsolete Alpha", "obsoletealpha requirement")],
        )

        results = self._search(
            "obsoletealpha",
            category=self.category,
            fuzzy_threshold=0.8,
        )

        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
