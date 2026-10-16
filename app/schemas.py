from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional


class JobRoleCreate(BaseModel):
    title: str
    description: str
    skills_required: Optional[str] = None


class JobRoleOut(JobRoleCreate):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class SessionCreate(BaseModel):
    job_role_id: UUID
    candidate_id: UUID
    question_source: str = "ai"
    mode: str = "recorded"


class TurnSubmit(BaseModel):
    transcript: str
class SessionOut(BaseModel):
    id: UUID
    job_role_id: UUID
    candidate_id: UUID
    status: str
    mode: Optional[str] = "recorded"
    created_at: datetime

    class Config:
        from_attributes = True

class SessionAnswerOut(BaseModel):
    id: UUID
    question_id: UUID
    question_text: str
    think_seconds: int
    answer_seconds: int
    status: str
    video_url: Optional[str] = None
    transcript: Optional[str] = None
    submitted_at: Optional[datetime] = None

    class Config:
        from_attributes = True
class SessionSummaryOut(BaseModel):
    id: UUID
    candidate_id: UUID
    status: str
    mode: Optional[str] = "recorded"
    created_at: datetime

    class Config:
        from_attributes = True

class QuestionCreate(BaseModel):
    question_text: str
    answer_seconds: int = 90


class QuestionOut(BaseModel):
    id: UUID
    question_text: str
    order_index: int
    generated_by: str
    think_seconds: int
    answer_seconds: int

    class Config:
        from_attributes = True