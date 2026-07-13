import os

import numpy as np
from sentence_transformers import SentenceTransformer

os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("./models/embedding_model")
    return _model


def embed_text(texts):
    embeddings = _get_model().encode(texts, show_progress_bar=False)
    return np.array(embeddings, dtype="float32")
