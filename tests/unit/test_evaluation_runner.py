import json
import tempfile
import unittest
from pathlib import Path

from virtual_staff_engineer.evaluation.dataset import (
    EvaluationCase,
    EvaluationDataset,
    PlaybookReference,
)
from virtual_staff_engineer.evaluation.report import (
    validate_report_destination,
    write_reports,
)
from virtual_staff_engineer.evaluation.runner import (
    BenchmarkConfig,
    run_benchmark,
)
from virtual_staff_engineer.retrieval.hybrid import reciprocal_rank_fusion
from virtual_staff_engineer.retrieval.models import (
    LexicalSearchResult,
    SemanticSearchResult,
)


def common_fields(chunk_id, rule_key):
    return {
        "playbook_chunk_id": chunk_id,
        "playbook_version_id": "version-1",
        "document_id": "document-1",
        "filename": "evaluation.md",
        "category": "evaluation",
        "version": 1,
        "rule_key": rule_key,
        "chunk_index": 0,
        "section": f"Rule {rule_key}",
        "content": f"Content for {rule_key}",
        "embedding_model": "models/test",
    }


def semantic_result(chunk_id, rule_key):
    return SemanticSearchResult(
        **common_fields(chunk_id, rule_key),
        similarity_score=0.9,
    )


def lexical_result(chunk_id, rule_key):
    return LexicalSearchResult(
        **common_fields(chunk_id, rule_key),
        exact_rule_key_match=True,
        full_text_rank=1.0,
        trigram_score=1.0,
        lexical_score=3.0,
    )


class EvaluationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.dataset = EvaluationDataset(
            dataset_id="test-v1",
            status="frozen",
            playbook=PlaybookReference(
                filename="evaluation.md",
                category="evaluation",
                version=1,
                rule_count=2,
            ),
            cases=(
                EvaluationCase(
                    case_id="positive-001",
                    query_type="semantic",
                    query="protect secrets",
                    expected_rule_keys=("SEC-01",),
                    notes="Positive.",
                ),
                EvaluationCase(
                    case_id="negative-001",
                    query_type="negative",
                    query="lunch menu",
                    expected_rule_keys=(),
                    notes="Negative.",
                ),
            ),
            source_path="cases.json",
            review={"reviewed_case_count": 2},
        )

    def test_runner_reuses_one_embedding_per_case(self):
        embedded_queries = []
        embedding_options = []
        semantic_options = []

        def fake_corpus(dataset, database_url=None):
            return {
                "filename": "evaluation.md",
                "version": 1,
                "chunk_count": 2,
                "embedding_model": "models/test",
                "embedding_dimension": 3,
            }

        def fake_embedder(query, **kwargs):
            embedded_queries.append(query)
            embedding_options.append(kwargs)
            return [0.1, 0.2, 0.3]

        def fake_semantic(query_embedding, **kwargs):
            semantic_options.append(kwargs)
            if len(embedded_queries) == 1:
                return [semantic_result("chunk-1", "SEC-01")]
            return []

        def fake_lexical(query, **kwargs):
            if query == "protect secrets":
                return [lexical_result("chunk-1", "SEC-01")]
            return []

        result = run_benchmark(
            self.dataset,
            config=BenchmarkConfig(
                cutoffs=(1,),
                candidate_k=2,
                embedding_model="models/test",
                embedding_dimension=3,
                min_similarity=0.59,
            ),
            corpus_verifier=fake_corpus,
            query_embedder=fake_embedder,
            semantic_retriever=fake_semantic,
            lexical_retriever=fake_lexical,
            fusion=reciprocal_rank_fusion,
        )

        self.assertEqual(embedded_queries, ["protect secrets", "lunch menu"])
        self.assertNotIn("min_similarity", embedding_options[0])
        self.assertEqual(semantic_options[0]["min_similarity"], 0.59)
        self.assertEqual(result["usage"]["embedding_requests"], 2)
        self.assertEqual(result["run_status"], "complete")
        self.assertEqual(
            result["summary"]["overall"]["hybrid"]["quality"]
            ["recall_at_k"]["1"],
            1.0,
        )
        self.assertNotIn(
            "content",
            result["cases"][0]["methods"]["semantic"]["candidates"][0],
        )

    def test_report_writer_refuses_accidental_overwrite(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        result = {
            "generated_at": "2026-08-04T00:00:00+00:00",
            "run_status": "complete",
            "dataset": {
                "dataset_id": "test-v1",
                "selected_case_count": 0,
                "total_case_count": 0,
            },
            "corpus": {
                "filename": "evaluation.md",
                "version": 1,
                "chunk_count": 0,
            },
            "config": {"cutoffs": [1], "candidate_k": 2},
            "usage": {"embedding_requests": 0},
            "summary": {
                "overall": {},
                "by_query_type": {},
            },
            "cases": [],
        }

        paths = write_reports(result, directory.name)

        self.assertTrue(Path(paths["json"]).exists())
        self.assertEqual(
            json.loads(Path(paths["json"]).read_text())["run_status"],
            "complete",
        )
        with self.assertRaises(FileExistsError):
            write_reports(result, directory.name)

    def test_report_destination_can_be_checked_before_benchmark(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        output = Path(directory.name)
        (output / "results.json").write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(FileExistsError, "results.json"):
            validate_report_destination(output)

        paths = validate_report_destination(output, overwrite=True)
        self.assertEqual(paths["json"], output / "results.json")


if __name__ == "__main__":
    unittest.main()
