from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class AnalysisSubmission(BaseModel):
    input_type: Literal["code_diff", "design_document"]
    content: str = Field(min_length=1, max_length=200000)
    source_path: Optional[str] = Field(default=None, max_length=1024)
    idempotency_key: str = Field(min_length=1, max_length=255)
    priority: int = Field(default=100, ge=0, le=1000)
    max_attempts: int = Field(default=3, ge=1, le=100)


class JobSubmissionResponse(BaseModel):
    workflow_job_id: str
    created: bool
    status: str


class WorkflowEventResponse(BaseModel):
    sequence: int
    from_status: Optional[str]
    to_status: str
    attempt_count: int
    checkpoint: str
    failure_code: Optional[str]
    error_message: Optional[str]
    created_at: datetime


class StageTimingResponse(BaseModel):
    stage: str
    duration_ms: float


class GitHubJobContextResponse(BaseModel):
    delivery_id: str
    repository_owner: str
    repository_name: str
    pull_request_number: int
    pull_request_title: Optional[str]
    pull_request_url: Optional[str]
    head_sha: str
    source_path: str
    created_pull_request_url: Optional[str]


class JobStatusResponse(BaseModel):
    workflow_job_id: str
    analysis_run_id: str
    status: str
    checkpoint: str
    attempt_count: int
    max_attempts: int
    failure_code: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    queue_wait_ms: Optional[float]
    human_wait_ms: Optional[float]
    automated_processing_ms: Optional[float]
    end_to_end_ms: Optional[float]
    stage_timings: List[StageTimingResponse]
    input_tokens: int
    output_tokens: int
    tool_call_count: int
    retry_count: int
    estimated_analysis_cost_usd: Optional[float]
    origin: Literal["manual", "github"] = "manual"
    github: Optional[GitHubJobContextResponse] = None


class GitHubJobSummaryResponse(BaseModel):
    workflow_job_id: str
    source_path: str
    status: str
    checkpoint: str
    failure_code: Optional[str]
    created_pull_request_url: Optional[str]
    head_sha: str
    received_at: datetime


class GitHubPullRequestSummaryResponse(BaseModel):
    latest_delivery_id: Optional[str]
    repository_owner: str
    repository_name: str
    pull_request_number: int
    pull_request_title: Optional[str]
    pull_request_url: Optional[str]
    head_sha: str
    base_sha: Optional[str]
    status: str
    changed_file_count: Optional[int]
    analyzable_file_count: Optional[int]
    skipped_file_count: Optional[int]
    received_at: datetime
    completed_at: Optional[datetime]
    lifecycle_state: Literal["open", "closed", "merged"]
    github_updated_at: datetime
    jobs: List[GitHubJobSummaryResponse]


class GitHubPullRequestPageResponse(BaseModel):
    items: List[GitHubPullRequestSummaryResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class ReviewRuleResponse(BaseModel):
    rule_key: str
    rule_snapshot: str


class ReviewCheckResponse(BaseModel):
    name: str
    status: str
    details: str


class ReviewResponse(BaseModel):
    workflow_job_id: str
    source_path: str
    original_sha256: str
    resulting_sha256: str
    explanation: str
    unified_diff: str
    rules: List[ReviewRuleResponse]
    checks: List[ReviewCheckResponse]


class DecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: Optional[str] = Field(default=None, min_length=1, max_length=4000)


class DecisionResponse(BaseModel):
    workflow_job_id: str
    status: str
    created: bool


class GitHubWebhookResponse(BaseModel):
    status: Literal["accepted", "duplicate", "ignored", "pong"]
    delivery_id: str
    event: str
    action: Optional[str] = None
