#!/usr/bin/env python3
"""Adaptive holdings FIX2: market-driven N reduction with score weighting.

Runs the requested F2_CAP_MA60 setting with:
- F2_v3 44 ETF core pool + capped PIT supplement
- MA60 overheat penalty
- market adaptive holdings based on benchmark 20d return
- score weighting enabled for the adaptive variants
- corrected 3.5bp/side cost model
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from run_multi_setting_pressure_tests import make_config, load_f2_pool, load_pit_pool
from strategies.etf_loop_engine import EngineParams, run_and_save
from strategies.etf_loop_strategy import FULL_ETF_POOL_JQ, _jq_to_ts


OUT = BASE_DIR / "outputs" / "etf_loop"
REPORT_DIR = OUT / "F2_CAP_MA60_deep_dive"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

COST = {"open_cost": 0.00015, "close_cost": 0.00015, "slippage": 0.0002}
BENCHMARK = "sh000300"
ADAPTIVE_WINDOW = 20
ADAPTIVE_TIERS_RET = "0.05,0.02,0.00,-0.03,-0.06"
ADAPTIVE_TIERS_N = "5,4,3,2,1,0"
ADAPTIVE_TIERS_EXPOSURE = "1.00,1.00,1.00,1.00,1.00,0.00"


def path_triplet(params: EngineParams) -> tuple[Path, Path, Path]:
    suffix = f"{params.exp_tag}_h{params.holdings_num}_{params.start.replace('-', '')}_{params.end.replace('-', '')}"
    return (
        OUT / f"etf_loop_equity_{suffix}.csv",
        OUT / f"etf_loop_targets_{suffix}.csv",
        OUT / f"etf_loop_summary_{suffix}.csv",
    )


def summarize_nav(equity: pd.DataFrame) -> dict[str, float]:
    nav = equity["portfolio_value"].dropna()
    if len(nav) < 2:
        return {"annual_return": 0.0, "sharpe_ratio": 0.0, "max_drawdown": 0.0, "total_return": 0.0}
    daily = nav.pct_change().dropna()
    ann = float(daily.mean() * 252.0)
    vol = float(daily.std() * (252.0 ** 0.5)) if len(daily) > 1 else 0.0
    return {
        "annual_return": ann,
        "sharpe_ratio": ann / vol if vol > 0 else 0.0,
        "max_drawdown": float((nav / nav.cummax() - 1.0).min()),
        "total_return": float(nav.iloc[-1] / nav.iloc[0] - 1.0),
    }


def run_case(
    label: str,
    start: str,
    end: str,
    trading_start: str,
    pit: dict,
    f2: list[str],
    f2o: list[str],
    extra: dict,
) -> dict:
    tag = f"ADAPT2_{label}"
    params = make_config("F2_CAP_MA60", pit, f2, f2o, tag, {}, start, end)
    params = EngineParams(
        **{
            **params.__dict__,
            **COST,
            "benchmark": BENCHMARK,
            "start": start,
            "end": end,
            "trading_start": trading_start,
            "exp_tag": tag,
            "adaptive_mode": "bench_20d_ret",
            "adaptive_window": ADAPTIVE_WINDOW,
            "adaptive_tiers_ret": ADAPTIVE_TIERS_RET,
            "adaptive_tiers_n": ADAPTIVE_TIERS_N,
            "adaptive_tiers_exposure": ADAPTIVE_TIERS_EXPOSURE,
            **extra,
        }
    )

    eq_path, tr_path, sm_path = path_triplet(params)
    if eq_path.exists() and tr_path.exists() and sm_path.exists():
        equity = pd.read_csv(eq_path, parse_dates=["date"]).set_index("date")
        trades = pd.read_csv(tr_path)
        stats = pd.read_csv(sm_path).iloc[0].to_dict()
        print(f"{tag}: skip existing")
    else:
        equity, trades, audit = run_and_save(params, OUT)
        stats = audit["stats"]
    nav = equity.loc[equity.index >= pd.Timestamp(trading_start), ["portfolio_value"]]
    active = summarize_nav(nav.rename(columns={"portfolio_value": "portfolio_value"}))
    return {
        "tag": tag,
        "label": label,
        "start": start,
        "end": end,
        "trading_start": trading_start,
        "annual_return": stats.get("annual_return"),
        "sharpe_ratio": stats.get("sharpe_ratio"),
        "max_drawdown": stats.get("max_drawdown"),
        "total_return": stats.get("total_return"),
        "final_value": stats.get("final_value"),
        "trade_count": len(trades),
        "active_annual_return": active["annual_return"],
        "active_sharpe_ratio": active["sharpe_ratio"],
        "active_max_drawdown": active["max_drawdown"],
        "active_total_return": active["total_return"],
    }


def write_report(df: pd.DataFrame) -> Path:
    path = REPORT_DIR / "adaptive_holdings_fix2_report.md"
    lines = [
        "# Adaptive Holdings FIX2",
        "",
        "- pool: `F2_CAP_MA60`",
        f"- benchmark: `{BENCHMARK}`",
        f"- adaptive window: `{ADAPTIVE_WINDOW}` trading days",
        "- costs: commission 1.5bp + slippage 2bp per side",
        "- adaptive tiers: 5/4/3/2/1/0 by benchmark 20d return",
        "",
        "| label | annual | sharpe | dd | total | final | trades | active annual | active dd |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in df.sort_values(["start", "annual_return"], ascending=[True, False]).iterrows():
        lines.append(
            f"| {r['label']} | {r['annual_return']*100:.2f}% | {r['sharpe_ratio']:.2f} | "
            f"{r['max_drawdown']*100:.2f}% | {r['total_return']*100:.2f}% | {r['final_value']:,.0f} | "
            f"{int(r['trade_count'])} | {r['active_annual_return']*100:.2f}% | {r['active_max_drawdown']*100:.2f}% |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    pit = load_pit_pool()
    f2 = load_f2_pool()
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2o = sorted(set(f2) | set(orig38))

    rows = []
    periods = [
        ("2026_NOWARMUP", "2025-10-01", "2026-06-25", "2026-01-02"),
        ("LONG_2013_2026", "2013-07-01", "2026-06-25", ""),
    ]
    variants = [
        ("Baseline_Fixed5", {}),
        ("20dRet", {"use_market_adaptive_holdings": True}),
        ("20dRet_ScoreW", {"use_market_adaptive_holdings": True, "use_score_weighting": True}),
        ("20dRet_ScoreW_Thresh01", {"use_market_adaptive_holdings": True, "use_score_weighting": True, "adaptive_score_threshold": 0.1}),
    ]
    for period_label, start, end, trading_start in periods:
        print(f"\n{'='*90}")
        print(f"  {period_label}")
        print(f"{'='*90}")
        for label, extra in variants:
            rows.append(run_case(f"{period_label}_{label}", start, end, trading_start, pit, f2, f2o, extra))
    df = pd.DataFrame(rows)
    csv_path = REPORT_DIR / "adaptive_holdings_fix2_results.csv"
    df.to_csv(csv_path, index=False)
    report = write_report(df)
    print(f"\nSaved: {csv_path}")
    print(f"Saved: {report}")
    print(df[[
        "label", "annual_return", "sharpe_ratio", "max_drawdown",
        "active_annual_return", "active_sharpe_ratio", "trade_count",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()
