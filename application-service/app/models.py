from typing import Literal, Optional

from pydantic import BaseModel, Field


class ApplicationCreate(BaseModel):
    candidate_id: int = Field(gt=0)
    job_id: int = Field(gt=0)


class ApplicationStatusUpdate(BaseModel):
    status: Literal[
        "SHORTLISTED",
        "INTERVIEW",
        "OFFERED",
        "REJECTED",
    ]
    reason: Optional[str] = None


class ApplicationResponse(BaseModel):
    id: int
    candidate_id: int
    job_id: int
    status: str
    saga_id: Optional[str]
    created_at: str
    updated_at: str


class SagaStepResponse(BaseModel):
    step: str
    status: str
    at: str
    error: Optional[str]


class SagaResponse(BaseModel):
    saga_id: str
    application_id: int
    status: str
    steps: list[SagaStepResponse]