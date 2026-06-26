#!/usr/bin/env python3
"""Batch runner for the theme ETF experiment matrix.

The runner is intentionally explicit: each experiment is mapped to a concrete
target-selection and risk rule profile so the result files can be compared
without hand-editing strategy code between runs.
"""
from __future__ import annotations

import argparse
import dataclasses
import multiprocessing
import os
import sys
from pathlib import Path

multiprocessing.set_start_method("fork")

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
os.environ.setdefault("MPLCONFIGDIR", str(BASE_DIR / ".matplotlib"))
from strategies._fundamental import FundamentalCache, qlib_to_tushare
from strategies._utils import QlibDailyReader, lot_floor, market_state, monthly_rebalance_dates, read_instrument_codes, summarize


def _weekly_rebalance_dates(calendar, start: str, end: str) -> list[pd.Timestamp]:
    """Return first trading day of each week."""
    cal = pd.DatetimeIndex([d for d in calendar if pd.Timestamp(start) <= d <= pd.Timestamp(end)])
    df = pd.DataFrame({"dt": cal, "wk": cal.to_period("W-MON")})
    return df.groupby("wk")["dt"].first().tolist()
from strategies.sector_prosperity import SectorProsperityCache
from strategies.theme_etf_momentum import (
    DailyBasicStore,
    DailyFrames,
    MoneyFlowCache,
    RealETFStore,
    RealETFUniverse,
    RollingFeatureStore,
    ThemeUniverse,
    add_buy_signals_fast,
    build_candidate_pool_fast,
    build_real_candidate_pool,
    compute_real_etf_scores,
    compute_theme_scores_fast,
    load_stock_basic_snapshot,
    output_paths,
    score_stock_pool_fast,
    select_themes,
)


PROVIDER_URI = Path(os.environ.get("QLIB_PROVIDER_URI", BASE_DIR / "data" / "a_share_qlib"))
TOKEN_PATH = BASE_DIR / "config" / "tushare_token.txt"
CACHE_DIR = BASE_DIR / "data" / "tushare_cache"
BENCHMARK = "sh000300"


@dataclasses.dataclass
class SuiteParams:
    initial_cash: float = 500_000.0
    target_num: int = 5
    etf_count: int = 5
    theme_top_pct: float = 0.10
    rs_top_pct: float = 0.20
    max_theme_weight: float = 0.40
    min_list_days: int = 120
    min_stock_amount_20d: float = 100_000.0
    min_turnover_20d: float = 1.0
    allow_min_total_mv: float = 500_000.0
    min_theme_amount_20d: float = 100_000.0
    min_theme_ret20: float = 0.05
    min_theme_ret60: float = 0.10
    max_theme_dist_ma60: float = 0.25
    constituents_per_theme: int = 30
    max_dist_ma20: float = 0.12
    max_dist_ma60: float = 0.35
    pullback_high_min: float = -0.08
    pullback_high_max: float = -0.02
    pullback_ma20_min: float = -0.03
    pullback_ma20_max: float = 0.05
    stop_loss: float = -0.08
    trailing_stop: float = -0.10
    trailing_activation: float = 0.10
    stale_hold_days: int = 20
    max_single_weight: float = 0.20
    risk_per_trade: float = 0.01
    market_filter: bool = True
    weak_market_position_scale: float = 0.50
    use_moneyflow: bool = False
    use_daily_basic: bool = True


@dataclasses.dataclass
class BacktestContext:
    provider_uri: Path
    cache_dir: Path
    token_path: Path
    market: str
    start: str
    end: str
    params: SuiteParams
    reader: QlibDailyReader
    calendar: pd.Index
    benchmark_close: pd.Series
    stock_codes: list[str]
    frames: DailyFrames
    store: RollingFeatureStore
    stock_basic: pd.DataFrame
    daily_basic_store: DailyBasicStore
    moneyflow: MoneyFlowCache | None
    theme_universe: ThemeUniverse | None
    real_universe: RealETFUniverse | None
    etf_store: RealETFStore | None
    sector_cache: SectorProsperityCache


def _safe_pct_rank(s: pd.Series, ascending: bool = True) -> pd.Series:
    return s.rank(ascending=ascending, pct=True).clip(0, 1).fillna(0.5)


def _weight_rows(rows: pd.DataFrame, theme_col: str = "theme", score_col: str | None = None) -> pd.DataFrame:
    if rows.empty:
        return rows
    df = rows.copy()
    themes = df[theme_col].dropna().astype(str).unique().tolist()
    if not themes:
        df["weight"] = 1.0 / len(df)
        return df
    theme_budget = 1.0 / len(themes)
    weights = []
    for theme in themes:
        part = df[df[theme_col].astype(str) == theme].copy()
        if part.empty:
            continue
        if score_col and score_col in part.columns and part[score_col].notna().any():
            w = pd.to_numeric(part[score_col], errors="coerce").clip(lower=0)
            if w.sum() <= 0:
                part["weight"] = theme_budget / len(part)
            else:
                part["weight"] = theme_budget * w / w.sum()
        else:
            part["weight"] = theme_budget / len(part)
        weights.append(part)
    out = pd.concat(weights, ignore_index=True) if weights else df
    out["weight"] = out["weight"].fillna(0.0)
    total = out["weight"].sum()
    if total > 0:
        out["weight"] /= total
    return out


def _apply_market_scale(ctx: BacktestContext, data_date: pd.Timestamp) -> float:
    if not ctx.params.market_filter:
        return 1.0
    state, _ = market_state(ctx.benchmark_close, data_date)
    if state == "MARKET_STRONG":
        return 1.0
    if state == "MARKET_NEUTRAL":
        return 0.70
    if state == "MARKET_WEAK":
        return ctx.params.weak_market_position_scale
    return 1.0


def _exit_reasons(
    code: str,
    theme: str,
    store: RollingFeatureStore,
    theme_scores: pd.DataFrame,
    stock_scores: pd.DataFrame,
    data_date: pd.Timestamp,
    entry_price: float,
    peak_price: float,
    entry_idx: int,
    current_idx: int,
    params: SuiteParams,
    trailing_activation: float | None = None,
    stale_fix: bool = False,
) -> list[str]:
    reasons: list[str] = []
    close = store.row("close", data_date).get(code, np.nan)
    ma20 = store.row("ma20", data_date).get(code, np.nan)
    if pd.isna(close) or pd.isna(ma20):
        return []
    if close < ma20:
        reasons.append("CLOSE_LT_MA20")
    if entry_price > 0 and close / entry_price - 1.0 < params.stop_loss:
        reasons.append("STOP_LOSS")
    if peak_price > 0:
        pnl = close / entry_price - 1.0 if entry_price > 0 else 0.0
        if trailing_activation is None:
            if close / peak_price - 1.0 < params.trailing_stop:
                reasons.append("TRAILING_STOP")
        else:
            if pnl >= trailing_activation and close / peak_price - 1.0 < params.trailing_stop:
                reasons.append("TRAILING_STOP")
    hold_days = current_idx - entry_idx
    if stale_fix:
        if hold_days > params.stale_hold_days and entry_price > 0 and peak_price / entry_price - 1.0 < 0.05:
            reasons.append("STALE_NO_PROFIT")
    else:
        if hold_days > params.stale_hold_days and close < peak_price:
            reasons.append("STALE_NO_NEWHIGH")

    row = stock_scores[stock_scores["code"] == code] if "code" in stock_scores.columns else pd.DataFrame()
    if not row.empty and float(row.iloc[0].get("rs20", 0.0)) < 0:
        reasons.append("RS20_LT_0")
    theme_row = theme_scores[theme_scores["theme"].astype(str) == str(theme)] if "theme" in theme_scores.columns else pd.DataFrame()
    if not theme_row.empty:
        tr = theme_row.iloc[0]
        if bool((tr.get("ret20", 0.0) < 0) or (not bool(tr.get("trend_ok", True))) or (not bool(tr.get("flow_ok", True)))):
            reasons.append("THEME_FAILED")
    volume = store.row("volume", data_date).get(code, np.nan)
    vol_ma20 = store.row("volume_ma20", data_date).get(code, np.nan)
    high60 = store.row("high60", data_date).get(code, np.nan)
    if pd.notnull(high60) and pd.notnull(volume) and pd.notnull(vol_ma20) and vol_ma20 > 0:
        pct_chg = store.row("pct_chg", data_date).get(code, np.nan)
        if close / high60 > 0.95 and volume > 2.0 * vol_ma20 and abs(pct_chg) < 0.01:
            reasons.append("HIGH_VOLUME_STALL")
    return reasons


def _select_random_targets(ctx: BacktestContext, data_date: pd.Timestamp, n: int = 5, seed: int = 0) -> pd.DataFrame:
    codes = [c for c in ctx.stock_codes if c in ctx.store.close.columns]
    if not codes:
        return pd.DataFrame()
    rng = np.random.default_rng(int(data_date.strftime("%Y%m%d")) + seed)
    chosen = rng.choice(codes, size=min(n, len(codes)), replace=False).tolist()
    return pd.DataFrame({"code": chosen, "weight": 1.0 / max(len(chosen), 1)})


def _select_momentum_targets(ctx: BacktestContext, data_date: pd.Timestamp, n: int = 5) -> pd.DataFrame:
    close = ctx.store.row("close", data_date)
    ret20 = ctx.store.row("ret20", data_date)
    df = pd.DataFrame({"code": ctx.stock_codes, "ret20": ret20.reindex(ctx.stock_codes).values})
    df = df[close.reindex(ctx.stock_codes).notna().values].copy()
    df = df.sort_values("ret20", ascending=False).head(n)
    if df.empty:
        return df
    df["weight"] = 1.0 / len(df)
    return df[["code", "weight"]]


def _select_trend_targets(ctx: BacktestContext, data_date: pd.Timestamp, n: int = 5) -> pd.DataFrame:
    close = ctx.store.row("close", data_date)
    ma20 = ctx.store.row("ma20", data_date)
    ma60 = ctx.store.row("ma60", data_date)
    ret60 = ctx.store.row("ret60", data_date)
    df = pd.DataFrame(
        {
            "code": ctx.stock_codes,
            "close": close.reindex(ctx.stock_codes).values,
            "ma20": ma20.reindex(ctx.stock_codes).values,
            "ma60": ma60.reindex(ctx.stock_codes).values,
            "ret60": ret60.reindex(ctx.stock_codes).values,
        }
    )
    df = df[(df["close"] > df["ma20"]) & (df["ma20"] > df["ma60"])].copy()
    df = df.sort_values("ret60", ascending=False).head(n)
    if df.empty:
        return df
    df["weight"] = 1.0 / len(df)
    return df[["code", "weight"]]


def _proxy_theme_setup(ctx: BacktestContext, data_date: pd.Timestamp):
    active_themes = ctx.theme_universe.industry.reindex(ctx.stock_codes).dropna() if ctx.theme_universe is not None else pd.Series(dtype=object)
    theme_scores = compute_theme_scores_fast(ctx.store, active_themes, data_date, ctx.params)
    selected_themes = select_themes(theme_scores, ctx.params) if not theme_scores.empty else pd.DataFrame()
    daily_basic = ctx.daily_basic_store.get(data_date)
    pool = build_candidate_pool_fast(ctx.store, ctx.theme_universe, selected_themes, data_date, daily_basic, ctx.params) if ctx.theme_universe is not None else pd.DataFrame()
    stock_scores = score_stock_pool_fast(pool, ctx.store, data_date, ctx.moneyflow, ctx.params) if not pool.empty else pd.DataFrame()
    stock_scores = add_buy_signals_fast(stock_scores, ctx.store, data_date) if not stock_scores.empty else stock_scores
    return theme_scores, selected_themes, pool, stock_scores


def _real_theme_setup(ctx: BacktestContext, data_date: pd.Timestamp):
    if ctx.real_universe is None or ctx.etf_store is None:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    etf_scores = compute_real_etf_scores(ctx.etf_store, ctx.real_universe.meta, data_date, ctx.params)
    selected_etfs = select_themes(etf_scores, ctx.params) if not etf_scores.empty else pd.DataFrame()
    daily_basic = ctx.daily_basic_store.get(data_date)
    pool = build_real_candidate_pool(
        ctx.store,
        ctx.sector_cache,
        selected_etfs,
        data_date,
        daily_basic,
        ctx.stock_basic,
        ctx.start,
        ctx.end,
        ctx.params,
    ) if not selected_etfs.empty else pd.DataFrame()
    stock_scores = score_stock_pool_fast(pool, ctx.store, data_date, ctx.moneyflow, ctx.params) if not pool.empty else pd.DataFrame()
    stock_scores = add_buy_signals_fast(stock_scores, ctx.store, data_date) if not stock_scores.empty else stock_scores
    return etf_scores, selected_etfs, pool, stock_scores


def _equal_weight_df(df: pd.DataFrame, code_col: str = "code") -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["weight"] = 1.0 / len(out)
    return out[[code_col, "weight"]]



def _build_no_theme_pool(ctx: BacktestContext, data_date: pd.Timestamp) -> pd.DataFrame:
    """Build a candidate pool from ALL stocks by reusing build_candidate_pool_fast
    with all themes selected.  This avoids maintaining duplicate filter logic."""
    if ctx.theme_universe is None:
        return pd.DataFrame()
    daily_basic = ctx.daily_basic_store.get(data_date)
    # Use the theme_scores from compute_theme_scores_fast as the "selected" themes,
    # but with all themes included (no filtering by selected_filter).
    active_themes = ctx.theme_universe.industry.reindex(ctx.store.codes).dropna()
    theme_scores = compute_theme_scores_fast(ctx.store, active_themes, data_date, ctx.params)
    if theme_scores.empty:
        return pd.DataFrame()
    # Create selected_themes with all themes (bypass select_themes filtering)
    fake_selected = theme_scores[["theme", "etf_score", "ret20", "ret60", "trend_ok", "flow_ok"]].copy()
    # Override constituents_per_theme to a large number so we don't truncate
    from dataclasses import replace as dcreplace
    p = dcreplace(ctx.params, constituents_per_theme=50)
    pool = build_candidate_pool_fast(
        ctx.store, ctx.theme_universe, fake_selected,
        data_date, daily_basic, p,
    )
    return pool if not pool.empty else pd.DataFrame()


def _proxy_targets(ctx: BacktestContext, data_date: pd.Timestamp, exp: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    theme_scores, selected_themes, pool, stock_scores = _proxy_theme_setup(ctx, data_date)

    # c6: C2_no_theme — skip theme grouping entirely
    if exp == "c6":
        pool = _build_no_theme_pool(ctx, data_date)
        if pool.empty:
            return pd.DataFrame(), pd.DataFrame()
        stock_scores = score_stock_pool_fast(pool, ctx.store, data_date, ctx.moneyflow, ctx.params)
        stock_scores = add_buy_signals_fast(stock_scores, ctx.store, data_date) if not stock_scores.empty else stock_scores
        if stock_scores.empty:
            return pd.DataFrame(), pd.DataFrame()
        df = stock_scores.copy()
        df = df[df["rs_ok"] & df["trend_ok"] & df["not_overheated"]].copy()
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()
        df = df[df["buy_signal_a"].fillna(False) & df["pullback_zone"].fillna(False)].copy()
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()
        df = df.sort_values("final_score", ascending=False).head(ctx.params.target_num).copy()
        df["theme"] = "ALL"
        df["weight"] = 1.0 / len(df)
        return df[["code", "theme", "weight"]], pd.DataFrame(), stock_scores

    if exp == "b0":
        df = pool.copy()
        if df.empty:
            return pd.DataFrame(), theme_scores, stock_scores
        df = _weight_rows(df, "theme")
        return df[["code", "theme", "weight"]], theme_scores, stock_scores
    if exp == "b1":
        df = pool.copy()
        if df.empty:
            return pd.DataFrame(), theme_scores, stock_scores
        score_col = "total_mv" if "total_mv" in df.columns and df["total_mv"].notna().any() else "amount20"
        df = _weight_rows(df, "theme", score_col=score_col)
        return df[["code", "theme", "weight"]], theme_scores, stock_scores
    if exp == "b2":
        df = pool.copy()
        if df.empty:
            return pd.DataFrame(), theme_scores, stock_scores
        top = df.sort_values(["theme", "amount20"], ascending=[True, False]).groupby("theme", as_index=False).head(10)
        top = _weight_rows(top, "theme")
        return top[["code", "theme", "weight"]], theme_scores
    if exp == "b3":
        df = stock_scores.copy()
        if df.empty:
            return pd.DataFrame(), theme_scores, stock_scores
        if "rs20" in df.columns:
            df = df.sort_values(["theme", "rs20"], ascending=[True, False]).groupby("theme", as_index=False).head(10)
        df = _weight_rows(df, "theme")
        return df[["code", "theme", "weight"]], theme_scores, stock_scores

    df = stock_scores.copy()
    if df.empty:
        return pd.DataFrame(), theme_scores, stock_scores
    df = df[df["rs_ok"] & df["trend_ok"] & df["not_overheated"]].copy()
    if df.empty:
        return pd.DataFrame(), theme_scores, stock_scores
    if exp in {"c2", "c3", "c4", "v3"}:
        if exp == "c2":
            df = df[df["buy_signal_a"].fillna(False) & df["pullback_zone"].fillna(False)]
        elif exp == "c3":
            df = df[df["buy_signal_b"].fillna(False)]
        elif exp == "c4":
            timing = (
                0.35 * _safe_pct_rank(df["stock_rs_score"])
                + 0.25 * _safe_pct_rank(df["structure_score"])
                + 0.20 * df["buy_signal_a"].fillna(False).astype(float)
                + 0.20 * df["buy_signal_b"].fillna(False).astype(float)
            )
            df = df.assign(timing_score=timing).sort_values("timing_score", ascending=False)
        elif exp == "v3":
            df = df[(df["buy_signal_a"].fillna(False) & df["pullback_zone"].fillna(False)) | df["buy_signal_b"].fillna(False)]
        elif exp == "c7a":
            # C7a: remove rs_cut only (keep rs_ok filter)
            df = df[df["rs_ok"] & df["trend_ok"] & df["not_overheated"]].copy()
            if df.empty:
                return pd.DataFrame(), theme_scores, stock_scores
            df = df[df["buy_signal_a"].fillna(False) & df["pullback_zone"].fillna(False)].copy()
            if df.empty:
                return pd.DataFrame(), theme_scores, stock_scores
            df = df.sort_values("final_score", ascending=False).head(ctx.params.target_num).copy()
            df = _weight_rows(df, "theme")
            return df[["code", "theme", "weight"]], theme_scores, stock_scores
        elif exp == "c7b":
            # C7b: remove rs_ok only (keep rs_cut)
            df = df[df["trend_ok"] & df["not_overheated"]].copy()
            if df.empty:
                return pd.DataFrame(), theme_scores, stock_scores
            df = df[df["buy_signal_a"].fillna(False) & df["pullback_zone"].fillna(False)].copy()
            if df.empty:
                return pd.DataFrame(), theme_scores, stock_scores
            df = df.sort_values("final_score", ascending=False)
            rs_cut = df["stock_rs_score"].quantile(1.0 - ctx.params.rs_top_pct)
            df = df[df["stock_rs_score"] >= rs_cut].copy()
            if df.empty:
                return pd.DataFrame(), theme_scores, stock_scores
            df = df.head(ctx.params.target_num).copy()
            df = _weight_rows(df, "theme")
            return df[["code", "theme", "weight"]], theme_scores, stock_scores
        elif exp == "c7c":
            # C7c: remove both rs_ok AND rs_cut (true no-RS)
            df = df[df["trend_ok"] & df["not_overheated"]].copy()
            if df.empty:
                return pd.DataFrame(), theme_scores, stock_scores
            df = df[df["buy_signal_a"].fillna(False) & df["pullback_zone"].fillna(False)].copy()
            if df.empty:
                return pd.DataFrame(), theme_scores, stock_scores
            df = df.sort_values("final_score", ascending=False).head(ctx.params.target_num).copy()
            df = _weight_rows(df, "theme")
            return df[["code", "theme", "weight"]], theme_scores, stock_scores
    if df.empty:
        return pd.DataFrame(), theme_scores, stock_scores
    if "timing_score" in df.columns:
        df = df.sort_values("timing_score", ascending=False)
    else:
        df = df.sort_values("final_score", ascending=False)
    if exp not in {"c7", "c7a", "c7c"}:
        rs_cut = df["stock_rs_score"].quantile(1.0 - ctx.params.rs_top_pct)
        df = df[df["stock_rs_score"] >= rs_cut].copy()
    df = df.head(ctx.params.target_num).copy()
    df = _weight_rows(df, "theme")
    return df[["code", "theme", "weight"]], theme_scores, stock_scores


def _real_targets(ctx: BacktestContext, data_date: pd.Timestamp, exp: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    etf_scores, selected_etfs, pool, stock_scores = _real_theme_setup(ctx, data_date)
    if exp == "d0":
        if selected_etfs.empty:
            return pd.DataFrame(), etf_scores, stock_scores, stock_scores
        selected_etfs = selected_etfs.copy()
        selected_etfs["weight"] = 1.0 / len(selected_etfs)
        return selected_etfs[["code", "weight"]], etf_scores
    if exp == "d1":
        if pool.empty:
            return pd.DataFrame(), etf_scores, stock_scores, stock_scores
        df = pool.copy()
        if "weight" in df.columns and df["weight"].notna().any():
            df = df.sort_values(["theme", "weight"], ascending=[True, False]).groupby("theme", as_index=False).head(10)
        else:
            df = df.sort_values(["theme", "amount20"], ascending=[True, False]).groupby("theme", as_index=False).head(10)
        df = _weight_rows(df, "theme", score_col="weight" if "weight" in df.columns else "amount20")
        return df[["code", "theme", "weight"]], etf_scores, stock_scores
    if exp == "d2":
        df = stock_scores.copy()
        if df.empty:
            return pd.DataFrame(), etf_scores, stock_scores, stock_scores
        df = df[df["rs_ok"] & df["trend_ok"]].copy()
        if df.empty:
            return pd.DataFrame(), etf_scores, stock_scores, stock_scores
        df = df.sort_values(["theme", "stock_rs_score"], ascending=[True, False]).groupby("theme", as_index=False).head(10)
        df = _weight_rows(df, "theme")
        return df[["code", "theme", "weight"]], etf_scores, stock_scores
    if exp == "d3":
        df = stock_scores.copy()
        if df.empty:
            return pd.DataFrame(), etf_scores, stock_scores, stock_scores
        df = df[df["rs_ok"] & df["trend_ok"]].copy()
        if df.empty:
            return pd.DataFrame(), etf_scores, stock_scores, stock_scores
        df = df[(df["buy_signal_a"].fillna(False) & df["pullback_zone"].fillna(False)) | df["buy_signal_b"].fillna(False)].copy()
        if df.empty:
            return pd.DataFrame(), etf_scores, stock_scores, stock_scores
        df = df.sort_values(["theme", "final_score"], ascending=[True, False]).groupby("theme", as_index=False).head(10)
        df = _weight_rows(df, "theme")
        return df[["code", "theme", "weight"]], etf_scores, stock_scores
    if exp == "d4":
        # D4 = D3 + C2 hard buy_signal_a filter (no buy_signal_b fallback) + not_overheated
        df = stock_scores.copy()
        if df.empty:
            return pd.DataFrame(), etf_scores, stock_scores, stock_scores
        df = df[df["rs_ok"] & df["trend_ok"] & df["not_overheated"]].copy()
        if df.empty:
            return pd.DataFrame(), etf_scores, stock_scores, stock_scores
        df = df[df["buy_signal_a"].fillna(False) & df["pullback_zone"].fillna(False)].copy()
        if df.empty:
            return pd.DataFrame(), etf_scores, stock_scores, stock_scores
        df = df.sort_values(["theme", "final_score"], ascending=[True, False]).groupby("theme", as_index=False).head(10)
        df = _weight_rows(df, "theme")
        return df[["code", "theme", "weight"]], etf_scores, stock_scores
    return pd.DataFrame(), etf_scores, stock_scores, stock_scores


def _build_context(market: str, start: str, end: str, params: SuiteParams, load_real_etf: bool = True) -> BacktestContext:
    reader = QlibDailyReader(PROVIDER_URI)
    if market.lower() in {"hs300", "csi300", "000300"}:
        from strategies._utils import Hs300HistoryUniverse, load_hs300_weights

        weights = load_hs300_weights(CACHE_DIR, TOKEN_PATH, start, end)
        universe = sorted(weights["code"].str.lower().unique().tolist())
        hist_uni = Hs300HistoryUniverse(weights)
    else:
        from strategies._utils import Hs300HistoryUniverse

        universe = read_instrument_codes(PROVIDER_URI, market)
        hist_uni = None
    all_codes = sorted(set(universe + [BENCHMARK]))
    frames = DailyFrames(reader, all_codes, start, end)
    stock_codes = [c for c in universe if c in frames.close.columns]
    if not stock_codes:
        raise RuntimeError("No stock OHLCV data available for selected market")
    store = RollingFeatureStore(frames, stock_codes)
    benchmark_close = frames.close[BENCHMARK].dropna()
    stock_basic_cache = FundamentalCache(TOKEN_PATH, CACHE_DIR / "theme_etf_momentum")
    stock_basic = load_stock_basic_snapshot(stock_basic_cache, CACHE_DIR)
    daily_basic_store = DailyBasicStore(CACHE_DIR)
    moneyflow = MoneyFlowCache(CACHE_DIR) if params.use_moneyflow else None
    theme_universe = ThemeUniverse(stock_basic, stock_codes) if not stock_basic.empty else None
    sector_cache = SectorProsperityCache(TOKEN_PATH, CACHE_DIR)
    if load_real_etf:
        sector_cache.prefetch_etf_data(start, end)
        real_universe = RealETFUniverse(sector_cache)
        etf_store = RealETFStore(sector_cache, real_universe, start, end) if not real_universe.meta.empty else None
    else:
        real_universe = RealETFUniverse(sector_cache)
        etf_store = None
    ctx = BacktestContext(
        provider_uri=PROVIDER_URI,
        cache_dir=CACHE_DIR,
        token_path=TOKEN_PATH,
        market=market,
        start=start,
        end=end,
        params=params,
        reader=reader,
        calendar=frames.close.index,
        benchmark_close=benchmark_close,
        stock_codes=stock_codes,
        frames=frames,
        store=store,
        stock_basic=stock_basic,
        daily_basic_store=daily_basic_store,
        moneyflow=moneyflow,
        theme_universe=theme_universe,
        real_universe=real_universe,
        etf_store=etf_store,
        sector_cache=sector_cache,
    )
    ctx._a0_seed = getattr(params, '_a0_seed', 0)
    return ctx


def _run_weighted_backtest(ctx: BacktestContext, exp: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if exp == "d0":
        return _run_etf_only_backtest(ctx)

    calendar = ctx.calendar
    # A/B: monthly rebalance; C/R/D: weekly theme selection + daily buy-signal check
    _monthly = set(monthly_rebalance_dates(pd.Series(calendar), ctx.start, ctx.end))
    _weekly = set(_weekly_rebalance_dates(pd.Series(calendar), ctx.start, ctx.end))
    rebal_dates = _weekly if exp.startswith(("c", "r", "d")) else _monthly
    cash = ctx.params.initial_cash
    shares = pd.Series(0.0, index=pd.Index(ctx.stock_codes))
    entry_price: dict[str, float] = {}
    entry_idx: dict[str, int] = {}
    peak_price: dict[str, float] = {}
    code_theme: dict[str, str] = {}
    records: list[dict] = []
    target_rows: list[dict] = []
    theme_rows: list[dict] = []

    for i, data_date in enumerate(calendar[:-1]):
        if i < 61:
            continue
        next_date = calendar[i + 1]
        # For A/B: skip non-rebal days (valuation-only).
        # For C/R/D: run sell rules daily, but only recompute themes/targets on rebal_dates.
        skip_targets = False
        if data_date not in rebal_dates:
            if not str(exp).startswith(("c", "r", "d")):
                next_open = ctx.store.open.loc[next_date]
                next_close = ctx.store.close.loc[next_date]
                value = cash + float((shares * next_close.reindex(ctx.stock_codes).fillna(next_open.reindex(ctx.stock_codes))).sum())
                records.append({"date": next_date, "portfolio_value": value, "cash": cash, "position_count": int((shares > 0).sum())})
                continue
            else:
                # C/R/D on non-rebal day: run sell rules only, skip target recomputation
                skip_targets = True

        if exp.startswith("a"):
            if exp == "a0":
                targets = _select_random_targets(ctx, data_date, 5, seed=getattr(ctx, '_a0_seed', 0))
            elif exp == "a1":
                targets = _select_momentum_targets(ctx, data_date, 5)
            else:
                targets = _select_trend_targets(ctx, data_date, 5)
            theme_scores = pd.DataFrame()
            stock_scores = pd.DataFrame()
        elif exp.startswith("b") or exp.startswith("c") or exp.startswith("r"):
            targets, theme_scores, stock_scores = _proxy_targets(ctx, data_date, exp)
        elif exp.startswith("d"):
            targets, theme_scores, stock_scores = _real_targets(ctx, data_date, exp)
        else:
            raise ValueError(f"Unknown experiment: {exp}")

        if skip_targets:
            targets = pd.DataFrame()
        target_set = set(targets["code"].astype(str).tolist()) if not targets.empty else set()
        next_open = ctx.store.open.loc[next_date]
        signal_close = ctx.store.close.loc[data_date]
        next_close = ctx.store.close.loc[next_date]
        market_scale = _apply_market_scale(ctx, data_date) if exp in {"c5", "d3", "d4", "d5"} else 1.0

        # Sell
        for code in shares[shares > 0].index.tolist():
            theme = code_theme.get(code, "UNKNOWN")
            TRAILING_EXPS = {"r1", "r3", "c2", "c3", "c4", "c5", "c6", "c7", "c7a", "c7b", "c7c", "d3", "d4", "d5"}
            STALE_FIX_EXPS = {"r2", "r3", "c2", "c3", "c4", "c5", "c6", "c7", "c7a", "c7b", "c7c"}
            trailing_activation = ctx.params.trailing_activation if exp in TRAILING_EXPS else None
            stale_fix = exp in STALE_FIX_EXPS
            reasons = _exit_reasons(
                code,
                theme,
                ctx.store,
                theme_scores if "theme_scores" in locals() else pd.DataFrame(),
                stock_scores if "stock_scores" in locals() else pd.DataFrame(),
                data_date,
                entry_price.get(code, np.nan),
                peak_price.get(code, np.nan),
                entry_idx.get(code, i),
                i,
                ctx.params,
                trailing_activation=trailing_activation,
                stale_fix=stale_fix,
            )
            if code in target_set and not reasons:
                continue
            px = next_open.get(code, np.nan)
            prev_px = signal_close.get(code, np.nan)
            if pd.isna(prev_px) or pd.isna(px) or px <= 0 or prev_px <= 0:
                continue
            if px / prev_px - 1.0 <= -0.095:
                continue
            if pd.notnull(px) and px > 0:
                cash += shares[code] * px * 0.9985
                shares[code] = 0.0
                entry_price.pop(code, None)
                entry_idx.pop(code, None)
                peak_price.pop(code, None)
                code_theme.pop(code, None)

        # Buy/rebalance
        if not targets.empty:
            total_value = cash + float((shares * next_open.reindex(ctx.stock_codes).fillna(signal_close.reindex(ctx.stock_codes))).sum())
            if exp in {"r3"}:
                max_weight = min(ctx.params.max_single_weight, ctx.params.risk_per_trade / abs(ctx.params.stop_loss))
            else:
                max_weight = ctx.params.max_single_weight
            for row in targets.sort_values("weight", ascending=False).itertuples(index=False):
                code = row.code if hasattr(row, "code") else getattr(row, "theme")
                weight = float(getattr(row, "weight", 0.0))
                weight = min(weight, max_weight)
                target_value = total_value * market_scale * weight
                px = next_open.get(code, np.nan)
                prev_px = signal_close.get(code, np.nan)
                if pd.isna(px) or px <= 0 or pd.isna(prev_px) or prev_px <= 0:
                    continue
                if px / prev_px - 1.0 >= 0.095:
                    continue
                current_value = shares.get(code, 0.0) * px
                diff_value = target_value - current_value
                if diff_value <= 0:
                    continue
                buy_cash = min(cash, diff_value)
                buy_shares = lot_floor(buy_cash / (px * 1.001))
                if buy_shares <= 0:
                    continue
                cash -= buy_shares * px * 1.001
                shares[code] += buy_shares
                if code not in entry_price:
                    entry_price[code] = px
                    entry_idx[code] = i + 1
                    peak_price[code] = next_close.get(code, px)
                    code_theme[code] = getattr(row, "theme", "UNKNOWN") if hasattr(row, "theme") else "UNKNOWN"
                target_rows.append({"date": data_date, "trade_date": next_date, "code": code, "theme": getattr(row, "theme", "UNKNOWN"), "weight": weight, "experiment": exp})

        for code in shares[shares > 0].index:
            px_close = next_close.get(code, np.nan)
            if pd.notnull(px_close):
                peak_price[code] = max(peak_price.get(code, px_close), px_close)

        for row in targets.itertuples(index=False):
            theme_rows.append({"date": data_date, "theme": getattr(row, "theme", getattr(row, "code", "")), "weight": getattr(row, "weight", np.nan), "experiment": exp})

        portfolio_value = cash + float((shares * next_close.reindex(ctx.stock_codes).fillna(next_open.reindex(ctx.stock_codes))).sum())
        records.append(
            {
                "date": next_date,
                "portfolio_value": portfolio_value,
                "cash": cash,
                "position_count": int((shares > 0).sum()),
                "target_count": int(len(targets)),
                "position_scale": market_scale,
            }
        )

    equity = pd.DataFrame(records).drop_duplicates("date", keep="last").set_index("date")
    if equity.empty:
        raise RuntimeError(f"Experiment {exp} produced no equity records")
    bench = ctx.benchmark_close.reindex(equity.index).ffill()
    equity["benchmark_value"] = ctx.params.initial_cash * bench / bench.dropna().iloc[0]
    equity["strategy_return"] = equity["portfolio_value"] / equity["portfolio_value"].iloc[0] - 1.0
    equity["benchmark_return"] = equity["benchmark_value"] / equity["benchmark_value"].iloc[0] - 1.0
    return equity, pd.DataFrame(target_rows), pd.DataFrame(theme_rows)


def _run_etf_only_backtest(ctx: BacktestContext) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if ctx.etf_store is None or ctx.real_universe is None:
        raise RuntimeError("Real ETF data is not available for D0")
    calendar = ctx.etf_store.close.index
    rebal_dates = set(_weekly_rebalance_dates(pd.Series(calendar), ctx.start, ctx.end))
    tradable_codes = [c for c in ctx.etf_store.close.columns if c in ctx.etf_store.close.columns]
    cash = ctx.params.initial_cash
    shares = pd.Series(0.0, index=pd.Index(tradable_codes))
    records: list[dict] = []
    target_rows: list[dict] = []
    theme_rows: list[dict] = []

    for i, data_date in enumerate(calendar[:-1]):
        if i < 20:
            continue
        next_date = calendar[i + 1]
        if data_date not in rebal_dates:
            next_open = ctx.etf_store.open.loc[next_date]
            next_close = ctx.etf_store.close.loc[next_date]
            value = cash + float((shares * next_close.reindex(tradable_codes).fillna(next_open.reindex(tradable_codes))).sum())
            records.append({"date": next_date, "portfolio_value": value, "cash": cash, "position_count": int((shares > 0).sum())})
            continue

        etf_scores = compute_real_etf_scores(ctx.etf_store, ctx.real_universe.meta, data_date, ctx.params)
        selected_etfs = select_themes(etf_scores, ctx.params) if not etf_scores.empty else pd.DataFrame()
        if selected_etfs.empty:
            next_open = ctx.etf_store.open.loc[next_date]
            next_close = ctx.etf_store.close.loc[next_date]
            value = cash + float((shares * next_close.reindex(tradable_codes).fillna(next_open.reindex(tradable_codes))).sum())
            records.append({"date": next_date, "portfolio_value": value, "cash": cash, "position_count": int((shares > 0).sum())})
            continue

        target_df = selected_etfs[["code"]].copy()
        target_df["theme"] = target_df["code"]
        target_df["weight"] = 1.0 / len(target_df)
        next_open = ctx.etf_store.open.loc[next_date]
        signal_close = ctx.etf_store.close.loc[data_date]
        next_close = ctx.etf_store.close.loc[next_date]

        for code in shares[shares > 0].index.tolist():
            if code not in set(target_df["code"]):
                px = next_open.get(code, np.nan)
                if pd.notnull(px) and px > 0:
                    cash += shares[code] * px * 0.9985
                    shares[code] = 0.0

        total_value = cash + float((shares * next_open.reindex(tradable_codes).fillna(signal_close.reindex(tradable_codes))).sum())
        for row in target_df.itertuples(index=False):
            code = row.code
            target_value = total_value / len(target_df)
            px = next_open.get(code, np.nan)
            if pd.isna(px) or px <= 0:
                continue
            diff_value = target_value - shares.get(code, 0.0) * px
            if diff_value <= 0:
                continue
            buy_cash = min(cash, diff_value)
            buy_shares = lot_floor(buy_cash / (px * 1.001))
            if buy_shares <= 0:
                continue
            cash -= buy_shares * px * 1.001
            shares[code] += buy_shares
            target_rows.append({"date": data_date, "trade_date": next_date, "code": code, "theme": code, "weight": 1.0 / len(target_df), "experiment": "d0"})

        for row in selected_etfs.itertuples(index=False):
            theme_rows.append({"date": data_date, "theme": row.code, "weight": 1.0 / len(selected_etfs), "experiment": "d0"})

        value = cash + float((shares * next_close.reindex(tradable_codes).fillna(next_open.reindex(tradable_codes))).sum())
        records.append({"date": next_date, "portfolio_value": value, "cash": cash, "position_count": int((shares > 0).sum())})

    equity = pd.DataFrame(records).drop_duplicates("date", keep="last").set_index("date")
    if equity.empty:
        raise RuntimeError("D0 produced no equity records")
    bench = ctx.benchmark_close.reindex(equity.index).ffill()
    equity["benchmark_value"] = ctx.params.initial_cash * bench / bench.dropna().iloc[0]
    equity["strategy_return"] = equity["portfolio_value"] / equity["portfolio_value"].iloc[0] - 1.0
    equity["benchmark_return"] = equity["benchmark_value"] / equity["benchmark_value"].iloc[0] - 1.0
    return equity, pd.DataFrame(target_rows), pd.DataFrame(theme_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the theme ETF experiment matrix")
    parser.add_argument("--market", default="all_a")
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="2026-06-22")
    parser.add_argument("--experiments", default="a0,a1,a2,b0,b1,b2,b3,c1,c2,c3,c4,c5,r1,r2,r3,r4,d0,d1,d2,d3")
    parser.add_argument("--initial-cash", type=float, default=500_000.0)
    parser.add_argument("--target-num", type=int, default=5)
    parser.add_argument("--etf-count", type=int, default=5)
    parser.add_argument("--rs-top-pct", type=float, default=None, help="Override rs_top_pct (default 0.20)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed override for A0 experiment")
    parser.add_argument("--no-moneyflow", action="store_true", default=False)
    parser.add_argument("--skip-real-etf", action="store_true", default=False)
    args = parser.parse_args()

    params = SuiteParams(
        initial_cash=args.initial_cash,
        target_num=args.target_num,
        etf_count=args.etf_count,
        use_moneyflow=not args.no_moneyflow,
    )
    if args.rs_top_pct is not None:
        params.rs_top_pct = args.rs_top_pct
    experiments = [e.strip().lower() for e in args.experiments.split(",") if e.strip()]
    if args.seed is not None:
        params._a0_seed = args.seed
    load_real_etf = any(e.startswith("d") for e in experiments) and not args.skip_real_etf
    ctx = _build_context(args.market, args.start, args.end, params, load_real_etf=load_real_etf)
    out_root = BASE_DIR / "outputs" / "theme_etf_experiments"
    out_root.mkdir(parents=True, exist_ok=True)

    for exp in experiments:
        if args.skip_real_etf and exp.startswith("d"):
            continue
        print(f"\n=== {exp.upper()} ===")
        equity, targets, themes = _run_weighted_backtest(ctx, exp)
        exp_dir = out_root / exp
        exp_dir.mkdir(parents=True, exist_ok=True)
        suffix = f"{args.market}_{exp}_{pd.Timestamp(args.start):%Y%m%d}_{pd.Timestamp(args.end):%Y%m%d}"
        equity_path = exp_dir / f"equity_{suffix}.csv"
        targets_path = exp_dir / f"targets_{suffix}.csv"
        themes_path = exp_dir / f"themes_{suffix}.csv"
        summary_path = exp_dir / f"summary_{suffix}.csv"
        equity.to_csv(equity_path)
        targets.to_csv(targets_path, index=False)
        themes.to_csv(themes_path, index=False)
        summary = summarize(equity)
        summary.update({"experiment": exp})
        pd.DataFrame([summary]).to_csv(summary_path, index=False)
        print(pd.DataFrame([summary]).to_string(index=False))
        print(f"  equity:  {equity_path}")
        print(f"  targets: {targets_path}")
        print(f"  themes:  {themes_path}")
        print(f"  summary: {summary_path}")


if __name__ == "__main__":
    main()
