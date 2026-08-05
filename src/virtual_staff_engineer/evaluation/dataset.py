import json
from dataclasses import dataclass
from pathlib import Path


VALID_QUERY_TYPES = {
    "exact",
    "semantic",
    "fuzzy",
    "tier",
    "multi_rule",
    "negative",
}


class DatasetValidationError(ValueError):
    """Raised when an evaluation dataset cannot be trusted."""


@dataclass(frozen=True)
class PlaybookReference:
    filename: str
    category: str
    version: int
    rule_count: int


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    query_type: str
    query: str
    expected_rule_keys: tuple
    notes: str

    @property
    def is_negative(self):
        return not self.expected_rule_keys


@dataclass(frozen=True)
class EvaluationDataset:
    dataset_id: str
    status: str
    playbook: PlaybookReference
    cases: tuple
    source_path: str
    review: dict


def load_dataset(file_path, require_frozen=True):
    """Load and strictly validate one retrieval evaluation dataset."""
    path = Path(file_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DatasetValidationError(
            f"Could not load evaluation dataset {path}: {error}"
        ) from error

    if not isinstance(payload, dict):
        raise DatasetValidationError("Dataset root must be a JSON object.")

    dataset_id = _require_nonempty_string(payload, "dataset_id", "dataset")
    status = _require_nonempty_string(payload, "status", "dataset")
    if require_frozen and status != "frozen":
        raise DatasetValidationError(
            f"Dataset status must be 'frozen', received {status!r}."
        )

    playbook_payload = payload.get("playbook")
    if not isinstance(playbook_payload, dict):
        raise DatasetValidationError("Dataset playbook must be an object.")

    playbook = PlaybookReference(
        filename=_require_nonempty_string(
            playbook_payload,
            "filename",
            "playbook",
        ),
        category=_require_nonempty_string(
            playbook_payload,
            "category",
            "playbook",
        ),
        version=_require_positive_integer(
            playbook_payload,
            "version",
            "playbook",
        ),
        rule_count=_require_positive_integer(
            playbook_payload,
            "rule_count",
            "playbook",
        ),
    )

    cases_payload = payload.get("cases")
    if not isinstance(cases_payload, list) or not cases_payload:
        raise DatasetValidationError("Dataset cases must be a non-empty array.")

    cases = []
    seen_ids = set()
    for index, case_payload in enumerate(cases_payload):
        location = f"cases[{index}]"
        if not isinstance(case_payload, dict):
            raise DatasetValidationError(f"{location} must be an object.")

        case_id = _require_nonempty_string(case_payload, "id", location)
        if case_id in seen_ids:
            raise DatasetValidationError(f"Duplicate case id: {case_id}.")
        seen_ids.add(case_id)

        query_type = _require_nonempty_string(
            case_payload,
            "query_type",
            location,
        )
        if query_type not in VALID_QUERY_TYPES:
            raise DatasetValidationError(
                f"{location}.query_type must be one of "
                f"{sorted(VALID_QUERY_TYPES)}, received {query_type!r}."
            )

        query = _require_nonempty_string(case_payload, "query", location)
        notes = _require_nonempty_string(case_payload, "notes", location)
        expected_rule_keys = case_payload.get("expected_rule_keys")
        if not isinstance(expected_rule_keys, list):
            raise DatasetValidationError(
                f"{location}.expected_rule_keys must be an array."
            )
        if any(
            not isinstance(rule_key, str) or not rule_key.strip()
            for rule_key in expected_rule_keys
        ):
            raise DatasetValidationError(
                f"{location}.expected_rule_keys must contain non-empty strings."
            )

        normalized_rule_keys = tuple(
            rule_key.strip().upper() for rule_key in expected_rule_keys
        )
        if len(normalized_rule_keys) != len(set(normalized_rule_keys)):
            raise DatasetValidationError(
                f"{location}.expected_rule_keys contains duplicates."
            )
        if query_type == "negative" and normalized_rule_keys:
            raise DatasetValidationError(
                f"{location} is negative but has expected rule keys."
            )
        if query_type != "negative" and not normalized_rule_keys:
            raise DatasetValidationError(
                f"{location} is positive but has no expected rule keys."
            )

        cases.append(
            EvaluationCase(
                case_id=case_id,
                query_type=query_type,
                query=query,
                expected_rule_keys=normalized_rule_keys,
                notes=notes,
            )
        )

    review = payload.get("review") or {}
    if not isinstance(review, dict):
        raise DatasetValidationError("Dataset review must be an object.")
    reviewed_count = review.get("reviewed_case_count")
    if status == "frozen" and reviewed_count != len(cases):
        raise DatasetValidationError(
            "Frozen dataset review count must equal the number of cases."
        )

    return EvaluationDataset(
        dataset_id=dataset_id,
        status=status,
        playbook=playbook,
        cases=tuple(cases),
        source_path=str(path),
        review=review,
    )


def select_cases(dataset, query_types=None, limit=None):
    """Select a deterministic subset without changing the frozen dataset."""
    if query_types:
        invalid_types = set(query_types) - VALID_QUERY_TYPES
        if invalid_types:
            raise DatasetValidationError(
                f"Unknown query types: {sorted(invalid_types)}."
            )
        selected = [
            case for case in dataset.cases if case.query_type in query_types
        ]
    else:
        selected = list(dataset.cases)

    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise DatasetValidationError("limit must be a positive integer.")
        selected = selected[:limit]

    if not selected:
        raise DatasetValidationError("Case selection produced no cases.")
    return tuple(selected)


def _require_nonempty_string(payload, key, location):
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DatasetValidationError(
            f"{location}.{key} must be a non-empty string."
        )
    return value.strip()


def _require_positive_integer(payload, key, location):
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DatasetValidationError(
            f"{location}.{key} must be a positive integer."
        )
    return value
