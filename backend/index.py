"""In-process vector index over the company's code.

Plan: sqlite-vec (FAISS as fallback).
TODO(day 2): build_index(repo_path) to chunk and embed files;
query(vectors, k) to return nearest chunks with similarity and file path.
"""


def build_index(repo_path: str) -> None:
    raise NotImplementedError("Index lands on Day 2")


def query(vectors, k: int = 5) -> list[dict]:
    return []  # stub: no semantic matches yet
