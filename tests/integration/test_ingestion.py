import os
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import psycopg

from virtual_staff_engineer.ingestion.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
)
from virtual_staff_engineer.ingestion.service import ingest_playbook


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


class FakeEmbeddingModels:
    def __init__(self, value=0.25):
        self.calls = []
        self.value = value
        self._lock = threading.Lock()

    def embed_content(self, **kwargs):
        with self._lock:
            self.calls.append(kwargs)
        return SimpleNamespace(
            embeddings=[
                SimpleNamespace(
                    values=[self.value] * EMBEDDING_DIMENSION
                )
            ]
        )


class IngestIntegrationTests(unittest.TestCase):
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
                    cur.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.tables
                            WHERE table_schema = 'public'
                              AND table_name = 'playbook_chunks'
                        );
                        """
                    )
                    schema_exists = cur.fetchone()[0]
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

    def tearDown(self):
        self._delete_test_documents()

    def _create_playbook(self, directory, markdown):
        filename = f"integration-{uuid.uuid4().hex}.md"
        self._filenames.append(filename)
        playbook_path = Path(directory) / filename
        playbook_path.write_text(markdown, encoding="utf-8")
        return playbook_path

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

    def _fetch_document_state(self, filename):
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        pd.document_id,
                        pd.category,
                        pd.archived_at,
                        pv.playbook_version_id,
                        pv.version,
                        pv.embedding_model,
                        pv.embedding_dimension,
                        COUNT(pc.playbook_chunk_id)
                    FROM playbook_documents AS pd
                    JOIN playbook_versions AS pv
                      ON pv.document_id = pd.document_id
                    LEFT JOIN playbook_chunks AS pc
                      ON pc.playbook_version_id = pv.playbook_version_id
                    WHERE pd.filename = %s
                    GROUP BY
                        pd.document_id,
                        pd.category,
                        pd.archived_at,
                        pv.playbook_version_id,
                        pv.version,
                        pv.embedding_model,
                        pv.embedding_dimension
                    ORDER BY pv.version;
                    """,
                    (filename,),
                )
                return cur.fetchall()

    def test_first_ingestion_persists_document_version_and_chunks(self):
        markdown = """# Engineering Standards

## Rule SEC-01: Sensitive Data
Do not log secrets.

## Rule CACHE-02: Cache TTL
Every cached value requires a TTL.
"""
        fake_models = FakeEmbeddingModels()
        fake_client = SimpleNamespace(models=fake_models)

        with tempfile.TemporaryDirectory() as temporary_directory:
            playbook_path = self._create_playbook(
                temporary_directory,
                markdown,
            )
            result = ingest_playbook(
                playbook_path,
                category="integration-test",
                database_url=TEST_DATABASE_URL,
                ai_client=fake_client,
            )

        rows = self._fetch_document_state(playbook_path.name)

        self.assertEqual(result["status"], "ingested")
        self.assertEqual(result["version"], 1)
        self.assertEqual(result["chunk_count"], 2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "integration-test")
        self.assertIsNone(rows[0][2])
        self.assertEqual(rows[0][4], 1)
        self.assertEqual(rows[0][5], DEFAULT_EMBEDDING_MODEL)
        self.assertEqual(rows[0][6], EMBEDDING_DIMENSION)
        self.assertEqual(rows[0][7], 2)

    def test_identical_ingestion_is_skipped_without_embedding_again(self):
        markdown = """## Rule SEC-01: Sensitive Data
Do not log secrets.
"""
        fake_models = FakeEmbeddingModels()
        fake_client = SimpleNamespace(models=fake_models)

        with tempfile.TemporaryDirectory() as temporary_directory:
            playbook_path = self._create_playbook(
                temporary_directory,
                markdown,
            )
            first_result = ingest_playbook(
                playbook_path,
                database_url=TEST_DATABASE_URL,
                ai_client=fake_client,
            )
            second_result = ingest_playbook(
                playbook_path,
                database_url=TEST_DATABASE_URL,
                ai_client=fake_client,
            )

        rows = self._fetch_document_state(playbook_path.name)

        self.assertEqual(first_result["status"], "ingested")
        self.assertEqual(second_result["status"], "skipped")
        self.assertEqual(len(fake_models.calls), 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][7], 1)

    def test_changed_content_creates_next_immutable_version(self):
        original_markdown = """## Rule SEC-01: Sensitive Data
Do not log secrets.
"""
        updated_markdown = """## Rule SEC-01: Sensitive Data
Do not log secrets or authentication tokens.
"""
        fake_models = FakeEmbeddingModels()
        fake_client = SimpleNamespace(models=fake_models)

        with tempfile.TemporaryDirectory() as temporary_directory:
            playbook_path = self._create_playbook(
                temporary_directory,
                original_markdown,
            )
            first_result = ingest_playbook(
                playbook_path,
                database_url=TEST_DATABASE_URL,
                ai_client=fake_client,
            )
            playbook_path.write_text(updated_markdown, encoding="utf-8")
            second_result = ingest_playbook(
                playbook_path,
                database_url=TEST_DATABASE_URL,
                ai_client=fake_client,
            )

        rows = self._fetch_document_state(playbook_path.name)

        self.assertEqual(first_result["version"], 1)
        self.assertEqual(second_result["version"], 2)
        self.assertEqual([row[4] for row in rows], [1, 2])
        self.assertEqual([row[7] for row in rows], [1, 1])

    def test_embedding_model_change_creates_next_version(self):
        markdown = """## Rule SEC-01: Sensitive Data
Do not log secrets.
"""
        fake_models = FakeEmbeddingModels()
        fake_client = SimpleNamespace(models=fake_models)
        replacement_model = "models/integration-test-embedding"

        with tempfile.TemporaryDirectory() as temporary_directory:
            playbook_path = self._create_playbook(
                temporary_directory,
                markdown,
            )
            first_result = ingest_playbook(
                playbook_path,
                database_url=TEST_DATABASE_URL,
                ai_client=fake_client,
            )
            second_result = ingest_playbook(
                playbook_path,
                database_url=TEST_DATABASE_URL,
                ai_client=fake_client,
                embedding_model=replacement_model,
            )

        rows = self._fetch_document_state(playbook_path.name)

        self.assertEqual(first_result["version"], 1)
        self.assertEqual(second_result["version"], 2)
        self.assertEqual(
            [row[5] for row in rows],
            [DEFAULT_EMBEDDING_MODEL, replacement_model],
        )

    def test_reingestion_restores_archived_document(self):
        markdown = """## Rule SEC-01: Sensitive Data
Do not log secrets.
"""
        fake_models = FakeEmbeddingModels()
        fake_client = SimpleNamespace(models=fake_models)

        with tempfile.TemporaryDirectory() as temporary_directory:
            playbook_path = self._create_playbook(
                temporary_directory,
                markdown,
            )
            ingest_playbook(
                playbook_path,
                category="old-category",
                database_url=TEST_DATABASE_URL,
                ai_client=fake_client,
            )

            with psycopg.connect(TEST_DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE playbook_documents
                        SET archived_at = CURRENT_TIMESTAMP
                        WHERE filename = %s;
                        """,
                        (playbook_path.name,),
                    )

            result = ingest_playbook(
                playbook_path,
                category="restored-category",
                database_url=TEST_DATABASE_URL,
                ai_client=fake_client,
            )

        rows = self._fetch_document_state(playbook_path.name)

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(rows[0][1], "restored-category")
        self.assertIsNone(rows[0][2])
        self.assertEqual(len(fake_models.calls), 1)

    def test_database_failure_rolls_back_all_ingestion_writes(self):
        markdown = """## Rule SEC-01: Sensitive Data
Do not log secrets.
"""

        duplicate_chunks = [
            {
                "chunk_index": 0,
                "rule_key": "SEC-01",
                "section": "Rule SEC-01: Sensitive Data",
                "content": "Do not log secrets.",
                "embedding": [0.25] * EMBEDDING_DIMENSION,
            },
            {
                "chunk_index": 0,
                "rule_key": "SEC-01",
                "section": "Rule SEC-01: Sensitive Data",
                "content": "Duplicate database key.",
                "embedding": [0.25] * EMBEDDING_DIMENSION,
            },
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            playbook_path = self._create_playbook(
                temporary_directory,
                markdown,
            )

            def duplicate_embedding_generator(
                parsed_chunks,
                ai_client,
                embedding_model,
                embedding_dimension,
            ):
                return duplicate_chunks

            with self.assertRaises(psycopg.errors.UniqueViolation):
                ingest_playbook(
                    playbook_path,
                    database_url=TEST_DATABASE_URL,
                    ai_client=object(),
                    embedding_generator=duplicate_embedding_generator,
                )

        self.assertEqual(self._fetch_document_state(playbook_path.name), [])

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM playbook_documents
                    WHERE filename = %s;
                    """,
                    (playbook_path.name,),
                )
                self.assertEqual(cur.fetchone()[0], 0)

    def test_concurrent_ingestion_creates_only_one_version(self):
        markdown = """## Rule SEC-01: Sensitive Data
Do not log secrets.
"""
        barrier = threading.Barrier(2)

        def synchronized_embeddings(
            parsed_chunks,
            ai_client,
            embedding_model,
            embedding_dimension,
        ):
            barrier.wait(timeout=10)
            return [
                {
                    "chunk_index": 0,
                    "rule_key": "SEC-01",
                    "section": "Rule SEC-01: Sensitive Data",
                    "content": "Do not log secrets.",
                    "embedding": [0.25] * EMBEDDING_DIMENSION,
                }
            ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            playbook_path = self._create_playbook(
                temporary_directory,
                markdown,
            )
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        ingest_playbook,
                        playbook_path,
                        database_url=TEST_DATABASE_URL,
                        ai_client=object(),
                        embedding_generator=synchronized_embeddings,
                    )
                    for _ in range(2)
                ]
                results = [future.result(timeout=20) for future in futures]

        rows = self._fetch_document_state(playbook_path.name)

        self.assertEqual(
            sorted(result["status"] for result in results),
            ["ingested", "skipped"],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][4], 1)
        self.assertEqual(rows[0][7], 1)


if __name__ == "__main__":
    unittest.main()
