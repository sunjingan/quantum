# Friend F2/PIT Intraday Strategy

- window: `2020-01-01` to `2026-06-25`
- independent runner: does not modify ETF Loop engine or existing friend replication script
- universe: F2_v3 static core + latest available G2 PIT monthly dynamic pool
- signal: friend-style weighted log-linear momentum score using previous daily history + current intraday 09:50 price
- default execution: same-day 09:55 open after 09:50 signal; `next_day_open` included as latency stress
- costs: configurable commission bp and percentage slippage bp, applied on each side

## Reproduce

```bash
source activate.sh && python runs/etf_loop/run_friend_f2pit_strategy.py --start 2020-01-01 --end 2026-06-25
```

## Results

| variant | fill | N | dyn lb | cost/slip bp | dyn margin | overheat | premium | stop | ann | CAGR | Sharpe | DD | total | final | trades | dyn buys |
|---|---|---:|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| friend_f2pit_base | same_0955_open | 1 | True | 7.0 | 0.00 | 10%/50% | True | 0% | 15.95% | 6.73% | 0.39 | -69.39% | 49.92% | 753453 | 1039 | 128 |
| friend_f2pit_guarded | same_0955_open | 1 | True | 7.0 | 0.05 | 10%/50% | True | 8% | 15.18% | 5.93% | 0.37 | -69.41% | 43.11% | 719224 | 1029 | 112 |
| friend_f2pit_no_premium | same_0955_open | 1 | True | 7.0 | 0.05 | 10%/50% | False | 8% | 13.79% | 4.30% | 0.33 | -68.23% | 29.91% | 652851 | 1033 | 116 |
| friend_f2pit_base | same_0955_open | 3 | True | 7.0 | 0.00 | 10%/50% | True | 0% | 27.43% | 26.51% | 0.98 | -37.04% | 331.63% | 2160290 | 2109 | 255 |
| friend_f2pit_guarded | same_0955_open | 3 | True | 7.0 | 0.05 | 10%/50% | True | 8% | 30.80% | 30.93% | 1.11 | -34.63% | 434.34% | 2693823 | 2041 | 136 |
| friend_f2pit_no_premium | same_0955_open | 3 | True | 7.0 | 0.05 | 10%/50% | False | 8% | 30.19% | 30.07% | 1.08 | -34.54% | 412.82% | 2585328 | 2049 | 141 |
| friend_f2pit_base | next_day_open | 1 | True | 7.0 | 0.00 | 10%/50% | True | 0% | 19.71% | 10.49% | 0.47 | -60.63% | 85.85% | 941513 | 1039 | 128 |
| friend_f2pit_guarded | next_day_open | 1 | True | 7.0 | 0.05 | 10%/50% | True | 8% | 18.69% | 9.38% | 0.45 | -60.77% | 74.55% | 884279 | 1029 | 112 |
| friend_f2pit_no_premium | next_day_open | 1 | True | 7.0 | 0.05 | 10%/50% | False | 8% | 18.20% | 8.93% | 0.44 | -60.60% | 70.18% | 862114 | 1033 | 116 |
| friend_f2pit_base | next_day_open | 3 | True | 7.0 | 0.00 | 10%/50% | True | 0% | 27.79% | 27.06% | 1.01 | -32.44% | 342.85% | 2234583 | 2107 | 255 |
| friend_f2pit_guarded | next_day_open | 3 | True | 7.0 | 0.05 | 10%/50% | True | 8% | 31.87% | 32.49% | 1.17 | -32.24% | 474.54% | 2879631 | 2041 | 136 |
| friend_f2pit_no_premium | next_day_open | 3 | True | 7.0 | 0.05 | 10%/50% | False | 8% | 31.82% | 32.44% | 1.17 | -32.20% | 473.02% | 2871984 | 2049 | 141 |

## Notes

- This is not a replacement for the ETF Loop candidate; it is a separate friend-style strategy experiment.
- Same-day execution assumes ETF T+0 trading and minute bars are available after the 09:50 signal.
- If same-day performance collapses under `next_day_open`, the alpha is execution-timing sensitive.