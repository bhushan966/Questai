import os
import re
import json
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

_CODING_PROMPT_RE = re.compile(
    r"\b("
    r"(write|type|code|implement|dictate|draft|compose)\s+"
    r"(a|an|the|some|me|out)?\s*"
    r"(python|java|javascript|typescript|sql|c\+\+|c#|go|rust|ruby|php|bash|"
    r"code|function|script|query|program|snippet|class|regex|pseudocode|algorithm)"
    r"|write\s+code"
    r"|live\s+coding"
    r"|leetcode"
    r")\b",
    re.IGNORECASE,
)


def _normalize_questions(parsed) -> list[dict]:
    items = parsed.get("questions", []) if isinstance(parsed, dict) else parsed
    if not isinstance(items, list):
        return []
    cleaned = []
    for item in items:
        if isinstance(item, dict) and str(item.get("question", "")).strip():
            cleaned.append(
                {
                    "question": str(item["question"]).strip(),
                    "think_seconds": int(item.get("think_seconds") or 30),
                    "answer_seconds": int(item.get("answer_seconds") or 120),
                }
            )
    return cleaned


def generate_questions(
    title: str,
    description: str,
    skills_required: str,
    num_questions: int = 10,
) -> list[dict]:
    system_prompt = """You are an expert technical interviewer designing questions for an asynchronous SPOKEN VIDEO interview platform.

MEDIUM CONSTRAINTS (STRICT):
- Candidates answer on webcam (spoken audio/video for 60-180 seconds). They have NO code editor, NO IDE, NO keyboard input, and NO whiteboard.

CRITICAL ANTI-CODING RULES (NEVER VIOLATE):
1. NEVER ask candidates to write, type, implement, or dictate code, functions, scripts, SQL queries, regex, or syntax in Python or ANY programming language.
2. NEVER generate LeetCode puzzles or "write a function to..." tasks.
3. Instead, test depth through spoken questions across a balanced, non-overlapping spread:
   - Role motivation & past project walkthroughs (1-2 questions)
   - Core technical architecture, system design, & data flow (3-4 questions)
   - Debugging, production incidents, performance & edge cases (2-3 questions)
   - Testing, reliability, trade-offs, & behavioral/team collaboration (2 questions)

EXAMPLES:
- BAD (Forbidden): "Write a Python function to parse and aggregate a 5GB log file."
- GOOD (Spoken): "If you needed to process and aggregate a 5GB log file in Python without exhausting memory, how would you architect that pipeline and handle failures?"

OUTPUT FORMAT:
Return ONLY a JSON object with a "questions" array:
{
  "questions": [
    {"question": "...", "think_seconds": 30, "answer_seconds": 90},
    {"question": "...", "think_seconds": 60, "answer_seconds": 150}
  ]
}"""

    user_prompt = f"""Generate exactly {num_questions} distinct, non-overlapping spoken video interview questions for this role:

Job title: {title}
Job description: {description}
Skills required: {skills_required}

For each question, estimate a fair think_seconds (20-60) and answer_seconds (60-180) based on complexity."""

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

    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    questions = _normalize_questions(json.loads(raw))

    # Guardrail retry if any generated question slipped into asking the candidate to write code
    flagged = [q["question"] for q in questions if _CODING_PROMPT_RE.search(q["question"])]
    if flagged:
        retry_messages = messages + [
            {"role": "assistant", "content": json.dumps({"questions": questions})},
            {
                "role": "user",
                "content": (
                    f"These generated questions asked the candidate to write code/syntax: {flagged}. "
                    "Replace ONLY those questions with spoken conceptual, debugging, or architecture questions "
                    "that require zero code writing. Return the full JSON object with all questions."
                ),
            },
        ]
        retry_resp = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=retry_messages,
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        retry_raw = retry_resp.choices[0].message.content.strip().replace("```json", "").replace("```", "").strip()
        retried = _normalize_questions(json.loads(retry_raw))
        if retried:
            questions = retried

    return questions