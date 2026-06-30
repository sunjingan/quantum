# Friend Pool Ablation

- window: `2020-01-01` to `2026-06-25`
- purpose: keep friend-style intraday scoring/execution/costs fixed, change only ETF pool
- signal: previous daily history + current 09:50 intraday price
- execution/cost default: 09:55 same-day open, commission 1.5bp/side + slippage 2bp/side
- pool modes: `friend9`, `f2_static`, `f2_pit_union`, `pit_pure`

## Reproduce

```bash
source activate.sh && python runs/etf_loop/run_friend_pool_ablation.py --start 2020-01-01 --end 2026-06-25
```

## Results

| pool | fill | N | logic | core | dyn_avg | ann | CAGR | Sharpe | DD | total | final | trades | dyn buys |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| friend9 | same_0955_open | 1 | friend_like | 9 | 0.0 | 48.45% | 55.98% | 1.71 | -24.69% | 1487.09% | 7946267 | 465 | 0 |
| friend9 | same_0955_open | 1 | guarded | 9 | 0.0 | 48.40% | 56.09% | 1.73 | -19.61% | 1493.63% | 7978987 | 443 | 0 |
| friend9 | same_0955_open | 3 | friend_like | 9 | 0.0 | 30.42% | 33.31% | 1.67 | -18.14% | 497.67% | 3000736 | 768 | 0 |
| friend9 | same_0955_open | 3 | guarded | 9 | 0.0 | 27.85% | 29.80% | 1.48 | -18.11% | 406.32% | 2542091 | 746 | 0 |
| f2_static | same_0955_open | 1 | friend_like | 44 | 0.0 | 22.21% | 13.98% | 0.55 | -68.98% | 125.64% | 1133961 | 1035 | 0 |
| f2_static | same_0955_open | 1 | guarded | 44 | 0.0 | 17.18% | 8.50% | 0.43 | -71.25% | 66.07% | 834608 | 1037 | 0 |
| f2_static | same_0955_open | 3 | friend_like | 44 | 0.0 | 35.68% | 37.45% | 1.29 | -30.08% | 622.68% | 3643320 | 1921 | 0 |
| f2_static | same_0955_open | 3 | guarded | 44 | 0.0 | 34.42% | 35.90% | 1.26 | -32.81% | 573.49% | 3395300 | 1889 | 0 |
| f2_pit_union | same_0955_open | 1 | friend_like | 44 | 27.8 | 20.59% | 11.56% | 0.49 | -64.83% | 97.48% | 992439 | 1127 | 122 |
| f2_pit_union | same_0955_open | 1 | guarded | 44 | 27.8 | 15.18% | 5.93% | 0.37 | -69.41% | 43.11% | 719224 | 1029 | 112 |
| f2_pit_union | same_0955_open | 3 | friend_like | 44 | 27.8 | 32.10% | 32.72% | 1.16 | -33.39% | 481.25% | 2909107 | 2233 | 274 |
| f2_pit_union | same_0955_open | 3 | guarded | 44 | 27.8 | 30.80% | 30.93% | 1.11 | -34.63% | 434.34% | 2693823 | 2041 | 136 |
| pit_pure | same_0955_open | 1 | friend_like | 0 | 27.8 | 6.34% | -2.20% | 0.16 | -76.30% | -12.90% | 435762 | 915 | 458 |
| pit_pure | same_0955_open | 1 | guarded | 0 | 27.8 | 8.73% | -0.16% | 0.22 | -73.53% | -0.98% | 495420 | 811 | 406 |
| pit_pure | same_0955_open | 3 | friend_like | 0 | 27.8 | 18.71% | 16.92% | 0.76 | -32.46% | 164.34% | 1325200 | 1799 | 901 |
| pit_pure | same_0955_open | 3 | guarded | 0 | 27.8 | 15.11% | 12.59% | 0.60 | -34.97% | 109.00% | 1047766 | 1649 | 826 |

## Interpretation

- If `friend9` dominates under the same logic, the original result is highly pool-dependent.
- If `f2_static` collapses but `f2_pit_union` improves, dynamic PIT contributes useful hot-spot coverage.
- If `pit_pure` has high turnover/drawdown, PIT alone is too noisy for friend-style Top1 rotation.