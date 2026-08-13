import hashlib
import hmac
import json
import unittest

from virtual_staff_engineer.github import (
    GitHubWebhookSignatureError,
    decode_webhook_payload,
    parse_pull_request_delivery,
    verify_webhook_signature,
)


class GitHubWebhookTests(unittest.TestCase):
    def test_signature_is_bound_to_exact_raw_body(self):
        secret = "secret"
        body = b'{"action":"opened"}'
        signature = "sha256=" + hmac.new(
            secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()

        verify_webhook_signature(body, signature, secret)
        with self.assertRaises(GitHubWebhookSignatureError):
            verify_webhook_signature(body + b"\n", signature, secret)

    def test_decodes_only_json_objects(self):
        self.assertEqual(decode_webhook_payload(b'{"ok":true}'), {"ok": True})
        for value in (b"not-json", b"[]", b'"text"'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    decode_webhook_payload(value)

    def test_parser_extracts_minimal_pull_request_identity(self):
        payload = {
            "action": "synchronize",
            "installation": {"id": 42},
            "repository": {"name": "repo", "owner": {"login": "owner"}},
            "pull_request": {"number": 9, "head": {"sha": "b" * 40}},
        }
        body = json.dumps(payload).encode("utf-8")

        delivery = parse_pull_request_delivery(
            "delivery", "pull_request", payload, body
        )

        self.assertEqual(delivery.action, "synchronize")
        self.assertEqual(delivery.installation_id, 42)
        self.assertEqual(delivery.pull_request_number, 9)
        self.assertEqual(
            delivery.payload_sha256, hashlib.sha256(body).hexdigest()
        )


if __name__ == "__main__":
    unittest.main()
