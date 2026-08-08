import json
from dataclasses import dataclass
from pathlib import Path

from virtual_staff_engineer.evaluation.dataset import (
    DatasetValidationError,
    PlaybookReference,
)


ANALYSIS_CASE_TYPES = frozenset(
    {"violating", "clean", "ambiguous", "irrelevant"}
)
ANALYSIS_INPUT_TYPES = frozenset({"code_diff", "design_document"})
ANALYSIS_EXPECTED_STATUSES = frozenset(
    {"completed_clean", "review_required", "inconclusive"}
)


@dataclass(frozen=True)
class AnalysisEvaluationCase:
    case_id: str
    case_type: str
    input_type: str
    source_path: str
    content: str
    candidate_rule_keys: tuple
    expected_rule_keys: tuple
    expected_status: str
    notes: str


@dataclass(frozen=True)
class AnalysisEvaluationDataset:
    dataset_id: str
    status: str
    playbook: PlaybookReference
    cases: tuple
    source_path: str
    review: dict


def load_analysis_dataset(file_path, require_frozen=True):
    """Load and validate labeled Phase 2 analysis cases."""
    path = Path(file_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetValidationError(
            f"Could not load analysis dataset {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise DatasetValidationError("Dataset root must be a JSON object.")

    dataset_id = _text(payload, "dataset_id", "dataset")
    status = _text(payload, "status", "dataset")
    if status not in {"draft", "frozen"}:
        raise DatasetValidationError(
            "dataset.status must be either 'draft' or 'frozen'."
        )
    if require_frozen and status != "frozen":
        raise DatasetValidationError(
            f"Dataset status must be 'frozen', received {status!r}."
        )

    playbook = payload.get("playbook")
    if not isinstance(playbook, dict):
        raise DatasetValidationError("Dataset playbook must be an object.")
    playbook_reference = PlaybookReference(
        filename=_text(playbook, "filename", "playbook"),
        category=_text(playbook, "category", "playbook"),
        version=_positive_integer(playbook, "version", "playbook"),
        rule_count=_positive_integer(playbook, "rule_count", "playbook"),
    )

    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise DatasetValidationError("Dataset cases must be a non-empty array.")

    cases = []
    seen_ids = set()
    for index, raw_case in enumerate(raw_cases):
        location = f"cases[{index}]"
        if not isinstance(raw_case, dict):
            raise DatasetValidationError(f"{location} must be an object.")
        case = _load_case(raw_case, location)
        if case.case_id in seen_ids:
            raise DatasetValidationError(
                f"Duplicate case id: {case.case_id}."
            )
        seen_ids.add(case.case_id)
        _validate_case_labels(case, location)
        cases.append(case)

    review = payload.get("review") or {}
    if not isinstance(review, dict):
        raise DatasetValidationError("Dataset review must be an object.")
    if status == "frozen" and review.get("reviewed_case_count") != len(cases):
        raise DatasetValidationError(
            "Frozen dataset review count must equal the number of cases."
        )

    return AnalysisEvaluationDataset(
        dataset_id=dataset_id,
        status=status,
        playbook=playbook_reference,
        cases=tuple(cases),
        source_path=str(path),
        review=review,
    )


def select_analysis_cases(dataset, case_types=None, case_ids=None, limit=None):
    """Select a deterministic Phase 2 subset without changing the dataset."""
    selected = list(dataset.cases)
    if case_types:
        invalid_types = set(case_types) - ANALYSIS_CASE_TYPES
        if invalid_types:
            raise DatasetValidationError(
                f"Unknown analysis case types: {sorted(invalid_types)}."
            )
        selected = [
            case for case in selected if case.case_type in set(case_types)
        ]
    if case_ids:
        requested_ids = set(case_ids)
        known_ids = {case.case_id for case in dataset.cases}
        unknown_ids = requested_ids - known_ids
        if unknown_ids:
            raise DatasetValidationError(
                f"Unknown analysis case ids: {sorted(unknown_ids)}."
            )
        selected = [case for case in selected if case.case_id in requested_ids]
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise DatasetValidationError("limit must be a positive integer.")
        selected = selected[:limit]
    if not selected:
        raise DatasetValidationError("Case selection produced no cases.")
    return tuple(selected)


def _load_case(payload, location):
    case_type = _text(payload, "case_type", location)
    if case_type not in ANALYSIS_CASE_TYPES:
        raise DatasetValidationError(
            f"{location}.case_type must be one of "
            f"{sorted(ANALYSIS_CASE_TYPES)}."
        )
    input_type = _text(payload, "input_type", location)
    if input_type not in ANALYSIS_INPUT_TYPES:
        raise DatasetValidationError(
            f"{location}.input_type must be one of "
            f"{sorted(ANALYSIS_INPUT_TYPES)}."
        )
    expected_status = _text(payload, "expected_status", location)
    if expected_status not in ANALYSIS_EXPECTED_STATUSES:
        raise DatasetValidationError(
            f"{location}.expected_status must be one of "
            f"{sorted(ANALYSIS_EXPECTED_STATUSES)}."
        )
    return AnalysisEvaluationCase(
        case_id=_text(payload, "id", location),
        case_type=case_type,
        input_type=input_type,
        source_path=_text(payload, "source_path", location),
        content=_text(payload, "content", location, strip=False),
        candidate_rule_keys=_rule_keys(
            payload, "candidate_rule_keys", location
        ),
        expected_rule_keys=_rule_keys(
            payload, "expected_rule_keys", location
        ),
        expected_status=expected_status,
        notes=_text(payload, "notes", location),
    )


def _validate_case_labels(case, location):
    if not case.candidate_rule_keys:
        raise DatasetValidationError(
            f"{location}.candidate_rule_keys must not be empty."
        )
    expected_status_by_type = {
        "violating": "review_required",
        "clean": "completed_clean",
        "ambiguous": "inconclusive",
        "irrelevant": "completed_clean",
    }
    required_status = expected_status_by_type[case.case_type]
    if case.expected_status != required_status:
        raise DatasetValidationError(
            f"{location} {case.case_type!r} case must expect "
            f"{required_status!r}."
        )
    if case.case_type == "violating":
        if not case.expected_rule_keys:
            raise DatasetValidationError(
                f"{location} violating case needs expected rule keys."
            )
        if not set(case.expected_rule_keys).issubset(
            case.candidate_rule_keys
        ):
            raise DatasetValidationError(
                f"{location} expected rules must be candidate rules."
            )
    elif case.expected_rule_keys:
        raise DatasetValidationError(
            f"{location} {case.case_type!r} case cannot expect violations."
        )


def _text(payload, key, location, strip=True):
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DatasetValidationError(
            f"{location}.{key} must be a non-empty string."
        )
    return value.strip() if strip else value


def _rule_keys(payload, key, location):
    values = payload.get(key)
    if not isinstance(values, list):
        raise DatasetValidationError(f"{location}.{key} must be an array.")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise DatasetValidationError(
            f"{location}.{key} must contain non-empty strings."
        )
    normalized = tuple(value.strip().upper() for value in values)
    if len(normalized) != len(set(normalized)):
        raise DatasetValidationError(f"{location}.{key} contains duplicates.")
    return normalized


def _positive_integer(payload, key, location):
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DatasetValidationError(
            f"{location}.{key} must be a positive integer."
        )
    return value
