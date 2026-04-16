from transformers import pipeline

generator = pipeline(
    "text-generation",
    model="google/flan-t5-base"
)

def generate_answer(query, context_chunks):
 context = "\n\n".join(context_chunks)

 prompt = f"""
Answer the question based only on the context below.

Context:
{context}

Question:
{query}

Answer:
"""

 result = generator(
        prompt,
        max_new_tokens=200,
        do_sample=False
    )

 return result[0]["generated_text"]
   