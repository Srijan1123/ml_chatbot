import faiss
import pickle
import os

def create_faiss_index(embeddings):
 dimensions = embeddings.shape[1]
 index = faiss.IndexFlatL2(dimensions)
 index.add(embeddings)
 return index

def save_index(index, chunks, path="vector_store"):
 os.makedirs(path, exist_ok=True)
 faiss.write_index(index, f"{path}/faiss_index")
 with open(f"{path}/chunks.pkl", "wb") as f:
  pickle.dump(chunks, f)

def load_index(path="vector_store"):
 index = faiss.read_index(f"{path}/faiss_index")
 with open(f"{path}/chunks.pkl", "rb") as f:
  chunks = pickle.load(f)
  return index, chunks