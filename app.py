import streamlit as st
from utils.pdf_extractor import extract_text_from_pdf
from utils.chunker import chunk_text
from utils.embedder import embed_text
from utils.vector_store import create_faiss_index, save_index
from utils.retriever import retrieve_top_k
from utils.answer_generator import generate_answer

st.set_page_config(page_title="PDF Chatbot", page_icon="**")
st.title("PDF Chatbot")
st.write("Upload a PDF and ask questions about it.")

uploaded_file = st.file_uploader("Upload your PDF", type="pdf")

if uploaded_file:
 with st.spinner("Processing PDF..."):
  raw_text = extract_text_from_pdf(uploaded_file)
  chunks = chunk_text(raw_text)
  chunk_texts = [chunk.page_content for chunk in chunks]
  embeddings = embed_text(chunk_texts)
  index = create_faiss_index(embeddings)
  save_index(index, chunk_texts)
  
  st.success("PDF processed! Ask your questions below.")
  if "messages" not in st.session_state:
   st.session_state.messages = []

  for msg in st.session_state.messages:
   with st.chat_message(msg["role"]):
    st.write(msg["content"])

   query = st.chat_input("Ask a question about the PDF...")

  if query:
   st.session_state.messages.append({"role": "user", "content": query})
   with st.chat_message("user"):
    st.write(query)

  with st.chat_message("assistant"):
   with st.spinner("Thinking..."):
    retrieved_chunks = retrieve_top_k(query, k=3)
    response = generate_answer(query, retrieved_chunks)
    st.write(response)

  st.session_state.messages.append({"role": "assistant", "content": response})