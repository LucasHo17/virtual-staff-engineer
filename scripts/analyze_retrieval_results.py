import argparse

from virtual_staff_engineer.evaluation.optimization import (
    analyze_optimization,
    load_benchmark_results,
    write_optimization_reports,
)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Replay threshold and fusion policies over saved results."
    )
    parser.add_argument(
        "--results",
        default="evaluation_results/phase1_v1/results.json",
        help="Existing benchmark results JSON.",
    )
    parser.add_argument(
        "--output-dir",
        default="evaluation_results/phase1_v1",
        help="Directory for optimization.json and optimization.md.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing optimization reports.",
    )
    parser.add_argument(
        "--locked-threshold",
        type=float,
        help="Evaluate a threshold selected before seeing this holdout.",
    )
    parser.add_argument(
        "--locked-lexical-policy",
        choices=["all", "confident", "explicit_only"],
        default="confident",
    )
    parser.add_argument(
        "--locked-lexical-weight",
        type=float,
        default=1.0,
    )
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    results = load_benchmark_results(arguments.results)
    locked_policy = None
    if arguments.locked_threshold is not None:
        locked_policy = {
            "semantic_threshold": arguments.locked_threshold,
            "lexical_policy": arguments.locked_lexical_policy,
            "lexical_weight": arguments.locked_lexical_weight,
        }
    analysis = analyze_optimization(results, locked_policy=locked_policy)
    paths = write_optimization_reports(
        analysis,
        arguments.output_dir,
        overwrite=arguments.overwrite,
    )
    print("✅ Offline optimization analysis complete.")
    print("   No database or embedding API calls were made.")
    print(f"   JSON: {paths['json']}")
    print(f"   Markdown: {paths['markdown']}")


if __name__ == "__main__":
    main()
