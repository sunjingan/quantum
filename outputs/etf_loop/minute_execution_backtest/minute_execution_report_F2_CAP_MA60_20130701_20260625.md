# Minute Execution Backtest

- setting: `F2_CAP_MA60`
- signal window: `2013-07-01` to `2026-06-25`
- trading_start: `2013-07-01`
- signal source: existing daily ETF Loop engine with detailed logs enabled
- minute overlay: independent target-portfolio execution simulator; it does not change ETF scores or candidate strategy logic
- constraints: minute turnover, max participation, limit-up buy block, limit-down sell block, no-minute-data rejection

## Reproduce

```bash
source activate.sh && python runs/etf_loop/run_minute_execution_backtest.py --setting F2_CAP_MA60 --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25
```

## Summary

| setting | capital | mode | roundtrip bp | ann | CAGR | Sharpe | DD | final | failed | capacity-limited | no data | no turnover | limit block | avg slip bp | avg participation | avg abs exposure gap |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| F2_CAP_MA60 | 1000000 | open_0935 | 7 | 9.81% | 8.28% | 0.50 | -58.59% | 2682078 | 24.65% | 43.52% | 2.17% | 13.28% | 0.02% | 14.68 | 5.98% | 22.02% |
| F2_CAP_MA60 | 1000000 | vwap_0935_1030 | 7 | 16.43% | 15.67% | 0.85 | -32.26% | 6090589 | 11.84% | 15.44% | 2.82% | 1.15% | 0.03% | 7.30 | 2.31% | 5.93% |
| F2_CAP_MA60 | 1000000 | twap_0935_1030 | 7 | 16.61% | 15.90% | 0.86 | -32.08% | 6237637 | 11.73% | 15.61% | 2.83% | 1.16% | 0.03% | 7.35 | 2.33% | 5.96% |
| F2_CAP_MA60 | 1000000 | tail_vwap_1430_1455 | 7 | 15.55% | 14.63% | 0.80 | -37.69% | 5440111 | 11.28% | 24.68% | 2.67% | 0.69% | 0.10% | 9.53 | 3.37% | 7.87% |
| F2_CAP_MA60 | 1000000 | t2_open_0935 | 7 | 11.53% | 9.66% | 0.51 | -51.42% | 3139508 | 23.55% | 45.51% | 2.16% | 12.57% | 0.04% | 15.04 | 6.15% | 21.96% |

## Notes

- `partial/failed` includes capacity-limited partial fills, lot-size residuals, missing minute data, limit blocks, and insufficient cash.
- `actual_exposure` is computed from minute-executed holdings at execution-date close; compare it with daily signal `target_exposure`.
- This is an execution-layer stress test.  It is not a replacement for the daily research backtest and should not be used to retune ETF scores directly.