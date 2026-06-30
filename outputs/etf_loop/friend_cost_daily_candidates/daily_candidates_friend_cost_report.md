# Daily Candidates Under Friend/JoinQuant Cost

## Cost Model

- Strategy logic is unchanged: daily close signal, next trading day open execution.
- Changed only costs: `open_cost=0.0002`, `close_cost=0.0002`, `slippage=0`, `fixed_price_slippage=0.001` yuan/share.
- This approximates JoinQuant `FixedSlippage(0.001)` plus fund commission 2bp/side.
- The 1 yuan minimum commission is not modeled; impact is negligible for the tested portfolio size.
- Fixed price slippage is embedded in execution price: buy at `open+0.001`, sell at `open-0.001`.

## Reproduce

```bash
source activate.sh && python runs/etf_loop/run_daily_candidate_friend_cost.py --force
```

## Results

| setting | start | end | annual | sharpe | DD | total | final | trades | weighted fixed slip bp/side | weighted all-in bp/side |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| F2_CAP_MA60 | 2013-07-01 | 2026-06-25 | 24.05% | 1.22 | -21.78% | 1483.79% | 7918940 | 7440 | 6.23 | 8.23 |
| WideA | 2013-07-01 | 2026-06-25 | 31.92% | 1.39 | -20.57% | 3800.96% | 19504822 | 5879 | 6.00 | 8.00 |
| F2_CAP_MA60 | 2020-01-01 | 2026-06-25 | 33.08% | 1.44 | -20.83% | 560.00% | 3299985 | 4399 | 6.22 | 8.22 |
| WideA | 2020-01-01 | 2026-06-25 | 45.67% | 1.66 | -20.49% | 1243.91% | 6719568 | 3257 | 5.93 | 7.93 |

## Interpretation Notes

- Friend's cost is price-dependent. For a 1 yuan ETF, 0.001 yuan is 10bp/side; for a 2 yuan ETF it is 5bp/side.
- Compare these rows against the same setting and same period, not against the long-period candidate table directly.