"""'Why this matched' evidence on /check and /check_file (real model, real index, no mocks)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402

client = TestClient(app.app)
DOCS = ROOT / "demo" / "company-docs"
KEYS = {"paste_span", "paste_text", "paste_marks", "source_doc", "source_text", "source_span", "source_marks", "kind", "score"}

VERBATIM = ("Ferrolake reported trailing twelve month revenue of 6.2 million dollars with 71 percent gross margin and net "
            "revenue retention of 118 percent. The company burns roughly 480,000 dollars per month and has 7 months of "
            "runway, which gives us meaningful leverage on price.")
PARAPHRASE = ("For 2027 the Team tier is 54 per seat monthly on annual billing with a 10 seat minimum, Business is 118, "
              "and Enterprise is a 96k platform fee plus 142 per seat.")
BENIGN = "A proof of concept should have clear success criteria agreed with the customer before any engineering work starts."


def check(text):
    return client.post("/check", json={"text": text, "source": "test"}).json()


def pairs(r):
    return [m for h in r["matches"] for m in h["matches"]]


def test_verbatim_has_ngram_pairs_with_expected_shape():
    r = check(VERBATIM)
    assert r["verdict"] == "block"
    top = r["semantic_match"]
    assert top["matches"] and len(top["matches"]) <= 3
    for m in top["matches"]:
        assert set(m) == KEYS
        assert m["source_doc"] == top["path"] and 0 < m["score"] <= 1
        assert len(m["paste_text"]) <= 240 and len(m["source_text"]) <= 240
    assert top["matches"][0]["kind"] == "ngram"
    assert "_text" not in top  # internal chunk text never leaves the server


def test_spans_index_into_the_paste_and_marks_are_real_overlap():
    r = check(VERBATIM)
    for m in pairs(r):
        s, e = m["paste_span"]
        assert VERBATIM[s:e] == m["paste_text"]
        ss, se = m["source_span"]
        assert 0 <= ss < se
        for a, b in m["paste_marks"]:
            assert 0 <= a < b <= len(m["paste_text"])
        for a, b in m["source_marks"]:
            assert 0 <= a < b <= len(m["source_text"])
        if m["kind"] == "ngram":
            assert m["paste_marks"] and m["source_marks"]
            phrase = " ".join(m["paste_text"][a:b] for a, b in m["paste_marks"][:1]).lower().split()
            src = m["source_text"].lower()
            assert " ".join(phrase[:3]) in src


def test_offsets_survive_zero_width_characters_and_homoglyphs():
    sneaky = VERBATIM.replace("revenue", "reve​nue", 1).replace("percent", "pеrcent")
    r = check(sneaky)
    got = pairs(r)
    assert got
    for m in got:
        s, e = m["paste_span"]
        assert sneaky[s:e] == m["paste_text"]
        assert all(0 <= a < b <= len(m["paste_text"]) for a, b in m["paste_marks"])


def test_paraphrase_gets_a_pair_with_source_doc():
    r = check(PARAPHRASE)
    assert r["verdict"] in ("coach", "block")
    got = pairs(r)
    assert got and {m["kind"] for m in got} & {"semantic", "tfidf"}
    assert all(m["source_doc"] == "pricing-sheet-2027.txt" for m in got)
    sem = [m for m in got if m["kind"] == "semantic"]
    assert all(m["score"] >= 0.5 and m["paste_marks"] == [] for m in sem)


def test_benign_paste_has_no_matches():
    r = check(BENIGN)
    assert r["verdict"] == "allow"
    assert pairs(r) == []
    assert all(h["matches"] == [] for h in r["matches"])


def test_long_sentences_are_trimmed():
    text = (DOCS / "board-memo-acquisition-ferrolake.md").read_text()
    long_one = " ".join(text.split()[60:200])  # about 140 words with no sentence end handling needed
    r = check(long_one)
    assert r["verdict"] == "block"
    for m in pairs(r):
        assert len(m["paste_text"]) <= 240 and len(m["source_text"]) <= 240
        assert long_one[m["paste_span"][0]:m["paste_span"][1]] == m["paste_text"]


def test_check_file_has_matches_too():
    r = client.post("/check_file", files={"file": ("notes.txt", VERBATIM.encode(), "text/plain")}, data={"source": "test"}).json()
    assert r["verdict"] == "block"
    assert r["semantic_match"]["matches"]
