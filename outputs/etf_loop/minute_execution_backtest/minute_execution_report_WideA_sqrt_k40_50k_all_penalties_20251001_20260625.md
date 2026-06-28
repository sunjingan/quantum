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
| WideA | 50000 | sqrt | vwap_0935_1030 | 7 | 72.10% | 95.58% | 2.29 | -13.65% | 67429 | 36.95% | 0.00% | 8.39 | 0.20 | 6.01 | 0.00% | 9.65% |
| WideA | 50000 | sqrt | twap_1000_1430 | 7 | 115.71% | 196.90% | 3.15 | -17.64% | 80212 | 16.99% | 0.00% | 5.61 | 0.15 | 3.36 | 0.00% | 3.00% |
| WideA | 50000 | sqrt | tail_vwap_1430_1455 | 7 | 127.90% | 231.33% | 3.21 | -16.06% | 83634 | 20.21% | 0.00% | 5.51 | 0.36 | 2.97 | 0.03% | 5.13% |
| WideA | 50000 | sqrt | split_0935_1455 | 7 | 112.79% | 188.40% | 3.07 | -16.77% | 79212 | 18.22% | 0.00% | 7.77 | 0.18 | 5.47 | 0.01% | 4.44% |

## Notes

- `partial/failed` includes capacity-limited partial fills, lot-size residuals, missing minute data, limit blocks, and insufficient cash.
- `actual_exposure` is computed from minute-executed holdings at execution-date close; compare it with daily signal `target_exposure`.
- This is an execution-layer stress test.  It is not a replacement for the daily research backtest and should not be used to retune ETF scores directly.