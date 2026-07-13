import logging

from utils.chat_service import ChatServiceError, answer_receptionist

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

def main():
    print("AI Receptionist ready! Type 'exit' to quit.\n")
    chat_history = []

    while True:
        query = input("You: ").strip()
        if query.lower() == "exit":
            break
        if not query:
            continue

        try:
            response, meta = answer_receptionist(query, chat_history)
            print(f"[Source: {meta['source']}]")
            print(f"Assistant: {response}\n")
        except ChatServiceError as exc:
            print(f"Assistant: {exc}\n")

if __name__ == "__main__":
    main()
