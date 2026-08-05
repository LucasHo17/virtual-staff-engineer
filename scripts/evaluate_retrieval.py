import argparse

from virtual_staff_engineer.evaluation.corpus import verify_corpus
from virtual_staff_engineer.evaluation.dataset import (
    VALID_QUERY_TYPES,
    load_dataset,
    select_cases,
)
from virtual_staff_engineer.evaluation.report import (
    validate_report_destination,
    write_reports,
)
from virtual_staff_engineer.evaluation.runner import (
    BenchmarkConfig,
    run_benchmark,
)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Benchmark semantic, lexical, and hybrid retrieval."
    )
    parser.add_argument(
        "--dataset",
        default="evaluation_data/retrieval_cases.json",
        help="Frozen labeled dataset (default: evaluation_data/retrieval_cases.json).",
    )
    parser.add_argument(
        "--output-dir",
        default="evaluation_results/phase1_v1",
        help="Report directory (default: evaluation_results/phase1_v1).",
    )
    parser.add_argument(
        "--cutoffs",
        type=int,
        nargs="+",
        default=[1, 3, 5],
        help="Evaluation cutoffs (default: 1 3 5).",
    )
    parser.add_argument("--candidate-k", type=int, default=20)
    parser.add_argument("--fuzzy-threshold", type=float, default=0.2)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--semantic-weight", type=float, default=1.0)
    parser.add_argument("--lexical-weight", type=float, default=1.0)
    parser.add_argument(
        "--min-similarity",
        type=float,
        help="Experimental semantic abstention threshold (-1 to 1).",
    )
    parser.add_argument(
        "--lexical-policy",
        choices=["all", "confident", "explicit_only"],
        default="confident",
        help="Lexical evidence allowed to influence RRF (default: confident).",
    )
    parser.add_argument(
        "--strong-trigram-threshold",
        type=float,
        default=0.3,
        help="Strong fuzzy evidence threshold used by confident fusion.",
    )
    parser.add_argument(
        "--query-type",
        action="append",
        choices=sorted(VALID_QUERY_TYPES),
        help="Run only this type; repeat to select multiple types.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Run only the first N selected cases (useful for a smoke test).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the dataset and PostgreSQL corpus without embedding queries.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing results.json and report.md in the output directory.",
    )
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    dataset = load_dataset(arguments.dataset)
    cases = select_cases(
        dataset,
        query_types=arguments.query_type,
        limit=arguments.limit,
    )
    config = BenchmarkConfig(
        cutoffs=tuple(arguments.cutoffs),
        candidate_k=arguments.candidate_k,
        fuzzy_threshold=arguments.fuzzy_threshold,
        rrf_k=arguments.rrf_k,
        semantic_weight=arguments.semantic_weight,
        lexical_weight=arguments.lexical_weight,
        min_similarity=arguments.min_similarity,
        lexical_policy=arguments.lexical_policy,
        strong_trigram_threshold=arguments.strong_trigram_threshold,
    ).validated()

    if arguments.dry_run:
        corpus = verify_corpus(dataset)
        print("✅ Evaluation dataset and PostgreSQL corpus match.")
        print(f"   Dataset: {dataset.dataset_id} ({len(dataset.cases)} total cases)")
        print(f"   Selected: {len(cases)} cases")
        print(
            f"   Corpus: {corpus['filename']} version {corpus['version']} "
            f"({corpus['chunk_count']} chunks)"
        )
        print(f"   Planned embedding requests: {len(cases)}")
        print("   No embeddings were requested and no report was written.")
        return

    # This guard intentionally runs before constructing a client or embedding
    # any query, so a repeated command cannot waste external API calls.
    try:
        validate_report_destination(
            arguments.output_dir,
            overwrite=arguments.overwrite,
        )
    except FileExistsError as error:
        raise SystemExit(
            f"❌ {error}\n"
            "Choose a new --output-dir, or pass --overwrite intentionally. "
            "No embedding requests were made."
        ) from error
    print(
        f"🔎 Running {len(cases)} cases across semantic, lexical, and hybrid "
        f"retrieval ({len(cases)} embedding requests)..."
    )
    result = run_benchmark(dataset, cases=cases, config=config)
    paths = write_reports(
        result,
        arguments.output_dir,
        overwrite=arguments.overwrite,
    )
    print("✅ Retrieval evaluation complete.")
    print(f"   JSON: {paths['json']}")
    print(f"   Markdown: {paths['markdown']}")


if __name__ == "__main__":
    main()
