"""Latency of real /check calls against a running backend (stdlib only, so it runs on the server).

  python3 eval/http_latency.py [--url http://127.0.0.1:8765] [--n 80] [--out eval/bench/vm_latency.json]
Uses eval sample pastes, cycles through them, reports p50 and p95 and the backend's RSS.
"""
import argparse, json, os, platform, statistics, subprocess, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:8765")
ap.add_argument("--n", type=int, default=80)
ap.add_argument("--out", default="")
a = ap.parse_args()
texts = []
for f in ("doc", "code"):
    texts += [json.loads(x)["text"] for x in (ROOT / "eval" / "data" / f"{f}_pastes.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
texts = texts[::max(1, len(texts) // a.n)][:a.n]


def call(t):
    req = urllib.request.Request(a.url + "/check", data=json.dumps({"text": t, "source": "benchmark"}).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    verdict = json.loads(urllib.request.urlopen(req, timeout=60).read())["verdict"]
    return (time.time() - t0) * 1000, verdict


call("warm up")
runs = [call(t) for t in texts]
lat = sorted(ms for ms, _ in runs)
flagged = sorted(ms for ms, v in runs if v in ("coach", "block"))  # these also pay for the "why this matched" pairs
pct = lambda xs, q: xs[int(q * (len(xs) - 1))] if xs else None  # noqa: E731
rss, ram = 0, "?"
try:  # Linux: server RSS and total RAM from /proc
    pid = subprocess.run(["pgrep", "-f", "port 8765|pasteguard serve|uvicorn app:app"], capture_output=True, text=True).stdout.split()
    for p in pid:
        try:
            rss = max(rss, int([l for l in open(f"/proc/{p}/status") if l.startswith("VmRSS")][0].split()[1]) / 1024)
        except Exception:
            pass
    ram = f"{int([l for l in open('/proc/meminfo')][0].split()[1]) / 1024 / 1024:.1f} GB RAM"
except Exception:  # Windows/macOS: no pgrep or /proc; report latency only
    pass
res = {"host": platform.node(), "cpus": os.cpu_count(), "ram": ram, "n": len(lat),
       "p50": statistics.median(lat), "p95": pct(lat, 0.95), "mean": statistics.mean(lat), "rss_mb": rss,
       "flagged_n": len(flagged), "flagged_p50": pct(flagged, 0.5), "flagged_p95": pct(flagged, 0.95)}
print(json.dumps(res))
if a.out:
    Path(a.out).write_text(json.dumps(res))
