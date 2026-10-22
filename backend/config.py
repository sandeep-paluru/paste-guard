"""Loads paste-guard.toml (path from PG_CONFIG, default: repo root).

A top-level `profile = "name"` (or PG_PROFILE) merges [profiles.<name>] over the base settings,
so one file can carry the accurate default and the fast profile side by side.

Environment variables override file values:
PG_T_DOC_NUDGE / PG_T_DOC_COACH / PG_T_DOC_BLOCK, PG_T_CODE_* (and legacy PG_T_NUDGE etc. for code),
PG_FP_DOC_COACH / PG_FP_DOC_BLOCK / PG_FP_CODE_* (fingerprint), PG_INDEX_DB, PG_AUDIT_DB,
PG_SECRETS_ALLOWLIST (file of known-safe secrets), PG_SECRETS_EXAMPLES=0 (turn off the built-in samples).
"""
import os
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(os.environ.get("PG_CONFIG", ROOT / "paste-guard.toml")).resolve()
VERSION = (ROOT / "VERSION").read_text().strip() if (ROOT / "VERSION").exists() else "0.0.0"

DEFAULTS = {
    "profile": "accurate",
    "model": {"name": "sentence-transformers/all-MiniLM-L6-v2"},
    "index": {"docs": [], "code": [], "db": "data/index.db"},
    "server": {"host": "127.0.0.1", "port": 8765},
    "thresholds": {"doc": {"nudge": 0.58, "coach": 0.64, "block": 0.74},
                   "code": {"nudge": 0.55, "coach": 0.65, "block": 0.85}},
    # Word 3-gram containment (share of the pasted window's 3-grams found in one indexed chunk).
    "fingerprint": {"min_shingles": 8, "doc": {"coach": 0.25, "block": 0.5}, "code": {"coach": 0.25, "block": 0.5}},
    # TF-IDF cosine (word 1-2 grams) over the indexed chunks. Off unless a profile turns it on.
    # On in the default (accurate) profile; the fast profile turns it off.
    "tfidf": {"enabled": True, "doc": {"coach": 0.23, "block": 0.45}, "code": {"coach": 1.01, "block": 1.01}},
    # Two-step matching. Skip MiniLM when the cheap step already says block, or when the best TF-IDF
    # score is below skip_below (chosen on the eval so no positive is lost; see eval/benchmarks.md).
    "fast_path": {"enabled": True, "skip_below": 0.10},
    "sites": {"allowed": ["claude.ai", "chatgpt.com", "chat.openai.com"]},
    "audit": {"db": "data/audit.db", "keep_days": 30},
    # Known-safe secrets. examples is four public documentation samples. allowlist and file
    # add value:, regex:, and sha256: entries. Off for anything that is not listed.
    "secrets": {"examples": True, "allowlist": [], "file": ""},
}


def _merge(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = _merge(a[k], v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
    return out


def load() -> dict:
    cfg = DEFAULTS
    if CONFIG_PATH.exists():
        cfg = _merge(DEFAULTS, tomllib.loads(CONFIG_PATH.read_text()))
    cfg = dict(cfg)
    cfg["profile"] = os.environ.get("PG_PROFILE") or cfg.get("profile", "accurate")
    if cfg["profile"] == "default":  # pre-0.5.1 name; the base settings are the accurate profile
        cfg["profile"] = "accurate"
    profiles = cfg.pop("profiles", {})
    if cfg["profile"] in profiles:
        cfg = _merge(cfg, profiles[cfg["profile"]])
    elif cfg["profile"] != "accurate":
        raise SystemExit(f"paste-guard.toml: unknown profile {cfg['profile']!r} (have: accurate, {', '.join(profiles) or 'none'})")
    cfg["model"]["name"] = os.environ.get("PG_MODEL") or cfg["model"]["name"]
    base = CONFIG_PATH.parent
    res = lambda p: str((base / p).resolve())  # noqa: E731
    cfg["index"]["docs"] = [res(p) for p in cfg["index"]["docs"]]
    cfg["index"]["code"] = [res(p) for p in cfg["index"]["code"]]
    cfg["index"]["db"] = os.environ.get("PG_INDEX_DB") or res(cfg["index"]["db"])
    cfg["audit"]["db"] = os.environ.get("PG_AUDIT_DB") or res(cfg["audit"]["db"])
    legacy = {"nudge": "PG_T_NUDGE", "coach": "PG_T_COACH", "block": "PG_T_BLOCK"}
    for kind, levels in cfg["thresholds"].items():
        for lvl in levels:
            v = os.environ.get(f"PG_T_{kind.upper()}_{lvl.upper()}") or (kind == "code" and os.environ.get(legacy[lvl]))
            if v:
                levels[lvl] = float(v)
    for kind in ("doc", "code"):
        for lvl in ("coach", "block"):
            v = os.environ.get(f"PG_FP_{kind.upper()}_{lvl.upper()}")
            if v:
                cfg["fingerprint"][kind][lvl] = float(v)
            v = os.environ.get(f"PG_TFIDF_{kind.upper()}_{lvl.upper()}")
            if v:
                cfg["tfidf"][kind][lvl] = float(v)
    if os.environ.get("PG_FAST_PATH") is not None:
        cfg["fast_path"]["enabled"] = os.environ["PG_FAST_PATH"] not in ("0", "false", "")
    sec = dict(cfg.get("secrets") or {})
    examples = sec.get("examples", True)
    if isinstance(examples, str):
        examples = examples.strip().lower() not in ("0", "false", "")
    else:
        examples = bool(examples)
    if os.environ.get("PG_SECRETS_EXAMPLES") is not None:
        examples = os.environ["PG_SECRETS_EXAMPLES"].strip().lower() not in ("0", "false", "")
    raw_list = sec.get("allowlist") or []
    if isinstance(raw_list, str):
        raw_list = [raw_list]
    if not isinstance(raw_list, list) or not all(isinstance(item, str) for item in raw_list):
        raise SystemExit("paste-guard.toml: [secrets] allowlist must be a list of strings")
    file = os.environ.get("PG_SECRETS_ALLOWLIST") or str(sec.get("file") or "")
    file = file.strip()
    if file:
        file_path = Path(file)
        if not file_path.is_absolute():
            file_path = (base / file_path).resolve()
        else:
            file_path = file_path.resolve()
        file = str(file_path)
    sec["examples"] = examples
    sec["allowlist"] = list(raw_list)
    sec["file"] = file
    cfg["secrets"] = sec
    return cfg


CONFIG = load()
