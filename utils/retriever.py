from utils.vector_store import load_index
from utils.embedder import embed_text
import numpy as np

def retrieve_top_k(query, k=3):
 index, chunks = load_index()
 query_embedding = embed_text([query])
 distances, indices = index.search(query_embedding, k)
 results = [chunks[i] for i in indices[0] if i < len(chunks)]
 return results