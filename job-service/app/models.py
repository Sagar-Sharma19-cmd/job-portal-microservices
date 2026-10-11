from typing import Optional

from pydantic import BaseModel, Field


class EmployerCreate(BaseModel):
    name: str
    location: str


class EmployerResponse(BaseModel):
    id: int
    name: str
    location: str
    created_at: str


class JobCreate(BaseModel):
    employer_id: int
    title: str
    location: str
    salary_min: int = Field(ge=0)
    salary_max: int = Field(ge=0)
    currency: str = "INR"
    skills: list[str]
    max_applications: int = Field(ge=1)
    deadline: Optional[str] = None


class JobPatch(BaseModel):
    title: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[int] = Field(
        default=None,
        ge=0,
    )
    salary_max: Optional[int] = Field(
        default=None,
        ge=0,
    )
    max_applications: Optional[int] = Field(
        default=None,
        ge=1,
    )
    deadline: Optional[str] = None
    status: Optional[str] = None


class ReservationCreate(BaseModel):
    application_id: int


class ReservationResponse(BaseModel):
    job_id: int
    application_id: int
    status: str
    slots_remaining: int