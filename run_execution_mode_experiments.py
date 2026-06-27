#!/usr/bin/env python3
"""Execution price and delay stress tests for ETF Loop."""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from strategies.etf_loop_engine import EngineParams, run_and_save  # noqa: E402


OUT = BASE_DIR / "outputs" / "etf_loop"
START = "2018-01-01"
END = "2026-06-25"


def load_pit_pool() -> dict[pd.Timestamp, list[str]]:
    with open(BASE_DIR / "data/tushare_cache/sector_prosperity/etf_pool_G2_PIT_monthly.pkl", "rb") as f:
        pools = pickle.load(f)
    return {pd.Timestamp(k): list(v) for k, v in pools.items()}


def load_f2_pool() -> list[str]:
    path = BASE_DIR / "data/tushare_cache/sector_prosperity/etf_pool_F2_v3.csv"
    return sorted(pd.read_csv(path, dtype={"ts_code": str})["ts_code"].astype(str).tolist())


def paths(tag: str) -> tuple[Path, Path, Path]:
    suffix = f"{tag}_h5_{START.replace('-', '')}_{END.replace('-', '')}"
    return (
        OUT / f"etf_loop_equity_{suffix}.csv",
        OUT / f"etf_loop_targets_{suffix}.csv",
        OUT / f"etf_loop_summary_{suffix}.csv",
    )


def bench_stats(equity: pd.DataFrame) -> dict[str, float]:
    if "benchmark_value" not in equity.columns:
        return {"benchmark_annual": np.nan, "benchmark_drawdown": np.nan}
    b = equity["benchmark_value"].dropna()
    daily = b.pct_change().dropna()
    if len(daily) < 2:
        return {"benchmark_annual": np.nan, "benchmark_drawdown": np.nan}
    return {
        "benchmark_annual": float(daily.mean() * 252.0),
        "benchmark_drawdown": float((b / b.cummax() - 1).min()),
    }


def run_case(rows: list[dict], params: EngineParams, label: str) -> None:
    eq_path, tr_path, sm_path = paths(params.exp_tag)
    if eq_path.exists() and tr_path.exists() and sm_path.exists():
        equity = pd.read_csv(eq_path, parse_dates=["date"]).set_index("date")
        trades = pd.read_csv(tr_path)
        stats = pd.read_csv(sm_path).iloc[0].to_dict()
        print(f"{params.exp_tag}: skip existing")
    else:
        equity, trades, audit = run_and_save(params, OUT)
        stats = audit["stats"]
    row = {
        "tag": params.exp_tag,
        "label": label,
        "execution_price_mode": params.execution_price_mode,
        "execution_delay_days": params.execution_delay_days,
        "slippage": params.slippage,
        "annual_return": stats.get("annual_return"),
        "sharpe_ratio": stats.get("sharpe_ratio"),
        "max_drawdown": stats.get("max_drawdown"),
        "final_value": stats.get("final_value"),
        "trade_count": int(len(trades)),
        **bench_stats(equity),
    }
    row["alpha_vs_hs300"] = row["annual_return"] - row["benchmark_annual"]
    rows.append(row)


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x * 100:.2f}%"


def write_report(df: pd.DataFrame) -> Path:
    path = OUT / "execution_mode_report.md"
    lines = [
        "# ETF Loop Execution Mode Stress",
        "",
        f"- window: `{START}` to `{END}`",
        "- config: `F2_CAP_MA60`",
        "- signal always uses signal-date close and prior data only",
        "",
        "| label | mode | delay | slippage | ann | sharpe | dd | alpha | trades | final |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in df.sort_values(["execution_delay_days", "execution_price_mode", "slippage"]).to_dict("records"):
        lines.append(
            f"| {r['label']} | {r['execution_price_mode']} | {int(r['execution_delay_days'])} | "
            f"{r['slippage'] * 100:.2f}% | {pct(r['annual_return'])} | {r['sharpe_ratio']:.2f} | "
            f"{pct(r['max_drawdown'])} | {pct(r['alpha_vs_hs300'])} | {int(r['trade_count'])} | {r['final_value']:.0f} |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pit = load_pit_pool()
    f2 = load_f2_pool()
    rows: list[dict] = []
    cases = [
        ("open_d1", "open", 1, 0.0001),
        ("vwap_d1", "vwap", 1, 0.0001),
        ("close_d1", "close", 1, 0.0001),
        ("open_d2", "open", 2, 0.0001),
        ("vwap_d2", "vwap", 2, 0.0001),
        ("close_d2", "close", 2, 0.0001),
        ("open_d1_adverse_20bp", "open", 1, 0.0020),
        ("open_d2_adverse_20bp", "open", 2, 0.0020),
    ]
    for label, mode, delay, slip in cases:
        tag = f"EXEC_F2_CAP_MA60_{label.upper()}"
        params = EngineParams(
            pit_pools=pit,
            core_pool=f2,
            holdings_num=5,
            start=START,
            end=END,
            exp_tag=tag,
            dynamic_fusion_mode="capped",
            dynamic_max_slots=1,
            dynamic_max_total_weight=0.10,
            dynamic_score_margin=0.05,
            dynamic_overheat_threshold=0.10,
            dynamic_overheat_penalty=0.50,
            mr_ma_period=60,
            mr_threshold=1.14,
            mr_penalty=0.50,
            execution_price_mode=mode,
            execution_delay_days=delay,
            slippage=slip,
        )
        run_case(rows, params, label)
    df = pd.DataFrame(rows)
    manifest = OUT / "execution_mode_manifest.csv"
    df.to_csv(manifest, index=False)
    report = write_report(df)
    print("Saved:", manifest)
    print("Saved:", report)
    print(df[["label", "annual_return", "sharpe_ratio", "max_drawdown", "alpha_vs_hs300", "trade_count"]].to_string(index=False))


if __name__ == "__main__":
    main()
