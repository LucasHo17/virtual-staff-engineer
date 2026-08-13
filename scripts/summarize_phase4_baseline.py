import argparse

from virtual_staff_engineer.evaluation.phase4_baseline import (
    aggregate_phase4_baseline,
    load_workload_runs,
    write_phase4_baseline,
)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Aggregate Phase 4 workload runs into a baseline report."
    )
    parser.add_argument(
        "inputs", nargs="+", help="One or more successful workload JSON files."
    )
    parser.add_argument(
        "--output-dir", default="evaluation_results/phase4_baseline/v1"
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    runs = load_workload_runs(arguments.inputs)
    result = aggregate_phase4_baseline(runs)
    try:
        paths = write_phase4_baseline(
            result, arguments.output_dir, overwrite=arguments.overwrite
        )
    except FileExistsError as exc:
        raise SystemExit(f"❌ {exc}") from exc
    print(
        f"✅ Baseline aggregated: {result['sample']['job_count']} jobs across "
        f"{result['sample']['run_count']} run(s)."
    )
    print(f"   JSON: {paths['json']}")
    print(f"   Markdown: {paths['markdown']}")
    if result["sample"]["small_sample_warning"]:
        print("   ⚠️  Fewer than 20 jobs; p95 is directional only.")


if __name__ == "__main__":
    main()
