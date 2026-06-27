#!/usr/bin/env python3
"""Signal stability diagnostics for ETF Loop."""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from strategies.etf_loop_engine import EngineParams, _apply_dynamic_overheat_penalty, _get_active_pool, _select_targets  # noqa: E402
from strategies.etf_loop_strategy import ETFDailyStore, SectorProsperityCache, get_ranked_etfs  # noqa: E402


OUT = BASE_DIR / "outputs" / "etf_loop"
START = "2023-01-01"
END = "2026-06-25"


def load_pit_pool() -> dict[pd.Timestamp, list[str]]:
    with open(BASE_DIR / "data/tushare_cache/sector_prosperity/etf_pool_G2_PIT_monthly.pkl", "rb") as f:
        pools = pickle.load(f)
    return {pd.Timestamp(k): list(v) for k, v in pools.items()}


def load_f2_pool() -> list[str]:
    path = BASE_DIR / "data/tushare_cache/sector_prosperity/etf_pool_F2_v3.csv"
    return sorted(pd.read_csv(path, dtype={"ts_code": str})["ts_code"].astype(str).tolist())


def active_ranked(store: ETFDailyStore, params: EngineParams, date: pd.Timestamp, pool_months: list[pd.Timestamp]) -> tuple[list[dict], set[str], dict[str, float]]:
    pit_active = _get_active_pool(params.pit_pools, pool_months, date)
    core_set = set(params.core_pool) & set(store.ts_codes)
    active_pool = set(pit_active) | core_set
    dynamic_only = active_pool - core_set
    temp = store.ts_codes
    store.ts_codes = [c for c in temp if c in active_pool]
    ranked = get_ranked_etfs(store, date, params)
    store.ts_codes = temp
    ranked = _apply_dynamic_overheat_penalty(ranked, dynamic_only, store, date, params)
    targets, weights = _select_targets(ranked, params, core_set, dynamic_only)
    return ranked, targets, weights


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x * 100:.2f}%"


def main() -> None:
    pit = load_pit_pool()
    pool_months = sorted(pit.keys())
    f2 = load_f2_pool()
    params = EngineParams(
        pit_pools=pit,
        core_pool=f2,
        holdings_num=5,
        start=START,
        end=END,
        exp_tag="STABILITY_F2_CAP_MA60",
        dynamic_fusion_mode="capped",
        dynamic_max_slots=1,
        dynamic_max_total_weight=0.10,
        dynamic_score_margin=0.05,
        dynamic_overheat_threshold=0.10,
        dynamic_overheat_penalty=0.50,
        mr_ma_period=60,
        mr_threshold=1.14,
        mr_penalty=0.50,
    )
    all_codes = sorted(set(f2) | {c for p in pit.values() for c in p})
    cache = SectorProsperityCache(BASE_DIR / "config/tushare_token.txt", BASE_DIR / "data/tushare_cache")
    store = ETFDailyStore(cache, all_codes, START, END)
    rng = np.random.default_rng(42)
    rows = []
    prev_top5: set[str] | None = None
    for i, date in enumerate(store.calendar):
        if i < max(params.lookback_days, params.mr_ma_period) + 20:
            continue
        ranked, targets, weights = active_ranked(store, params, date, pool_months)
        if len(ranked) < 5:
            continue
        top = ranked[:5]
        top_codes = [r["ts_code"] for r in top]
        scores = np.array([float(r["score"]) for r in ranked[:10]], dtype=float)
        top1 = float(ranked[0]["score"])
        top2 = float(ranked[1]["score"]) if len(ranked) > 1 else np.nan
        denom = abs(top1) if abs(top1) > 1e-12 else 1.0
        margin = (top1 - top2) / denom if not np.isnan(top2) else np.nan

        noisy_top1_changes = 0
        base_top1 = ranked[0]["ts_code"]
        base_top5 = set(top_codes)
        top5_jaccards = []
        for _ in range(100):
            noisy = []
            for r in ranked[:20]:
                rr = dict(r)
                rr["score"] = float(rr["score"]) * (1.0 + rng.normal(0, 0.02))
                noisy.append(rr)
            noisy.sort(key=lambda x: x["score"], reverse=True)
            if noisy[0]["ts_code"] != base_top1:
                noisy_top1_changes += 1
            n5 = set(r["ts_code"] for r in noisy[:5])
            top5_jaccards.append(len(base_top5 & n5) / len(base_top5 | n5))

        turnover = np.nan
        if prev_top5 is not None:
            turnover = 1.0 - len(prev_top5 & base_top5) / len(prev_top5 | base_top5)
        prev_top5 = base_top5
        rows.append({
            "date": date,
            "top1": base_top1,
            "top2": ranked[1]["ts_code"],
            "top1_score": top1,
            "top2_score": top2,
            "top1_top2_margin": margin,
            "top5": ",".join(top_codes),
            "target_codes": ",".join(sorted(targets)),
            "top5_turnover": turnover,
            "noise_top1_change_rate": noisy_top1_changes / 100.0,
            "noise_top5_jaccard": float(np.mean(top5_jaccards)),
        })

    df = pd.DataFrame(rows)
    manifest = OUT / "signal_stability_manifest.csv"
    report = OUT / "signal_stability_report.md"
    df.to_csv(manifest, index=False)
    summary = {
        "days": len(df),
        "median_top1_top2_margin": df["top1_top2_margin"].median(),
        "p10_top1_top2_margin": df["top1_top2_margin"].quantile(0.10),
        "low_margin_days_lt_5pct": int((df["top1_top2_margin"] < 0.05).sum()),
        "median_top5_turnover": df["top5_turnover"].median(),
        "median_noise_top1_change_rate": df["noise_top1_change_rate"].median(),
        "p90_noise_top1_change_rate": df["noise_top1_change_rate"].quantile(0.90),
        "median_noise_top5_jaccard": df["noise_top5_jaccard"].median(),
    }
    lines = [
        "# ETF Loop Signal Stability",
        "",
        f"- window: `{START}` to `{END}`",
        "- config: `F2_CAP_MA60`",
        "- noise test: multiply scores by `1 + N(0, 0.02)` for 100 trials per day",
        "",
        "## Summary",
        "",
    ]
    for k, v in summary.items():
        lines.append(f"- `{k}`: `{v:.4f}`" if isinstance(v, float) else f"- `{k}`: `{v}`")
    lines += [
        "",
        "## Lowest Margin Days",
        "",
        "| date | top1 | top2 | margin | noise_top1_change | top5_turnover |",
        "|---|---|---|---:|---:|---:|",
    ]
    for r in df.sort_values("top1_top2_margin").head(30).to_dict("records"):
        lines.append(
            f"| {pd.Timestamp(r['date']).date()} | {r['top1']} | {r['top2']} | {pct(r['top1_top2_margin'])} | "
            f"{pct(r['noise_top1_change_rate'])} | {pct(r['top5_turnover'])} |"
        )
    report.write_text("\n".join(lines), encoding="utf-8")
    print("Saved:", manifest)
    print("Saved:", report)
    print(summary)


if __name__ == "__main__":
    main()
