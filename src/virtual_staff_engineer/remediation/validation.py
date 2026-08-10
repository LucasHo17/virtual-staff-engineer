import ast
import hashlib
import json
import re
from pathlib import Path

from virtual_staff_engineer.remediation.contracts import (
    PatchValidationCheck,
    PatchValidationResult,
    PersistedPatchProposal,
    SourceSnapshot,
)


HUNK_HEADER = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$"
)


class PatchApplyError(ValueError):
    """The generated unified diff cannot apply to its stored baseline."""


class DeterministicPatchValidator:
    """Validate a proposal entirely in memory without source mutation."""

    version = "deterministic-v1"

    def __init__(self, maximum_changed_lines=200):
        if (
            isinstance(maximum_changed_lines, bool)
            or not isinstance(maximum_changed_lines, int)
            or maximum_changed_lines < 1
        ):
            raise ValueError("maximum_changed_lines must be positive.")
        self.maximum_changed_lines = maximum_changed_lines

    def validate(self, proposal, current_source):
        if not isinstance(proposal, PersistedPatchProposal):
            raise TypeError("proposal must be a PersistedPatchProposal.")
        if not isinstance(current_source, SourceSnapshot):
            raise TypeError("current_source must be a SourceSnapshot.")
        checks = []
        stored_hash = hashlib.sha256(
            proposal.original_content.encode("utf-8")
        ).hexdigest()
        self._record(
            checks,
            "stored_original_hash",
            stored_hash == proposal.original_sha256,
            "Stored original content matches its recorded SHA-256.",
            "Stored original content hash is inconsistent.",
        )
        current_matches = (
            current_source.source_path == proposal.source_path
            and current_source.content_sha256 == proposal.original_sha256
        )
        self._record(
            checks,
            "current_source_hash",
            current_matches,
            "Current source matches the patch-generation baseline.",
            "Current source changed after patch generation.",
        )

        resulting_content = None
        changed_lines = 0
        try:
            resulting_content, changed_lines = apply_unified_diff(
                proposal.original_content,
                proposal.unified_diff,
                proposal.source_path,
            )
            checks.append(
                PatchValidationCheck(
                    "unified_diff_applies",
                    "passed",
                    "Unified diff applies exactly to the stored baseline.",
                )
            )
        except PatchApplyError as exc:
            checks.append(
                PatchValidationCheck(
                    "unified_diff_applies", "failed", str(exc)
                )
            )

        budget_passed = (
            resulting_content is not None
            and changed_lines <= self.maximum_changed_lines
        )
        self._record(
            checks,
            "change_budget",
            budget_passed,
            f"Patch changes {changed_lines} line(s), within the limit.",
            (
                "Patch could not be measured."
                if resulting_content is None
                else f"Patch changes {changed_lines} line(s), exceeding the "
                f"limit of {self.maximum_changed_lines}."
            ),
        )
        checks.append(
            self._syntax_check(proposal.source_path, resulting_content)
        )
        status = (
            "invalid"
            if any(check.status == "failed" for check in checks)
            else "valid"
        )
        resulting_sha256 = (
            hashlib.sha256(resulting_content.encode("utf-8")).hexdigest()
            if resulting_content is not None
            else None
        )
        return PatchValidationResult(
            status=status,
            checks=tuple(checks),
            changed_lines=changed_lines,
            resulting_sha256=resulting_sha256,
        )

    @staticmethod
    def _record(checks, name, passed, success, failure):
        checks.append(
            PatchValidationCheck(
                name=name,
                status="passed" if passed else "failed",
                details=success if passed else failure,
            )
        )

    @staticmethod
    def _syntax_check(source_path, content):
        if content is None:
            return PatchValidationCheck(
                "syntax", "skipped", "Syntax check requires an applied patch."
            )
        suffix = Path(source_path).suffix.lower()
        try:
            if suffix == ".py":
                ast.parse(content)
            elif suffix == ".json":
                json.loads(content)
            else:
                return PatchValidationCheck(
                    "syntax",
                    "skipped",
                    f"No deterministic syntax parser configured for {suffix or 'this file type'}.",
                )
        except (SyntaxError, json.JSONDecodeError) as exc:
            return PatchValidationCheck(
                "syntax", "failed", f"Patched source has invalid syntax: {exc}"
            )
        return PatchValidationCheck(
            "syntax", "passed", "Patched source syntax is valid."
        )


def apply_unified_diff(original_content, unified_diff, source_path):
    """Apply one-file unified diff text to source content in memory."""
    diff_lines = unified_diff.splitlines()
    if len(diff_lines) < 3:
        raise PatchApplyError("Unified diff is incomplete.")
    if diff_lines[0] != f"--- a/{source_path}":
        raise PatchApplyError("Unified diff old path does not match source.")
    if diff_lines[1] != f"+++ b/{source_path}":
        raise PatchApplyError("Unified diff new path does not match source.")
    if sum(line.startswith("--- ") for line in diff_lines) != 1:
        raise PatchApplyError("Unified diff must modify exactly one file.")
    if sum(line.startswith("+++ ") for line in diff_lines) != 1:
        raise PatchApplyError("Unified diff must modify exactly one file.")

    original_lines = original_content.splitlines()
    output = []
    original_cursor = 0
    diff_cursor = 2
    changed_lines = 0
    hunk_count = 0
    while diff_cursor < len(diff_lines):
        match = HUNK_HEADER.match(diff_lines[diff_cursor])
        if match is None:
            raise PatchApplyError("Expected a valid unified diff hunk header.")
        hunk_count += 1
        old_start = int(match.group(1))
        old_count = int(match.group(2) or 1)
        new_count = int(match.group(4) or 1)
        hunk_start = max(0, old_start - 1)
        if hunk_start < original_cursor or hunk_start > len(original_lines):
            raise PatchApplyError("Unified diff hunk location is invalid.")
        output.extend(original_lines[original_cursor:hunk_start])
        original_cursor = hunk_start
        diff_cursor += 1
        consumed = 0
        produced = 0
        while diff_cursor < len(diff_lines) and not diff_lines[
            diff_cursor
        ].startswith("@@ "):
            line = diff_lines[diff_cursor]
            if line == "\\ No newline at end of file":
                diff_cursor += 1
                continue
            if not line or line[0] not in {" ", "+", "-"}:
                raise PatchApplyError("Unified diff contains an invalid line.")
            marker, text = line[0], line[1:]
            if marker in {" ", "-"}:
                if (
                    original_cursor >= len(original_lines)
                    or original_lines[original_cursor] != text
                ):
                    raise PatchApplyError(
                        "Unified diff context does not match original content."
                    )
                original_cursor += 1
                consumed += 1
            if marker in {" ", "+"}:
                output.append(text)
                produced += 1
            if marker in {"+", "-"}:
                changed_lines += 1
            diff_cursor += 1
        if consumed != old_count or produced != new_count:
            raise PatchApplyError("Unified diff hunk line counts do not match.")
    if hunk_count == 0:
        raise PatchApplyError("Unified diff contains no hunks.")
    output.extend(original_lines[original_cursor:])
    trailing_newline = "\n" if original_content.endswith("\n") else ""
    return "\n".join(output) + trailing_newline, changed_lines
