#!/usr/bin/env python3
"""Run capped dynamic-pool fusion experiments for ETF Loop."""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from strategies.etf_loop_engine import EngineParams, run_and_save
from strategies.etf_loop_strategy import FULL_ETF_POOL_JQ, _jq_to_ts


START = "2013-07-01"
END = "2026-06-25"
OUT = BASE_DIR / "outputs" / "etf_loop"


def load_pit_pool(name: str) -> dict[pd.Timestamp, list[str]]:
    path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / name
    with open(path, "rb") as f:
        pools = pickle.load(f)
    return {pd.Timestamp(k): list(v) for k, v in pools.items()}


def load_f2_pool() -> list[str]:
    path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / "etf_pool_F2_v3.csv"
    return sorted(pd.read_csv(path, dtype={"ts_code": str})["ts_code"].astype(str).tolist())


def paths(tag: str) -> tuple[Path, Path, Path]:
    suffix = f"{tag}_h5_{START.replace('-', '')}_{END.replace('-', '')}"
    return (
        OUT / f"etf_loop_equity_{suffix}.csv",
        OUT / f"etf_loop_targets_{suffix}.csv",
        OUT / f"etf_loop_summary_{suffix}.csv",
    )


def trade_diagnostics(trades_path: Path) -> dict:
    if not trades_path.exists():
        return {}
    trades = pd.read_csv(trades_path)
    if trades.empty or "action" not in trades.columns:
        return {"trades": len(trades), "dynamic_buys": 0, "dynamic_buy_value": 0.0, "penalized_dynamic_buys": 0}
    dyn = trades.get("is_dynamic_only", pd.Series(False, index=trades.index)).astype("boolean").fillna(False)
    buys = trades["action"].eq("BUY")
    gross = pd.to_numeric(trades.get("gross_cost", pd.Series(0.0, index=trades.index)), errors="coerce").fillna(0.0)
    penalized = trades.get("dynamic_overheat_penalized", pd.Series(False, index=trades.index)).astype("boolean").fillna(False)
    return {
        "trades": len(trades),
        "dynamic_buys": int((dyn & buys).sum()),
        "dynamic_buy_value": float(gross[dyn & buys].sum()),
        "penalized_dynamic_buys": int((dyn & buys & penalized).sum()),
    }


def run_case(rows: list[dict], params: EngineParams, group: str, notes: str) -> None:
    equity_path, trades_path, summary_path = paths(params.exp_tag)
    if equity_path.exists() and trades_path.exists() and summary_path.exists():
        stats = pd.read_csv(summary_path).iloc[0].to_dict()
        diag = trade_diagnostics(trades_path)
        print(f"{params.exp_tag}: skip existing")
    else:
        _, trades, audit = run_and_save(params, OUT)
        stats = audit["stats"]
        dyn = trades.get("is_dynamic_only", pd.Series(False, index=trades.index)).astype("boolean").fillna(False) if not trades.empty else pd.Series(dtype=bool)
        buys = trades.get("action", pd.Series("", index=trades.index)).eq("BUY") if not trades.empty else pd.Series(dtype=bool)
        penalized = trades.get("dynamic_overheat_penalized", pd.Series(False, index=trades.index)).astype("boolean").fillna(False) if not trades.empty else pd.Series(dtype=bool)
        diag = {
            "trades": len(trades),
            "dynamic_buys": int((dyn & buys).sum()) if not trades.empty else 0,
            "dynamic_buy_value": float(pd.to_numeric(
                trades.loc[
                    dyn & buys,
                    "gross_cost",
                ],
                errors="coerce",
            ).fillna(0.0).sum()) if not trades.empty and "gross_cost" in trades.columns else 0.0,
            "penalized_dynamic_buys": int((dyn & buys & penalized).sum()) if not trades.empty else 0,
        }

    rows.append({
        "tag": params.exp_tag,
        "group": group,
        "notes": notes,
        "start": params.start,
        "end": params.end,
        "annual_return": stats.get("annual_return"),
        "sharpe_ratio": stats.get("sharpe_ratio"),
        "max_drawdown": stats.get("max_drawdown"),
        "total_return": stats.get("total_return"),
        "final_value": stats.get("final_value"),
        "dynamic_fusion_mode": params.dynamic_fusion_mode,
        "dynamic_max_slots": params.dynamic_max_slots,
        "dynamic_max_total_weight": params.dynamic_max_total_weight,
        "dynamic_score_margin": params.dynamic_score_margin,
        "dynamic_overheat_lookback": params.dynamic_overheat_lookback,
        "dynamic_overheat_threshold": params.dynamic_overheat_threshold,
        "dynamic_overheat_penalty": params.dynamic_overheat_penalty,
        **diag,
    })


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    g2_pit = load_pit_pool("etf_pool_G2_PIT_monthly.pkl")
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2 = load_f2_pool()
    f2_orig = sorted(set(f2) | set(orig38))

    variants = [
        ("CAP1_W20_M00", {"dynamic_max_slots": 1, "dynamic_max_total_weight": 0.20, "dynamic_score_margin": 0.00, "dynamic_overheat_penalty": 1.0}, "1 dynamic slot, 20% weight cap, no score margin, no overheat penalty"),
        ("CAP1_W20_M05", {"dynamic_max_slots": 1, "dynamic_max_total_weight": 0.20, "dynamic_score_margin": 0.05, "dynamic_overheat_penalty": 1.0}, "1 dynamic slot, 20% weight cap, 5% score margin, no overheat penalty"),
        ("CAP1_W20_M05_H10P50", {"dynamic_max_slots": 1, "dynamic_max_total_weight": 0.20, "dynamic_score_margin": 0.05, "dynamic_overheat_threshold": 0.10, "dynamic_overheat_penalty": 0.50}, "1 dynamic slot, 20% cap, 5% margin, prior20d >10% score x0.5"),
        ("CAP1_W20_M10_H10P50", {"dynamic_max_slots": 1, "dynamic_max_total_weight": 0.20, "dynamic_score_margin": 0.10, "dynamic_overheat_threshold": 0.10, "dynamic_overheat_penalty": 0.50}, "1 dynamic slot, 20% cap, 10% margin, prior20d >10% score x0.5"),
        ("CAP1_W10_M05_H10P50", {"dynamic_max_slots": 1, "dynamic_max_total_weight": 0.10, "dynamic_score_margin": 0.05, "dynamic_overheat_threshold": 0.10, "dynamic_overheat_penalty": 0.50}, "1 dynamic slot, 10% cap, 5% margin, prior20d >10% score x0.5"),
        ("CAP2_W20_M05_H15P50", {"dynamic_max_slots": 2, "dynamic_max_total_weight": 0.20, "dynamic_score_margin": 0.05, "dynamic_overheat_threshold": 0.15, "dynamic_overheat_penalty": 0.50}, "2 dynamic slots, 20% total cap, 5% margin, prior20d >15% score x0.5"),
    ]

    core_sets = [
        ("F2v3", f2),
        ("F2v3_ORIG38", f2_orig),
    ]
    rows: list[dict] = []

    for group, core in core_sets:
        for suffix, kwargs, notes in variants:
            run_case(rows, EngineParams(
                pit_pools=g2_pit,
                core_pool=core,
                holdings_num=5,
                start=START,
                end=END,
                exp_tag=f"DYNFUSE_{group}_{suffix}",
                dynamic_fusion_mode="capped",
                **kwargs,
            ), group, notes)

    manifest = pd.DataFrame(rows)
    manifest.to_csv(OUT / "dynamic_fusion_experiment_manifest.csv", index=False)
    print("\nSaved:", OUT / "dynamic_fusion_experiment_manifest.csv")
    print(manifest[[
        "tag", "annual_return", "sharpe_ratio", "max_drawdown",
        "final_value", "dynamic_buys", "dynamic_buy_value", "penalized_dynamic_buys",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()
