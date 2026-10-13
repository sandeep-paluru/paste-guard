"""Split code into overlapping line windows and normalise for embedding."""
import re

CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java", ".rb", ".rs", ".c", ".h",
            ".cpp", ".cs", ".php", ".kt", ".swift", ".scala", ".sh", ".sql"}
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build", ".tox"}


def normalise(text: str) -> str:
    # Collapse whitespace so reformatting does not change the vector much.
    return re.sub(r"\s+", " ", text).strip()


def windows(text: str, size: int = 30, step: int = 15, min_chars: int = 40):
    """Yield (start_line, end_line, chunk) windows, 1-based inclusive."""
    lines = text.splitlines()
    if not lines:
        return
    i = 0
    while True:
        part = lines[i:i + size]
        chunk = "\n".join(part)
        if len(chunk.strip()) >= min_chars:
            yield i + 1, i + len(part), chunk
        if i + size >= len(lines):
            break
        i += step
