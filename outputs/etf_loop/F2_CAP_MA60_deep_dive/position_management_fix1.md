# Position Management FIX1

- engine: dynamic pool caps are re-applied after score/vol weighting
- friend_mode: not used

| period | variant | ann | sharpe | dd | final |
|---|---|---:|---:|---:|---:|
| 2026_NOWARMUP | Dynamic holdings (3-8) | 114.62% | 3.34 | -16.86% | 1031060 |
| 2026_NOWARMUP | DynHold + ScoreW | 111.77% | 2.99 | -17.93% | 1004763 |
| 2026_NOWARMUP | Baseline (equal-weight 5) | 93.34% | 3.35 | -15.61% | 907070 |
| 2026_NOWARMUP | Score-weighted | 86.18% | 2.55 | -18.30% | 854653 |
| 2026_NOWARMUP | Score+Vol (Kelly-style) | 72.26% | 2.34 | -18.51% | 783930 |
| LONG_2013_2026 | Score-weighted | 36.39% | 1.56 | -19.26% | 33654866 |
| LONG_2013_2026 | DynHold + ScoreW | 35.86% | 1.39 | -31.03% | 29222876 |
| LONG_2013_2026 | Dynamic holdings (3-8) | 35.11% | 1.50 | -26.99% | 28601698 |
| LONG_2013_2026 | Score+Vol (Kelly-style) | 34.48% | 1.61 | -18.91% | 27955361 |
| LONG_2013_2026 | Baseline (equal-weight 5) | 30.54% | 1.54 | -18.45% | 17827823 |