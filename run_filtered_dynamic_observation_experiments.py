#!/usr/bin/env python3
"""Filtered dynamic-observation experiments for F2 static pool.

This keeps the existing F2 experiments intact by using new tags and writing
all outputs into a separate report file.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from run_multi_setting_pressure_tests import make_config, load_pit_pool, load_f2_pool
from strategies.etf_loop_engine import EngineParams, run_and_save
from strategies.etf_loop_strategy import FULL_ETF_POOL_JQ, _jq_to_ts


OUT = BASE_DIR / "outputs" / "etf_loop"
REPORT_DIR = OUT / "F2_CAP_MA60_deep_dive"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

START = "2013-07-01"
END = "2026-06-25"
TAG_PREFIX = "DYNOBS_F2_STATIC_FILTERED"


def pct(x: float) -> str:
    return "NA" if pd.isna(x) else f"{x * 100:.2f}%"


def ival(x) -> str:
    if x is None or pd.isna(x):
        return "NA"
    return str(int(x))


def load_baseline(tag: str) -> dict:
    sm = OUT / f"etf_loop_summary_{tag}_h5_{START.replace('-', '')}_{END.replace('-', '')}.csv"
    if not sm.exists():
        return {}
    return pd.read_csv(sm).iloc[0].to_dict()


def run_case(label: str, pit, f2_pool, f2_orig, overrides: dict) -> dict:
    tag = f"{TAG_PREFIX}_{label}"
    params = make_config("F2_STATIC_BASE", pit, f2_pool, f2_orig, tag, {}, START, END)
    params = EngineParams(
        **{
            **params.__dict__,
            "exp_tag": tag,
            "start": START,
            "end": END,
            "core_pool": f2_pool,
            "pit_pools": pit,
            "use_dynamic_pool": True,
            "dynamic_fusion_mode": "capped",
            "dynamic_min_amount": 50_000_000,
            "dynamic_min_list_days": 180,
            "dynamic_use_trend_filter": True,
            "dynamic_trend_ma_period": 60,
            "dynamic_max_total_weight": 0.20,
            "dynamic_score_margin": 0.05,
            "dynamic_overheat_threshold": 0.10,
            "dynamic_overheat_penalty": 0.50,
            "use_trend_filter": True,
            "trend_ma_period": 60,
            "use_short_momentum_filter": True,
            "short_momentum_threshold": 0.0,
            **overrides,
        }
    )
    eq_path = OUT / f"etf_loop_equity_{tag}_h5_{START.replace('-', '')}_{END.replace('-', '')}.csv"
    tr_path = OUT / f"etf_loop_targets_{tag}_h5_{START.replace('-', '')}_{END.replace('-', '')}.csv"
    sm_path = OUT / f"etf_loop_summary_{tag}_h5_{START.replace('-', '')}_{END.replace('-', '')}.csv"
    if eq_path.exists() and tr_path.exists() and sm_path.exists():
        trades = pd.read_csv(tr_path)
        stats = pd.read_csv(sm_path).iloc[0].to_dict()
    else:
        _, trades, audit = run_and_save(params, OUT)
        stats = audit["stats"]
    dyn_buys = int((trades.get("action", pd.Series("", index=trades.index)).eq("BUY") & trades.get("is_dynamic_only", pd.Series(False, index=trades.index)).astype("boolean").fillna(False)).sum()) if not trades.empty else 0
    return {
        "tag": tag,
        "label": label,
        "annual_return": stats.get("annual_return"),
        "sharpe_ratio": stats.get("sharpe_ratio"),
        "max_drawdown": stats.get("max_drawdown"),
        "total_return": stats.get("total_return"),
        "final_value": stats.get("final_value"),
        "trade_count": len(trades),
        "dynamic_buys": dyn_buys,
        "dynamic_max_slots": params.dynamic_max_slots,
        "dynamic_max_total_weight": params.dynamic_max_total_weight,
        "dynamic_min_list_days": params.dynamic_min_list_days,
        "dynamic_min_amount": params.dynamic_min_amount,
    }


def main() -> None:
    pit = load_pit_pool()
    f2_pool = load_f2_pool()
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2_orig = sorted(set(f2_pool) | set(orig38))

    rows = []
    configs = [
        ("CAP1", {"dynamic_max_slots": 1}),
        ("CAP2", {"dynamic_max_slots": 2}),
    ]
    for label, overrides in configs:
        rows.append(run_case(label, pit, f2_pool, f2_orig, overrides))

    baseline_f2 = load_baseline("LONGPERIOD_FIX1_F2_STATIC_Baseline")
    baseline_cap = load_baseline("LONGPERIOD_FIX1_F2_CAP_MA60_Baseline")

    df = pd.DataFrame(rows)
    df.to_csv(REPORT_DIR / "dynamic_observation_filtered_long_period.csv", index=False)

    lines = [
        "# Filtered Dynamic Observation Pool",
        "",
        "- pool: `F2_STATIC` core with capped dynamic PIT supplement",
        "- dynamic filters: list age >= 180 days, 5d avg amount >= 5e7, trend MA60 gate, overheat penalty, trend/short momentum filters on",
        "- experiment tags are isolated and do not overwrite any existing F2 results",
        "",
        "## Results",
        "",
        "| label | tag | annual | sharpe | dd | total | final | trades | dynamic buys |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in df.sort_values("annual_return", ascending=False).to_dict("records"):
        lines.append(
            f"| {r['label']} | {r['tag']} | {pct(r['annual_return'])} | {r['sharpe_ratio']:.2f} | "
            f"{pct(r['max_drawdown'])} | {pct(r['total_return'])} | {r['final_value']:,.0f} | {ival(r['trade_count'])} | {ival(r['dynamic_buys'])} |"
        )

    lines += [
        "",
        "## Baseline Context",
        "",
        "| benchmark | annual | sharpe | dd | total | final |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, b in [
        ("F2_STATIC_Baseline", baseline_f2),
        ("F2_CAP_MA60_Baseline", baseline_cap),
    ]:
        if not b:
            continue
        lines.append(
            f"| {name} | {pct(b.get('annual_return'))} | {b.get('sharpe_ratio', float('nan')):.2f} | "
            f"{pct(b.get('max_drawdown'))} | {pct(b.get('total_return'))} | {b.get('final_value', float('nan')):,.0f} |"
        )

    lines += [
        "",
        "## Notes",
        "",
        "- 这组实验只改动态补漏池的候选过滤，不动原 F2 静态池。",
        "- 如果 filtered dynamic 仍低于静态基线，说明动态池更适合做候选观察，而不是常态补漏。",
    ]

    md = REPORT_DIR / "dynamic_observation_filtered_long_period.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    print(df.to_string(index=False))
    print("Saved:", md)
    print("Saved:", REPORT_DIR / "dynamic_observation_filtered_long_period.csv")


if __name__ == "__main__":
    main()
