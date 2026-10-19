"""PDF uploads should score like the same text pasted.

pypdf's plain extractor keeps one newline per visual line and drops the gap
between paragraphs. A code block in a longer file then gets mixed into the
surrounding prose and can fall under the coach line. These tests build a
one-page "Signing Module Review" the same way the demo PDFs are built.
"""
import re
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402
from chunking import extract_text  # noqa: E402

client = TestClient(app.app)
DOCS = Path(__file__).resolve().parents[1] / "demo" / "company-docs"

CODE = """\
def accept_signed(self, blob, mac):
    mac_bytes = self._from_b64(mac)
    if not mac_bytes:
        return False
    blob = self._coerce(blob)
    for secret in reversed(list(self._ring)):
        if self._impl.equal(self._kdf(secret), blob, mac_bytes):
            return True
    return False"""


def _pdf(lines) -> bytes:
    """One page, Helvetica, one text object per line. lines are (x, y, size, text)."""
    ops = ["BT"]
    for x, y, size, text in lines:
        esc = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        ops.append(f"/F1 {size:.2f} Tf")
        ops.append(f"1 0 0 1 {x:.2f} {y:.2f} Tm ({esc}) Tj")
    ops.append("ET")
    stream = "\n".join(ops).encode()
    font = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    contents = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    page = (b"<< /Type /Page /Parent 4 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 1 0 R >> >> /Contents 2 0 R >>")
    pages = b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>"
    catalog = b"<< /Type /Catalog /Pages 4 0 R >>"
    objs = [font, contents, page, pages, catalog]
    chunks = [b"%PDF-1.4\n"]
    offsets, pos = [], len(chunks[0])
    for i, data in enumerate(objs, 1):
        offsets.append(pos)
        chunk = f"{i} 0 obj\n".encode() + data + b"\nendobj\n"
        chunks.append(chunk)
        pos += len(chunk)
    xref = [f"xref\n0 {len(objs) + 1}\n", "0000000000 65535 f \n"]
    xref += [f"{off:010d} 00000 n \n" for off in offsets]
    trailer = f"trailer << /Size {len(objs) + 1} /Root 5 0 R >>\nstartxref\n{pos}\n%%EOF\n"
    return b"".join(chunks) + "".join(xref).encode() + trailer.encode()


def _review():
    """The pasted text, and a PDF of the same lines with a real gap around the code."""
    note = "Quarterly notes from facilities about the kitchen schedule and the Friday fridge clear out. "
    before = textwrap.wrap((note * 12).strip(), 90)
    after = textwrap.wrap((note * 8).strip(), 90)
    code = CODE.splitlines()
    items, y = [], 740
    items.append((72, y, 16, "Signing Module Review"))
    y -= 28
    for ln in before:
        items.append((72, y, 11, ln))
        y -= 14
    y -= 18
    for ln in code:
        items.append((72, y, 10, ln))
        y -= 13
    y -= 18
    for ln in after:
        items.append((72, y, 11, ln))
        y -= 14
    pasted = "\n\n".join([
        "Signing Module Review",
        "\n".join(before),
        "\n".join(code),
        "\n".join(after),
    ]) + "\n"
    return pasted, _pdf(items)


def test_paragraph_gaps_do_not_change_the_words():
    from pypdf import PdfReader
    path = DOCS / "layoff-plan-q4-2026.pdf"
    plain = "\n\n".join((page.extract_text() or "") for page in PdfReader(path).pages)
    got = extract_text(path, ".pdf", keep_paragraphs=True)
    assert re.findall(r"\w+", got) == re.findall(r"\w+", plain)
    assert got.count("\n\n") > plain.count("\n\n")


def test_signing_module_review_pdf_matches_the_paste():
    pasted, raw = _review()
    text = extract_text(raw, ".pdf", keep_paragraphs=True)
    assert "\n\ndef accept_signed" in text
    paste = client.post("/check", json={"text": pasted}).json()
    drop = client.post("/check_file", files={"file": ("Signing Module Review.pdf", raw, "application/pdf")}).json()
    assert paste["verdict"] in {"coach", "block"}
    assert paste["semantic_match"]["kind"] == "code"
    assert drop["verdict"] == paste["verdict"]
    assert drop["semantic_match"]["kind"] == "code"
    assert drop["semantic_match"]["path"].endswith("signer.py")
