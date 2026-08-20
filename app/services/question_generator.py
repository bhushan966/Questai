import os
import json
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def generate_questions(title: str, description: str, skills_required: str, num_questions: int = 5) -> list[str]:
    prompt = f"""You are an expert technical interviewer. Based on the job role below, generate {num_questions} interview questions.

    Job title: {title}
    Job description: {description}
    Skills required: {skills_required}

    Rules:
    - Mix of technical and role-relevant behavioral questions
    - For each question, estimate a fair thinking time and answer time in seconds, based on question complexity
    - Return ONLY a JSON array of objects, no preamble, no markdown

    Example output format:
    [
    {{"question": "Tell me about yourself.", "think_seconds": 30, "answer_seconds": 90}},
    {{"question": "Design a scalable RAG pipeline for X.", "think_seconds": 60, "answer_seconds": 180}}
    ]"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    raw = response.choices[0].message.content.strip()
    # strip accidental markdown fences if the model adds them anyway
    raw = raw.replace("```json", "").replace("```", "").strip()

    return json.loads(raw)