"""Check every <id>.out in a directory against the contest's shape rules: python3 tools/validate.py <out dir>"""
import json, math, sys
from pathlib import Path
bad = 0
for f in sorted(Path(sys.argv[1]).glob("*.out")):
    try:
        raw = f.read_bytes(); assert len(raw) <= 65536
        d = json.loads(raw); assert list(d) == ["hours"] and len(d["hours"]) == 23
        assert sorted(r["hour"] for r in d["hours"]) == list(range(2, 25))
        for r in d["hours"]:
            assert sorted(r) == ["hour", "q"] and len(r["q"]) == 5
            assert all(isinstance(x, (int, float)) and math.isfinite(x) and 0 < x <= 1e9 for x in r["q"])
            assert all(a <= b for a, b in zip(r["q"], r["q"][1:]))
        print(f.name, "valid")
    except Exception as e:
        bad += 1; print(f.name, "INVALID", repr(e))
sys.exit(1 if bad else 0)
