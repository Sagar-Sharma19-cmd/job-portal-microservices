from typing import Optional

from pydantic import BaseModel, Field, field_validator

class CandidateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3)
    phone: Optional[str] = None
    experience_years: int = Field(default=0, ge=0, le=50)
    skills: list[str] = Field(default_factory=list)
    resume_url: Optional[str] = None

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        if "@" not in value:
            raise ValueError("must contain @")
        return value

class CandidateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    email: Optional[str] = None
    phone: Optional[str] = None
    experience_years: Optional[int] = Field(default=None, ge=0, le=50)
    skills: Optional[list[str]] = None
    resume_url: Optional[str] = None

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        if value is not None and "@" not in value:
            raise ValueError("must contain @")
        return value
