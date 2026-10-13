"""Local embedding model wrapper.

TODO(day 2): load a small local code embedding model (for example a
sentence-transformers model), chunk input into windows, return vectors.
No network calls at check time.
"""


def embed(texts: list[str]) -> list[list[float]]:
    raise NotImplementedError("Embedder lands on Day 2")
