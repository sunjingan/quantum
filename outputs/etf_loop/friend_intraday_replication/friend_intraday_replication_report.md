# Friend Intraday Replication

- window: `2020-01-01` to `2026-06-25`
- pool: 9 ETFs from the friend baseline
- signal: previous daily close history + current-day intraday last price at configured signal time
- exact JQ cost mode: fixed price slippage 0.001 yuan/share plus 2bp fund commission with 1 yuan minimum
- no independent stop loss: original JoinQuant code only sells when the current holding is not the top-ranked ETF
- data: `data/local_etf_data/2000-2025/{1min,5min}` and `data/local_etf_data/2026/2026_{1分钟,5分钟}`
- note: this is independent from the daily ETF Loop engine; old daily `friend_mode` remains disabled.

## Reproduce

```bash
source activate.sh && python runs/etf_loop/run_friend_intraday_replication.py --start 2020-01-01 --end 2026-06-25 --frequency 1min --adjust none --ranking-modes jq_auto,jq_simple --fill-modes same_0950_close,same_0951_open,same_0955_open,next_day_open
```

## Results

| variant | rank | freq | fill mode | adjust | exact cost | ann | CAGR | sharpe | dd | total | final | trades | buys | sells |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| simple25d | jq_simple | 1min | same_0950_close | none | True | 49.19% | 56.52% | 1.65 | -25.47% | 1521.58% | 8203898 | 417 | 209 | 208 |
| simple25d | jq_simple | 1min | same_0951_open | none | True | 49.45% | 56.92% | 1.66 | -25.23% | 1547.47% | 8334854 | 417 | 209 | 208 |
| simple25d | jq_simple | 1min | same_0955_open | none | True | 49.49% | 56.94% | 1.66 | -25.01% | 1548.89% | 8332489 | 417 | 209 | 208 |
| simple25d | jq_simple | 1min | next_day_open | none | True | 27.63% | 26.12% | 0.93 | -37.64% | 322.94% | 2109503 | 417 | 209 | 208 |
| full_friend_logic | jq_auto | 1min | same_0950_close | none | True | 46.96% | 53.73% | 1.67 | -24.30% | 1349.60% | 7252749 | 467 | 234 | 233 |
| full_friend_logic | jq_auto | 1min | same_0951_open | none | True | 47.07% | 53.90% | 1.67 | -24.45% | 1359.93% | 7304427 | 467 | 234 | 233 |
| full_friend_logic | jq_auto | 1min | same_0955_open | none | True | 47.71% | 54.89% | 1.69 | -24.62% | 1419.36% | 7588782 | 467 | 234 | 233 |
| full_friend_logic | jq_auto | 1min | next_day_open | none | True | 46.57% | 52.63% | 1.59 | -21.43% | 1283.93% | 7077465 | 467 | 234 | 233 |

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