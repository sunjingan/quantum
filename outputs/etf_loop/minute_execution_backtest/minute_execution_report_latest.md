# Minute Execution Backtest

- setting: `WideA`
- signal window: `2013-07-01` to `2026-06-25`
- trading_start: `2013-07-01`
- signal source: existing daily ETF Loop engine with detailed logs enabled
- minute overlay: independent target-portfolio execution simulator; it does not change ETF scores or candidate strategy logic
- constraints: minute turnover, max participation, limit-up buy block, limit-down sell block, no-minute-data rejection
- slippage model: `tiered`

## Reproduce

```bash
source activate.sh && python runs/etf_loop/run_minute_execution_backtest.py --setting WideA --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25
```

## Summary

| setting | capital | model | mode | roundtrip bp | ann | CAGR | Sharpe | DD | final | failed | capacity-limited | avg slip bp | impact bp | extra bp | avg participation | avg abs exposure gap |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| WideA | 50000 | tiered | open_0935 | 7 | 15.77% | 14.86% | 0.81 | -31.83% | 278988 | 35.36% | 19.93% | 9.94 | 7.18 | 0.00 | 3.27% | 12.50% |
| WideA | 50000 | tiered | vwap_0935_1030 | 7 | 22.71% | 22.79% | 1.09 | -35.14% | 638894 | 23.07% | 2.52% | 4.11 | 1.76 | 0.00 | 0.75% | 4.55% |
| WideA | 50000 | tiered | twap_0935_1030 | 7 | 22.86% | 22.99% | 1.10 | -34.78% | 651811 | 23.15% | 2.59% | 4.14 | 1.78 | 0.00 | 0.77% | 4.54% |
| WideA | 50000 | tiered | twap_1000_1430 | 7 | 25.93% | 26.69% | 1.22 | -36.69% | 941652 | 21.61% | 0.99% | 3.28 | 1.06 | 0.00 | 0.42% | 3.67% |
| WideA | 50000 | tiered | tail_vwap_1430_1455 | 7 | 23.82% | 23.99% | 1.11 | -33.18% | 720483 | 21.80% | 6.66% | 5.69 | 3.10 | 0.00 | 1.41% | 5.53% |
| WideA | 50000 | tiered | split_0935_1455 | 7 | 25.33% | 25.99% | 1.20 | -34.32% | 878643 | 21.88% | 1.60% | 3.69 | 1.41 | 0.00 | 0.58% | 3.98% |
| WideA | 50000 | tiered | t2_open_0935 | 7 | 18.41% | 16.88% | 0.75 | -37.28% | 346259 | 32.89% | 22.62% | 10.51 | 7.81 | 0.00 | 3.60% | 14.16% |

## Notes

- `partial/failed` includes capacity-limited partial fills, lot-size residuals, missing minute data, limit blocks, and insufficient cash.
- `actual_exposure` is computed from minute-executed holdings at execution-date close; compare it with daily signal `target_exposure`.
- This is an execution-layer stress test.  It is not a replacement for the daily research backtest and should not be used to retune ETF scores directly.