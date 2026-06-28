# Minute Execution Backtest

- setting: `WideA`
- signal window: `2013-07-01` to `2026-06-25`
- trading_start: `2013-07-01`
- signal source: existing daily ETF Loop engine with detailed logs enabled
- minute overlay: independent target-portfolio execution simulator; it does not change ETF scores or candidate strategy logic
- constraints: minute turnover, max participation, limit-up buy block, limit-down sell block, no-minute-data rejection

## Reproduce

```bash
source activate.sh && python runs/etf_loop/run_minute_execution_backtest.py --setting WideA --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25
```

## Summary

| setting | capital | mode | roundtrip bp | ann | CAGR | Sharpe | DD | final | failed | capacity-limited | no data | no turnover | limit block | avg slip bp | avg participation | avg abs exposure gap |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| WideA | 1000000 | open_0935 | 7 | 11.74% | 10.33% | 0.59 | -52.94% | 3387136 | 23.76% | 46.55% | 2.38% | 14.05% | 0.04% | 15.50 | 6.40% | 28.28% |
| WideA | 1000000 | vwap_0935_1030 | 7 | 17.79% | 17.07% | 0.88 | -32.13% | 7070927 | 10.74% | 19.08% | 3.10% | 1.33% | 0.02% | 8.39 | 2.80% | 8.33% |
| WideA | 1000000 | twap_0935_1030 | 7 | 17.89% | 17.20% | 0.89 | -32.00% | 7164579 | 10.69% | 19.25% | 3.11% | 1.33% | 0.02% | 8.44 | 2.82% | 8.39% |
| WideA | 1000000 | tail_vwap_1430_1455 | 7 | 16.76% | 15.74% | 0.81 | -36.98% | 6137097 | 9.38% | 28.76% | 2.93% | 0.76% | 0.15% | 10.56 | 3.85% | 11.07% |
| WideA | 1000000 | t2_open_0935 | 7 | 11.54% | 9.56% | 0.50 | -52.83% | 3105717 | 22.84% | 47.40% | 2.39% | 13.25% | 0.05% | 15.60 | 6.42% | 27.48% |

## Notes

- `partial/failed` includes capacity-limited partial fills, lot-size residuals, missing minute data, limit blocks, and insufficient cash.
- `actual_exposure` is computed from minute-executed holdings at execution-date close; compare it with daily signal `target_exposure`.
- This is an execution-layer stress test.  It is not a replacement for the daily research backtest and should not be used to retune ETF scores directly.