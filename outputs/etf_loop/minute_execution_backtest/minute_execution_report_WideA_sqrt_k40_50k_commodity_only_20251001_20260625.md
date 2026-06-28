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
| WideA | 50000 | sqrt | vwap_0935_1030 | 7 | 79.29% | 110.19% | 2.52 | -13.22% | 69588 | 37.15% | 0.00% | 2.33 | 0.20 | 0.11 | 0.00% | 9.70% |
| WideA | 50000 | sqrt | twap_1000_1430 | 7 | 121.48% | 214.50% | 3.31 | -17.33% | 82240 | 15.50% | 0.00% | 2.32 | 0.15 | 0.14 | 0.00% | 3.09% |
| WideA | 50000 | sqrt | tail_vwap_1430_1455 | 7 | 133.17% | 249.26% | 3.35 | -15.71% | 85561 | 16.27% | 0.00% | 2.56 | 0.38 | 0.13 | 0.03% | 4.31% |
| WideA | 50000 | sqrt | split_0935_1455 | 7 | 121.94% | 216.04% | 3.33 | -16.25% | 82422 | 16.88% | 0.00% | 2.35 | 0.19 | 0.13 | 0.01% | 4.52% |

## Notes

- `partial/failed` includes capacity-limited partial fills, lot-size residuals, missing minute data, limit blocks, and insufficient cash.
- `actual_exposure` is computed from minute-executed holdings at execution-date close; compare it with daily signal `target_exposure`.
- This is an execution-layer stress test.  It is not a replacement for the daily research backtest and should not be used to retune ETF scores directly.