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
