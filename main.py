"""GTA VI launch-day Twitch viewer forecast (hours 2..24 of the UTC release day), Python 3.13, standard library only.

Reads every <id>.in in $MAKEFUN_INPUT_DIR (default /input) and writes <id>.out to $MAKEFUN_OUTPUT_DIR (default
/output). model.py forecasts each hour's log ratio to hour 1 from comparable past launches; signals.py nudges it
with the final-only fields (minute reads, streams, categories). Layers, each a fallback for the one before:
model + signals, model alone, model without the case's history, the house baseline's band. Every case is written.

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

try:
    import signals  # noqa: E402
except Exception:  # pragma: no cover - a broken signals module must not break the entry
    signals = None

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))
DAY0 = "2026-11-19T00:00:00Z"


def log(msg):
    try:
        print(msg, file=sys.stderr, flush=True)
    except Exception:
        pass


def num(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    return float(x)


def day_start(case):
    try:
        return model.parse_t(case["day_start"])
    except Exception:
        return model.parse_t(DAY0)


def hour1_print(case):
    for k in case.get("known") or []:
        if isinstance(k, dict) and k.get("hour") == 1 and num(k.get("viewers")) is not None:
            return max(1.0, num(k["viewers"]))
    # no usable known row: the mean of hour 1's minute reads, else 1 (what the grader would use)
    d0 = day_start(case)
    vals = []
    for p in case.get("history") or []:
        try:
            t = model.parse_t(p["at"])
            if d0 <= t < d0 + timedelta(hours=1) and num(p["viewers"]) is not None:
                vals.append(num(p["viewers"]))
        except Exception:
            pass
    return max(1.0, sum(vals) / len(vals)) if vals else 1.0


def hourly_history(case):
    vals = {}
    rows = case.get("history_hourly")
    if isinstance(rows, list):
        for r in rows:
            try:
                v = num(r["viewers"])
                if v is not None and v >= 0:
                    vals[model.parse_t(r["from"])] = v
            except Exception:
                continue
    if not vals and isinstance(case.get("history"), list):
        pts = []
        for p in case["history"]:
            try:
                if num(p["viewers"]) is not None and isinstance(p["at"], str):
                    model.parse_t(p["at"])
                    pts.append(p)
            except Exception:
                continue
        vals = model.hourly_from_points(pts)
    return vals


def target_from_case(case, h1, use_history=True):
    d0 = day_start(case)
    vals = hourly_history(case) if use_history else {}
    vals[d0] = h1
    notes = case.get("notes") if isinstance(case.get("notes"), str) else ""
    us_open = 0.0  # GTA VI: rolling midnight local, the US is locked through hour 1
    if notes:
        try:
            tier = "early-access" if "early access" in notes.lower() and "no early access" not in notes.lower() else ""
            v = model.us_open_at_h1(notes, tier, d0)
            us_open = 0.0 if v == 0.5 else v
        except Exception:
            pass
    return {"h1": h1, "ev": model.evening_ratio(vals, d0, h1), "us_open": us_open}


def pool_from_case(case):
    game = case.get("game") if isinstance(case.get("game"), dict) else {}
    own = (game.get("name") or "").strip().lower() if isinstance(game.get("name"), str) else ""
    pool = []
    for cm in case.get("comparables") or []:
        try:
            if (cm.get("name") or "").strip().lower() == own:
                continue
            r = model.comparable_record(cm)
        except Exception:
            r = None
        if r and r["meta"]["tier"] != "target-history":
            pool.append(r)
    return pool


def baseline_logq():
    return {h: [z * 0.15 * math.sqrt(h - 1) for z in model.Z] for h in range(2, 25)}


def check_logq(logq):
    for h in range(2, 25):
        qs = logq[h]
        if len(qs) != 5 or not all(isinstance(q, float) and math.isfinite(q) for q in qs):
            raise ValueError(f"bad quantiles at hour {h}")
    return logq


def clean(qs, p1):
    out, prev = [], 0.0
    for q in qs:
        v = p1 * math.exp(max(-30.0, min(30.0, q)))
        v = min(1e9, max(1e-3, v, prev))
        v = round(v, 2) if v >= 1 else v
        v = min(v, 1e9)
        out.append(v)
        prev = v
    return out


def forecast_case(case):
    p1 = hour1_print(case)
    d0 = day_start(case)
    logq = None
    pool = []
    try:
        pool = pool_from_case(case)
    except Exception as e:
        log(f"pool failed: {e!r}")
    layers = [("model+signals", True, True), ("model", True, False), ("model without history", False, False)]
    for name, use_hist, use_sig in layers:
        try:
            if len(pool) < 3:
                raise ValueError("too few comparables")
            target = target_from_case(case, p1, use_hist)
            lq = check_logq(model.forecast(target, pool))
            if use_sig:
                if signals is None:
                    raise ValueError("signals unavailable")
                lq = check_logq(signals.apply(lq, case, d0, p1, log=log))
            logq = lq
            log(f"{case.get('id')}: {name}, hour 1 {p1:.0f}, ev {target['ev']}, {len(pool)} comparables")
            break
        except Exception as e:
            log(f"{case.get('id')}: {name} failed ({e!r})")
    if logq is None:
        log("falling back to the baseline band")
        logq = baseline_logq()
    hours = list(range(2, 25))
    return {"hours": [{"hour": h, "q": clean(logq[h], p1)} for h in hours]}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(case, dict):
                raise ValueError("case is not an object")
            out = forecast_case(case)
        except Exception as e:
            log(f"{path.name}: unreadable ({e!r}); baseline with hour 1 = 1")
            out = {"hours": [{"hour": h, "q": clean(q, 1.0)} for h, q in baseline_logq().items()]}
        (OUTPUT_DIR / f"{path.stem}.out").write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
