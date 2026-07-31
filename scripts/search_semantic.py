import argparse
import json
from dataclasses import asdict

from virtual_staff_engineer.retrieval import semantic_search


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Search active engineering playbooks by semantic similarity."
    )
    parser.add_argument("query", help="Natural-language rule query.")
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
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_arguments()
    results = semantic_search(
        arguments.query,
        top_k=arguments.top_k,
        category=arguments.category,
    )
    print(
        json.dumps(
            [asdict(result) for result in results],
            indent=2,
            ensure_ascii=False,
        )
    )
