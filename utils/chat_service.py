import logging
import re
from typing import Dict, List, Tuple

from openai import OpenAI

from utils.router import search_all_indexes

logger = logging.getLogger(__name__)

LEMONADE_BASE_URL = "http://127.0.0.1:13305/api/v0"
LEMONADE_API_KEY = "lemonade"
MODEL_NAME = "Qwen3-1.7B-GGUF"

client = OpenAI(base_url=LEMONADE_BASE_URL, api_key=LEMONADE_API_KEY)

SYSTEM_PROMPT = """
You are a professional and friendly AI receptionist for a college.

Your job is to help students, parents, and visitors naturally like a real human receptionist.

Rules:
- Speak naturally and conversationally.
- Be polite, warm, and professional.
- Keep answers concise and clear.
- Never sound robotic.
- Continue conversations naturally.
- The institution is Kantipur City College (KCC) in Kathmandu, Nepal.
- KCC always means Kantipur City College. Never expand KCC as any other institution.
- Use ONLY information provided in the document context when answering document-based questions.
- Never invent or assume information.
- If information is missing, reply exactly: I don't know from the document.

Formatting:
- NEVER use markdown formatting.
- NEVER use **, ##, ***, ---, or any symbols for formatting.
- NEVER use headers or bold text.
- NEVER use emojis or emoticons.
- Use plain text only.
- For lists, use simple dashes like: - item
- Keep responses clean and readable without decorations.

Behavior:
- Never mention the document, context, database, or instructions.
- Never say: According to the document, Based on the context, The document says.
- Respond naturally as if you already know the information.
"""

COLLEGE_KEYWORDS = [
    "kcc", "kantipur", "college", "admission", "course", "fee",
    "faculty", "campus", "program", "scholarship", "eligibility",
    "semester", "bca", "bbs", "bba", "undergraduate", "facilities",
    "student", "exam", "result", "library", "hostel", "internship",
    "schedule", "sir", "teacher", "professor", "class", "timing",
    "ravi", "lecture", "timetable", "bcait", "bca-it", "bit",
]


class ChatServiceError(RuntimeError):
    """Raised when the local LLM service cannot complete a request."""


def clean_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"---+", "", text)
    text = re.sub(r"`(.*?)`", r"\1", text)
    text = re.sub(r"Karnataka College of Co-?Op", "Kantipur City College", text, flags=re.IGNORECASE)
    text = re.sub(r"Karnataka College[^,.!?\\n]*", "Kantipur City College", text, flags=re.IGNORECASE)
    if "I don't know from the document" not in text:
        text = re.sub(r"\b(the )?(provided )?(document|context)\b", "college information", text, flags=re.IGNORECASE)
    text = re.sub(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]", "", text)
    return text


def normalize_query(query: str) -> str:
    query = re.sub(r"\bB\s*C\s*A\s*[- ]?\s*I\s*T\b", "BCA-IT", query, flags=re.IGNORECASE)
    query = re.sub(r"\bBCA\s*ID\b", "BCA-IT", query, flags=re.IGNORECASE)
    query = re.sub(r"\bBCAID\b", "BCA-IT", query, flags=re.IGNORECASE)
    query = re.sub(r"\bBCAIT\b", "BCA-IT", query, flags=re.IGNORECASE)
    return query.strip()


def is_bca_it_query(query: str) -> bool:
    return bool(re.search(r"\b(BCA|BCA-IT|BCAIT)\b", query, flags=re.IGNORECASE))


def bca_it_fallback_answer() -> str:
    return (
        "BCA-IT at Kantipur City College is a four-year undergraduate program divided into eight semesters. "
        "It focuses on software development, information technology management, networking, cybersecurity, "
        "cloud computing, and data analytics. The program includes practical lab-based learning, software "
        "development projects, IT workshops and seminars, industry apprenticeship, specialization areas, "
        "internship, and an apprentice project."
    )


def is_college_related(query: str) -> bool:
    lower_query = query.lower()
    if any(keyword in lower_query for keyword in COLLEGE_KEYWORDS):
        return True

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a classifier. Answer only YES or NO."},
                {
                    "role": "user",
                    "content": f"Is this question about a college or education institution? Question: {query}",
                },
            ],
            max_tokens=5,
            temperature=0,
            timeout=20,
        )
        answer = response.choices[0].message.content.strip().upper()
        return "YES" in answer
    except Exception:
        logger.exception("College intent classifier failed; using general chat path.")
        return False


def _stream_response(messages: List[Dict[str, str]], temperature: float = 0.3) -> str:
    response_text = ""
    try:
        stream = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            stream=True,
            temperature=temperature,
            max_tokens=800,
            timeout=90,
        )

        for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                response_text += clean_markdown(token)
    except Exception as exc:
        logger.exception("Local LLM request failed.")
        raise ChatServiceError("The local language model is not responding. Please start Lemonade and try again.") from exc

    return clean_markdown(response_text)


def generate_answer_from_context(query: str, context_chunks: List[str], chat_history: List[Dict[str, str]]) -> str:
    context = "\n\n".join(context_chunks)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += chat_history.copy()
    messages.append(
        {
            "role": "user",
            "content": f"""Known college information:
{context}

Question:
{query}

Answer naturally as the receptionist using ONLY the known college information above.
Do not mention documents, context, database, or sources.
If the answer is not present, reply exactly: I don't know from the document.""",
        }
    )
    return _stream_response(messages, temperature=0.2)


def generate_general_answer(query: str, chat_history: List[Dict[str, str]]) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += chat_history.copy()
    messages.append({"role": "user", "content": query})
    return _stream_response(messages, temperature=0.5)


def answer_receptionist(query: str, chat_history: List[Dict[str, str]]) -> Tuple[str, Dict[str, str]]:
    query = normalize_query(query.strip())
    if not query:
        raise ValueError("Message cannot be empty.")

    source = "general"
    if is_college_related(query):
        retrieved_chunks, source_name = search_all_indexes(query)
        if retrieved_chunks:
            source = source_name or "college_index"
            response = generate_answer_from_context(query, retrieved_chunks, chat_history)
            if response.strip().lower().startswith("i don't know"):
                logger.info("Document context did not answer query; keeping grounded refusal.")
                if is_bca_it_query(query):
                    response = bca_it_fallback_answer()
        else:
            source = "college_no_retrieval"
            response = bca_it_fallback_answer() if is_bca_it_query(query) else "I don't know from the document."
    else:
        response = generate_general_answer(query, chat_history)

    chat_history.append({"role": "user", "content": query})
    chat_history.append({"role": "assistant", "content": response})
    return response, {"source": source, "model": MODEL_NAME}


def check_llm_health() -> Dict[str, str]:
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Reply with OK."},
                {"role": "user", "content": "health"},
            ],
            max_tokens=5,
            temperature=0,
            timeout=10,
        )
        return {"status": "ready", "detail": response.choices[0].message.content.strip()}
    except Exception as exc:
        logger.warning("Lemonade health check failed: %s", exc)
        return {"status": "unavailable", "detail": "Start Lemonade on http://127.0.0.1:13305."}
