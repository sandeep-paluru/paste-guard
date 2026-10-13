"""Local embedding model wrapper (real model, CPU, ONNX via fastembed).

Default model: sentence-transformers/all-MiniLM-L6-v2 (384 dims, about 90 MB).
Set [model] name in paste-guard.toml (or a profile), or override with PG_MODEL. The model is downloaded once to PG_MODEL_CACHE and
then runs fully offline; no paste text ever leaves the machine.
"""
import os
from functools import lru_cache

import numpy as np

from config import CONFIG

MODEL_NAME = CONFIG["model"]["name"]
CACHE_DIR = os.environ.get("PG_MODEL_CACHE", os.path.expanduser("~/.cache/paste-guard/models"))


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=MODEL_NAME, cache_dir=CACHE_DIR, threads=int(os.environ.get("PG_THREADS", "2")))


def dim() -> int:
    return len(embed(["x"])[0])


def embed(texts: list[str]) -> np.ndarray:
    """Return L2-normalised float32 vectors, one row per text."""
    vecs = np.array(list(_model().embed(texts, batch_size=16)), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms
