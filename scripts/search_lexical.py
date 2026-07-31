import argparse
import json
from dataclasses import asdict

from virtual_staff_engineer.retrieval import lexical_search


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Search active engineering playbooks by lexical relevance."
    )
    parser.add_argument("query", help="Words, phrases, or rule identifiers.")
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Maximum number of chunks to return (default: 5).",
    )
    parser.add_argument(
        "--category",
        help="Optional exact playbook category filter.",
    )
    parser.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=0.2,
        help="Minimum trigram similarity from 0 to 1 (default: 0.2).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_arguments()
    results = lexical_search(
        arguments.query,
        top_k=arguments.top_k,
        category=arguments.category,
        fuzzy_threshold=arguments.fuzzy_threshold,
    )
    print(
        json.dumps(
            [asdict(result) for result in results],
            indent=2,
            ensure_ascii=False,
        )
    )
