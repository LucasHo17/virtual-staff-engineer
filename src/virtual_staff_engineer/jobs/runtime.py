from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeExecution:
    stage: str
    execution: object


class WorkerRuntime:
    """Poll each independently leased workflow stage without HTTP coupling."""

    def __init__(self, workers, max_parallelism=1):
        normalized = tuple(workers)
        if not normalized:
            raise ValueError("workers must contain at least one stage worker.")
        if not all(
            isinstance(name, str) and name.strip() and hasattr(worker, "run_once")
            for name, worker in normalized
        ):
            raise ValueError("workers must contain named run_once workers.")
        if (
            isinstance(max_parallelism, bool)
            or not isinstance(max_parallelism, int)
            or max_parallelism < 1
        ):
            raise ValueError("max_parallelism must be a positive integer.")
        self.workers = normalized
        self.max_parallelism = max_parallelism

    def run_cycle(self):
        if self.max_parallelism == 1:
            executions = tuple(
                worker.run_once() for _, worker in self.workers
            )
        else:
            with ThreadPoolExecutor(
                max_workers=min(self.max_parallelism, len(self.workers)),
                thread_name_prefix="vse-worker",
            ) as executor:
                executions = tuple(
                    executor.map(
                        lambda named_worker: named_worker[1].run_once(),
                        self.workers,
                    )
                )
        results = []
        for (stage, _), execution in zip(self.workers, executions):
            if execution.claimed:
                results.append(RuntimeExecution(stage, execution))
        return tuple(results)
