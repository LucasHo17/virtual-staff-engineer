import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class Phase4ApiClient:
    """Small authenticated HTTP client shared by Phase 4 evaluation runners."""

    def __init__(self, base_url, viewer_key, reviewer_key=None, timeout=30):
        self.base_url = base_url.rstrip("/")
        self.viewer_key = viewer_key
        self.reviewer_key = reviewer_key
        self.timeout = timeout

    def health(self):
        return self._request("GET", "/health", authenticated=False)

    def submit(self, payload):
        return self._request("POST", "/analysis-runs", payload)

    def status(self, job_id):
        return self._request("GET", f"/jobs/{job_id}")

    def review(self, job_id):
        return self._request("GET", f"/jobs/{job_id}/review")

    def decide(self, job_id, payload):
        if not self.reviewer_key:
            raise RuntimeError(
                "VSE_REVIEWER_API_KEY is required for decision cases."
            )
        return self._request(
            "POST",
            f"/jobs/{job_id}/decision",
            payload,
            api_key=self.reviewer_key,
        )

    def _request(
        self, method, path, payload=None, authenticated=True, api_key=None
    ):
        data = None
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["X-API-Key"] = api_key or self.viewer_key
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"API returned HTTP {exc.code} for {method} {path}: {detail}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                f"Could not reach API at {self.base_url}: {exc.reason}"
            ) from exc
