#!/usr/bin/env python3
"""Single-factor tests for target correlation de-duplication."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from run_detailed_trade_log import build_params  # noqa: E402
from strategies.etf_loop_engine import EngineParams, run_and_save  # noqa: E402


OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "correlation_filter"


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x * 100:.2f}%"


def run_case(
    *,
    setting: str,
    start: str,
    end: str,
    trading_start: str,
    threshold: float | None,
    lookback: int,
    backfill: bool,
    force: bool,
) -> dict[str, Any]:
    params = build_params(setting, start, end, trading_start, signal_top_n=20)
    label = "OFF" if threshold is None else f"C{int(threshold * 100)}"
    fill_label = "BF" if backfill else "NOBF"
    params.exp_tag = f"CORR_{setting}_{label}_LB{lookback}_{fill_label}_{start.replace('-', '')}_{end.replace('-', '')}"
    if threshold is not None:
        params.use_correlation_filter = True
        params.correlation_lookback = lookback
        params.correlation_threshold = threshold
        params.correlation_backfill = backfill
    suffix = f"{params.exp_tag}_h{params.holdings_num}_{params.start.replace('-', '')}_{params.end.replace('-', '')}"
    summary_path = OUT / f"etf_loop_summary_{suffix}.csv"
    trades_path = OUT / f"etf_loop_targets_{suffix}.csv"
    if summary_path.exists() and trades_path.exists() and not force:
        stats = pd.read_csv(summary_path).iloc[0].to_dict()
        trades = pd.read_csv(trades_path)
    else:
        _, trades, audit = run_and_save(params, OUT)
        stats = audit["stats"]
    return {
        "setting": setting,
        "period": "long" if start == "2013-07-01" else "2026_nowarmup",
        "start": start,
        "end": end,
        "trading_start": trading_start,
        "correlation_filter": threshold is not None,
        "correlation_threshold": threshold,
        "correlation_lookback": lookback,
        "correlation_backfill": backfill,
        "trade_count": int(len(trades)),
        **stats,
    }


def write_report(df: pd.DataFrame, out_dir: Path) -> Path:
    path = out_dir / "correlation_filter_report.md"
    lines = [
        "# ETF Loop Correlation Filter Experiments",
        "",
        "## Setting",
        "",
        "- Single-factor experiment: only add target correlation de-duplication.",
        "- Filter: greedily keep high-score ETFs, skip a candidate if trailing return correlation with any selected ETF exceeds threshold.",
        "- Scope: this does not permanently remove ETFs from the pool; it only reorders daily candidates before the existing target-selection rules.",
        "- Data safety: correlation uses signal-date-visible price history only.",
        "- `backfill=True`: if strict de-correlation cannot fill N, the engine backfills by original score order to avoid unintended cash bias.",
        "- `backfill=False`: if strict de-correlation cannot fill N, the strategy holds fewer ETFs instead of buying lower-score low-correlation names.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "source activate.sh && python runs/etf_loop/run_correlation_filter_experiments.py",
        "```",
        "",
        "## Results",
        "",
        "| setting | period | corr | lookback | backfill | ann | sharpe | DD | total | final | trades |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in df.sort_values(["setting", "period", "correlation_threshold"], na_position="first").to_dict("records"):
        corr = "OFF" if pd.isna(r["correlation_threshold"]) else f"{r['correlation_threshold']:.2f}"
        lines.append(
            f"| {r['setting']} | {r['period']} | {corr} | {int(r['correlation_lookback'])} | {bool(r['correlation_backfill'])} | "
            f"{pct(r['annual_return'])} | {r['sharpe_ratio']:.2f} | {pct(r['max_drawdown'])} | "
            f"{pct(r['total_return'])} | {r['final_value']:.0f} | {int(r['trade_count'])} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- F2_CAP_MA60: 0.70/0.80/0.90 thresholds all reduce long-period annualized return versus OFF. Drawdown improves by about 1.8-2.2 pct points, but the return trade-off is large.",
        "- WideA: 0.70/0.80/0.90 thresholds also underperform OFF on the long period. 0.90 improves 2026-nowarmup Sharpe and annualized return slightly, but this is not enough to justify replacing the long-period candidate.",
        "- Practical conclusion: correlation de-duplication can be kept as a defensive optional overlay, but current evidence does not support making it the default candidate rule.",
        "",
        "## Notes",
        "",
        "- This is not yet a candidate replacement; it tests whether reducing intra-pool correlation helps.",
        "- Compare against `corr=OFF` within the same setting and period only.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ETF Loop correlation filter experiments")
    parser.add_argument("--settings", default="F2_CAP_MA60,WideA")
    parser.add_argument("--thresholds", default="0.70,0.80,0.90")
    parser.add_argument("--lookback", type=int, default=60)
    parser.add_argument("--no-backfill", action="store_true", help="Do not fill missing slots after correlation filtering")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    periods = [
        ("long", "2013-07-01", "2026-06-25", "2013-07-01"),
        ("2026_nowarmup", "2025-10-01", "2026-06-25", "2026-01-02"),
    ]
    thresholds = [None] + [float(x) for x in args.thresholds.split(",") if x.strip()]
    rows: list[dict[str, Any]] = []
    for setting in [x.strip() for x in args.settings.split(",") if x.strip()]:
        for _, start, end, trading_start in periods:
            for threshold in thresholds:
                row = run_case(
                    setting=setting,
                    start=start,
                    end=end,
                    trading_start=trading_start,
                    threshold=threshold,
                    lookback=args.lookback,
                    backfill=not args.no_backfill,
                    force=args.force,
                )
                rows.append(row)
                corr = "OFF" if threshold is None else f"{threshold:.2f}"
                print(
                    f"{setting:<12s} {row['period']:<13s} corr={corr:<4s} "
                    f"ann={pct(row['annual_return'])} sharpe={row['sharpe_ratio']:.2f} "
                    f"dd={pct(row['max_drawdown'])} trades={row['trade_count']}"
                )
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "correlation_filter_results.csv", index=False)
    report = write_report(df, OUT)
    print("Saved:", OUT / "correlation_filter_results.csv")
    print("Saved:", report)


if __name__ == "__main__":
    main()
