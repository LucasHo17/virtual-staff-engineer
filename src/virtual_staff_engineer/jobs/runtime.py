from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeExecution:
    stage: str
    execution: object


class WorkerRuntime:
    """Poll each independently leased workflow stage without HTTP coupling."""

    def __init__(self, workers):
        normalized = tuple(workers)
        if not normalized:
            raise ValueError("workers must contain at least one stage worker.")
        if not all(
            isinstance(name, str) and name.strip() and hasattr(worker, "run_once")
            for name, worker in normalized
        ):
            raise ValueError("workers must contain named run_once workers.")
        self.workers = normalized

    def run_cycle(self):
        results = []
        for stage, worker in self.workers:
            execution = worker.run_once()
            if execution.claimed:
                results.append(RuntimeExecution(stage, execution))
        return tuple(results)
