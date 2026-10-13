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


DOC_EXT = {".md", ".txt", ".pdf", ".docx"}


def doc_chunks(text: str, target: int = 160, max_words: int = 200, min_words: int = 120, overlap: int = 30):
    """Paragraph-aware chunks of about 120-200 words with ~30 words overlap.

    Yields (start_para, end_para, chunk). Paragraphs are packed until the
    target is reached; oversized paragraphs are split on word boundaries.
    """
    paras = [re.sub(r"[ \t]+", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    paras = [p for p in paras if p]
    units = []  # (para_index, words)
    for i, p in enumerate(paras):
        w = p.split()
        while len(w) > max_words:
            units.append((i, w[:target]))
            w = w[target - overlap:]
        units.append((i, w))
    buf, start, last = [], None, None
    for i, w in units:
        if buf and len(buf) + len(w) > max_words and len(buf) >= min_words // 2:
            yield start + 1, last + 1, " ".join(buf)
            tail = buf[-overlap:]
            buf, start = list(tail), last
        if start is None:
            start = i
        buf.extend(w)
        last = i
        if len(buf) >= target:
            yield start + 1, last + 1, " ".join(buf)
            buf, start = buf[-overlap:], i
    if buf and (len(buf) > overlap or start == 0):
        yield (start or 0) + 1, (last or 0) + 1, " ".join(buf)


def extract_text(path_or_bytes, suffix: str) -> str:
    """Extract plain text from .md/.txt/.pdf/.docx (path or raw bytes)."""
    import io
    suffix = suffix.lower()
    if isinstance(path_or_bytes, (bytes, bytearray)):
        data = bytes(path_or_bytes)
    else:
        with open(path_or_bytes, "rb") as f:
            data = f.read()
    if suffix == ".pdf":
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(data))
        return "\n\n".join((pg.extract_text() or "") for pg in r.pages)
    if suffix == ".docx":
        import docx
        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n\n".join(parts)
    return data.decode("utf-8", errors="ignore")


def doc_passages(text: str):
    """Two granularities for documents: ~120-200 word chunks (context) plus
    ~60 word passages (so a short excerpt or a one-paragraph summary still has
    a close neighbour). Yields (start_para, end_para, chunk)."""
    yield from doc_chunks(text)
    yield from doc_chunks(text, target=60, max_words=80, min_words=40, overlap=20)
