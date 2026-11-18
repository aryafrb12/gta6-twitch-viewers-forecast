"""Signals only the final case carries (minute reads, `streams`, `categories_hourly`), each optional.

Every function returns None when its input is missing or odd; main.py applies only what came back. Their effects
are deliberately small: the comparables (hourly data only) cannot calibrate them, so they nudge the median of
the next few hours, widen a band, or cap an implausible upper tail. They never set the forecast on their own.
"""

import math
from datetime import timedelta

import model


def _num(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    if not math.isfinite(x) or x < 0:
        return None
    return float(x)


def _t(s):
    try:
        return model.parse_t(s) if isinstance(s, str) else None
    except (ValueError, TypeError):
        return None


def minute_points(case):
    pts = []
    for p in case.get("history") or []:
        if not isinstance(p, dict):
            continue
        t, v = _t(p.get("at")), _num(p.get("viewers"))
        if t is not None and v is not None:
            pts.append((t, v))
    pts.sort()
    return pts


def hour1_momentum(case, d0, h1):
    """log(mean of hour 1's last 15 minutes / hour 1's print), from the minute reads; None without them."""
    pts = [(t, v) for t, v in minute_points(case) if d0 <= t < d0 + timedelta(hours=1)]
    last = [v for t, v in pts if t >= d0 + timedelta(minutes=45)]
    if len(pts) < 20 or len(last) < 8 or h1 <= 0:
        return None
    m = sum(last) / len(last)
    if m <= 0:
        return None
    return max(-0.3, min(0.3, math.log(m / h1)))


def english_share(case):
    """Share of the top-20 streams' viewers on English-language streams at the checkpoint."""
    rows = case.get("streams")
    if not isinstance(rows, list):
        return None
    en = tot = 0.0
    for r in rows:
        if not isinstance(r, dict):
            continue
        v = _num(r.get("viewers"))
        if v is None:
            continue
        tot += v
        if isinstance(r.get("language"), str) and r["language"].lower().startswith("en"):
            en += v
    if tot <= 0 or sum(1 for r in rows if isinstance(r, dict)) < 5:
        return None
    return en / tot


def twitch_others(case, game_name):
    """{hour_start: viewers of the top-20 categories other than the game} from `categories_hourly`."""
    rows = case.get("categories_hourly")
    if not isinstance(rows, list):
        return None
    gn = (game_name or "").strip().lower()
    out = {}
    for r in rows:
        if not isinstance(r, dict) or not isinstance(r.get("top"), list):
            continue
        t = _t(r.get("from"))
        if t is None:
            continue
        s, n = 0.0, 0
        for c in r["top"]:
            if not isinstance(c, dict):
                continue
            v = _num(c.get("viewers"))
            name = c.get("name") if isinstance(c.get("name"), str) else ""
            if v is None or name.strip().lower() == gn or "grand theft auto vi" == name.strip().lower():
                continue
            s += v
            n += 1
        if n >= 5:
            out[t.replace(minute=0, second=0, microsecond=0)] = s
    return out or None


def others_projection(others, d0):
    """Expected other-category viewers at each hour 2..24 of the day: the previous days' same-UTC-hour level,
    rescaled so the latest available hour matches. None when there is too little."""
    if not others:
        return None
    latest_t = max(others)
    if latest_t < d0 - timedelta(hours=3):
        return None
    proj = {}
    for h in range(2, 25):
        t = d0 + timedelta(hours=h - 1)
        same = [others[t - timedelta(days=k)] for k in (1, 2) if (t - timedelta(days=k)) in others]
        ref = [others[latest_t - timedelta(days=k)] for k in (1, 2) if (latest_t - timedelta(days=k)) in others]
        if not same or not ref:
            return None
        scale = others[latest_t] / (sum(ref) / len(ref))
        proj[h] = scale * sum(same) / len(same)
    return proj


def apply(logq, case, d0, h1, max_share=0.8, log=None):
    """Adjust {h: [5 log-ratio quantiles]} in place with whatever signals the case supports."""
    notes = []
    mom = hour1_momentum(case, d0, h1)
    if mom is not None:
        # Hour 2 starts where hour 1 ended: carry half the within-hour drift, fading over a few hours.
        for h in logq:
            d = 0.5 * mom * math.exp(-(h - 2) / 2.0)
            logq[h] = [q + d for q in logq[h]]
        notes.append(f"momentum {mom:+.3f}")
    reads = None
    for k in case.get("known") or []:
        if isinstance(k, dict) and k.get("hour") == 1:
            reads = _num(k.get("reads"))
    minute_data = sum(1 for t, _ in minute_points(case) if d0 - timedelta(hours=3) <= t < d0 + timedelta(hours=1)) >= 60
    if reads is not None and reads < 30 and minute_data:
        # A thin hour-1 print is itself noisy: widen every hour.
        extra = 0.15 * math.sqrt((30 - reads) / 30)
        for h in logq:
            logq[h] = [q + extra * z / 1.645 for q, z in zip(logq[h], model.Z)]
        notes.append(f"thin hour 1 ({reads:.0f} reads)")
    es = english_share(case)
    if es is not None:
        # The US (English-speaking, largest audience) unlocks at 05:00-08:00Z. If English streams already dominate
        # at hour 1 the US wave is partly in, so less upside; if they are scarce, a little more.
        d = max(-0.1, min(0.1, -0.3 * (es - 0.5)))
        for h in logq:
            if h >= 6:
                logq[h] = [q + d for q in logq[h]]
        notes.append(f"english share {es:.2f} -> {d:+.3f} on hours 6-24")
    gname = (case.get("game") or {}).get("name") if isinstance(case.get("game"), dict) else None
    proj = others_projection(twitch_others(case, gname or "Grand Theft Auto VI"), d0)
    if proj:
        # Saturation guard: the game cannot plausibly hold more than max_share of the top-20 audience.
        capped = 0
        for h in logq:
            cap = math.log(max_share / (1 - max_share) * proj[h] / h1)
            new = []
            for q in logq[h]:
                if q > cap - 0.5:  # soft cap: smooth approach to cap
                    q2 = cap - 0.5 * math.exp(-(q - (cap - 0.5)) / 0.5)
                    capped += q2 < q - 1e-9
                    q = q2
                new.append(q)
            logq[h] = new
        notes.append(f"twitch-share cap ({capped} quantiles touched)")
    if log:
        log("; ".join(notes) or "no extra signals")
    return logq
