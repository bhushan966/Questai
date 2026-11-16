import os
import json
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MAX_ANSWERS = int(os.getenv("INTERVIEW_MAX_ANSWERS", "10"))


def get_next_ai_turn(
    job_title: str,
    job_description: str,
    skills: str,
    topics: list[str],
    conversation_history: list[dict],
    max_answers: int = MAX_ANSWERS,
) -> dict:
    answers_so_far = sum(1 for t in conversation_history if t["role"] == "candidate")

    history_text = "\n".join(
        f"{'Interviewer' if t['role'] == 'ai' else 'Candidate'}: {t['content']}"
        for t in conversation_history
    )

    last_candidate_turn = next(
        (t["content"] for t in reversed(conversation_history) if t["role"] == "candidate"),
        "",
    )
    last_turn_silent = (
        not str(last_candidate_turn).strip()
        or "no verbal response detected" in str(last_candidate_turn).lower()
        or "no speech detected" in str(last_candidate_turn).lower()
    )

    silence_note = (
        "\nIMPORTANT: On the most recent turn, no spoken response was heard from the candidate. "
        "Politely say in one brief, natural sentence that you didn't catch their response "
        "(e.g. audio may have dropped or they'd like to pass), then smoothly move on to a NEW topic with action='next_topic'. "
        "Do NOT pretend they answered or praise an answer they didn't give."
        if last_turn_silent and answers_so_far > 0
        else ""
    )

    prompt = f"""You are a friendly, professional interviewer running a live voice interview. Your words will be spoken aloud, so write the way people talk: short, natural sentences, no lists, no markdown.

Role: {job_title}
Description: {job_description}
Skills required: {skills}

Topics you'd like to cover, in any sensible order:
{chr(10).join('- ' + t for t in topics)}

Conversation so far:
{history_text if history_text else "(the interview is just starting)"}

The candidate has completed {answers_so_far} turns so far. Plan to wrap up by about {max_answers} turns.{silence_note}

Rules:
- If the interview is just starting, greet the candidate warmly in one short sentence and ask your first question. Don't begin with "Sure" or "Okay".
- If the candidate gave a spoken response, start with a brief, genuine reaction (a few words) referencing something specific they just said, then ask your next question. If they struggled or said they didn't know, be kind and either simplify or move on.
- If no verbal response was detected, kindly mention you didn't hear them and move to a fresh topic rather than repeating the exact same question.
- Ask conceptual, architectural, debugging, or practical experience questions only—never ask the candidate to write code or solve whiteboard puzzles aloud.
- Ask at most ONE follow-up on any single topic. If you already followed up on the current topic, move to a new one.
- Ask one question at a time. Keep your whole reply under 45 words.
- When the topics are covered, or the candidate has reached {max_answers} turns, thank them warmly and conclude.

Return ONLY a JSON object:
{{"message": "what you will say", "action": "follow_up" | "next_topic" | "conclude"}}"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)

    if not isinstance(result, dict) or not str(result.get("message", "")).strip():
        raise ValueError("Model returned JSON without a usable 'message'")

    if result.get("action") not in ("follow_up", "next_topic", "conclude"):
        result["action"] = "follow_up"

    # Hard stop: never let an interview run past the cap, whatever the model says
    if answers_so_far >= max_answers and result["action"] != "conclude":
        result = {
            "message": "Thank you, that covers everything I wanted to ask today. Our team will be in touch soon.",
            "action": "conclude",
        }

    return result


def generate_verdict(job_title: str, skills: str, conversation_history: list[dict]) -> str:
    history_text = "\n".join(
        f"{'Interviewer' if t['role'] == 'ai' else 'Candidate'}: {t['content']}"
        for t in conversation_history
    )

    prompt = f"""You just conducted a voice interview for a {job_title} role (key skills: {skills}).

Full conversation:
{history_text}

Write a concise recruiter-facing summary covering:
1. Overall communication clarity
2. Relevant strengths shown
3. Any gaps, concerns, or silent/unanswered questions (note accurately if the candidate did not respond on any turns—do not fabricate answers)
4. A recommendation: Strong fit / Worth a follow-up / Not a fit

Keep it to a short paragraph, direct and professional."""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()