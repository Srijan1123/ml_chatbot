from utils.router import search_all_indexes
from utils.answer_generator import generate_answer_from_context, generate_general_answer
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:13305/api/v0",
    api_key="lemonade"
)

def is_college_related(query):
    keywords = ["kcc", "kantipur", "college", "admission", "course", "fee",
            "faculty", "campus", "program", "scholarship", "eligibility",
            "semester", "bca", "bbs", "bba", "undergraduate", "facilities",
            "student", "exam", "result", "library", "hostel", "internship",
            "schedule", "sir", "teacher", "professor", "class", "timing",
            "ravi", "lecture", "timetable"]

    if any(kw in query.lower() for kw in keywords):
        return True
    try:
        response = client.chat.completions.create(
            model="Qwen3-1.7B-GGUF",
            messages=[
                {"role": "system", "content": "You are a classifier. Answer only YES or NO."},
                {"role": "user", "content": f"Is this question about a college or education institution? Question: {query}"}
            ],
            max_tokens=5,
            temperature=0
        )
        answer = response.choices[0].message.content.strip().upper()
        return "YES" in answer
    except:
        return False

def main():
    print("AI Receptionist ready! Type 'exit' to quit.\n")
    chat_history = []

    while True:
        query = input("You: ").strip()
        if query.lower() == "exit":
            break
        if not query:
            continue

        if is_college_related(query):
            retrieved_chunks, source = search_all_indexes(query)
            if retrieved_chunks:
                print(f"[Searching: {source}]")
                response = generate_answer_from_context(query, retrieved_chunks, chat_history)
                if "I don't know from the document" in response:
                    response = generate_general_answer(query, chat_history)
            else:
                response = generate_general_answer(query, chat_history)
        else:
            response = generate_general_answer(query, chat_history)
        print()

        chat_history.append({"role": "user", "content": query})
        chat_history.append({"role": "assistant", "content": response})

if __name__ == "__main__":
    main()