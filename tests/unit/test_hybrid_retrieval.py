import unittest

from virtual_staff_engineer.retrieval.hybrid import (
    filter_lexical_results,
    hybrid_search,
    reciprocal_rank_fusion,
)
from virtual_staff_engineer.retrieval.models import (
    LexicalSearchResult,
    SemanticSearchResult,
)


def common_result_fields(chunk_id, rule_key):
    return {
        "playbook_chunk_id": chunk_id,
        "playbook_version_id": f"version-{chunk_id}",
        "document_id": f"document-{chunk_id}",
        "filename": f"{chunk_id}.md",
        "category": "standards",
        "version": 1,
        "rule_key": rule_key,
        "chunk_index": 0,
        "section": f"Rule {rule_key}",
        "content": f"Content for {rule_key}",
        "embedding_model": "models/test-embedding",
    }


def semantic_result(chunk_id, rule_key, score):
    return SemanticSearchResult(
        **common_result_fields(chunk_id, rule_key),
        similarity_score=score,
    )


def lexical_result(chunk_id, rule_key, score):
    return LexicalSearchResult(
        **common_result_fields(chunk_id, rule_key),
        exact_rule_key_match=False,
        full_text_rank=score,
        trigram_score=score,
        lexical_score=score,
    )


class HybridRetrievalUnitTests(unittest.TestCase):
    def test_overlap_is_promoted_without_comparing_raw_scores(self):
        semantic_results = [
            semantic_result("a", "SEM-01", 0.99),
            semantic_result("b", "BOTH-02", 0.01),
        ]
        lexical_results = [
            lexical_result("b", "BOTH-02", 500.0),
            lexical_result("c", "LEX-03", 400.0),
        ]

        results = reciprocal_rank_fusion(
            semantic_results,
            lexical_results,
            top_k=3,
        )

        self.assertEqual(
            [result.playbook_chunk_id for result in results],
            ["b", "a", "c"],
        )
        self.assertEqual(results[0].semantic_rank, 2)
        self.assertEqual(results[0].lexical_rank, 1)
        self.assertEqual(results[0].similarity_score, 0.01)
        self.assertEqual(results[0].lexical_score, 500.0)

    def test_one_sided_candidates_preserve_missing_rank_provenance(self):
        results = reciprocal_rank_fusion(
            [semantic_result("a", "SEM-01", 0.9)],
            [lexical_result("b", "LEX-02", 2.0)],
            top_k=2,
        )

        result_by_id = {
            result.playbook_chunk_id: result for result in results
        }
        self.assertEqual(result_by_id["a"].semantic_rank, 1)
        self.assertIsNone(result_by_id["a"].lexical_rank)
        self.assertIsNone(result_by_id["a"].lexical_score)
        self.assertIsNone(result_by_id["b"].semantic_rank)
        self.assertEqual(result_by_id["b"].lexical_rank, 1)
        self.assertIsNone(result_by_id["b"].similarity_score)

    def test_weights_change_rank_contributions(self):
        semantic_results = [
            semantic_result("a", "SEM-01", 0.9),
            semantic_result("b", "BOTH-02", 0.8),
        ]
        lexical_results = [lexical_result("b", "BOTH-02", 2.0)]

        results = reciprocal_rank_fusion(
            semantic_results,
            lexical_results,
            top_k=2,
            semantic_weight=0,
            lexical_weight=1,
        )

        self.assertEqual(results[0].playbook_chunk_id, "b")
        self.assertEqual(len(results), 1)

    def test_fusion_rejects_invalid_parameters(self):
        invalid_options = [
            {"rrf_k": 0},
            {"rrf_k": 1.5},
            {"semantic_weight": -1},
            {"lexical_weight": float("nan")},
            {"semantic_weight": 0, "lexical_weight": 0},
        ]

        for options in invalid_options:
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    reciprocal_rank_fusion([], [], **options)

    def test_hybrid_search_rejects_candidate_pool_smaller_than_output(self):
        with self.assertRaisesRegex(ValueError, "candidate_k"):
            hybrid_search("credentials", top_k=5, candidate_k=4)

    def test_hybrid_search_rejects_fuzzy_threshold_before_retrieval(self):
        with self.assertRaisesRegex(ValueError, "fuzzy_threshold"):
            hybrid_search("credentials", fuzzy_threshold=1.1)

    def test_confident_policy_rejects_weak_fuzzy_noise(self):
        weak = LexicalSearchResult(
            **common_result_fields("weak", "AUTH-04"),
            exact_rule_key_match=False,
            full_text_rank=0,
            trigram_score=0.21,
            lexical_score=0.0525,
        )
        strong = LexicalSearchResult(
            **common_result_fields("strong", "SEC-01"),
            exact_rule_key_match=False,
            full_text_rank=0,
            trigram_score=0.35,
            lexical_score=0.0875,
        )

        filtered = filter_lexical_results(
            "misspelled logging requirement",
            [weak, strong],
            policy="confident",
            strong_trigram_threshold=0.3,
        )

        self.assertEqual([result.rule_key for result in filtered], ["SEC-01"])

    def test_explicit_rule_key_is_always_confident(self):
        weak = lexical_result("weak", "SEC-01", 0.01)

        filtered = filter_lexical_results(
            "Review SEC-01 please",
            [weak],
            policy="confident",
        )

        self.assertEqual(filtered, [weak])


if __name__ == "__main__":
    unittest.main()
