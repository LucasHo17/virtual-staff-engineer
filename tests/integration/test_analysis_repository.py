import os
import unittest

import psycopg

from virtual_staff_engineer.analysis.contracts import (
    AnalysisInput,
    EvaluationDecision,
    ProposedFinding,
    RuleEvidence,
    SearchQuery,
)
from virtual_staff_engineer.analysis.orchestrator import AnalysisResult
from virtual_staff_engineer.analysis.repository import AnalysisRepository
from virtual_staff_engineer.analysis.validation import FindingRejection


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


class AnalysisRepositoryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TEST_DATABASE_URL:
            raise unittest.SkipTest("Set TEST_DATABASE_URL or DATABASE_URL.")
        try:
            with psycopg.connect(TEST_DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT to_regclass('analysis_run_queries') IS NOT NULL;
                        """
                    )
                    if not cur.fetchone()[0]:
                        raise unittest.SkipTest(
                            "Run python scripts/migrate.py before Phase 2 tests."
                        )
        except psycopg.Error as exc:
            raise unittest.SkipTest(
                f"PostgreSQL is unavailable for integration tests: {exc}"
            ) from exc

    def setUp(self):
        self.analysis_run_ids = []

    def tearDown(self):
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                for analysis_run_id in self.analysis_run_ids:
                    cur.execute(
                        """
                        DELETE FROM violation_evidence
                        WHERE violation_id IN (
                            SELECT violation_id FROM violations
                            WHERE analysis_run_id = %s
                        );
                        """,
                        (analysis_run_id,),
                    )
                    cur.execute(
                        "DELETE FROM violations WHERE analysis_run_id = %s;",
                        (analysis_run_id,),
                    )
                    cur.execute(
                        """
                        DELETE FROM analysis_finding_reviews
                        WHERE analysis_run_id = %s;
                        """,
                        (analysis_run_id,),
                    )
                    cur.execute(
                        """
                        DELETE FROM analysis_finding_rejections
                        WHERE analysis_run_id = %s;
                        """,
                        (analysis_run_id,),
                    )
                    cur.execute(
                        """
                        DELETE FROM analysis_retrieval_evidence
                        WHERE analysis_query_id IN (
                            SELECT analysis_query_id
                            FROM analysis_run_queries
                            WHERE analysis_run_id = %s
                        );
                        """,
                        (analysis_run_id,),
                    )
                    cur.execute(
                        """
                        DELETE FROM analysis_run_queries
                        WHERE analysis_run_id = %s;
                        """,
                        (analysis_run_id,),
                    )
                    cur.execute(
                        """
                        DELETE FROM analysis_run_playbook_versions
                        WHERE analysis_run_id = %s;
                        """,
                        (analysis_run_id,),
                    )
                    cur.execute(
                        "DELETE FROM analysis_runs WHERE analysis_run_id = %s;",
                        (analysis_run_id,),
                    )

    def test_persists_complete_audit_trail_and_supported_violation(self):
        evidence = self._load_evaluation_evidence()
        analysis_input = AnalysisInput(
            "code_diff",
            "logger.info(access_token)\nreturn response",
            "app.py",
        )
        supported = _finding(
            evidence,
            start_line=1,
            end_line=1,
            input_excerpt="logger.info(access_token)",
        )
        unsupported = _finding(
            evidence,
            start_line=2,
            end_line=2,
            input_excerpt="return response",
        )
        fabricated = _finding(
            evidence,
            playbook_chunk_id="fabricated-chunk",
            start_line=2,
            end_line=2,
            input_excerpt="return response",
        )
        rejection = FindingRejection(
            finding_index=2,
            finding=fabricated,
            code="unknown_playbook_chunk",
            reason="The cited playbook chunk was not returned by retrieval.",
        )
        result = AnalysisResult(
            status="review_required",
            findings=(supported,),
            evaluated_findings=(supported, unsupported),
            decisions=(
                EvaluationDecision(0, "supported", "Evidence matches."),
                EvaluationDecision(1, "unsupported", "No violation here."),
            ),
            rejected_findings=(rejection,),
            evidence=(evidence,),
            queries=(
                SearchQuery(
                    evidence.retrieval_query,
                    "Find sensitive logging restrictions.",
                ),
            ),
            iterations=1,
        )
        repository = AnalysisRepository(TEST_DATABASE_URL)
        analysis_run_id = repository.create_run(
            analysis_input,
            model_name="test-model",
            workflow_version="test-v1",
            prompt_version="test-v1",
        )
        self.analysis_run_ids.append(analysis_run_id)

        repository.complete_run(
            analysis_run_id,
            result,
            input_tokens=100,
            output_tokens=25,
        )

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status, input_type, source_path, input_checksum,
                           input_tokens, output_tokens, tool_call_count
                    FROM analysis_runs
                    WHERE analysis_run_id = %s;
                    """,
                    (analysis_run_id,),
                )
                run = cur.fetchone()
                cur.execute(
                    """
                    SELECT
                        (SELECT count(*) FROM analysis_run_queries
                         WHERE analysis_run_id = %s),
                        (SELECT count(*) FROM analysis_retrieval_evidence AS e
                         JOIN analysis_run_queries AS q
                           ON q.analysis_query_id = e.analysis_query_id
                         WHERE q.analysis_run_id = %s),
                        (SELECT count(*) FROM analysis_finding_reviews
                         WHERE analysis_run_id = %s),
                        (SELECT count(*) FROM analysis_finding_rejections
                         WHERE analysis_run_id = %s),
                        (SELECT count(*) FROM violations
                         WHERE analysis_run_id = %s);
                    """,
                    (analysis_run_id,) * 5,
                )
                counts = cur.fetchone()
                cur.execute(
                    """
                    SELECT verdict
                    FROM analysis_finding_reviews
                    WHERE analysis_run_id = %s
                    ORDER BY finding_index;
                    """,
                    (analysis_run_id,),
                )
                verdicts = [row[0] for row in cur.fetchall()]

        self.assertEqual(run[0], "review_required")
        self.assertEqual(run[1], "code_diff")
        self.assertEqual(run[2], "app.py")
        self.assertEqual(len(run[3]), 64)
        self.assertEqual(run[4:], (100, 25, 1))
        self.assertEqual(counts, (1, 1, 2, 1, 1))
        self.assertEqual(verdicts, ["supported", "unsupported"])

    @staticmethod
    def _load_evaluation_evidence():
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        pc.playbook_chunk_id,
                        pc.playbook_version_id,
                        pc.rule_key,
                        pd.filename,
                        pc.section,
                        pc.content
                    FROM playbook_chunks AS pc
                    JOIN playbook_versions AS pv
                      ON pv.playbook_version_id = pc.playbook_version_id
                    JOIN playbook_documents AS pd
                      ON pd.document_id = pv.document_id
                    WHERE pd.category = 'evaluation'
                      AND pd.archived_at IS NULL
                    ORDER BY pc.created_at
                    LIMIT 1;
                    """
                )
                row = cur.fetchone()
        if row is None:
            raise unittest.SkipTest("Ingest evaluation_playbook.md first.")
        return RuleEvidence(
            playbook_chunk_id=str(row[0]),
            playbook_version_id=str(row[1]),
            rule_key=row[2],
            filename=row[3],
            section=row[4],
            content=row[5],
            retrieval_query="sensitive logging rules",
            rank_position=1,
            retrieval_score=0.03,
            semantic_rank=1,
        )


def _finding(evidence, **overrides):
    values = {
        "rule_key": evidence.rule_key,
        "playbook_chunk_id": evidence.playbook_chunk_id,
        "source_path": "app.py",
        "start_line": 1,
        "end_line": 1,
        "input_excerpt": "logger.info(access_token)",
        "explanation": "Evidence-backed integration finding.",
        "severity": "high",
        "confidence": 0.9,
    }
    values.update(overrides)
    return ProposedFinding(**values)


if __name__ == "__main__":
    unittest.main()
