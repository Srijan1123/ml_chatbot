from sentence_transformers import SentenceTransformer
import numpy as np
import os

os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

model = SentenceTransformer("./models/embedding_model")

def embed_text(texts):
    embeddings = model.encode(texts, show_progress_bar=False)
    return np.array(embeddings, dtype="float32")