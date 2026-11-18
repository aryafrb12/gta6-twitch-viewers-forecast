# GTA VI launch-day Twitch viewers: comparable-launch forecast

[![make.fun](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/aryafrb12/gta6-twitch-viewers-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/aryafrb12/gta6-twitch-viewers-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

Entry for make.fun `gta6-twitch-ccu-forecast-01`. `python3 main.py` reads every `*.in` in `$MAKEFUN_INPUT_DIR`
(default `/input`) and writes `<id>.out` (five quantiles for each of hours 2–24) to `$MAKEFUN_OUTPUT_DIR` (default
`/output`). It uses only the standard library, is deterministic, and runs in well under a second per case.

## Model (`model.py`)

1. **Launch curves.** For each comparable launch, take its release UTC day and compute
   `y_h = ln(viewers_h / viewers_1)` for h = 2..24. GTA VI's own pre-release category history is excluded, because it
   holds no launch.
2. **Unlock waves.** GTA VI unlocks at midnight local time, rolling: NZ 11:00Z, central Europe 23:00Z, UK 00:00Z,
   US East 05:00Z, US West 08:00Z. At hour 1 (00–01Z) Europe is in, but the Americas, the biggest Twitch audience,
   are not. Each comparable is flagged by whether the US could already play by the end of hour 1:
   - **yes:** early access, or a PC/global unlock at or before 01:00Z, as with Elden Ring and Cyberpunk;
   - **no:** rolling midnight-local console launches;
   - **unknown:** everything else.

   A comparable whose flag differs from the target's is weighted ×0.35 per unit of mismatch. This stops the biggest
   PC launches, which held flat all day because the US was already watching at hour 1, from setting GTA VI's curve.
   The comparables' own curves carry the rest of the wave: the dip at 02–10Z, the US East and West unlock bumps, and
   the US daytime rise at 14–23Z.
3. **Similarity weights.**
   - Tier: comparable 1, early-access-contaminated 0.35, weak 0.1.
   - Unlock style: a simultaneous global unlock ×0.12, rolling consoles plus simultaneous PC ×0.6, unverified ×0.6.
   - Platforms: a launch that includes PC ×0.6.
   - An hour 1 under 5k ×0.15.
   - A Gaussian kernel on `ln(hour 1)` (bandwidth 1.0), because big launches grow less through the day. The target's
     size is capped at the 2nd-largest same-wave comparable, so an off-scale GTA VI hour 1 is matched to the biggest
     console launches, not to one launch.
4. **Evening-before adjustment.** A shrunk regression on `ln(mean of 19–24Z before / hour 1)`, clamped to the
   comparables' range.
5. **Spread.** The weighted SD around the location (the mean of the weighted mean and median), which is:
   - inflated for a small effective sample size;
   - given a floor of `0.10 + 0.02·sqrt(h-1)`;
   - given fatter 5%/95% tails (×1.3);
   - widened by an extra 0.15 log units when hour 1 is beyond every comparable.

## Final-only signals (`signals.py`)

The final case carries data the practice cases don't. Each signal is optional and capped, and is skipped when it is
missing or malformed:

- **Minute reads:** drift inside hour 1, `ln(last 15 min / print)` clipped to ±0.3. Half of it carries into hour 2
  and fades over a few hours. An hour 1 with fewer than 30 minute reads widens every band.
- **`streams`:** the English share of the top-20 viewers. A high share means part of the US wave is already in, so the
  hours from 6 onward go down slightly; a low share raises them slightly (±0.1 at most).
- **`categories_hourly`:** projects the other top-20 categories' viewers to each hour, using the same UTC hour on the
  previous days (Twitch's daily cycle), and soft-caps the upper quantiles so GTA VI stays at or below 80% of the
  top-20 audience.

`main.py` runs layers, each the fallback for the one before: model + signals, model alone, model without the case's
history, then the house baseline band. Every case gets a valid file. `tools/make_synthetic.py` builds a final-shaped
h00 case plus 10 broken variants (missing, null or mistyped fields, no comparables, a 4-read hour 1, an absurd hour
1); all of them come out valid (`tools/validate.py`).

## Validation (`tools/loo.py`)

Leave-one-out over the 37 launch comparables in the practice cases, scored with the contest's log-scale pinball loss:

| targets                                       | model | house baseline | 90% coverage |
|-----------------------------------------------|-------|----------------|--------------|
| GTA-like (rolling midnight, base weight ≥0.5) | 0.236 | 0.393          | 0.92         |
| all 37 launches                               | 0.471 | 0.930          | 0.87         |

On GTA-like launches, the share of outcomes below each quantile is 0.004 / 0.17 / 0.51 / 0.85 / 0.925 (ideal 0.05 /
0.25 / 0.5 / 0.75 / 0.95): the median is unbiased and the bands are a little conservative.

The model beats the baseline on 10 of 11 GTA-like launches and 30 of 37 overall. The GTA-like exception is The Last of
Us Part II, the biggest US-locked launch, which stayed flatter than predicted, though inside the band. The settings sit
on flat parts of small grids and were not tuned to the four practice cases, whose answers are not in the kit.

```
python3 tools/loo.py <case.in> [param=value ...]
python3 tools/make_synthetic.py <practice case.in> <dir> && MAKEFUN_INPUT_DIR=<dir> MAKEFUN_OUTPUT_DIR=<out> python3 main.py && python3 tools/validate.py <out>
```

## License

MIT, see `LICENSE`.
