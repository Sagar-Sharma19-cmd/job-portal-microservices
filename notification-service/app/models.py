from typing import Literal

from pydantic import BaseModel, Field


NotificationType = Literal[
    "APPLICATION_SUBMITTED",
    "APPLICATION_CANCELLED",
    "STATUS_CHANGED",
    "INTERVIEW_SCHEDULED",
]


class NotificationCreate(BaseModel):
    recipient_id: int
    type: NotificationType
    message: str = Field(min_length=1, max_length=500)


class NotificationResponse(BaseModel):
    id: int
    recipient_id: int
    type: NotificationType
    message: str
    created_at: str