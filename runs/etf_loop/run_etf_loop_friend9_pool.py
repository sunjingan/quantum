#!/usr/bin/env python3
"""Run ETF Loop candidate logic on the friend's original 9-ETF pool.

This is the reverse ablation of the friend-style F2/PIT test:
keep our daily ETF Loop engine/execution/cost model, change only the universe
to the friend's cross-asset 9 ETF pool.
"""
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

from run_friend_intraday_replication import FRIEND_POOL_9, pct  # noqa: E402
from strategies.etf_loop_engine import EngineParams, run_and_save  # noqa: E402


OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "friend9_pool_etf_loop"
COST = {"open_cost": 0.00015, "close_cost": 0.00015, "slippage": 0.00020}


def build_params(variant: str, start: str, end: str, holdings_num: int) -> EngineParams:
    common: dict[str, Any] = {
        "etf_pool_ts": FRIEND_POOL_9,
        "holdings_num": holdings_num,
        "lookback_days": 25,
        "start": start,
        "end": end,
        "benchmark": "sh000300",
        "execution_price_mode": "open",
        "execution_delay_days": 1,
        "exp_tag": f"FRIEND9_{variant}_H{holdings_num}_{start.replace('-', '')}_{end.replace('-', '')}",
        **COST,
    }
    if variant == "base":
        pass
    elif variant == "ma60":
        common.update({
            "mr_ma_period": 60,
            "mr_threshold": 1.14,
            "mr_penalty": 0.50,
        })
    elif variant == "widea":
        common.update({
            "mr_ma_period": 60,
            "mr_threshold": 1.14,
            "mr_penalty": 0.50,
            "use_market_adaptive_holdings": True,
            "adaptive_mode": "bench_20d_ret",
            "adaptive_window": 15,
            "adaptive_tiers_ret": "0.06,0.03,0.00,-0.02,-0.05,-0.08",
            "adaptive_tiers_n": "5,5,4,3,2,1,0",
            "adaptive_tiers_exposure": "1,1,1,1,1,1,0",
        })
    else:
        raise ValueError(f"Unsupported variant: {variant}")
    return EngineParams(**common)


def run_case(variant: str, start: str, end: str, holdings_num: int, force: bool) -> dict[str, Any]:
    params = build_params(variant, start, end, holdings_num)
    suffix = f"{params.exp_tag}_h{params.holdings_num}_{params.start.replace('-', '')}_{params.end.replace('-', '')}"
    summary_path = OUT / f"etf_loop_summary_{suffix}.csv"
    equity_path = OUT / f"etf_loop_equity_{suffix}.csv"
    trades_path = OUT / f"etf_loop_targets_{suffix}.csv"
    if summary_path.exists() and equity_path.exists() and trades_path.exists() and not force:
        stats = pd.read_csv(summary_path).iloc[0].to_dict()
        trades = pd.read_csv(trades_path)
    else:
        _, trades, audit = run_and_save(params, OUT)
        stats = audit["stats"]
    return {
        "variant": variant,
        "holdings_num": holdings_num,
        "start": start,
        "end": end,
        "pool": "friend9",
        "pool_size": len(FRIEND_POOL_9),
        "execution": "T_close_signal_T1_open",
        "roundtrip_cost_bp": 7.0,
        "trade_count": int(len(trades)),
        **stats,
    }


def write_report(rows: list[dict[str, Any]], start: str, end: str) -> Path:
    df = pd.DataFrame(rows)
    suffix = f"{start.replace('-', '')}_{end.replace('-', '')}"
    path = OUT / f"friend9_pool_etf_loop_report_{suffix}.md"
    lines = [
        "# ETF Loop on Friend9 Pool",
        "",
        f"- window: `{start}` to `{end}`",
        "- engine: our daily ETF Loop engine",
        "- changed variable: static ETF pool is replaced by friend's original 9-ETF cross-asset pool",
        "- signal/execution: T close signal, T+1 open execution; no signal-day price fallback",
        "- cost: commission 1.5bp/side + slippage 2bp/side, roundtrip 7bp",
        "",
        "## Reproduce",
        "",
        "```bash",
        f"source activate.sh && python runs/etf_loop/run_etf_loop_friend9_pool.py --start {start} --end {end}",
        "```",
        "",
        "## Results",
        "",
        "| variant | N | ann | sharpe | DD | total | final | trades |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['variant']} | {int(r['holdings_num'])} | {pct(r['annual_return'])} | "
            f"{r['sharpe_ratio']:.2f} | {pct(r['max_drawdown'])} | {pct(r['total_return'])} | "
            f"{r['final_value']:.0f} | {int(r['trade_count'])} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "- This test does not use friend intraday 09:50 execution; it uses our daily engine.",
        "- Compare with friend-style pool ablation separately: friend9 works especially well with same-day intraday Top1.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    (OUT / "friend9_pool_etf_loop_report.md").write_text("\n".join(lines), encoding="utf-8")
    df.to_csv(OUT / f"friend9_pool_etf_loop_summary_{suffix}.csv", index=False)
    df.to_csv(OUT / "friend9_pool_etf_loop_summary.csv", index=False)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ETF Loop candidate logic on friend9 ETF pool")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2026-06-25")
    parser.add_argument("--variants", default="base,ma60,widea")
    parser.add_argument("--holdings", default="1,5")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for holdings_num in [int(x) for x in args.holdings.split(",") if x.strip()]:
        for variant in [x.strip() for x in args.variants.split(",") if x.strip()]:
            row = run_case(variant, args.start, args.end, holdings_num, args.force)
            rows.append(row)
            print(
                f"{variant:<8s} H{holdings_num:<2d} ann={pct(row['annual_return'])} "
                f"sharpe={row['sharpe_ratio']:.2f} dd={pct(row['max_drawdown'])} "
                f"trades={row['trade_count']}"
            )
    report = write_report(rows, args.start, args.end)
    print("Saved:", OUT / "friend9_pool_etf_loop_summary.csv")
    print("Saved:", report)


if __name__ == "__main__":
    main()
