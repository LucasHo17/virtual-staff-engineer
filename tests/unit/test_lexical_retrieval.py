import unittest

from virtual_staff_engineer.retrieval.lexical import lexical_search


class LexicalRetrievalUnitTests(unittest.TestCase):
    def test_search_rejects_empty_query(self):
        with self.assertRaisesRegex(ValueError, "non-empty string"):
            lexical_search("   ")

    def test_search_rejects_invalid_top_k(self):
        for invalid_top_k in (0, 101, 1.5, True):
            with self.subTest(top_k=invalid_top_k):
                with self.assertRaises(ValueError):
                    lexical_search("SEC-01", top_k=invalid_top_k)

    def test_search_rejects_invalid_category(self):
        with self.assertRaisesRegex(ValueError, "category"):
            lexical_search("SEC-01", category="   ")

    def test_search_rejects_invalid_fuzzy_threshold(self):
        for invalid_threshold in (-0.1, 1.1, "0.2", True):
            with self.subTest(fuzzy_threshold=invalid_threshold):
                with self.assertRaises(ValueError):
                    lexical_search(
                        "SEC-01",
                        fuzzy_threshold=invalid_threshold,
                    )


if __name__ == "__main__":
    unittest.main()
