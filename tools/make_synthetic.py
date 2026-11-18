"""Build synthetic final-shaped cases (h00 and broken variants) from a practice case's comparables.

    python3 tools/make_synthetic.py <practice case.in> <out dir>

h00.in mimics the final: minute reads of the GTA VI category since 2026-11-17 (quiet ~2k, the NZ unlock at
11:00Z Nov 18, Asia, then central Europe at 23:00Z), hour 1's print, `streams` and `categories_hourly`. The
variants drop or garble the final-only fields so main.py can be checked never to crash or go invalid.
"""
import copy, json, math, random, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

D0 = datetime(2026, 11, 19, tzinfo=timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def gta_level(t):
    """Synthetic GTA VI category level (viewers) at time t, before the checkpoint."""
    h = (t - D0).total_seconds() / 3600.0  # hours relative to the release day start
    if h < -13:  # before NZ unlock
        return 2000 + 1500 * math.sin((h + 6) / 24 * 2 * math.pi) + max(0, 30000 * math.exp((h + 13) / 2))
    if h < -1:  # NZ/AU/Asia playing, Europe watching
        return 60000 + (h + 13) * 30000
    return 420000 + (h + 1) * 380000  # central Europe in at 23:00Z, UK at 00:00Z


def build(base, rng):
    case = copy.deepcopy(base)
    case["id"] = "h00"
    case["game"] = {"name": "Grand Theft Auto VI", "twitch_id": "1867279146"}
    case["day_start"] = iso(D0)
    case["checkpoint"] = iso(D0 + timedelta(hours=1))
    hist, t = [], datetime(2026, 11, 17, 0, 0, tzinfo=timezone.utc)
    while t < D0 + timedelta(hours=1):
        if rng.random() > 0.02:  # a few missed minutes
            v = gta_level(t) * (1 + rng.gauss(0, 0.02))
            hist.append({"at": iso(t), "viewers": max(0, int(v)), "channels": int(50 + v / 120)})
        t += timedelta(minutes=1)
    in_h1 = [p for p in hist if p["at"] >= iso(D0)]
    hist_before = [p for p in hist if p["at"] < iso(D0)]
    acc = {}
    for p in hist_before:
        acc.setdefault(p["at"][:13] + ":00:00Z", []).append(p)
    case["history"] = hist_before
    case["history_hourly"] = [
        {"from": k, "viewers": round(sum(p["viewers"] for p in v) / len(v)),
         "channels": round(sum(p["channels"] for p in v) / len(v)), "reads": len(v)} for k, v in sorted(acc.items())]
    p1 = round(sum(p["viewers"] for p in in_h1) / len(in_h1))
    case["known"] = [{"hour": 1, "from": iso(D0), "until": iso(D0 + timedelta(hours=1)), "viewers": p1,
                      "channels": round(sum(p["channels"] for p in in_h1) / len(in_h1)), "reads": len(in_h1)}]
    # the final's history holds every valid read before the checkpoint, hour 1's included
    case["history"] = hist
    langs = ["en"] * 8 + ["es"] * 4 + ["fr", "de", "pt", "pt", "it", "ja", "ko", "ru"]
    case["streams"] = [{"login": f"streamer{i}", "viewers": int(p1 * 0.4 / (i + 1.5)), "language": langs[i],
                        "started_at": iso(D0 - timedelta(hours=1 + i % 5))} for i in range(20)]
    cats = []
    t = datetime(2026, 11, 17, 0, 0, tzinfo=timezone.utc)
    while t <= D0:
        hr = t.hour + t.minute / 60
        cyc = 1 + 0.35 * math.cos((hr - 20) / 24 * 2 * math.pi)  # Twitch peaks in the US afternoon/evening
        top = [{"name": "Just Chatting", "viewers": int(420000 * cyc), "channels": 9000}]
        top += [{"name": f"Game {i}", "viewers": int(200000 * cyc / (i + 1)), "channels": 3000 // (i + 1)} for i in range(18)]
        g = gta_level(t)
        top.append({"name": "Grand Theft Auto VI", "viewers": int(g), "channels": int(50 + g / 120)})
        top.sort(key=lambda r: -r["viewers"])
        cats.append({"from": iso(t), "top": top[:20]})
        t += timedelta(hours=1)
    case["categories_hourly"] = cats
    case["notes"] = ("Grand Theft Auto VI (Twitch category 1867279146), released 2026-11-19 on PS5 and Xbox Series X|S; "
                     "unlock midnight local time, rolling (NZ 2026-11-18T11:00Z, central Europe 23:00Z, UK 00:00Z, "
                     "US east 05:00Z, US west 08:00Z). SYNTHETIC TEST CASE.")
    return case


def variants(h00):
    out = {}
    v = copy.deepcopy(h00); v["streams"] = None; v["categories_hourly"] = None; out["v01"] = v
    v = copy.deepcopy(h00); v["history"] = []; v["history_hourly"] = []; out["v02"] = v
    v = copy.deepcopy(h00); del v["history"]; del v["history_hourly"]; del v["streams"]; del v["categories_hourly"]; out["v03"] = v
    v = copy.deepcopy(h00); v["streams"] = [{"login": None, "viewers": "x", "language": 5}, None, 7]
    v["categories_hourly"] = [{"from": "bad", "top": None}, {"top": [{"name": None, "viewers": -3}]}, "zz"]; out["v04"] = v
    v = copy.deepcopy(h00); v["known"][0]["reads"] = 4; v["known"][0]["viewers"] = 0; out["v05"] = v
    v = copy.deepcopy(h00); v["comparables"] = []; out["v06"] = v
    v = copy.deepcopy(h00); v["history"] = [{"at": "2026-11-18T23:59:00Z", "viewers": None}, {"at": None}, {"viewers": 5}]
    v["history_hourly"] = None; out["v07"] = v
    v = copy.deepcopy(h00); v["comparables"] = [{"name": "x"}, None, {"hourly": "no"}] + v["comparables"][:2]; out["v08"] = v
    v = copy.deepcopy(h00); v["known"][0]["viewers"] = 40_000_000; out["v09"] = v  # absurd hour 1
    v = copy.deepcopy(h00); v["forecast"] = None; v["game"] = None; v["notes"] = None; out["v10"] = v
    return out


if __name__ == "__main__":
    base = json.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    h00 = build(base, random.Random(19))
    (out / "h00.in").write_text(json.dumps(h00))
    for k, v in variants(h00).items():
        (out / f"{k}.in").write_text(json.dumps(v))
    print("hour 1:", h00["known"][0])
