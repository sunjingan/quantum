# ETF Loop Detailed Trading Logs

This log mode is generated inside the backtest loop, not reconstructed after the fact.

## Usage

```bash
source activate.sh
python runs/etf_loop/run_detailed_trade_log.py --setting WideA --start 2025-10-01 --trading-start 2026-01-02 --end 2026-06-25 --signal-top-n 20
```

Supported settings:

- `F2_CAP_MA60`
- `WideA`
- `Current`

The engine switch is:

- `write_detailed_logs=True`
- `log_signal_top_n=20`

Default is off, so existing experiments do not produce extra files unless explicitly enabled.

## Output Files

All files are written next to the normal equity / trade / summary CSVs.

| file | purpose |
|---|---|
| `etf_loop_account_*.csv` | daily NAV, cash ratio, position ratio, target exposure, effective holdings, daily cost |
| `etf_loop_positions_*.csv` | daily ETF-level holdings after execution-date close valuation |
| `etf_loop_signals_*.csv` | signal-date TopN momentum and risk snapshot before execution |
| `etf_loop_advice_*.csv` | next execution-date operation advice / executed order log, bucketed by reason |
| `etf_loop_daily_log_*.md` | human-readable latest daily report |

## Important Semantics

- `signal_date` is the date whose close generated the signal.
- `trade_date` is the future execution date used by the engine.
- Signals, momentum scores, amount CV, and return-std risk metrics use only data available through `signal_date`.
- Execution price still requires an exact `trade_date` price; no signal-day close fallback is introduced by logging.
- `risk_throttled=True` in `signals` means the risk metric crossed the configured threshold. It is a diagnostic hit; it only changes trades when `use_position_risk_throttle=True`.

## Buckets

| bucket | meaning |
|---|---|
| `REBALANCE` | rank-in, rank-out, or regular rebalance trade |
| `STOP` | fixed stop loss or ATR stop |
| `RISK_HALF` | risk throttle partial sell |
| `EXPOSURE_REBALANCE` | adaptive exposure sell-down |
| `NO_TRADE` | hold current position or hold cash |
| `DIP_ADD` | permanent-hold dip add overlay |

## Current Limitation

The Markdown report shows the latest snapshot and recent risk/stop records. The full history is in CSV. If we later need a real-time paper-trading style "tomorrow order ticket" before execution prices are known, we should add a separate paper mode that records planned orders at signal generation time and reconciles them after broker fills.
