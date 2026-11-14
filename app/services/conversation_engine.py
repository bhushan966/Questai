import os
import re
import json
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MAX_ANSWERS = int(os.getenv("INTERVIEW_MAX_ANSWERS", "10"))

# Guardrail regex to catch code-writing prompts if the LLM slips
_CODING_PROMPT_RE = re.compile(
    r"\b("
    r"(write|type|code|implement|dictate|draft|compose|give\s+me)\s+"
    r"(a|an|the|some|me|out)?\s*"
    r"(python|java|javascript|typescript|sql|c\+\+|c#|go|rust|ruby|php|bash|"
    r"code|function|script|query|program|snippet|class|regex|pseudocode|algorithm)"
    r"|write\s+code"
    r"|live\s+coding"
    r"|leetcode"
    r")\b",
    re.IGNORECASE,
)


def _contains_coding_request(text: str) -> bool:
    return bool(_CODING_PROMPT_RE.search(text or ""))


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

    system_prompt = """You are a friendly, professional technical interviewer conducting a SPOKEN-ONLY live voice/video interview.

MEDIUM CONSTRAINTS (STRICT):
- The candidate is speaking into a microphone and camera. They have NO keyboard, NO code editor, NO IDE, NO screen share, and NO whiteboard.
- Your words will be spoken aloud via text-to-speech: use short, natural, conversational sentences. No bullet lists, no markdown, no code blocks.

CRITICAL ANTI-CODING RULES (NEVER VIOLATE):
1. NEVER ask the candidate to write, type, implement, dictate, or recite code, functions, scripts, classes, SQL queries, regex, or syntax in Python or ANY other programming language.
2. NEVER ask LeetCode/algorithm coding puzzles (e.g., "write a Python function to reverse a list" or "code this out").
3. If any topic in the topic list sounds like a coding task, DO NOT ask them to write code—automatically convert it into a spoken architectural, debugging, or trade-off question instead.
4. Assess engineering skill strictly through spoken discussion:
   - System & API design, data flow, and architecture decisions
   - Debugging real production issues and bottlenecks
   - Trade-offs (e.g., memory vs. speed, SQL vs. NoSQL, sync vs. async)
   - Testing, reliability, error handling, and real project ownership

EXAMPLES:
- BAD (Forbidden): "Can you write a Python function to deduplicate a large list of records?"
- GOOD (Spoken): "If you had to deduplicate millions of incoming records in a Python service without running out of memory, how would you design that approach?"

CONVERSATION RULES:
- If the interview is just starting, greet the candidate warmly in one short sentence and ask your first question. Don't begin with "Sure" or "Okay".
- Otherwise, start with a brief, genuine reaction (a few words) referring to something specific they said, then ask your next question. If they struggled or didn't know, be kind and either simplify or move to the next topic.
- Ask at most ONE follow-up on any single topic. If you already followed up on the current topic, move to a new one.
- Ask only ONE question at a time. Keep your whole reply under 40 words.
- When all topics are covered, or the candidate reaches the answer cap, thank them warmly and conclude.
- You do NOT need to cover every topic in the list: prioritize the strongest 5-7 distinct topics matching the role and pace naturally so you wrap up smoothly by about the answer cap without getting cut off.
- When you have covered enough signal, or the candidate reaches the answer cap, thank them warmly and conclude.

Return ONLY a JSON object:
{"message": "what you will say", "action": "follow_up" | "next_topic" | "conclude"}"""

    user_prompt = f"""Role: {job_title}
Description: {job_description}
Skills required: {skills}

Topics you'd like to cover, in any sensible order (reframe any coding-sounding topic into a spoken design/debugging question):
{chr(10).join('- ' + t for t in topics)}

Conversation so far:
{history_text if history_text else "(the interview is just starting)"}

Progress: The candidate has given {answers_so_far} answers so far. Plan to wrap up by about {max_answers} answers."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        temperature=0.65,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)

    if not isinstance(result, dict) or not str(result.get("message", "")).strip():
        raise ValueError("Model returned JSON without a usable 'message'")

    if result.get("action") not in ("follow_up", "next_topic", "conclude"):
        result["action"] = "follow_up"

    # Guardrail retry: if the LLM still slipped and asked the candidate to write code, force a spoken rephrase
    if result["action"] != "conclude" and _contains_coding_request(result["message"]):
        retry_messages = messages + [
            {"role": "assistant", "content": json.dumps(result)},
            {
                "role": "user",
                "content": (
                    "Your last message asked the candidate to write or implement code/syntax. "
                    "Remember this is a spoken-only voice interview with NO keyboard or editor. "
                    "Rewrite it into a short spoken question (under 40 words) about system design, debugging, or trade-offs instead. "
                    "Return ONLY the JSON object."
                ),
            },
        ]
        retry_resp = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=retry_messages,
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        retry_result = json.loads(retry_resp.choices[0].message.content)
        if isinstance(retry_result, dict) and str(retry_result.get("message", "")).strip():
            result = retry_result
            if result.get("action") not in ("follow_up", "next_topic", "conclude"):
                result["action"] = "follow_up"

    # Hard stop: never let an interview run past the cap, whatever the model says
    if answers_so_far >= max_answers and result["action"] != "conclude":
        result = {
            "message": "Thank you, that covers everything I wanted to ask. We'll be in touch soon.",
            "action": "conclude",
        }

    return result


def generate_verdict(job_title: str, skills: str, conversation_history: list[dict]) -> str:
    history_text = "\n".join(
        f"{'Interviewer' if t['role'] == 'ai' else 'Candidate'}: {t['content']}"
        for t in conversation_history
    )

    prompt = f"""You just conducted a spoken voice interview (conceptual/architectural, not a live coding test) for a {job_title} role (key skills: {skills}).

Full conversation:
{history_text}

Write a concise recruiter-facing summary covering:
1. Overall communication clarity
2. Relevant technical & problem-solving strengths shown
3. Any gaps or concerns
4. A recommendation: Strong fit / Worth a follow-up / Not a fit

Keep it to a short paragraph, direct and professional."""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()