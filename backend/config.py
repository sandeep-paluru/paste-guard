"""Loads paste-guard.toml (path from PG_CONFIG, default: repo root).

Environment variables override file values:
PG_T_DOC_NUDGE / PG_T_DOC_COACH / PG_T_DOC_BLOCK, PG_T_CODE_* (and legacy PG_T_NUDGE etc. for code),
PG_INDEX_DB, PG_AUDIT_DB.
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
    "index": {"docs": [], "code": [], "db": "data/index.db"},
    "server": {"host": "127.0.0.1", "port": 8765},
    "thresholds": {"doc": {"nudge": 0.62, "coach": 0.65, "block": 0.78},
                   "code": {"nudge": 0.55, "coach": 0.65, "block": 0.85}},
    "sites": {"allowed": ["claude.ai", "chatgpt.com", "chat.openai.com"]},
    "audit": {"db": "data/audit.db", "keep_days": 30},
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
    return cfg


CONFIG = load()
