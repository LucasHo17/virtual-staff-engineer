import base64
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from virtual_staff_engineer.github import (
    GitHubAppClient,
    GitHubPullRequestChangedError,
    GitHubPullRequestDelivery,
)


NOW = 1_800_000_000
HEAD_SHA = "a" * 40
BASE_SHA = "b" * 40


class FakeGitHubAppApi:
    def __init__(self, files=None, move_head=False):
        self.files = files or [_file()]
        self.move_head = move_head
        self.calls = []
        self.pull_reads = 0

    def __call__(self, method, path, payload, token):
        self.calls.append((method, path, payload, token))
        if path == "/app/installations/42/access_tokens":
            return {
                "token": "installation-token",
                "expires_at": "2030-01-01T00:00:00Z",
            }
        if path == "/repos/example/demo/pulls/7":
            self.pull_reads += 1
            head = (
                "c" * 40
                if self.move_head and self.pull_reads > 1
                else HEAD_SHA
            )
            return {
                "number": 7,
                "title": "Test pull request",
                "html_url": "https://github.com/example/demo/pull/7",
                "head": {"sha": head},
                "base": {"sha": BASE_SHA},
            }
        if path.endswith("/files?per_page=100&page=1"):
            return self.files[:100]
        if path.endswith("/files?per_page=100&page=2"):
            return self.files[100:200]
        if "/git/blobs/" in path:
            return {
                "encoding": "base64",
                "content": base64.b64encode(b"current source\n").decode(),
            }
        raise AssertionError((method, path, payload, token))


class GitHubAppClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_directory = tempfile.TemporaryDirectory()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.private_key = key
        cls.key_path = Path(cls.temp_directory.name, "app.pem")
        cls.key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp_directory.cleanup()

    def test_creates_short_lived_rs256_app_jwt(self):
        client = self._client(FakeGitHubAppApi())

        token = client.create_app_jwt()
        header_segment, payload_segment, signature_segment = token.split(".")
        signing_input = (header_segment + "." + payload_segment).encode("ascii")
        signature = _decode_segment(signature_segment)
        self.private_key.public_key().verify(
            signature,
            signing_input,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        header = json.loads(_decode_segment(header_segment))
        payload = json.loads(_decode_segment(payload_segment))

        self.assertEqual(header["alg"], "RS256")
        self.assertEqual(payload["iss"], "123")
        self.assertEqual(payload["iat"], NOW - 60)
        self.assertEqual(payload["exp"], NOW + 540)

    def test_requests_read_only_installation_token_and_caches_it(self):
        api = FakeGitHubAppApi()
        client = self._client(api)

        first = client.installation_token(42)
        second = client.installation_token(42)

        self.assertIs(first, second)
        token_calls = [call for call in api.calls if "access_tokens" in call[1]]
        self.assertEqual(len(token_calls), 1)
        self.assertEqual(
            token_calls[0][2],
            {"permissions": {"contents": "read", "pull_requests": "read"}},
        )
        self.assertEqual(len(token_calls[0][3].split(".")), 3)

    def test_fetches_stable_snapshot_and_normalizes_analyzable_files(self):
        api = FakeGitHubAppApi(
            files=[
                _file(),
                _file(
                    filename="new.py",
                    status="added",
                    patch="@@ -0,0 +1 @@\n+safe = True",
                ),
                _file(filename="image.png", patch=None),
                _file(filename="old.py", status="removed"),
            ]
        )
        snapshot = self._client(api).fetch_pull_request(_delivery())

        self.assertEqual(snapshot.head_sha, HEAD_SHA)
        analysis_inputs = snapshot.analysis_inputs("00000000-0000-0000-0000-000000000001")
        self.assertEqual(len(analysis_inputs), 2)
        self.assertEqual(len(snapshot.skipped_files), 2)
        self.assertEqual(analysis_inputs[0].source_path, "app.py")
        self.assertEqual(
            analysis_inputs[0].commit_id,
            "00000000-0000-0000-0000-000000000001",
        )
        self.assertTrue(
            analysis_inputs[0].content.startswith(
                "--- a/app.py\n+++ b/app.py\n@@"
            )
        )
        self.assertTrue(
            analysis_inputs[1].content.startswith(
                "--- /dev/null\n+++ b/new.py\n@@"
            )
        )
        self.assertEqual(
            {item.skip_reason for item in snapshot.skipped_files},
            {"patch_unavailable_or_binary", "deleted_file"},
        )
        file_calls = [call for call in api.calls if "/files?" in call[1]]
        self.assertEqual(file_calls[0][3], "installation-token")

    def test_rejects_head_change_during_download(self):
        with self.assertRaises(GitHubPullRequestChangedError):
            self._client(FakeGitHubAppApi(move_head=True)).fetch_pull_request(
                _delivery()
            )

    def test_paginates_changed_files_without_silently_truncating(self):
        files = [
            _file(filename=f"src/file_{index}.py") for index in range(101)
        ]
        api = FakeGitHubAppApi(files=files)

        snapshot = self._client(api).fetch_pull_request(_delivery())

        self.assertEqual(len(snapshot.files), 101)
        file_calls = [call for call in api.calls if "/files?" in call[1]]
        self.assertEqual(len(file_calls), 2)

    def test_skips_patch_above_configured_size(self):
        client = self._client(
            FakeGitHubAppApi(files=[_file(patch="x" * 11)]),
            max_patch_characters=10,
        )

        snapshot = client.fetch_pull_request(_delivery())

        self.assertEqual(snapshot.files[0].skip_reason, "patch_too_large")
        self.assertFalse(
            snapshot.analysis_inputs("00000000-0000-0000-0000-000000000001")
        )

    def _client(self, api, **options):
        return GitHubAppClient(
            app_id=123,
            private_key_path=self.key_path,
            transport=api,
            clock=lambda: NOW,
            **options,
        )


def _delivery(head_sha=HEAD_SHA):
    return GitHubPullRequestDelivery(
        delivery_id="delivery-1",
        event_name="pull_request",
        action="opened",
        repository_owner="example",
        repository_name="demo",
        installation_id=42,
        pull_request_number=7,
        head_sha=head_sha,
        payload_sha256=hashlib.sha256(b"payload").hexdigest(),
    )


def _file(
    filename="app.py",
    status="modified",
    patch="@@ -1 +1 @@\n-old\n+new",
):
    return {
        "filename": filename,
        "sha": "d" * 40,
        "status": status,
        "additions": 1,
        "deletions": 1,
        "changes": 2,
        "patch": patch,
    }


def _decode_segment(value):
    padding_length = (-len(value)) % 4
    return base64.urlsafe_b64decode(value + "=" * padding_length)


if __name__ == "__main__":
    unittest.main()
