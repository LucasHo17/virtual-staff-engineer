import argparse
import os

from virtual_staff_engineer.evaluation.analysis_dataset import (
    ANALYSIS_CASE_TYPES,
    load_analysis_dataset,
    select_analysis_cases,
)
from virtual_staff_engineer.evaluation.analysis_report import (
    write_analysis_reports,
)
from virtual_staff_engineer.evaluation.analysis_runner import (
    AnalysisBenchmarkConfig,
    run_analysis_benchmark,
)
from virtual_staff_engineer.evaluation.corpus import verify_corpus
from virtual_staff_engineer.evaluation.report import (
    validate_report_destination,
)


MODEL_PRICING = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.6-flash": (1.50, 7.50),
}


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Benchmark the evidence-grounded Phase 2 agent workflow."
    )
    parser.add_argument(
        "--dataset",
        default="evaluation_data/analysis_workflow_cases.json",
        help="Frozen Phase 2 labeled dataset.",
    )
    parser.add_argument(
        "--output-dir",
        default="evaluation_results/phase2_v1",
        help="Report directory (default: evaluation_results/phase2_v1).",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("GEMINI_REASONING_MODEL"),
        help="Explicit Gemini reasoning model (or GEMINI_REASONING_MODEL).",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--candidate-k", type=int, default=20)
    parser.add_argument("--max-iterations", type=int, default=2)
    parser.add_argument(
        "--case-delay-seconds",
        type=float,
        default=0.0,
        help=(
            "Pause between cases to respect model request quotas "
            "(default: 0)."
        ),
    )
    parser.add_argument(
        "--thinking-budget",
        type=int,
        default=None,
        help=(
            "Optional legacy numeric thinking budget per reasoning call; "
            "omit to use the model default."
        ),
    )
    parser.add_argument(
        "--input-cost-per-million",
        type=float,
        default=None,
        help="Reasoning-model input price used only for cost estimation.",
    )
    parser.add_argument(
        "--output-cost-per-million",
        type=float,
        default=None,
        help="Reasoning-model output/thinking price used for cost estimation.",
    )
    parser.add_argument(
        "--case-type",
        action="append",
        choices=sorted(ANALYSIS_CASE_TYPES),
    )
    parser.add_argument(
        "--case-id",
        action="append",
        help="Run one case id; repeat to select multiple cases.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate labels, selection, and PostgreSQL without API calls.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing results.json and report.md intentionally.",
    )
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    dataset = load_analysis_dataset(arguments.dataset)
    cases = select_analysis_cases(
        dataset,
        case_types=arguments.case_type,
        case_ids=arguments.case_id,
        limit=arguments.limit,
    )
    if not arguments.model:
        raise SystemExit(
            "❌ Pass --model or configure GEMINI_REASONING_MODEL."
        )
    default_input_price, default_output_price = MODEL_PRICING.get(
        arguments.model, (0.0, 0.0)
    )
    config = AnalysisBenchmarkConfig(
        model=arguments.model,
        top_k=arguments.top_k,
        candidate_k=arguments.candidate_k,
        max_iterations=arguments.max_iterations,
        case_delay_seconds=arguments.case_delay_seconds,
        thinking_budget=arguments.thinking_budget,
        input_cost_per_million=(
            arguments.input_cost_per_million
            if arguments.input_cost_per_million is not None
            else default_input_price
        ),
        output_cost_per_million=(
            arguments.output_cost_per_million
            if arguments.output_cost_per_million is not None
            else default_output_price
        ),
    ).validated()

    corpus = verify_corpus(dataset)
    if arguments.dry_run:
        print("✅ Phase 2 dataset and PostgreSQL corpus match.")
        print(f"   Dataset: {dataset.dataset_id} ({len(dataset.cases)} cases)")
        print(f"   Selected: {len(cases)} cases")
        print(
            f"   Corpus: {corpus['filename']} version {corpus['version']} "
            f"({corpus['chunk_count']} chunks)"
        )
        print(f"   Reasoning model: {config.model}")
        print(f"   Maximum model calls: {len(cases) * 5}")
        print(f"   Maximum embedding requests: {len(cases) * 5}")
        print("   No API requests were made and no report was written.")
        return

    try:
        validate_report_destination(
            arguments.output_dir,
            overwrite=arguments.overwrite,
        )
    except FileExistsError as exc:
        raise SystemExit(
            f"❌ {exc}\nChoose a new --output-dir or pass --overwrite. "
            "No model or embedding requests were made."
        ) from exc

    print(
        f"🧠 Running {len(cases)} Phase 2 cases with {config.model}...",
        flush=True,
    )
    result = run_analysis_benchmark(
        dataset,
        cases=cases,
        config=config,
        corpus_verifier=lambda dataset, database_url=None: corpus,
        progress_callback=lambda case, completed, total: print(
            f"   [{completed}/{total}] {case['case_id']}: "
            f"{case['actual_status']} ({case['latency_ms']:.0f} ms)",
            flush=True,
        ),
    )
    paths = write_analysis_reports(
        result,
        arguments.output_dir,
        overwrite=arguments.overwrite,
    )
    print("✅ Phase 2 agent evaluation complete.")
    print(f"   JSON: {paths['json']}")
    print(f"   Markdown: {paths['markdown']}")


if __name__ == "__main__":
    main()
