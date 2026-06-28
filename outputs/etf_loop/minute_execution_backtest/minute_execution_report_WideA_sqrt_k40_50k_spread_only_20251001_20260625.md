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
| WideA | 50000 | sqrt | vwap_0935_1030 | 7 | 75.31% | 101.99% | 2.39 | -13.48% | 68381 | 38.98% | 0.00% | 6.01 | 0.19 | 3.67 | 0.00% | 9.66% |
| WideA | 50000 | sqrt | twap_1000_1430 | 7 | 116.82% | 200.20% | 3.18 | -17.59% | 80593 | 17.45% | 0.00% | 4.98 | 0.14 | 2.78 | 0.00% | 3.02% |
| WideA | 50000 | sqrt | tail_vwap_1430_1455 | 7 | 129.22% | 235.71% | 3.24 | -16.00% | 84107 | 20.21% | 0.00% | 4.96 | 0.37 | 2.44 | 0.03% | 5.14% |
| WideA | 50000 | sqrt | split_0935_1455 | 7 | 117.53% | 202.42% | 3.20 | -16.55% | 80855 | 18.22% | 0.00% | 5.20 | 0.19 | 2.91 | 0.01% | 4.49% |

## Notes

- `partial/failed` includes capacity-limited partial fills, lot-size residuals, missing minute data, limit blocks, and insufficient cash.
- `actual_exposure` is computed from minute-executed holdings at execution-date close; compare it with daily signal `target_exposure`.
- This is an execution-layer stress test.  It is not a replacement for the daily research backtest and should not be used to retune ETF scores directly.