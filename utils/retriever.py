from utils.vector_store import load_index
from utils.embedder import embed_text
import numpy as np

RELEVANCE_THRESHOLD = 0.8

def retrieve_top_k(query, k=3):
    index, chunks = load_index()
    query_embedding = embed_text([query])
    distances, indices = index.search(query_embedding, k)

    results = [
        chunks[i] for i, d in zip(indices[0], distances[0])
        if i < len(chunks) and d < RELEVANCE_THRESHOLD
    ]
    return results