# Minute Execution Backtest

- setting: `WideA`
- signal window: `2025-10-01` to `2026-06-25`
- trading_start: `2026-01-02`
- signal source: existing daily ETF Loop engine with detailed logs enabled
- minute overlay: independent target-portfolio execution simulator; it does not change ETF scores or candidate strategy logic
- constraints: minute turnover, max participation, limit-up buy block, limit-down sell block, no-minute-data rejection
- slippage model: `tiered`

## Reproduce

```bash
source activate.sh && python runs/etf_loop/run_minute_execution_backtest.py --setting WideA --start 2025-10-01 --trading-start 2026-01-02 --end 2026-06-25
```

## Summary

| setting | capital | model | mode | roundtrip bp | ann | CAGR | Sharpe | DD | final | failed | capacity-limited | avg slip bp | impact bp | extra bp | avg participation | avg abs exposure gap |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| WideA | 50000 | tiered | open_0935 | 7 | 86.24% | 125.14% | 2.73 | -12.74% | 72347 | 35.40% | 0.20% | 2.80 | 0.79 | 0.00 | 0.20% | 9.69% |
| WideA | 50000 | tiered | vwap_0935_1030 | 7 | 80.07% | 111.84% | 2.55 | -13.19% | 69822 | 36.97% | 0.00% | 2.00 | 0.00 | 0.00 | 0.01% | 9.70% |
| WideA | 50000 | tiered | twap_0935_1030 | 7 | 78.57% | 108.70% | 2.50 | -13.12% | 69362 | 37.83% | 0.00% | 2.00 | 0.00 | 0.00 | 0.01% | 9.63% |
| WideA | 50000 | tiered | twap_1000_1430 | 7 | 122.37% | 217.33% | 3.33 | -17.30% | 82557 | 15.40% | 0.00% | 2.00 | 0.00 | 0.00 | 0.00% | 3.09% |
| WideA | 50000 | tiered | tail_vwap_1430_1455 | 7 | 134.23% | 252.97% | 3.38 | -15.72% | 85952 | 17.27% | 0.00% | 2.04 | 0.04 | 0.00 | 0.03% | 4.31% |
| WideA | 50000 | tiered | split_0935_1455 | 7 | 122.76% | 218.67% | 3.35 | -16.25% | 82716 | 18.53% | 0.00% | 2.01 | 0.01 | 0.00 | 0.01% | 4.56% |
| WideA | 50000 | tiered | t2_open_0935 | 7 | 53.46% | 62.13% | 1.67 | -13.83% | 61436 | 35.01% | 0.00% | 2.66 | 0.64 | 0.00 | 0.17% | 9.49% |

## Notes

- `partial/failed` includes capacity-limited partial fills, lot-size residuals, missing minute data, limit blocks, and insufficient cash.
- `actual_exposure` is computed from minute-executed holdings at execution-date close; compare it with daily signal `target_exposure`.
- This is an execution-layer stress test.  It is not a replacement for the daily research backtest and should not be used to retune ETF scores directly.