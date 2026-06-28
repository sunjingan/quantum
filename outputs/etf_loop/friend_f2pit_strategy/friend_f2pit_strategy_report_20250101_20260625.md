# Friend F2/PIT Intraday Strategy

- window: `2025-01-01` to `2026-06-25`
- independent runner: does not modify ETF Loop engine or existing friend replication script
- universe: F2_v3 static core + latest available G2 PIT monthly dynamic pool
- signal: friend-style weighted log-linear momentum score using previous daily history + current intraday 09:50 price
- default execution: same-day 09:55 open after 09:50 signal; `next_day_open` included as latency stress
- costs: configurable commission bp and percentage slippage bp, applied on each side

## Reproduce

```bash
source activate.sh && python runs/etf_loop/run_friend_f2pit_strategy.py --start 2025-01-01 --end 2026-06-25
```

## Results

| variant | fill | N | dyn lb | cost/slip bp | dyn margin | overheat | premium | stop | ann | CAGR | Sharpe | DD | total | final | trades | dyn buys |
|---|---|---:|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| friend_f2pit_base | same_0955_open | 1 | True | 7.0 | 0.00 | 10%/50% | True | 0% | 68.58% | 83.21% | 1.72 | -20.97% | 134.66% | 1146650 | 289 | 22 |
| friend_f2pit_guarded | same_0955_open | 1 | True | 7.0 | 0.05 | 10%/50% | True | 8% | 65.43% | 77.53% | 1.64 | -20.97% | 124.46% | 1096814 | 283 | 17 |
| friend_f2pit_no_premium | same_0955_open | 1 | True | 7.0 | 0.05 | 10%/50% | False | 8% | 62.13% | 71.62% | 1.55 | -23.87% | 114.01% | 1045728 | 285 | 20 |
| friend_f2pit_base | same_0955_open | 3 | True | 7.0 | 0.00 | 10%/50% | True | 0% | 75.75% | 104.81% | 2.69 | -13.15% | 174.54% | 1342055 | 559 | 45 |
| friend_f2pit_guarded | same_0955_open | 3 | True | 7.0 | 0.05 | 10%/50% | True | 8% | 75.20% | 104.19% | 2.76 | -15.57% | 173.37% | 1333917 | 545 | 21 |
| friend_f2pit_no_premium | same_0955_open | 3 | True | 7.0 | 0.05 | 10%/50% | False | 8% | 74.82% | 103.27% | 2.72 | -15.59% | 171.64% | 1339557 | 545 | 24 |
| friend_f2pit_base | next_day_open | 1 | True | 7.0 | 0.00 | 10%/50% | True | 0% | 79.07% | 100.61% | 1.82 | -37.48% | 165.90% | 1324547 | 289 | 22 |
| friend_f2pit_guarded | next_day_open | 1 | True | 7.0 | 0.05 | 10%/50% | True | 8% | 75.33% | 93.25% | 1.73 | -38.10% | 152.30% | 1256786 | 283 | 17 |
| friend_f2pit_no_premium | next_day_open | 1 | True | 7.0 | 0.05 | 10%/50% | False | 8% | 72.29% | 88.33% | 1.71 | -32.23% | 143.33% | 1212083 | 285 | 20 |
| friend_f2pit_base | next_day_open | 3 | True | 7.0 | 0.00 | 10%/50% | True | 0% | 75.62% | 103.63% | 2.55 | -21.33% | 171.55% | 1347940 | 557 | 45 |
| friend_f2pit_guarded | next_day_open | 3 | True | 7.0 | 0.05 | 10%/50% | True | 8% | 75.14% | 103.34% | 2.63 | -21.93% | 171.01% | 1339119 | 543 | 21 |
| friend_f2pit_no_premium | next_day_open | 3 | True | 7.0 | 0.05 | 10%/50% | False | 8% | 72.92% | 99.06% | 2.58 | -20.22% | 163.02% | 1307031 | 543 | 24 |

## Notes

- This is not a replacement for the ETF Loop candidate; it is a separate friend-style strategy experiment.
- Same-day execution assumes ETF T+0 trading and minute bars are available after the 09:50 signal.
- If same-day performance collapses under `next_day_open`, the alpha is execution-timing sensitive.