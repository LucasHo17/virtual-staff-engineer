import asyncio
import json
import os

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from virtual_staff_engineer.analysis.contracts import AnalysisInput
from virtual_staff_engineer.api.auth import ApiKeyAuthenticator, api_key_header
from virtual_staff_engineer.api.models import (
    AnalysisSubmission,
    DecisionRequest,
    DecisionResponse,
    JobStatusResponse,
    JobSubmissionResponse,
    GitHubWebhookResponse,
    GitHubPullRequestSummaryResponse,
    GitHubPullRequestPageResponse,
    ReviewResponse,
)
from virtual_staff_engineer.github import (
    GitHubDeliveryConflictError,
    GitHubWebhookDeliveryRepository,
    GitHubWebhookSignatureError,
    decode_webhook_payload,
    parse_pull_request_delivery,
    parse_pull_request_lifecycle_update,
    verify_webhook_signature,
)
from virtual_staff_engineer.jobs.lifecycle import TERMINAL_JOB_STATES
from virtual_staff_engineer.jobs.repository import (
    ApprovalConflictError,
    IdempotencyConflictError,
    WorkflowJobRepository,
)
from virtual_staff_engineer.remediation.approval import HumanDecision


def create_app(
    repository=None,
    authenticator=None,
    webhook_repository=None,
    webhook_secret=None,
):
    app = FastAPI(
        title="Virtual Staff Engineer API",
        version="0.1.0",
        description=(
            "Asynchronous, human-supervised engineering review workflow."
        ),
    )
    app.state.repository = repository or WorkflowJobRepository()
    app.state.authenticator = authenticator or ApiKeyAuthenticator()
    app.state.webhook_repository = (
        webhook_repository or GitHubWebhookDeliveryRepository()
    )
    app.state.github_webhook_secret = (
        webhook_secret
        if webhook_secret is not None
        else os.getenv("GITHUB_WEBHOOK_SECRET")
    )
    origins = tuple(
        value.strip()
        for value in os.getenv(
            "VSE_CORS_ORIGINS", "http://localhost:3000"
        ).split(",")
        if value.strip()
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

    def principal(api_key=Depends(api_key_header)):
        return app.state.authenticator.authenticate(api_key)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post(
        "/webhooks/github",
        response_model=GitHubWebhookResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def github_webhook(request: Request):
        secret = app.state.github_webhook_secret
        if not secret:
            raise HTTPException(
                status_code=503,
                detail="GitHub webhook secret is not configured.",
            )
        delivery_id = _required_webhook_header(
            request, "X-GitHub-Delivery", 100
        )
        event_name = _required_webhook_header(
            request, "X-GitHub-Event", 100
        )
        signature = request.headers.get("X-Hub-Signature-256")
        raw_body = await request.body()
        if len(raw_body) > 2_000_000:
            raise HTTPException(
                status_code=413,
                detail="GitHub webhook body exceeds the 2 MB limit.",
            )
        try:
            verify_webhook_signature(raw_body, signature, secret)
        except GitHubWebhookSignatureError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        try:
            payload = decode_webhook_payload(raw_body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if event_name == "ping":
            return GitHubWebhookResponse(
                status="pong",
                delivery_id=delivery_id,
                event=event_name,
            )
        try:
            lifecycle = parse_pull_request_lifecycle_update(
                delivery_id, event_name, payload, raw_body
            )
            lifecycle_result = (
                app.state.webhook_repository.record_lifecycle(lifecycle)
                if lifecycle is not None else None
            )
            delivery = parse_pull_request_delivery(
                delivery_id, event_name, payload, raw_body
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if delivery is None:
            if lifecycle_result is not None:
                return GitHubWebhookResponse(
                    status=(
                        "accepted" if lifecycle_result.created else "duplicate"
                    ),
                    delivery_id=delivery_id,
                    event=event_name,
                    action=lifecycle.action,
                )
            action = payload.get("action")
            return GitHubWebhookResponse(
                status="ignored",
                delivery_id=delivery_id,
                event=event_name,
                action=action if isinstance(action, str) else None,
            )
        try:
            result = app.state.webhook_repository.record(delivery)
        except GitHubDeliveryConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return GitHubWebhookResponse(
            status="accepted" if result.created else "duplicate",
            delivery_id=delivery.delivery_id,
            event=delivery.event_name,
            action=delivery.action,
        )

    @app.post(
        "/analysis-runs",
        response_model=JobSubmissionResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def submit(payload: AnalysisSubmission, _principal=Depends(principal)):
        model = os.getenv("GEMINI_REASONING_MODEL")
        if not model:
            raise HTTPException(
                status_code=503,
                detail="GEMINI_REASONING_MODEL is not configured.",
            )
        try:
            result = app.state.repository.submit(
                AnalysisInput(
                    payload.input_type,
                    payload.content,
                    payload.source_path,
                ),
                idempotency_key=payload.idempotency_key,
                model_name=model,
                workflow_version="phase4-api-v1",
                prompt_version="phase2-v1",
                priority=payload.priority,
                max_attempts=payload.max_attempts,
            )
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return JobSubmissionResponse(
            workflow_job_id=result.job.workflow_job_id,
            created=result.created,
            status=result.job.status.value,
        )

    @app.get("/jobs/{workflow_job_id}", response_model=JobStatusResponse)
    def job_status(workflow_job_id: str, _principal=Depends(principal)):
        observation = app.state.repository.observe(workflow_job_id)
        if observation is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        context_getter = getattr(
            app.state.webhook_repository, "get_job_context", None
        )
        context = (
            context_getter(workflow_job_id) if context_getter else None
        )
        return _status_response(observation, context)

    @app.get(
        "/github/pull-requests",
        response_model=GitHubPullRequestPageResponse,
    )
    def github_pull_requests(
        view: str = Query(default="active"),
        state: str = Query(default="all"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=10, ge=1, le=100),
        _principal=Depends(principal),
    ):
        list_method = getattr(
            app.state.webhook_repository, "list_pull_requests", None
        )
        if list_method is None:
            return {
                "items": [], "page": page, "page_size": page_size,
                "total": 0, "total_pages": 0,
            }
        if view not in {"active", "archive", "all"}:
            raise HTTPException(status_code=422, detail="Invalid view.")
        if state not in {"all", "open", "closed", "merged"}:
            raise HTTPException(status_code=422, detail="Invalid state.")
        states = {
            "active": ("open",),
            "archive": ("closed", "merged"),
            "all": ("open", "closed", "merged"),
        }[view]
        if state != "all":
            if state not in states:
                return {
                    "items": [], "page": page, "page_size": page_size,
                    "total": 0, "total_pages": 0,
                }
            states = (state,)
        result = list_method(states=states, page=page, page_size=page_size)
        items = [
            {
                **vars(item),
                "jobs": [vars(job) for job in item.jobs],
            }
            for item in result.items
        ]
        total_pages = (
            (result.total + result.page_size - 1) // result.page_size
            if result.total else 0
        )
        return {
            "items": items, "page": result.page,
            "page_size": result.page_size, "total": result.total,
            "total_pages": total_pages,
        }

    @app.get("/jobs/{workflow_job_id}/review", response_model=ReviewResponse)
    def review(workflow_job_id: str, _principal=Depends(principal)):
        request = app.state.repository.get_approval_request(workflow_job_id)
        if request is None:
            raise HTTPException(
                status_code=404,
                detail="No validated patch is awaiting approval.",
            )
        return ReviewResponse(
            workflow_job_id=request.workflow_job_id,
            source_path=request.source_path,
            original_sha256=request.original_sha256,
            resulting_sha256=request.resulting_sha256,
            explanation=request.explanation,
            unified_diff=request.unified_diff,
            rules=[vars(rule) for rule in request.rules],
            checks=[vars(check) for check in request.checks],
        )

    @app.post(
        "/jobs/{workflow_job_id}/decision",
        response_model=DecisionResponse,
    )
    def decide(
        workflow_job_id: str,
        payload: DecisionRequest,
        reviewer=Depends(principal),
    ):
        if reviewer.role != "reviewer":
            raise HTTPException(
                status_code=403,
                detail="Reviewer authorization is required.",
            )
        try:
            result = app.state.repository.record_human_decision(
                workflow_job_id,
                HumanDecision(
                    payload.decision,
                    reviewer.subject,
                    payload.comment,
                    authentication_method="api_key",
                    authenticated_subject=reviewer.subject,
                    authentication_issuer="vse-api-key",
                ),
            )
        except ApprovalConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return DecisionResponse(
            workflow_job_id=result.job.workflow_job_id,
            status=result.job.status.value,
            created=result.created,
        )

    @app.get("/jobs/{workflow_job_id}/events")
    async def events(
        workflow_job_id: str,
        after: int = Query(default=0, ge=0),
        _principal=Depends(principal),
    ):
        if app.state.repository.get(workflow_job_id) is None:
            raise HTTPException(status_code=404, detail="Job not found.")

        async def stream():
            sequence = after
            while True:
                new_events = app.state.repository.list_events(
                    workflow_job_id, after_sequence=sequence
                )
                for event in new_events:
                    sequence = event.sequence
                    payload = {
                        "sequence": event.sequence,
                        "status": event.to_status,
                        "checkpoint": event.checkpoint,
                        "attempt_count": event.attempt_count,
                        "failure_code": event.failure_code,
                        "created_at": event.created_at.isoformat(),
                    }
                    yield (
                        f"id: {event.sequence}\n"
                        f"event: workflow_status\n"
                        f"data: {json.dumps(payload)}\n\n"
                    )
                current = app.state.repository.get(workflow_job_id)
                if current is None or current.status in TERMINAL_JOB_STATES:
                    return
                yield ": keep-alive\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


def _required_webhook_header(request, name, max_length):
    value = request.headers.get(name)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail=f"{name} is required.")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise HTTPException(
            status_code=400,
            detail=f"{name} exceeds {max_length} characters.",
        )
    return normalized


def _status_response(observation, github_context=None):
    job = observation.job
    return JobStatusResponse(
        workflow_job_id=job.workflow_job_id,
        analysis_run_id=job.analysis_run_id,
        status=job.status.value,
        checkpoint=job.checkpoint.value,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        failure_code=job.failure_code,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
        queue_wait_ms=observation.queue_wait_ms,
        human_wait_ms=observation.human_wait_ms,
        automated_processing_ms=observation.automated_processing_ms,
        end_to_end_ms=observation.end_to_end_ms,
        stage_timings=[vars(item) for item in observation.stage_timings],
        input_tokens=observation.input_tokens,
        output_tokens=observation.output_tokens,
        tool_call_count=observation.tool_call_count,
        retry_count=observation.retry_count,
        estimated_analysis_cost_usd=_estimated_cost(observation),
        origin="github" if github_context is not None else "manual",
        github=vars(github_context) if github_context is not None else None,
    )


def _estimated_cost(observation):
    input_value = os.getenv("VSE_INPUT_COST_PER_MILLION")
    output_value = os.getenv("VSE_OUTPUT_COST_PER_MILLION")
    if input_value is None or output_value is None:
        return None
    try:
        input_rate = float(input_value)
        output_rate = float(output_value)
    except ValueError:
        return None
    if input_rate < 0 or output_rate < 0:
        return None
    return round(
        (
            observation.input_tokens * input_rate
            + observation.output_tokens * output_rate
        )
        / 1_000_000,
        8,
    )


app = create_app()
