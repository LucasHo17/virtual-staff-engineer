import argparse
import json
from dataclasses import asdict

from virtual_staff_engineer.retrieval import hybrid_search


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Search playbooks using semantic and lexical rank fusion."
    )
    parser.add_argument("query", help="Natural-language rule query.")
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Maximum number of fused chunks to return (default: 5).",
    )
    parser.add_argument(
        "--candidate-k",
        type=int,
        default=20,
        help="Candidates requested from each retriever (default: 20).",
    )
    parser.add_argument(
        "--category",
        help="Optional exact playbook category filter.",
    )
    parser.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=0.2,
        help="Minimum lexical trigram similarity (default: 0.2).",
    )
    parser.add_argument(
        "--rrf-k",
        type=int,
        default=60,
        help="RRF rank-damping constant (default: 60).",
    )
    parser.add_argument(
        "--semantic-weight",
        type=float,
        default=1.0,
        help="Semantic rank contribution weight (default: 1.0).",
    )
    parser.add_argument(
        "--lexical-weight",
        type=float,
        default=1.0,
        help="Lexical rank contribution weight (default: 1.0).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_arguments()
    results = hybrid_search(
        arguments.query,
        top_k=arguments.top_k,
        candidate_k=arguments.candidate_k,
        category=arguments.category,
        fuzzy_threshold=arguments.fuzzy_threshold,
        rrf_k=arguments.rrf_k,
        semantic_weight=arguments.semantic_weight,
        lexical_weight=arguments.lexical_weight,
    )
    print(
        json.dumps(
            [asdict(result) for result in results],
            indent=2,
            ensure_ascii=False,
        )
    )
