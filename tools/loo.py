"""Leave-one-out validation over the comparables of a case file.

    python3 tools/loo.py <case.in> [key=value ...]

For each comparable j with a usable release day, forecast it from all the others and score the pinball loss
(the contest's: 2*max(tau*d, (tau-1)*d), d = ln y - ln q) on hours 2..24. Reports the loss over all targets and
over the "GTA-like" ones (rolling midnight-local, base weight >= 0.5), next to the house baseline.
"""
import json, math, sys, copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import model

def pinball(y, qs):
    tot = 0.0
    for tau, q in zip(model.LEVELS, qs):
        d = y - q
        tot += 2 * max(tau * d, (tau - 1) * d)
    return tot / 5

def baseline(h):
    return [z * 0.15 * math.sqrt(h - 1) for z in model.Z]

def run(recs, p, verbose=False):
    res = {"all": [0, 0, 0, 0, 0], "like": [0, 0, 0, 0, 0]}
    rows = []
    for j, t in enumerate(recs):
        pool = [r for i, r in enumerate(recs) if i != j]
        f = model.forecast({"h1": t["h1"], "ev": t["ev"], "us_open": t["meta"]["us_open"]}, pool, p)
        L = B = C = n = 0
        ae = 0
        for h, y in t["y"].items():
            L += pinball(y, f[h]); B += pinball(y, baseline(h)); n += 1
            C += f[h][0] <= y <= f[h][4]
            ae += abs(y - f[h][2])
        like = model.base_weight(t, model.PARAMS) >= 0.5
        for k in (["all", "like"] if like else ["all"]):
            a = res[k]; a[0] += L; a[1] += B; a[2] += n; a[3] += C; a[4] += ae
        rows.append((t["name"][:24], like, L / n, B / n, C / n))
    if verbose:
        for r in rows:
            print(f"  {r[0]:24s} {'*' if r[1] else ' '} loss {r[2]:.3f} base {r[3]:.3f} cov {r[4]:.2f}")
    return {k: (a[0] / a[2], a[1] / a[2], a[3] / a[2], a[4] / a[2]) for k, a in res.items() if a[2]}

def load(case_path):
    case = json.loads(Path(case_path).read_text())
    recs = [model.comparable_record(c) for c in case["comparables"]]
    return [r for r in recs if r and r["meta"]["tier"] != "target-history"]

if __name__ == "__main__":
    recs = load(sys.argv[1])
    p = copy.deepcopy(model.PARAMS)
    for kv in sys.argv[2:]:
        k, v = kv.split("=")
        p[k] = v if k == "loc" else float(v)
    out = run(recs, p, verbose=True)
    for k, (l, b, c, ae) in out.items():
        print(f"{k:4s} loss {l:.4f}  baseline {b:.4f}  cov90 {c:.3f}  mae {ae:.3f}")
