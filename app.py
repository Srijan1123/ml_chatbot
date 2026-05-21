'''from utils.pdf_extractor import extract_text_from_pdf
from utils.chunker import chunk_text
from utils.embedder import embed_text
from utils.vector_store import create_faiss_index, save_index
from utils.retriever import retrieve_top_k
from utils.answer_generator import generate_answer_from_context, generate_general_answer

def main():
    pdf_path = input("Enter PDF file path: ").strip()

    print("Processing PDF...")
    with open(pdf_path, "rb") as f:
        raw_text = extract_text_from_pdf(f)

    chunks = chunk_text(raw_text)
    chunk_texts = [chunk.page_content for chunk in chunks]
    embeddings = embed_text(chunk_texts)
    index = create_faiss_index(embeddings)
    save_index(index, chunk_texts)
    print("PDF processed! Ask your questions below. Type 'exit' to quit.\n")

    while True:
        query = input("You: ").strip()
        if query.lower() == "exit":
            break
        if not query:
            continue

        retrieved_chunks = retrieve_top_k(query, k=3)
        if retrieved_chunks:
            generate_answer_from_context(query, retrieved_chunks)
        else:
            generate_general_answer(query)
        print()

if __name__ == "__main__":
    main()'''
    
    
'''from utils.pdf_extractor import extract_text_from_pdf
from utils.chunker import chunk_text
from utils.embedder import embed_text
from utils.vector_store import create_faiss_index, save_index
from utils.retriever import retrieve_top_k
from utils.answer_generator import generate_answer_from_context, generate_general_answer

def main():
    pdf_path = input("Enter file path (PDF or TXT): ").strip()

    print("Processing file...")
    if pdf_path.endswith(".txt"):
        with open(pdf_path, "r", encoding="utf-8") as f:
            raw_text = f.read()
    else:
        with open(pdf_path, "rb") as f:
            raw_text = extract_text_from_pdf(f)

    chunks = chunk_text(raw_text)
    chunk_texts = [chunk.page_content for chunk in chunks]
    embeddings = embed_text(chunk_texts)
    index = create_faiss_index(embeddings)
    save_index(index, chunk_texts)
    print("File processed! Ask your questions below. Type 'exit' to quit.\n")

    chat_history = []

    while True:
        query = input("You: ").strip()
        if query.lower() == "exit":
            break
        if not query:
            continue

        retrieved_chunks = retrieve_top_k(query, k=3)
        if retrieved_chunks:
            response = generate_answer_from_context(query, retrieved_chunks, chat_history)
            if "I don't know from the document" in response:
                print("\nFalling back to general knowledge...\n")
                response = generate_general_answer(query, chat_history)
        else:
            response = generate_general_answer(query, chat_history)
        print()

        chat_history.append({"role": "user", "content": query})
        chat_history.append({"role": "assistant", "content": response})

if __name__ == "__main__":
    main()'''
    
'''from utils.router import search_all_indexes
from utils.answer_generator import generate_answer_from_context, generate_general_answer

def main():
    print("AI Receptionist ready! Type 'exit' to quit.\n")
    chat_history = []

    while True:
        query = input("You: ").strip()
        if query.lower() == "exit":
            break
        if not query:
            continue

        retrieved_chunks, source = search_all_indexes(query)

        if retrieved_chunks:
            print(f"[Searching: {source}]")
            response = generate_answer_from_context(query, retrieved_chunks, chat_history)
            if "I don't know from the document" in response:
                response = generate_general_answer(query, chat_history)
        else:
            response = generate_general_answer(query, chat_history)
        print()

        chat_history.append({"role": "user", "content": query})
        chat_history.append({"role": "assistant", "content": response})

if __name__ == "__main__":
    main()'''
    
    
'''from utils.router import search_all_indexes
from utils.answer_generator import generate_answer_from_context, generate_general_answer
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:13305/api/v0",
    api_key="lemonade"
)

def is_college_related(query):
    response = client.chat.completions.create(
        model="Qwen3-1.7B-GGUF",
        messages=[
            {
                "role": "system",
                "content": "You are a classifier. Answer only YES or NO. Nothing else."
            },
            {
                "role": "user",
                "content": f"""Is this question about a college, university, institution, KCC, Kantipur City College, admission, courses, fees, faculty, campus, programs, scholarships, eligibility, or anything related to education at an institution?

Question: {query}

Answer YES or NO only."""
            }
        ],
        max_tokens=5,
        temperature=0
    )
    answer = response.choices[0].message.content.strip().upper()
    return "YES" in answer

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
    main()'''
    
    
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