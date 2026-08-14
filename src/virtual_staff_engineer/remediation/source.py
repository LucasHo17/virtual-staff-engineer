import re
import subprocess
from pathlib import Path

from virtual_staff_engineer.database.connection import connect
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


class GitHubSnapshotSourceProvider:
    """Read immutable source captured from a GitHub PR head commit."""

    def __init__(self, database_url=None):
        self.database_url = database_url

    def load(self, source_path, revision=None):
        if revision is None or not re.fullmatch(
            r"[0-9a-fA-F]{40}([0-9a-fA-F]{24})?", revision
        ):
            raise ValueError("GitHub snapshot revision must be a full commit SHA.")
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT snapshot.source_content
                    FROM github_pr_file_snapshots AS snapshot
                    JOIN commits AS commit
                      ON commit.commit_id = snapshot.commit_id
                    WHERE lower(commit.commit_sha) = lower(%s)
                      AND snapshot.source_path = %s;
                    """,
                    (revision, source_path),
                )
                rows = cur.fetchall()
        if not rows:
            raise FileNotFoundError(
                f"GitHub source snapshot is unavailable: {source_path}"
            )
        contents = {row[0] for row in rows}
        if len(contents) != 1:
            raise ValueError("GitHub source snapshot identity is ambiguous.")
        return SourceSnapshot(source_path, contents.pop(), revision.lower())


class RoutedSourceProvider:
    """Use durable GitHub snapshots for revisions and local files otherwise."""

    def __init__(self, local_provider, revision_provider):
        self.local_provider = local_provider
        self.revision_provider = revision_provider

    def load(self, source_path, revision=None):
        if revision is not None:
            return self.revision_provider.load(source_path, revision=revision)
        return self.local_provider.load(source_path)
