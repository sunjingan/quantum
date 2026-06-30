#!/usr/bin/env python3
"""Pool-only ablation for friend-style intraday momentum.

Keep the same scoring, execution, costs, and risk switches, then change only
the ETF universe.  This answers whether the friend-style result mainly comes
from the original 9-ETF pool.
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

from run_friend_f2pit_strategy import OUT as F2PIT_OUT  # noqa: E402
from run_friend_f2pit_strategy import run_backtest  # noqa: E402
from run_friend_intraday_replication import FRIEND_POOL_9, LOCAL_DATA, LocalETFIntradayStore, pct  # noqa: E402
from run_multi_setting_pressure_tests import load_f2_pool, load_pit_pool  # noqa: E402


OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "friend_pool_ablation"


def pool_defs() -> dict[str, tuple[set[str], dict[pd.Timestamp, list[str]]]]:
    f2 = set(load_f2_pool())
    pit = load_pit_pool()
    friend9 = set(FRIEND_POOL_9)
    empty_pit: dict[pd.Timestamp, list[str]] = {}
    return {
        "friend9": (friend9, empty_pit),
        "f2_static": (f2, empty_pit),
        "f2_pit_union": (f2, pit),
        "pit_pure": (set(), pit),
    }


def all_codes_for_modes(modes: list[str]) -> list[str]:
    defs = pool_defs()
    codes: set[str] = set()
    for mode in modes:
        core, pit = defs[mode]
        codes |= core
        codes |= {c for xs in pit.values() for c in xs}
    return sorted(codes)


def write_report(rows: list[dict[str, Any]], out_dir: Path, start: str, end: str) -> Path:
    df = pd.DataFrame(rows)
    suffix = f"{start.replace('-', '')}_{end.replace('-', '')}"
    path = out_dir / f"friend_pool_ablation_report_{suffix}.md"
    lines = [
        "# Friend Pool Ablation",
        "",
        f"- window: `{start}` to `{end}`",
        "- purpose: keep friend-style intraday scoring/execution/costs fixed, change only ETF pool",
        "- signal: previous daily history + current 09:50 intraday price",
        "- execution/cost default: 09:55 same-day open, commission 1.5bp/side + slippage 2bp/side",
        "- pool modes: `friend9`, `f2_static`, `f2_pit_union`, `pit_pure`",
        "",
        "## Reproduce",
        "",
        "```bash",
        f"source activate.sh && python runs/etf_loop/run_friend_pool_ablation.py --start {start} --end {end}",
        "```",
        "",
        "## Results",
        "",
        "| pool | fill | N | logic | core | dyn_avg | ann | CAGR | Sharpe | DD | total | final | trades | dyn buys |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['pool_mode']} | {r['fill_mode']} | {r['target_num']} | {r['logic']} | "
            f"{r['core_pool_size']} | {r['avg_dynamic_pool_size']:.1f} | {pct(r['annual_return'])} | "
            f"{pct(r['cagr'])} | {r['sharpe_ratio']:.2f} | {pct(r['max_drawdown'])} | "
            f"{pct(r['total_return'])} | {r['final_value']:.0f} | {int(r['trade_count'])} | "
            f"{int(r['dynamic_buy_count'])} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- If `friend9` dominates under the same logic, the original result is highly pool-dependent.",
        "- If `f2_static` collapses but `f2_pit_union` improves, dynamic PIT contributes useful hot-spot coverage.",
        "- If `pit_pure` has high turnover/drawdown, PIT alone is too noisy for friend-style Top1 rotation.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "friend_pool_ablation_report.md").write_text("\n".join(lines), encoding="utf-8")
    df.to_csv(out_dir / f"friend_pool_ablation_summary_{suffix}.csv", index=False)
    df.to_csv(out_dir / "friend_pool_ablation_summary.csv", index=False)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Pool-only ablation for friend-style ETF strategy")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2026-06-25")
    parser.add_argument("--signal-time", default="09:50")
    parser.add_argument("--frequency", choices=["1min", "5min"], default="5min")
    parser.add_argument("--fill-modes", default="same_0955_open,next_day_open")
    parser.add_argument("--target-nums", default="1,3")
    parser.add_argument("--pool-modes", default="friend9,f2_static,f2_pit_union,pit_pure")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    modes = [x.strip() for x in args.pool_modes.split(",") if x.strip()]
    defs = pool_defs()
    codes = all_codes_for_modes(modes)
    store = LocalETFIntradayStore(
        LOCAL_DATA,
        codes,
        args.start,
        args.end,
        args.signal_time,
        adjust="none",
        frequency=args.frequency,
    )
    rows: list[dict[str, Any]] = []
    for pool_mode in modes:
        core, pit = defs[pool_mode]
        core = core & set(store.ts_codes)
        pit = {k: [c for c in v if c in store.ts_codes] for k, v in pit.items()}
        dyn_sizes = [len(v) for v in pit.values()]
        avg_dyn = float(sum(dyn_sizes) / len(dyn_sizes)) if dyn_sizes else 0.0
        for fill_mode in [x.strip() for x in args.fill_modes.split(",") if x.strip()]:
            for target_num in [int(x) for x in args.target_nums.split(",") if x.strip()]:
                for logic, risk in [
                    ("friend_like", {
                        "dynamic_score_margin": 0.0,
                        "dynamic_overheat_threshold": 1.0,
                        "dynamic_overheat_penalty": 0.0,
                        "use_drawdown_filter": False,
                        "use_premium_penalty": True,
                        "premium_threshold": 0.05,
                        "premium_penalty": 1.0,
                        "stop_loss": 0.0,
                    }),
                    ("guarded", {
                        "dynamic_score_margin": 0.05,
                        "dynamic_overheat_threshold": 0.10,
                        "dynamic_overheat_penalty": 0.50,
                        "use_drawdown_filter": True,
                        "use_premium_penalty": True,
                        "premium_threshold": 0.05,
                        "premium_penalty": 1.0,
                        "stop_loss": 0.08,
                    }),
                ]:
                    tag = f"{pool_mode}_{logic}_{args.frequency}_{fill_mode}_N{target_num}_{args.start.replace('-', '')}_{args.end.replace('-', '')}"
                    eq_path = OUT / f"equity_{tag}.csv"
                    tr_path = OUT / f"trades_{tag}.csv"
                    sig_path = OUT / f"signals_{tag}.csv"
                    if eq_path.exists() and tr_path.exists() and sig_path.exists() and not args.force:
                        equity = pd.read_csv(eq_path, parse_dates=["date"]).set_index("date")
                        trades = pd.read_csv(tr_path)
                        from run_friend_intraday_replication import summarize
                        stats = summarize(equity)
                    else:
                        equity, trades, signals, stats = run_backtest(
                            store=store,
                            pit=pit,
                            core_pool=core,
                            fill_mode=fill_mode,
                            min_days=20,
                            max_days=60,
                            use_dynamic_lookback=True,
                            target_num=target_num,
                            open_cost_bp=1.5,
                            close_cost_bp=1.5,
                            slippage_bp=2.0,
                            min_score=0.0,
                            max_score=6.0,
                            **risk,
                        )
                        equity.to_csv(eq_path)
                        trades.to_csv(tr_path, index=False)
                        signals.to_csv(sig_path, index=False)
                    dyn_buys = int((trades.get("reason", pd.Series(dtype=str)).astype(str).eq("RANK_IN_DYNAMIC")).sum()) if not trades.empty else 0
                    row = {
                        "pool_mode": pool_mode,
                        "logic": logic,
                        "frequency": args.frequency,
                        "fill_mode": fill_mode,
                        "target_num": target_num,
                        "core_pool_size": len(core),
                        "avg_dynamic_pool_size": avg_dyn,
                        **risk,
                        **stats,
                        "trade_count": int(len(trades)),
                        "buy_count": int((trades.get("action", pd.Series(dtype=str)) == "BUY").sum()) if not trades.empty else 0,
                        "sell_count": int((trades.get("action", pd.Series(dtype=str)) == "SELL").sum()) if not trades.empty else 0,
                        "dynamic_buy_count": dyn_buys,
                    }
                    rows.append(row)
                    print(
                        f"{pool_mode:<13s} {logic:<11s} fill={fill_mode:<14s} N={target_num} "
                        f"ann={pct(row['annual_return'])} sharpe={row['sharpe_ratio']:.2f} "
                        f"dd={pct(row['max_drawdown'])} trades={row['trade_count']} dyn_buys={dyn_buys}"
                    )
    report = write_report(rows, OUT, args.start, args.end)
    print("Saved:", OUT / "friend_pool_ablation_summary.csv")
    print("Saved:", report)


if __name__ == "__main__":
    main()
