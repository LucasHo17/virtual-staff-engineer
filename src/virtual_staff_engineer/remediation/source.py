import re
import subprocess
from pathlib import Path

from virtual_staff_engineer.remediation.contracts import SourceSnapshot


class FilesystemSourceProvider:
    """Read source snapshots without permitting paths outside a repository."""

    def __init__(self, repository_root):
        self.repository_root = Path(repository_root).resolve()
        if not self.repository_root.is_dir():
            raise ValueError("repository_root must be an existing directory.")

    def load(self, source_path, revision=None):
        if revision is not None:
            raise ValueError(
                "FilesystemSourceProvider cannot guarantee historical revisions."
            )
        candidate = (self.repository_root / source_path).resolve()
        try:
            candidate.relative_to(self.repository_root)
        except ValueError as exc:
            raise ValueError("source_path escapes repository_root.") from exc
        if not candidate.is_file():
            raise FileNotFoundError(f"Source file does not exist: {source_path}")
        return SourceSnapshot(
            source_path=str(candidate.relative_to(self.repository_root)),
            content=candidate.read_text(encoding="utf-8"),
            revision=None,
        )


class GitSourceProvider(FilesystemSourceProvider):
    """Read an exact file snapshot from a validated local Git revision."""

    def load(self, source_path, revision=None):
        if revision is None:
            return super().load(source_path)
        if not re.fullmatch(r"[0-9a-fA-F]{40}([0-9a-fA-F]{24})?", revision):
            raise ValueError("revision must be a full Git commit SHA.")
        candidate = (self.repository_root / source_path).resolve()
        try:
            relative_path = candidate.relative_to(self.repository_root)
        except ValueError as exc:
            raise ValueError("source_path escapes repository_root.") from exc
        result = subprocess.run(
            ["git", "show", f"{revision}:{relative_path.as_posix()}"],
            cwd=self.repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise FileNotFoundError(
                f"Source file is unavailable at revision: {source_path}"
            )
        return SourceSnapshot(
            source_path=relative_path.as_posix(),
            content=result.stdout,
            revision=revision.lower(),
        )
