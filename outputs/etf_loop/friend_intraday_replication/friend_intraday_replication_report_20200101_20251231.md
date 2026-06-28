# Friend Intraday Replication

- window: `2020-01-01` to `2025-12-31`
- pool: 9 ETFs from the friend baseline
- signal: previous daily close history + current-day intraday last price at configured signal time
- exact JQ cost mode: fixed price slippage 0.001 yuan/share plus 2bp fund commission with 1 yuan minimum
- no independent stop loss: original JoinQuant code only sells when the current holding is not the top-ranked ETF
- data: `data/local_etf_data/2000-2025/{1min,5min}` and `data/local_etf_data/2026/2026_{1分钟,5分钟}`
- note: this is independent from the daily ETF Loop engine; old daily `friend_mode` remains disabled.

## Reproduce

```bash
source activate.sh && python runs/etf_loop/run_friend_intraday_replication.py --start 2020-01-01 --end 2025-12-31 --frequency 1min --adjust none --ranking-modes jq_auto,jq_simple --fill-modes same_0950_close,same_0951_open,same_0955_open,next_day_open
```

## Results

| variant | rank | freq | fill mode | adjust | exact cost | ann | CAGR | sharpe | dd | total | final | trades | buys | sells |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| simple25d | jq_simple | 1min | same_0950_close | none | True | 42.78% | 47.50% | 1.52 | -25.47% | 841.69% | 4764178 | 379 | 190 | 189 |
| simple25d | jq_simple | 1min | same_0951_open | none | True | 43.08% | 47.92% | 1.53 | -25.23% | 857.43% | 4843842 | 379 | 190 | 189 |
| simple25d | jq_simple | 1min | same_0955_open | none | True | 43.30% | 48.22% | 1.54 | -25.01% | 868.63% | 4894851 | 379 | 190 | 189 |
| simple25d | jq_simple | 1min | next_day_open | none | True | 23.63% | 21.75% | 0.84 | -37.64% | 211.06% | 1551457 | 379 | 190 | 189 |
| full_friend_logic | jq_auto | 1min | same_0950_close | none | True | 48.55% | 56.60% | 1.78 | -16.84% | 1230.43% | 6656486 | 411 | 206 | 205 |
| full_friend_logic | jq_auto | 1min | same_0951_open | none | True | 48.76% | 56.92% | 1.79 | -16.82% | 1246.20% | 6735428 | 411 | 206 | 205 |
| full_friend_logic | jq_auto | 1min | same_0955_open | none | True | 49.40% | 57.94% | 1.81 | -16.64% | 1297.18% | 6978535 | 411 | 206 | 205 |
| full_friend_logic | jq_auto | 1min | next_day_open | none | True | 43.64% | 48.65% | 1.54 | -21.43% | 883.12% | 5027699 | 411 | 206 | 205 |

## Friend Claim

- claimed annual return: `66.04%`
- claimed max drawdown: `-16.53%`

## Interpretation

- `same_0950_close` is optimistic because signal and fill use the same bar close.
- `same_0951_open` is the first more tradeable T+0 assumption available from 1-minute bars.
- `same_0955_open` is a conservative T+0 assumption available from 5-minute bars.
- `next_day_open` is included only as a latency comparison; it is not the friend's intended execution model.
- The original code's intraday/T+0 execution assumption is material: switching to next-day open cuts performance sharply in the simple 25d variant and changes drawdown behavior.
- Remaining gaps can still come from JoinQuant fill simulation, exact current_data timing, unit_net_value source, and any unpublished code differences.