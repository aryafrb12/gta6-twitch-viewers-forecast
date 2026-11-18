# GTA VI launch-day Twitch viewers: comparable-launch forecast

[![make.fun](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/aryafrb12/gta6-twitch-viewers-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/aryafrb12/gta6-twitch-viewers-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

Entry for make.fun `gta6-twitch-ccu-forecast-01`. `python3 main.py` reads every `*.in` in `$MAKEFUN_INPUT_DIR`
(default `/input`) and writes `<id>.out` (five quantiles for each of hours 2–24) to `$MAKEFUN_OUTPUT_DIR` (default
`/output`). It uses only the standard library, is deterministic, and runs in about 0.2 s.

## Model (`model.py`)

1. **Launch curves.** For each comparable launch, take its release UTC day and compute
   `y_h = ln(viewers_h / viewers_1)` for h = 2..24. GTA VI unlocks at midnight local time, rolling (NZ 11:00Z,
   central Europe 23:00Z, UK 00:00Z, US East 05:00Z, US West 08:00Z). Its UTC day is therefore aligned the same way
   as the other rolling-midnight launches, so no re-alignment is needed. GTA VI's own pre-release category history
   is excluded from the pool because it holds no launch.
2. **Similarity weights.**
   - Tier: comparable 1, early-access-contaminated 0.35, weak 0.1.
   - Unlock style, read from the comparable's notes: a single simultaneous global unlock ×0.12, rolling consoles plus
     simultaneous PC ×0.6, unverified ×0.6.
   - Platforms: a launch that includes PC ×0.6, because GTA VI is console only.
   - An hour 1 under 5k (the category had not really launched at 00Z) ×0.15.
   - A Gaussian kernel on `ln(hour 1)` (bandwidth 1.0). Big launches stay flatter through the day than small ones.
     The target's size is capped at the 3rd-largest comparable, so an off-scale hour 1 (GTA VI) is treated as "among
     the biggest" instead of matching only one or two launches.
3. **Evening-before adjustment.** The ratio of the 5 hours before the day (19:00–24:00Z) to hour 1 predicts how much
   the day rises later. A weighted regression slope on `ln(ev)`, shrunk by half, moves every comparable to the
   target's ratio.
4. **Location and spread.** Each hour's median is the average of the weighted mean and the weighted median. Its
   spread is the weighted SD around that location, which is:
   - inflated for the effective sample size (`sqrt(1+1/neff)`, and more when `neff < 4`);
   - given a floor of `0.10 + 0.02·sqrt(h-1)`;
   - given fatter 5%/95% tails (×1.15);
   - widened by an extra 0.15 log units when hour 1 is above every comparable (an unseen mega launch).
5. Quantiles are `hour1 · exp(loc + z·sd)`. If anything fails, the program falls back to the baseline's random-walk
   band, so the case stays valid.

## Validation (`tools/loo.py`)

Leave-one-out over the 37 launch comparables in the practice cases. Each launch is forecast from all the others and
scored with the contest's log-scale pinball loss:

| targets                                       | model | house baseline | 90% coverage |
|-----------------------------------------------|-------|----------------|--------------|
| GTA-like (rolling midnight, base weight ≥0.5) | 0.232 | 0.393          | 0.92         |
| all 37 launches                               | 0.484 | 0.930          | 0.85         |

The model beats the baseline on all 11 GTA-like targets and on 28 of 37 overall. It does worse on the very largest
PC-heavy launches (Elden Ring, Cyberpunk), which held flat all day. The settings sit on a flat part of a small grid
and were not tuned to the four practice cases. Those cases' answers are not in the kit, so they were only checked for
valid output.

```
python3 tools/loo.py <case.in> [param=value ...]
```

## License

MIT, see `LICENSE`.
