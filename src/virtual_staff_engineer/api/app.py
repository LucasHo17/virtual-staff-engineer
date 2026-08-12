import asyncio
import json
import os

from fastapi import Depends, FastAPI, HTTPException, Query, status
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
    ReviewResponse,
)
from virtual_staff_engineer.jobs.lifecycle import TERMINAL_JOB_STATES
from virtual_staff_engineer.jobs.repository import (
    ApprovalConflictError,
    IdempotencyConflictError,
    WorkflowJobRepository,
)
from virtual_staff_engineer.remediation.approval import HumanDecision


def create_app(repository=None, authenticator=None):
    app = FastAPI(
        title="Virtual Staff Engineer API",
        version="0.1.0",
        description=(
            "Asynchronous, human-supervised engineering review workflow."
        ),
    )
    app.state.repository = repository or WorkflowJobRepository()
    app.state.authenticator = authenticator or ApiKeyAuthenticator()
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
        return _status_response(observation)

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


def _status_response(observation):
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
        estimated_analysis_cost_usd=_estimated_cost(observation),
    )


def _estimated_cost(observation):
    try:
        input_rate = float(os.getenv("VSE_INPUT_COST_PER_MILLION", "0"))
        output_rate = float(os.getenv("VSE_OUTPUT_COST_PER_MILLION", "0"))
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
