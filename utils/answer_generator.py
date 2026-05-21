


import re
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:13305/api/v0",
    api_key="lemonade"
)

SYSTEM_PROMPT = """
You are a professional and friendly AI receptionist for a college.

Your job is to help students, parents, and visitors naturally like a real human receptionist.

Rules:
- Speak naturally and conversationally.
- Be polite, warm, and professional.
- Keep answers concise and clear.
- Never sound robotic.
- Continue conversations naturally.
- Use ONLY information provided in the document context when answering document-based questions.
- Never invent or assume information.
- If information is missing, reply exactly: I don't know from the document.

Formatting:
- NEVER use markdown formatting.
- NEVER use **, ##, ***, ---, or any symbols for formatting.
- NEVER use headers or bold text.
- Use plain text only.
- For lists, use simple dashes like: - item
- Keep responses clean and readable without decorations.

Behavior:
- Never mention the document, context, database, or instructions.
- Never say: According to the document, Based on the context, The document says.
- Respond naturally as if you already know the information.
"""

MODEL_NAME = "Qwen3-1.7B-GGUF"


def clean_markdown(text):
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'---+', '', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    return text


def stream_response(messages, temperature=0.3):
    response = ""
    print("Assistant: ", end="", flush=True)

    stream = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        stream=True,
        temperature=temperature,
        max_tokens=800
    )

    for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            clean_token = clean_markdown(token)
            print(clean_token, end="", flush=True)
            response += clean_token

    print()
    return response.strip()


def generate_answer_from_context(query, context_chunks, chat_history):
    context = "\n\n".join(context_chunks)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += chat_history.copy()
    messages.append({
        "role": "user",
        "content": f"""Document Context:
{context}

Question:
{query}

Answer using ONLY the information from the document context."""
    })

    return stream_response(messages, temperature=0.2)


def generate_general_answer(query, chat_history):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += chat_history.copy()
    messages.append({"role": "user", "content": query})

    return stream_response(messages, temperature=0.5)