import os
import faiss
import pickle
from utils.embedder import embed_text

INDEX_DIR = "indexes"
RELEVANCE_THRESHOLD = 1.5

def search_all_indexes(query, k=3):
    query_embedding = embed_text([query])
    best_chunks = []
    best_distance = float("inf")
    best_source = None

    for name in os.listdir(INDEX_DIR):
        index_path = f"{INDEX_DIR}/{name}/faiss_index"
        chunks_path = f"{INDEX_DIR}/{name}/chunks.pkl"

        if not os.path.exists(index_path):
            continue

        index = faiss.read_index(index_path)
        with open(chunks_path, "rb") as f:
            chunks = pickle.load(f)

        distances, indices = index.search(query_embedding, k)
        top_distance = distances[0][0]

        if top_distance < best_distance:
            best_distance = top_distance
            best_chunks = [
                chunks[i] for i, d in zip(indices[0], distances[0])
                if i < len(chunks) and d < RELEVANCE_THRESHOLD
            ]
            best_source = name

    return best_chunks, best_source