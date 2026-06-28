# Minute Execution Backtest

- setting: `WideA`
- signal window: `2013-07-01` to `2026-06-25`
- trading_start: `2013-07-01`
- signal source: existing daily ETF Loop engine with detailed logs enabled
- minute overlay: independent target-portfolio execution simulator; it does not change ETF scores or candidate strategy logic
- constraints: minute turnover, max participation, limit-up buy block, limit-down sell block, no-minute-data rejection
- slippage model: `sqrt`

## Reproduce

```bash
source activate.sh && python runs/etf_loop/run_minute_execution_backtest.py --setting WideA --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25
```

## Summary

| setting | capital | model | mode | roundtrip bp | ann | CAGR | Sharpe | DD | final | failed | capacity-limited | avg slip bp | impact bp | extra bp | avg participation | avg abs exposure gap |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| WideA | 50000 | sqrt | vwap_0935_1030 | 7 | 17.35% | 16.39% | 0.83 | -40.54% | 328800 | 24.44% | 2.29% | 8.83 | 2.00 | 4.48 | 0.69% | 4.50% |
| WideA | 50000 | sqrt | twap_1000_1430 | 7 | 23.18% | 23.26% | 1.09 | -37.01% | 669926 | 22.21% | 0.92% | 5.73 | 1.24 | 2.05 | 0.41% | 3.65% |
| WideA | 50000 | sqrt | tail_vwap_1430_1455 | 7 | 21.76% | 21.45% | 1.01 | -33.55% | 557731 | 22.13% | 6.51% | 8.21 | 4.13 | 2.08 | 1.39% | 5.47% |
| WideA | 50000 | sqrt | split_0935_1455 | 7 | 20.06% | 19.52% | 0.95 | -36.30% | 456967 | 23.43% | 1.37% | 8.30 | 1.59 | 4.31 | 0.53% | 3.84% |

## Notes

- `partial/failed` includes capacity-limited partial fills, lot-size residuals, missing minute data, limit blocks, and insufficient cash.
- `actual_exposure` is computed from minute-executed holdings at execution-date close; compare it with daily signal `target_exposure`.
- This is an execution-layer stress test.  It is not a replacement for the daily research backtest and should not be used to retune ETF scores directly.