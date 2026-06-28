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
| WideA | 50000 | sqrt | vwap_0935_1030 | 7 | 79.03% | 109.63% | 2.51 | -13.23% | 69508 | 36.58% | 0.00% | 2.51 | 0.20 | 0.28 | 0.00% | 9.68% |
| WideA | 50000 | sqrt | twap_1000_1430 | 7 | 120.90% | 212.65% | 3.29 | -17.39% | 82033 | 15.13% | 0.00% | 2.64 | 0.15 | 0.44 | 0.00% | 3.07% |
| WideA | 50000 | sqrt | tail_vwap_1430_1455 | 7 | 132.31% | 246.28% | 3.33 | -15.79% | 85247 | 16.49% | 0.00% | 2.85 | 0.38 | 0.42 | 0.03% | 4.56% |
| WideA | 50000 | sqrt | split_0935_1455 | 7 | 121.43% | 214.44% | 3.31 | -16.31% | 82243 | 18.36% | 0.00% | 2.64 | 0.19 | 0.42 | 0.01% | 4.53% |

## Notes

- `partial/failed` includes capacity-limited partial fills, lot-size residuals, missing minute data, limit blocks, and insufficient cash.
- `actual_exposure` is computed from minute-executed holdings at execution-date close; compare it with daily signal `target_exposure`.
- This is an execution-layer stress test.  It is not a replacement for the daily research backtest and should not be used to retune ETF scores directly.