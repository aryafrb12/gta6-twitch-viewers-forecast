"""GTA VI launch-day Twitch viewer forecast (hours 2..24 of the UTC release day), Python 3.13, standard library only.

Reads every <id>.in in $MAKEFUN_INPUT_DIR (default /input) and writes <id>.out to $MAKEFUN_OUTPUT_DIR (default
/output). The model (model.py) forecasts each hour's log ratio to hour 1 from the release days of comparable past
launches, weighted by similarity; see README.md. If anything goes wrong for a case, the house baseline's random-walk
spread around hour 1 is written instead, so every case stays valid.

    mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
import sys
from datetime import timedelta
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put this file's directory back first so model.py imports.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import model  # noqa: E402

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))


def fallback_rows(p1):
    return {h: [z * 0.15 * math.sqrt(h - 1) for z in model.Z] for h in range(2, 25)}


def target_from_case(case):
    first = next(k for k in case["known"] if k["hour"] == 1)
    h1 = max(1.0, float(first["viewers"]))
    d0 = model.parse_t(case["day_start"])
    vals = {}
    if case.get("history_hourly"):
        for r in case["history_hourly"]:
            if r.get("viewers") is not None:
                vals[model.parse_t(r["from"])] = r["viewers"]
    elif case.get("history"):
        vals = model.hourly_from_points(case["history"])
    vals[d0] = h1
    return {"h1": h1, "ev": model.evening_ratio(vals, d0, h1)}


def pool_from_case(case):
    own = ((case.get("game") or {}).get("name") or "").strip().lower()
    pool = []
    for cm in case.get("comparables") or []:
        if (cm.get("name") or "").strip().lower() == own:
            continue
        try:
            r = model.comparable_record(cm)
        except Exception:
            r = None
        if r and r["meta"]["tier"] != "target-history":
            pool.append(r)
    return pool


def clean(qs, p1):
    out, prev = [], 0.0
    for q in qs:
        v = p1 * math.exp(max(-30.0, min(30.0, q)))
        v = min(1e9, max(1e-3, v, prev))
        v = round(v, 2) if v >= 1 else v
        out.append(v)
        prev = v
    return out


def forecast_case(case):
    first = next(k for k in case["known"] if k["hour"] == 1)
    p1 = max(1.0, float(first["viewers"]))
    try:
        target = target_from_case(case)
        pool = pool_from_case(case)
        if len(pool) < 3:
            raise ValueError("too few comparables")
        logq = model.forecast(target, pool)
    except Exception as e:  # keep the case valid whatever happens
        print(f"model failed ({e!r}); falling back to persistence", file=sys.stderr)
        logq = fallback_rows(p1)
    hours = [row["hour"] for row in case["forecast"]] if case.get("forecast") else list(range(2, 25))
    return {"hours": [{"hour": h, "q": clean(logq[h], p1)} for h in hours]}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        out = forecast_case(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
