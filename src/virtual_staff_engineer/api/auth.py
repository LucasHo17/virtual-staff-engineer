import hashlib
import hmac
import os
from dataclasses import dataclass

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str


class ApiKeyAuthenticator:
    """Small MVP authentication boundary with server-configured identities."""

    def __init__(
        self,
        viewer_key=None,
        reviewer_key=None,
        viewer_subject=None,
        reviewer_subject=None,
    ):
        self.viewer_key = viewer_key or os.getenv("VSE_VIEWER_API_KEY")
        self.reviewer_key = reviewer_key or os.getenv("VSE_REVIEWER_API_KEY")
        self.viewer_subject = (
            viewer_subject or os.getenv("VSE_VIEWER_IDENTITY") or "viewer"
        )
        self.reviewer_subject = (
            reviewer_subject
            or os.getenv("VSE_REVIEWER_IDENTITY")
            or "reviewer"
        )

    def authenticate(self, supplied_key):
        if not supplied_key:
            raise _unauthorized()
        if self.reviewer_key and hmac.compare_digest(
            _digest(supplied_key), _digest(self.reviewer_key)
        ):
            return Principal(self.reviewer_subject, "reviewer")
        if self.viewer_key and hmac.compare_digest(
            _digest(supplied_key), _digest(self.viewer_key)
        ):
            return Principal(self.viewer_subject, "viewer")
        raise _unauthorized()


def api_key_header(x_api_key: str = Header(default=None)):
    return x_api_key


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).digest()


def _unauthorized():
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="A valid API key is required.",
    )
