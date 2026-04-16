from sentence_transformers import SentenceTransformer
import numpy as np
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def embed_text(texts):
 embeddings = model.encode(texts, show_progress_bar=False)
 return np.array(embeddings, dtype="float32")