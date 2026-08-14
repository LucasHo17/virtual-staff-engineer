import base64
import json
import os
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from virtual_staff_engineer.analysis.contracts import AnalysisInput
from virtual_staff_engineer.github.client import GitHubApiError
from virtual_staff_engineer.github.webhook import GitHubPullRequestDelivery


class GitHubPullRequestChangedError(ValueError):
    """The pull-request head changed while its snapshot was being fetched."""


class GitHubPullRequestTooLargeError(ValueError):
    """The pull request exceeded the bounded changed-file retrieval contract."""


@dataclass(frozen=True)
class GitHubInstallationToken:
    token: str
    expires_at: datetime

    def __post_init__(self):
        if not isinstance(self.token, str) or not self.token.strip():
            raise ValueError("token must be a non-empty string.")
        if not isinstance(self.expires_at, datetime):
            raise TypeError("expires_at must be a datetime.")
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware.")


@dataclass(frozen=True)
class GitHubPullRequestFile:
    filename: str
    blob_sha: str
    status: str
    additions: int
    deletions: int
    changes: int
    patch: Optional[str]
    source_content: Optional[str] = None
    previous_filename: Optional[str] = None
    skip_reason: Optional[str] = None

    def __post_init__(self):
        _path(self.filename, "filename")
        if not _sha(self.blob_sha):
            raise ValueError("blob_sha must be a 40- or 64-character hex SHA.")
        if self.previous_filename is not None:
            _path(self.previous_filename, "previous_filename")
        if not isinstance(self.status, str) or not self.status.strip():
            raise ValueError("status must be a non-empty string.")
        for name in ("additions", "deletions", "changes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer.")
        if self.patch is not None and not isinstance(self.patch, str):
            raise TypeError("patch must be a string or None.")
        if self.source_content is not None and not isinstance(
            self.source_content, str
        ):
            raise TypeError("source_content must be a string or None.")
        if self.skip_reason is not None and (
            not isinstance(self.skip_reason, str) or not self.skip_reason.strip()
        ):
            raise ValueError("skip_reason must be non-empty or None.")

    @property
    def analyzable(self):
        return self.skip_reason is None and self.source_content is not None

    @property
    def needs_source(self):
        return self.skip_reason is None and bool(self.patch)

    @property
    def unified_diff(self):
        if not self.analyzable or not self.patch:
            return None
        old_path = (
            "/dev/null"
            if self.status == "added"
            else "a/" + (self.previous_filename or self.filename)
        )
        new_path = "b/" + self.filename
        return f"--- {old_path}\n+++ {new_path}\n{self.patch.rstrip()}"


@dataclass(frozen=True)
class GitHubPullRequestSnapshot:
    repository_owner: str
    repository_name: str
    installation_id: int
    pull_request_number: int
    title: str
    html_url: str
    head_sha: str
    base_sha: str
    files: Tuple[GitHubPullRequestFile, ...]

    def analysis_inputs(self, commit_id):
        return tuple(
            AnalysisInput(
                "code_diff",
                item.unified_diff,
                source_path=item.filename,
                commit_id=commit_id,
            )
            for item in self.files
            if item.analyzable
        )

    @property
    def skipped_files(self):
        return tuple(item for item in self.files if not item.analyzable)


class GitHubAppClient:
    """Read-only GitHub App authentication and stable PR snapshot adapter."""

    def __init__(
        self,
        app_id=None,
        private_key_path=None,
        api_url="https://api.github.com",
        transport=None,
        clock=None,
        max_files=3000,
        max_patch_characters=200000,
    ):
        resolved_id = app_id if app_id is not None else os.getenv("GITHUB_APP_ID")
        resolved_path = (
            private_key_path
            if private_key_path is not None
            else os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")
        )
        if isinstance(resolved_id, bool) or not str(resolved_id or "").isdigit():
            raise RuntimeError("GITHUB_APP_ID must be a positive numeric App ID.")
        self.app_id = str(resolved_id)
        if int(self.app_id) < 1:
            raise RuntimeError("GITHUB_APP_ID must be a positive numeric App ID.")
        if not isinstance(resolved_path, (str, Path)) or not str(resolved_path):
            raise RuntimeError("GITHUB_APP_PRIVATE_KEY_PATH is not configured.")
        self.private_key_path = Path(resolved_path).expanduser()
        self.private_key = _load_private_key(self.private_key_path)
        if (
            isinstance(max_files, bool)
            or not isinstance(max_files, int)
            or max_files < 1
            or max_files > 3000
        ):
            raise ValueError("max_files must be between 1 and 3000.")
        if (
            isinstance(max_patch_characters, bool)
            or not isinstance(max_patch_characters, int)
            or max_patch_characters < 1
        ):
            raise ValueError("max_patch_characters must be positive.")
        self.max_files = max_files
        self.max_patch_characters = max_patch_characters
        self.api_url = api_url.rstrip("/")
        self.transport = transport or self._request
        self.clock = clock or time.time
        self._tokens = {}
        self._token_lock = threading.Lock()

    def create_app_jwt(self):
        now = int(self.clock())
        header = {"alg": "RS256", "typ": "JWT"}
        payload = {
            "iat": now - 60,
            "exp": now + 9 * 60,
            "iss": self.app_id,
        }
        signing_input = (
            _base64url(_compact_json(header))
            + b"."
            + _base64url(_compact_json(payload))
        )
        signature = self.private_key.sign(
            signing_input,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return (signing_input + b"." + _base64url(signature)).decode("ascii")

    def installation_token(self, installation_id):
        _positive_integer(installation_id, "installation_id")
        with self._token_lock:
            cached = self._tokens.get(installation_id)
            now = datetime.fromtimestamp(self.clock(), timezone.utc)
            if cached is not None and (
                cached.expires_at.timestamp() - now.timestamp() > 60
            ):
                return cached
            response = self.transport(
                "POST",
                f"/app/installations/{installation_id}/access_tokens",
                {
                    "permissions": {
                        "contents": "read",
                        "pull_requests": "read",
                    }
                },
                self.create_app_jwt(),
            )
            token = _parse_installation_token(response)
            self._tokens[installation_id] = token
            return token

    def fetch_pull_request(self, delivery):
        if not isinstance(delivery, GitHubPullRequestDelivery):
            raise TypeError("delivery must be a GitHubPullRequestDelivery.")
        token = self.installation_token(delivery.installation_id).token
        prefix = (
            "/repos/"
            + quote(delivery.repository_owner, safe="")
            + "/"
            + quote(delivery.repository_name, safe="")
            + "/pulls/"
            + str(delivery.pull_request_number)
        )
        pull = self.transport("GET", prefix, None, token)
        first_head = _pull_head_sha(pull)
        if first_head.lower() != delivery.head_sha.lower():
            raise GitHubPullRequestChangedError(
                "Webhook head SHA no longer matches the pull request."
            )
        files = self._fetch_files(prefix, token)
        files = tuple(
            self._fetch_source(delivery, item, token)
            if item.needs_source
            else item
            for item in files
        )
        confirmed = self.transport("GET", prefix, None, token)
        if _pull_head_sha(confirmed).lower() != first_head.lower():
            raise GitHubPullRequestChangedError(
                "Pull-request head changed while files were downloaded."
            )
        return _snapshot(delivery, pull, first_head, files)

    def _fetch_files(self, prefix, token):
        collected = []
        page = 1
        while True:
            response = self.transport(
                "GET",
                f"{prefix}/files?per_page=100&page={page}",
                None,
                token,
            )
            if not isinstance(response, list):
                raise GitHubApiError(
                    "GitHub changed-files response must be an array."
                )
            if len(response) > 100:
                raise GitHubApiError(
                    "GitHub changed-files page exceeded 100 entries."
                )
            if len(collected) + len(response) > self.max_files:
                raise GitHubPullRequestTooLargeError(
                    f"Pull request exceeds the {self.max_files}-file limit."
                )
            collected.extend(
                _parse_file(item, self.max_patch_characters)
                for item in response
            )
            if len(response) < 100:
                return tuple(collected)
            if len(collected) == self.max_files:
                raise GitHubPullRequestTooLargeError(
                    "Pull request reached the bounded changed-file limit; "
                    "refusing a potentially incomplete snapshot."
                )
            page += 1

    def _fetch_source(self, delivery, item, token):
        prefix = (
            "/repos/"
            + quote(delivery.repository_owner, safe="")
            + "/"
            + quote(delivery.repository_name, safe="")
        )
        response = self.transport(
            "GET",
            prefix + "/git/blobs/" + quote(item.blob_sha, safe=""),
            None,
            token,
        )
        try:
            if response["encoding"] != "base64":
                raise ValueError("encoding is not base64")
            encoded = response["content"].replace("\n", "")
            content = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
            return replace(
                item,
                patch=None,
                skip_reason="source_unavailable_or_binary",
            )
        return replace(item, source_content=content)

    def _request(self, method, path, payload, token):
        data = None if payload is None else _compact_json(payload)
        request = Request(
            self.api_url + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + token,
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "virtual-staff-engineer",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise GitHubApiError(
                f"GitHub API returned HTTP {exc.code} for {method} {path}.",
                status_code=exc.code,
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise ConnectionError(f"GitHub API request failed: {exc}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubApiError("GitHub API returned invalid JSON.") from exc


def _load_private_key(path):
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"Unable to read GitHub App private key: {path}") from exc
    try:
        key = serialization.load_pem_private_key(data, password=None)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("GitHub App private key is not valid PEM.") from exc
    if not isinstance(key, rsa.RSAPrivateKey):
        raise RuntimeError("GitHub App private key must be an RSA key.")
    return key


def _parse_installation_token(response):
    try:
        token = response["token"]
        expires_at = datetime.fromisoformat(
            response["expires_at"].replace("Z", "+00:00")
        )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise GitHubApiError(
            "GitHub installation-token response is incomplete."
        ) from exc
    return GitHubInstallationToken(token, expires_at)


def _pull_head_sha(pull):
    try:
        value = pull["head"]["sha"]
    except (KeyError, TypeError) as exc:
        raise GitHubApiError("GitHub pull-request response lacks head SHA.") from exc
    if not _sha(value):
        raise GitHubApiError("GitHub pull-request head SHA is invalid.")
    return value


def _snapshot(delivery, pull, head_sha, files):
    try:
        number = pull["number"]
        title = pull["title"]
        html_url = pull["html_url"]
        base_sha = pull["base"]["sha"]
    except (KeyError, TypeError) as exc:
        raise GitHubApiError(
            "GitHub pull-request response lacks required metadata."
        ) from exc
    if number != delivery.pull_request_number:
        raise GitHubApiError("GitHub pull-request number does not match request.")
    for value, name in ((title, "title"), (html_url, "html_url")):
        if not isinstance(value, str) or not value.strip():
            raise GitHubApiError(f"GitHub pull-request {name} is invalid.")
    if not _sha(base_sha):
        raise GitHubApiError("GitHub pull-request base SHA is invalid.")
    return GitHubPullRequestSnapshot(
        repository_owner=delivery.repository_owner,
        repository_name=delivery.repository_name,
        installation_id=delivery.installation_id,
        pull_request_number=number,
        title=title,
        html_url=html_url,
        head_sha=head_sha,
        base_sha=base_sha,
        files=files,
    )


def _parse_file(item, max_patch_characters):
    if not isinstance(item, dict):
        raise GitHubApiError("GitHub changed-files array contains invalid data.")
    try:
        filename = item["filename"]
        blob_sha = item["sha"]
        status = item["status"]
        additions = item["additions"]
        deletions = item["deletions"]
        changes = item["changes"]
    except KeyError as exc:
        raise GitHubApiError("GitHub changed-file response is incomplete.") from exc
    patch = item.get("patch")
    previous = item.get("previous_filename")
    reason = None
    if status == "removed":
        reason = "deleted_file"
    elif not isinstance(patch, str) or not patch.strip():
        reason = "patch_unavailable_or_binary"
        patch = None
    elif len(patch) > max_patch_characters:
        reason = "patch_too_large"
        patch = None
    try:
        return GitHubPullRequestFile(
            filename=filename,
            blob_sha=blob_sha,
            status=status,
            additions=additions,
            deletions=deletions,
            changes=changes,
            patch=patch,
            previous_filename=previous,
            skip_reason=reason,
        )
    except (TypeError, ValueError) as exc:
        raise GitHubApiError(f"GitHub changed-file response is invalid: {exc}") from exc


def _path(value, name):
    if (
        not isinstance(value, str)
        or not value.strip()
        or "\x00" in value
        or "\n" in value
        or "\r" in value
    ):
        raise ValueError(f"{name} must be a safe non-empty path.")


def _positive_integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")


def _sha(value):
    return (
        isinstance(value, str)
        and len(value) in {40, 64}
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _compact_json(value):
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _base64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=")
