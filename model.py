"""Launch-day Twitch viewer forecast from comparable launches (standard library only, deterministic).

For every comparable launch we take its release UTC day and compute the log ratio of each hour h = 2..24 to its
hour 1 (00:00-01:00 UTC).  The forecast for the target is a similarity-weighted, robust location of those log
ratios (optionally adjusted by a regression on the "evening before" ratio), with a spread built from the weighted
dispersion of the comparables, inflated for small samples and for targets bigger than anything in the pool.
"""

import math
from datetime import datetime, timedelta, timezone

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.6448536, -0.6744898, 0.0, 0.6744898, 1.6448536]

# Tunable settings (picked by leave-one-out over the comparables, see tools/loo.py).
PARAMS = {
    "tier_w": {"comparable": 1.0, "early-access-contaminated": 0.35, "weak": 0.1},
    "simul_w": 0.12,        # weight multiplier for a single simultaneous global unlock (shape differs)
    "mixed_w": 0.6,         # rolling consoles + simultaneous PC
    "unverified_w": 0.6,    # unlock not verified
    "pc_w": 0.6,            # launch includes PC (GTA VI is console only)
    "small_h1": 5000,       # hour 1 below this: category barely launched at 00 UTC
    "small_w": 0.15,
    "size_bw": 1.0,         # kernel bandwidth on log(h1) (0 = off)
    "size_cap_rank": 3,     # target size capped at the k-th largest comparable hour 1 (0 = no cap)
    "neff_min": 4.0,        # below this effective sample size the spread widens (sqrt(neff_min/neff))
    "ev_bw": 0.0,           # kernel bandwidth on log(evening-before / h1) (0 = off)
    "ev_slope": 0.5,        # shrunk regression slope of y_h on log(ev) (0 = off)
    "loc": "blend",         # "wmean" | "wmedian" | "blend"
    "sd_inflate": 0.9,
    "sd_floor": 0.10,
    "sd_floor_growth": 0.02,  # extra floor per sqrt(h-1)
    "tail_mult": 1.15,        # extra multiplier on the 5%/95% (fat tails)
    "extrap_sd": 0.15,         # extra sd when the target's hour 1 is above every comparable's
    "loc_shift": 0.0,         # constant log shift of the median (judgement), 0 = none
}


def parse_t(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def by_hour(rows, key="from"):
    out = {}
    for r in rows:
        t = r.get(key) or r.get("at")
        if t is None or r.get("viewers") is None:
            continue
        out[parse_t(t)] = r
    return out


def hourly_from_points(points):
    """Whole-hour means of minute (or hourly) points: {hour_start: mean viewers}."""
    acc = {}
    for p in points:
        if p.get("viewers") is None:
            continue
        t = parse_t(p["at"]).replace(minute=0, second=0, microsecond=0)
        s = acc.setdefault(t, [0.0, 0])
        s[0] += p["viewers"]
        s[1] += 1
    return {t: s[0] / s[1] for t, s in acc.items()}


def evening_ratio(vals, d0, h1):
    """Mean of the 5 hours before day start relative to hour 1 (None when absent)."""
    ev = [vals[d0 + timedelta(hours=h)] for h in range(-5, 0) if (d0 + timedelta(hours=h)) in vals]
    ev = [v for v in ev if v and v > 0]
    if not ev or not h1:
        return None
    return sum(ev) / len(ev) / h1


def meta_from_text(text):
    """Unlock style and platform hints from free text."""
    t = (text or "").lower()
    rolling = ("midnight local" in t) or ("rolling" in t)
    simul = ("simultaneous" in t) or ("single global" in t) or ("single time" in t) or ("global unlock" in t)
    unverified = "unverified" in t and not rolling
    return {"rolling": rolling, "simul": simul, "unverified": unverified}


def comparable_record(cm):
    d0 = parse_t(cm["day_start"])
    m = by_hour(cm.get("hourly") or [])
    vals = {t: r["viewers"] for t, r in m.items()}
    h1 = vals.get(d0)
    if not h1 or h1 <= 0:
        return None
    y = {}
    for h in range(2, 25):
        v = vals.get(d0 + timedelta(hours=h - 1))
        if v and v > 0:
            y[h] = math.log(v / h1)
    if len(y) < 12:
        return None
    unlock = cm.get("unlock") or ""
    tier = "comparable"
    if "Tier:" in unlock:
        tier = unlock.split("Tier:")[1].strip().split(".")[0].strip().lower()
    plat = (cm.get("platforms") or "").lower()
    meta = meta_from_text(unlock.split("Tier:")[0])
    meta.update({"tier": tier, "pc": "pc" in plat, "f2p": "free-to-play" in plat})
    return {"name": cm.get("name"), "h1": h1, "y": y, "ev": evening_ratio(vals, d0, h1), "meta": meta}


def base_weight(rec, p=PARAMS):
    m = rec["meta"]
    if m["tier"] == "target-history":
        return 0.0
    w = p["tier_w"].get(m["tier"], 0.3)
    if m["simul"] and m["rolling"]:
        w *= p["mixed_w"]
    elif m["simul"]:
        w *= p["simul_w"]
    elif m["unverified"]:
        w *= p["unverified_w"]
    if m["pc"]:
        w *= p["pc_w"]
    if rec["h1"] < p["small_h1"]:
        w *= p["small_w"]
    return w


def wquantile(pairs, q):
    pairs = sorted(pairs)
    tot = sum(w for _, w in pairs)
    if tot <= 0:
        return pairs[len(pairs) // 2][0]
    c = 0.0
    for v, w in pairs:
        c += w
        if c >= q * tot:
            return v
    return pairs[-1][0]


def forecast(target, pool, p=PARAMS):
    """target: {"h1", "ev"}; pool: comparable records. Returns {h: [5 quantiles of log ratio]}."""
    lh1 = math.log(max(1.0, target["h1"]))
    k = int(p.get("size_cap_rank", 0))
    if k > 0:
        tops = sorted((r["h1"] for r in pool if base_weight(r, p) > 0), reverse=True)
        if len(tops) >= k:
            lh1 = min(lh1, math.log(tops[k - 1]))
    lev = math.log(target["ev"]) if target.get("ev") else None
    ws = []
    for r in pool:
        w = base_weight(r, p)
        if w <= 0:
            continue
        if p["size_bw"] > 0:
            k = math.exp(-0.5 * ((math.log(r["h1"]) - lh1) / p["size_bw"]) ** 2)
            w *= k
        if p["ev_bw"] > 0 and lev is not None and r["ev"]:
            w *= math.exp(-0.5 * ((math.log(r["ev"]) - lev) / p["ev_bw"]) ** 2)
        ws.append((r, w))
    tot_w = sum(w for _, w in ws)
    max_h1 = max((r["h1"] for r, w in ws if w > 0), default=1)
    out = {}
    for h in range(2, 25):
        pts = [(r["y"][h], w, r["ev"]) for r, w in ws if h in r["y"] and w > 0]
        sw = sum(w for _, w, _ in pts)
        mean = sum(v * w for v, w, _ in pts) / sw
        # optional regression adjustment on log(ev)
        adj = 0.0
        if p["ev_slope"] and lev is not None:
            evp = [(math.log(e), v, w) for v, w, e in pts if e]
            sw2 = sum(w for _, _, w in evp)
            mx = sum(x * w for x, _, w in evp) / sw2
            my = sum(v * w for _, v, w in evp) / sw2
            sxx = sum(w * (x - mx) ** 2 for x, _, w in evp)
            sxy = sum(w * (x - mx) * (v - my) for x, v, w in evp)
            b = sxy / sxx if sxx > 0 else 0.0
            b *= p["ev_slope"]  # shrink
            # move every comparable to the target's ev (those without ev are moved by the mean shift)
            pts = [(v + b * (lev - (math.log(e) if e else mx)), w, e) for v, w, e in pts]
            mean = sum(v * w for v, w, _ in pts) / sw
        med = wquantile([(v, w) for v, w, _ in pts], 0.5)
        if p["loc"] == "wmedian":
            loc = med
        elif p["loc"] == "blend":
            loc = 0.5 * (mean + med)
        else:
            loc = mean
        var = sum(w * (v - loc) ** 2 for v, w, _ in pts) / sw
        neff = sw ** 2 / sum(w * w for _, w, _ in pts)
        sd = math.sqrt(var) * p["sd_inflate"] * math.sqrt(1 + 1 / max(neff, 1))
        if p["neff_min"] > neff:
            sd *= math.sqrt(p["neff_min"] / neff)
        floor = p["sd_floor"] + p["sd_floor_growth"] * math.sqrt(h - 1)
        sd = math.sqrt(sd * sd + floor * floor)
        if target["h1"] > max_h1:
            sd = math.sqrt(sd * sd + p["extrap_sd"] ** 2)
        loc += p["loc_shift"]
        qs = []
        for z in Z:
            m = p["tail_mult"] if abs(z) > 1 else 1.0
            qs.append(loc + z * sd * m)
        out[h] = qs
    return out
