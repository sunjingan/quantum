# Minute Execution Backtest

- setting: `WideA`
- signal window: `2025-10-01` to `2026-06-25`
- trading_start: `2026-01-02`
- signal source: existing daily ETF Loop engine with detailed logs enabled
- minute overlay: independent target-portfolio execution simulator; it does not change ETF scores or candidate strategy logic
- constraints: minute turnover, max participation, limit-up buy block, limit-down sell block, no-minute-data rejection
- slippage model: `sqrt`

## Reproduce

```bash
source activate.sh && python runs/etf_loop/run_minute_execution_backtest.py --setting WideA --start 2025-10-01 --trading-start 2026-01-02 --end 2026-06-25
```

## Summary

| setting | capital | model | mode | roundtrip bp | ann | CAGR | Sharpe | DD | final | failed | capacity-limited | avg slip bp | impact bp | extra bp | avg participation | avg abs exposure gap |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| WideA | 50000 | sqrt | vwap_0935_1030 | 7 | 79.53% | 110.68% | 2.53 | -13.22% | 69657 | 36.63% | 0.00% | 2.32 | 0.29 | 0.00 | 0.00% | 9.70% |
| WideA | 50000 | sqrt | twap_1000_1430 | 7 | 121.63% | 214.98% | 3.31 | -17.32% | 82293 | 16.38% | 0.00% | 2.25 | 0.22 | 0.00 | 0.00% | 3.09% |
| WideA | 50000 | sqrt | tail_vwap_1430_1455 | 7 | 132.87% | 248.25% | 3.34 | -15.75% | 85453 | 16.63% | 0.00% | 2.63 | 0.57 | 0.00 | 0.03% | 4.31% |
| WideA | 50000 | sqrt | split_0935_1455 | 7 | 121.97% | 216.15% | 3.33 | -16.26% | 82434 | 16.92% | 0.00% | 2.31 | 0.28 | 0.00 | 0.01% | 4.53% |

## Notes

- `partial/failed` includes capacity-limited partial fills, lot-size residuals, missing minute data, limit blocks, and insufficient cash.
- `actual_exposure` is computed from minute-executed holdings at execution-date close; compare it with daily signal `target_exposure`.
- This is an execution-layer stress test.  It is not a replacement for the daily research backtest and should not be used to retune ETF scores directly.