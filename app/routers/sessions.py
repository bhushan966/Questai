import os
import shutil
import subprocess
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas

from app.services.transcription import transcribe_audio
from app.auth import get_current_user
from supabase import create_client
import shutil as shutil_module


router = APIRouter(prefix="/sessions", tags=["sessions"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# FFMPEG_PATH = r"C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0-full_build\bin\ffmpeg.exe"
FFMPEG_PATH = shutil_module.which("ffmpeg") or r"C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0-full_build\bin\ffmpeg.exe"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
BUCKET_NAME = "interview-videos"

@router.post("/", response_model=schemas.SessionOut)
def create_session(session: schemas.SessionCreate, db: Session = Depends(get_db)):
    db_session = models.InterviewSession(
        job_role_id=session.job_role_id,
        candidate_id=session.candidate_id,
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)

    questions = (
        db.query(models.Question)
        .filter(
            models.Question.job_role_id == session.job_role_id,
            models.Question.generated_by == session.question_source,
        )
        .order_by(models.Question.order_index)
        .all()
    )
    if not questions:
        raise HTTPException(
            status_code=400,
            detail=f"No '{session.question_source}' questions found for this job role",
        )

    for q in questions:
        db.add(models.SessionAnswer(session_id=db_session.id, question_id=q.id))
    db.commit()

    return db_session

@router.get("/{session_id}", response_model=schemas.SessionOut)
def get_session(session_id: str, db: Session = Depends(get_db)):
    db_session = db.query(models.InterviewSession).filter(models.InterviewSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    return db_session


# Candidate-facing — NO auth, used by /interview/[sessionId]
@router.get("/{session_id}/answers", response_model=list[schemas.SessionAnswerOut])
def get_session_answers(session_id: str, db: Session = Depends(get_db)):
    db_session = db.query(models.InterviewSession).filter(models.InterviewSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")

    answers = (
        db.query(models.SessionAnswer)
        .join(models.Question, models.SessionAnswer.question_id == models.Question.id)
        .filter(models.SessionAnswer.session_id == session_id)
        .order_by(models.Question.order_index)
        .all()
    )

    return [
        schemas.SessionAnswerOut(
            id=a.id, question_id=a.question_id, question_text=a.question.question_text,
            think_seconds=a.question.think_seconds, answer_seconds=a.question.answer_seconds,
            status=a.status, video_url=a.video_url, transcript=a.transcript, submitted_at=a.submitted_at,
        )
        for a in answers
    ]


# Recruiter-facing — auth required, ownership-checked, used by the dashboard
@router.get("/{session_id}/answers/recruiter-view", response_model=list[schemas.SessionAnswerOut])
def get_session_answers_for_recruiter(session_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    db_session = (
        db.query(models.InterviewSession)
        .join(models.JobRole, models.InterviewSession.job_role_id == models.JobRole.id)
        .filter(models.InterviewSession.id == session_id, models.JobRole.owner_id == user_id)
        .first()
    )
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")

    answers = (
        db.query(models.SessionAnswer)
        .join(models.Question, models.SessionAnswer.question_id == models.Question.id)
        .filter(models.SessionAnswer.session_id == session_id)
        .order_by(models.Question.order_index)
        .all()
    )

    return [
        schemas.SessionAnswerOut(
            id=a.id, question_id=a.question_id, question_text=a.question.question_text,
            think_seconds=a.question.think_seconds, answer_seconds=a.question.answer_seconds,
            status=a.status, video_url=a.video_url, transcript=a.transcript, submitted_at=a.submitted_at,
        )
        for a in answers
    ]



@router.post("/{session_id}/answers/{answer_id}/upload")
def upload_answer_video(session_id: str, answer_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    db_answer = db.query(models.SessionAnswer).filter(
        models.SessionAnswer.id == answer_id,
        models.SessionAnswer.session_id == session_id,
    ).first()
    if not db_answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    filename = f"{session_id}_{answer_id}.webm"
    raw_filepath = os.path.join(UPLOAD_DIR, f"raw_{filename}")
    final_filepath = os.path.join(UPLOAD_DIR, filename)

    with open(raw_filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    result = subprocess.run(
        [FFMPEG_PATH, "-y", "-i", raw_filepath, "-c", "copy", final_filepath],
        capture_output=True,
    )

    os.remove(raw_filepath)

    if result.returncode != 0 or not os.path.exists(final_filepath):
        raise HTTPException(status_code=500, detail=f"Video processing failed: {result.stderr.decode()}")

    # Upload the ffmpeg-fixed file to Supabase Storage
    with open(final_filepath, "rb") as f:
        supabase_client.storage.from_(BUCKET_NAME).upload(
            filename,
            f,
            file_options={"content-type": "video/webm", "upsert": "true"},
        )

        public_url = supabase_client.storage.from_(BUCKET_NAME).get_public_url(filename)

    db_answer.video_url = public_url
    db_answer.status = "uploaded"
    db_answer.submitted_at = datetime.utcnow()

    try:
        db_answer.transcript = transcribe_audio(final_filepath)
    except Exception as e:
        print(f"Transcription failed for answer {answer_id}: {e}")
        db_answer.transcript = None

    # Clean up local file now that upload + transcription are both done
    os.remove(final_filepath)

    db.commit()

    return {
        "answer_id": answer_id,
        "video_url": db_answer.video_url,
        "status": "uploaded",
        "transcript": db_answer.transcript,
    }

@router.post("/{session_id}/submit")
def submit_session(session_id: str, db: Session = Depends(get_db)):
    db_session = db.query(models.InterviewSession).filter(models.InterviewSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")

    db_session.status = "submitted"
    db.commit()
    return {"session_id": session_id, "status": "submitted"}