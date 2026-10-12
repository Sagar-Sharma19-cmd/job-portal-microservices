from typing import Literal, Optional
from pydantic import BaseModel, Field
class ScreeningCreate(BaseModel): application_id: int = Field(gt=0); job_id: int = Field(gt=0); candidate_id: int = Field(gt=0)
class InterviewCreate(BaseModel): round: int = Field(ge=1); scheduled_at: str = Field(min_length=1)
class InterviewUpdate(BaseModel): result: Literal["PASS", "FAIL"]; feedback: Optional[str] = None
class DecisionCreate(BaseModel): decision: Literal["SHORTLISTED", "INTERVIEW", "OFFERED", "REJECTED"]; reason: Optional[str] = None
