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
| WideA | 50000 | sqrt | vwap_0935_1030 | 7 | 79.91% | 111.49% | 2.54 | -13.19% | 69773 | 36.87% | 0.00% | 2.11 | 0.10 | 0.00 | 0.00% | 9.70% |
| WideA | 50000 | sqrt | twap_1000_1430 | 7 | 122.24% | 216.92% | 3.33 | -17.26% | 82511 | 15.84% | 0.00% | 2.08 | 0.07 | 0.00 | 0.00% | 3.11% |
| WideA | 50000 | sqrt | tail_vwap_1430_1455 | 7 | 133.88% | 251.73% | 3.37 | -15.73% | 85821 | 16.23% | 0.00% | 2.21 | 0.19 | 0.00 | 0.03% | 4.30% |
| WideA | 50000 | sqrt | split_0935_1455 | 7 | 122.44% | 217.62% | 3.34 | -16.26% | 82599 | 16.99% | 0.00% | 2.11 | 0.09 | 0.00 | 0.01% | 4.56% |

## Notes

- `partial/failed` includes capacity-limited partial fills, lot-size residuals, missing minute data, limit blocks, and insufficient cash.
- `actual_exposure` is computed from minute-executed holdings at execution-date close; compare it with daily signal `target_exposure`.
- This is an execution-layer stress test.  It is not a replacement for the daily research backtest and should not be used to retune ETF scores directly.