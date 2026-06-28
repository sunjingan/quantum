# Minute Execution Backtest

- setting: `Exph_v3_exp_looser`
- signal window: `2013-07-01` to `2026-06-25`
- trading_start: `2013-07-01`
- signal source: existing daily ETF Loop engine with detailed logs enabled
- minute overlay: independent target-portfolio execution simulator; it does not change ETF scores or candidate strategy logic
- constraints: minute turnover, max participation, limit-up buy block, limit-down sell block, no-minute-data rejection

## Reproduce

```bash
source activate.sh && python runs/etf_loop/run_minute_execution_backtest.py --setting Exph_v3_exp_looser --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25
```

## Summary

| setting | capital | mode | roundtrip bp | ann | CAGR | Sharpe | DD | final | failed | capacity-limited | no data | no turnover | limit block | avg slip bp | avg participation | avg abs exposure gap |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Exph_v3_exp_looser | 1000000 | open_0935 | 7 | 11.04% | 9.89% | 0.60 | -49.85% | 3221036 | 23.01% | 43.82% | 2.26% | 13.65% | 0.03% | 14.80 | 6.04% | 20.78% |
| Exph_v3_exp_looser | 1000000 | vwap_0935_1030 | 7 | 16.12% | 15.72% | 0.92 | -32.13% | 6118579 | 9.81% | 15.87% | 2.93% | 1.24% | 0.02% | 7.40 | 2.36% | 6.38% |
| Exph_v3_exp_looser | 1000000 | twap_0935_1030 | 7 | 16.30% | 15.92% | 0.93 | -32.00% | 6253872 | 9.59% | 16.03% | 2.94% | 1.24% | 0.02% | 7.45 | 2.38% | 6.41% |
| Exph_v3_exp_looser | 1000000 | tail_vwap_1430_1455 | 7 | 14.48% | 13.76% | 0.81 | -36.95% | 4950238 | 9.05% | 25.08% | 2.78% | 0.70% | 0.14% | 9.61 | 3.41% | 8.14% |
| Exph_v3_exp_looser | 1000000 | t2_open_0935 | 7 | 11.84% | 10.27% | 0.55 | -47.74% | 3363734 | 22.32% | 45.41% | 2.26% | 12.98% | 0.05% | 15.08 | 6.17% | 20.16% |

## Notes

- `partial/failed` includes capacity-limited partial fills, lot-size residuals, missing minute data, limit blocks, and insufficient cash.
- `actual_exposure` is computed from minute-executed holdings at execution-date close; compare it with daily signal `target_exposure`.
- This is an execution-layer stress test.  It is not a replacement for the daily research backtest and should not be used to retune ETF scores directly.