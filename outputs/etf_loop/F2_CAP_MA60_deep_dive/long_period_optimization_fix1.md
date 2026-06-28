# Long Period Optimization FIX1

- window: 2013-07-01 to 2026-06-25
- friend_mode: not used
- dynamic cap enforced after vol/score weighting

| pool | variant | ann | sharpe | dd | final |
|---|---|---:|---:|---:|---:|
| F2_CAP_MA60 | Premium(soft) | 30.78% | 1.56 | -18.47% | 18413435 |
| F2_CAP_MA60 | Baseline | 30.54% | 1.54 | -18.45% | 17827823 |
| F2_CAP_MA60 | Premium(soft)+VolW | 25.14% | 1.44 | -18.26% | 9587143 |
| F2_STATIC | Baseline | 28.59% | 1.48 | -17.39% | 14116550 |
| F2_STATIC | Premium(soft) | 28.36% | 1.47 | -17.38% | 13738963 |
| F2_STATIC | Premium(soft)+VolW | 23.01% | 1.35 | -17.44% | 7411611 |
| ORIG38_STATIC | Baseline | 22.34% | 1.46 | -16.43% | 7060913 |
| ORIG38_STATIC | Premium(soft) | 21.71% | 1.44 | -16.48% | 6553604 |
| ORIG38_STATIC | Premium(soft)+VolW | 14.14% | 1.13 | -13.93% | 2654179 |