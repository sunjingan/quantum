# Filtered Dynamic Observation Pool

- pool: `F2_STATIC` core with capped dynamic PIT supplement
- dynamic filters: list age >= 180 days, 5d avg amount >= 5e7, trend MA60 gate, overheat penalty, trend/short momentum filters on
- experiment tags are isolated and do not overwrite any existing F2 results

## Results

| label | tag | annual | sharpe | dd | total | final | trades | dynamic buys |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| CAP2 | DYNOBS_F2_STATIC_FILTERED_CAP2 | 29.69% | 1.46 | -19.33% | 3066.42% | 15,832,103 | 7446 | 719 |
| CAP1 | DYNOBS_F2_STATIC_FILTERED_CAP1 | 28.83% | 1.44 | -17.81% | 2758.19% | 14,290,960 | 7345 | 566 |

## Baseline Context

| benchmark | annual | sharpe | dd | total | final |
|---|---:|---:|---:|---:|---:|
| F2_STATIC_Baseline | 28.59% | 1.48 | -17.39% | 2723.31% | 14,116,550 |
| F2_CAP_MA60_Baseline | 30.54% | 1.54 | -18.45% | 3465.56% | 17,827,823 |

## Notes

- 这组实验只改动态补漏池的候选过滤，不动原 F2 静态池。
- 如果 filtered dynamic 仍低于静态基线，说明动态池更适合做候选观察，而不是常态补漏。