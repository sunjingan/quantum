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
| WideA | 50000 | sqrt | vwap_0935_1030 | 7 | 79.77% | 111.21% | 2.54 | -13.20% | 69732 | 36.53% | 0.00% | 2.22 | 0.20 | 0.00 | 0.00% | 9.71% |
| WideA | 50000 | sqrt | twap_1000_1430 | 7 | 121.99% | 216.12% | 3.32 | -17.26% | 82421 | 16.38% | 0.00% | 2.17 | 0.15 | 0.00 | 0.00% | 3.10% |
| WideA | 50000 | sqrt | tail_vwap_1430_1455 | 7 | 133.41% | 250.08% | 3.35 | -15.73% | 85647 | 16.67% | 0.00% | 2.42 | 0.38 | 0.00 | 0.03% | 4.31% |
| WideA | 50000 | sqrt | split_0935_1455 | 7 | 122.20% | 216.85% | 3.33 | -16.28% | 82513 | 17.61% | 0.00% | 2.21 | 0.19 | 0.00 | 0.01% | 4.53% |

## Notes

- `partial/failed` includes capacity-limited partial fills, lot-size residuals, missing minute data, limit blocks, and insufficient cash.
- `actual_exposure` is computed from minute-executed holdings at execution-date close; compare it with daily signal `target_exposure`.
- This is an execution-layer stress test.  It is not a replacement for the daily research backtest and should not be used to retune ETF scores directly.