#!/usr/bin/env python3
"""Trend-Serenity V2 回测脚本 — 支持 HS300 / all_a universe"""
from __future__ import annotations
import argparse, datetime as dt, multiprocessing, os, sys
from pathlib import Path
multiprocessing.set_start_method("fork")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = PROJECT_ROOT
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
os.environ.setdefault("MPLCONFIGDIR", str(BASE_DIR / ".matplotlib"))
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np, pandas as pd

PROVIDER_URI = Path(os.environ.get("QLIB_PROVIDER_URI", BASE_DIR / "data" / "a_share_qlib"))
TOKEN_PATH = BASE_DIR / "config" / "tushare_token.txt"
CACHE_DIR = BASE_DIR / "data" / "tushare_cache"
OUT_DIR = BASE_DIR / "outputs"
BENCHMARK = "sh000300"
sys.path.insert(0, str(PROJECT_ROOT))

from strategies._fundamental import FundamentalCache, qlib_to_tushare
from strategies._enrichment import EnrichmentCache
from strategies._utils import (QlibDailyReader, Hs300HistoryUniverse, load_hs300_weights, lot_floor, rebalance_dates, summarize, read_instrument_codes)
from strategies.sector_prosperity import (
    SectorProsperityCache,
    SectorProsperityParams,
    attach_sector_scores,
    compute_sector_scores,
    compute_stock_topic_scores,
)
from strategies._risk import RiskParams, check_single_stop_loss
from strategies.trend_serenity import (TrendSerenityParams, build_serenity_pool_v2, select_targets_v2, check_invalidation)
from strategies.trend_serenity_v2 import compute_serenity_v2, compute_theme_enhancement, select_serenity_v2_targets


def _held_days(entry_date: pd.Timestamp | None, current_date: pd.Timestamp) -> int:
    if entry_date is None:
        return 10**9
    return max(0, (pd.Timestamp(current_date) - pd.Timestamp(entry_date)).days)


def _score_column(pool: pd.DataFrame) -> str | None:
    for col in (
        "prosperity_score",
        "serenity_score_v2",
        "serenity_score",
        "serenity_score_before_sector",
    ):
        if col in pool.columns:
            return col
    return None


def _sell_position(
    code: str,
    px: float,
    cash: float,
    shares: pd.Series,
    entry_dates: dict,
    entry_prices: dict,
    highest_since_entry: dict,
    close_cost: float,
) -> tuple[float, float]:
    amount = float(shares.get(code, 0.0))
    if amount <= 0 or pd.isnull(px) or px <= 0:
        return cash, 0.0
    gross = amount * px
    cash += gross * (1 - close_cost)
    shares[code] = 0
    entry_dates.pop(code, None)
    entry_prices.pop(code, None)
    highest_since_entry.pop(code, None)
    return cash, gross

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2018-01-02")
    p.add_argument("--end", default="2026-06-22")
    p.add_argument("--market", default="hs300")
    p.add_argument("--target-num", type=int, default=10)
    p.add_argument("--initial-cash", type=float, default=1_000_000.0)
    p.add_argument("--skip-enrich", action="store_true", default=False)
    p.add_argument("--factor-version", choices=["v1", "v2"], default="v2")
    p.add_argument("--no-buffer", action="store_true", default=False)
    p.add_argument("--rebalance-frequency", choices=["monthly", "weekly"], default="monthly")
    p.add_argument("--risk-controls", action="store_true", default=False)
    p.add_argument("--stop-loss-pct", type=float, default=-0.20)
    p.add_argument("--trailing-stop-activation", type=float, default=0.30)
    p.add_argument("--trailing-stop-distance", type=float, default=0.15)
    p.add_argument("--min-hold-days", type=int, default=0)
    p.add_argument("--max-turnover-pct", type=float, default=1.0)
    p.add_argument("--v2-experiment", choices=["base", "theme"], default="base")
    p.add_argument("--theme-weight", type=float, default=0.18)
    p.add_argument("--sector-model", choices=["none", "boost", "gate", "hybrid"], default="none")
    p.add_argument("--sector-top-k", type=int, default=12)
    p.add_argument("--sector-min-score", type=float, default=0.58)
    p.add_argument("--sector-weight", type=float, default=0.25)
    p.add_argument("--sector-reserve-quantile", type=float, default=0.30)
    p.add_argument("--no-topic-graph", action="store_true", default=False)
    p.add_argument("--sector-fetch-data", action="store_true", default=False)
    p.add_argument("--sector-fetch-max-topics", type=int, default=500)
    p.add_argument("--sector-fetch-topic-daily", action="store_true", default=False)
    p.add_argument("--sector-fetch-events", action="store_true", default=False)
    p.add_argument("--sector-fetch-etf", action="store_true", default=False)
    args = p.parse_args()

    print(f"数据源: {PROVIDER_URI}")
    print(
        f"回测: {args.start} — {args.end} 市场:{args.market} "
        f"因子:{args.factor_version} 实验:{args.v2_experiment} "
        f"板块:{args.sector_model} 调仓:{args.rebalance_frequency} "
        f"风控:{args.risk_controls} 富集:{not args.skip_enrich}"
    )
    params = TrendSerenityParams(
        initial_cash=args.initial_cash,
        target_num=args.target_num,
        factor_version=args.factor_version,
        use_buffer=not args.no_buffer,
    )
    risk = RiskParams(
        stop_loss_pct=args.stop_loss_pct,
        trailing_stop_activation=args.trailing_stop_activation,
        trailing_stop_distance=args.trailing_stop_distance,
        min_hold_days=max(0, args.min_hold_days),
    )
    max_turnover_pct = min(max(float(args.max_turnover_pct), 0.0), 1.0)

    # ── 1. universe ──
    market = args.market.lower()
    if market in {"hs300", "csi300_history", "000300"}:
        print("加载 HS300 成分股...")
        weights = load_hs300_weights(CACHE_DIR, TOKEN_PATH, args.start, args.end)
        hist_uni = Hs300HistoryUniverse(weights)
        universe = sorted(weights["code"].str.lower().unique().tolist())
    else:
        print(f"加载 {market} universe...")
        universe = read_instrument_codes(PROVIDER_URI, market)
        hist_uni = None
    print(f"  {len(universe)} 只")

    # ── 2. 行情 ──
    print("加载行情...")
    reader = QlibDailyReader(PROVIDER_URI)
    all_codes = sorted(set(universe + [BENCHMARK]))
    close = reader.close_frame(all_codes, args.start, args.end)
    stock_close = close[[c for c in universe if c in close.columns]]
    bench_close = close[BENCHMARK]
    print(f"  有效: {stock_close.shape[1]}只 × {stock_close.shape[0]}日")
    if stock_close.empty:
        print("ERROR: 无行情数据"); sys.exit(1)

    # ── 3. 基础数据 ──
    print("预拉取基础财务数据...")
    data = FundamentalCache(TOKEN_PATH, CACHE_DIR / "trend_serenity")
    ts_uni = [qlib_to_tushare(c) for c in universe]
    data.prefetch(ts_uni, args.start, args.end)
    print("  基础数据就绪")

    # ── 4. 富集数据 ──
    enrich = None
    if not args.skip_enrich:
        print("预拉取富集数据...")
        enrich = EnrichmentCache(TOKEN_PATH, CACHE_DIR)
        try:
            enrich.prefetch(ts_uni, args.start, args.end)
            print("  富集数据就绪")
        except Exception as e:
            print(f"  富集部分失败(历史数据缺失属正常): {e}")

    sector_params = SectorProsperityParams(
        model=args.sector_model,
        top_k=args.sector_top_k,
        min_score=args.sector_min_score,
        weight=args.sector_weight,
        reserve_quantile=args.sector_reserve_quantile,
        use_topic_graph=not args.no_topic_graph,
    )
    sector_cache = None
    stock_basic = None
    if sector_params.model != "none":
        print("启用板块景气度层...")
        sector_cache = SectorProsperityCache(TOKEN_PATH, CACHE_DIR)
        if args.sector_fetch_data:
            print("  拉取/补齐题材图谱缓存...")
            sector_cache.prefetch_topic_graph(
                args.start,
                args.end,
                max_topics=args.sector_fetch_max_topics,
                fetch_topic_daily=args.sector_fetch_topic_daily,
                fetch_events=args.sector_fetch_events,
                fetch_etf=args.sector_fetch_etf,
            )
        stock_basic = data.stock_basic()
        print("  板块缓存就绪")

    # ── 5. 回测循环 ──
    cal = pd.Series(reader.calendar)
    rebal = rebalance_dates(cal, args.start, args.end, args.rebalance_frequency)
    rebal_set = set(rebal)
    print(f"调仓日期: {len(rebal)}")

    cash = params.initial_cash
    shares = pd.Series(0.0, index=stock_close.columns)
    records, target_rows = [], []
    entry_dates, entry_prices, highest_since_entry = {}, {}, {}

    for i, date in enumerate(stock_close.index[:-1]):
        next_date = stock_close.index[i + 1]
        prices = stock_close.loc[date]

        risk_sells = 0
        risk_sell_notional = 0.0
        if args.risk_controls:
            for code in list(shares.index):
                if shares[code] <= 0:
                    continue
                px = prices.get(code, np.nan)
                if pd.isnull(px) or px <= 0:
                    continue
                if code in highest_since_entry:
                    highest_since_entry[code] = max(float(highest_since_entry[code]), float(px))
                elif code in entry_prices:
                    highest_since_entry[code] = max(float(entry_prices[code]), float(px))
                else:
                    continue
                should_sell, _ = check_single_stop_loss(
                    code,
                    float(entry_prices.get(code, px)),
                    float(px),
                    float(highest_since_entry.get(code, px)),
                    risk,
                )
                if should_sell:
                    cash, gross = _sell_position(
                        code,
                        float(px),
                        cash,
                        shares,
                        entry_dates,
                        entry_prices,
                        highest_since_entry,
                        params.close_cost,
                    )
                    if gross > 0:
                        risk_sells += 1
                        risk_sell_notional += gross

        if date not in rebal_set or i == 0:
            nv = cash + float((shares * stock_close.loc[next_date].fillna(prices)).sum())
            records.append({
                "date": next_date,
                "portfolio_value": nv,
                "cash": cash,
                "position_count": int((shares > 0).sum()),
                "risk_sells": risk_sells,
                "risk_sell_notional": risk_sell_notional,
                "invalidation_sells": 0,
                "rebalance_sell_notional": 0.0,
                "min_hold_blocks": 0,
                "turnover_blocks": 0,
            })
            continue

        data_date = stock_close.index[i - 1]
        if hist_uni is not None:
            au = hist_uni.codes_for_date(data_date)
        else:
            au = [c for c in universe if c in stock_close.columns]

        # 失效纪律
        force_sell = set()
        if enrich is not None:
            for code in shares.index:
                if shares[code] > 0 and code in entry_dates:
                    try:
                        inv = check_invalidation(code, data, enrich, data_date, entry_dates[code])
                        if inv["invalidated"]:
                            force_sell.add(code)
                    except Exception:
                        pass

        # 选股
        try:
            if args.factor_version == "v2":
                pool = compute_serenity_v2(
                    data,
                    enrich,
                    stock_close,
                    au,
                    data_date,
                    industry_neutral=params.industry_neutral_v2,
                )
                if args.v2_experiment == "theme" and pool is not None and not pool.empty:
                    pool = compute_theme_enhancement(
                        pool,
                        stock_close,
                        data_date,
                        theme_weight=args.theme_weight,
                    )
                hard_excl = pd.DataFrame()
            else:
                pool, hard_excl = build_serenity_pool_v2(data, enrich, stock_close, au, data_date, params)
            if sector_params.model != "none" and pool is not None and not pool.empty:
                sector_scores = compute_sector_scores(
                    stock_close,
                    au,
                    data_date,
                    stock_basic=stock_basic,
                    pool=pool,
                    cache=sector_cache,
                    params=sector_params,
                )
                topic_scores = compute_stock_topic_scores(
                    stock_close,
                    au,
                    data_date,
                    cache=sector_cache,
                    pool=pool,
                    params=sector_params,
                )
                pool = attach_sector_scores(pool, sector_scores, sector_params, stock_topic_scores=topic_scores)
        except Exception as e:
            print(f"  [{date.date()}] 选股异常: {e}, 跳过")
            pool, hard_excl = pd.DataFrame(), pd.DataFrame()

        if not pool.empty and args.factor_version == "v2":
            current_holdings = set(shares[shares > 0].index)
            targets = select_serenity_v2_targets(
                pool,
                current_holdings=current_holdings if params.use_buffer else set(),
                target_num=params.target_num,
                buy_top_n=params.buy_top_n,
                hold_threshold_n=params.hold_threshold_n if params.use_buffer else 0,
                max_per_industry=params.max_per_industry,
            )
        else:
            targets = select_targets_v2(pool, params) if not pool.empty else []
        target_set = set(targets)

        tv_before_trade = cash + float((shares * prices.fillna(0)).sum())
        turnover_budget = tv_before_trade * max_turnover_pct
        rebalance_sell_notional = 0.0
        invalidation_sells = 0
        min_hold_blocks = 0
        turnover_blocks = 0

        # 失效卖出优先执行；最短持有和换手上限只约束普通调仓。
        for code in list(force_sell):
            if shares.get(code, 0.0) <= 0:
                continue
            px = prices.get(code, np.nan)
            cash, gross = _sell_position(
                code,
                float(px) if pd.notnull(px) else np.nan,
                cash,
                shares,
                entry_dates,
                entry_prices,
                highest_since_entry,
                params.close_cost,
            )
            if gross > 0:
                invalidation_sells += 1

        score_col = _score_column(pool)
        score_map = (
            pool.set_index("code")[score_col].to_dict()
            if score_col is not None and not pool.empty and "code" in pool.columns
            else {}
        )
        rebalance_candidates = []
        for code in list(shares.index):
            if shares[code] <= 0 or code in target_set or code in force_sell:
                continue
            if _held_days(entry_dates.get(code), data_date) < risk.min_hold_days:
                min_hold_blocks += 1
                continue
            px = prices.get(code, np.nan)
            if pd.isnull(px) or px <= 0:
                continue
            rebalance_candidates.append((float(score_map.get(code, -np.inf)), code, float(px)))
        rebalance_candidates.sort(key=lambda x: (x[0], x[1]))

        for _, code, px in rebalance_candidates:
            gross = float(shares[code]) * px
            if rebalance_sell_notional + gross > turnover_budget:
                turnover_blocks += 1
                continue
            cash, sold_gross = _sell_position(
                code,
                px,
                cash,
                shares,
                entry_dates,
                entry_prices,
                highest_since_entry,
                params.close_cost,
            )
            rebalance_sell_notional += sold_gross

        # 买入
        if targets:
            tv = cash + float((shares * prices.fillna(0)).sum())
            allocation_codes = sorted(set(targets) | set(shares[shares > 0].index))
            pv = tv / max(1, len(allocation_codes))
            trade_turnover_used = rebalance_sell_notional
            for code in targets:
                px = prices.get(code, np.nan)
                if pd.isnull(px) or px <= 0:
                    continue
                cv = shares.get(code, 0.0) * px
                diff = pv - cv
                if diff < 0:
                    remaining_turnover = turnover_budget - trade_turnover_used
                    if remaining_turnover <= 0:
                        continue
                    sa = min(shares.get(code, 0.0), lot_floor(min(abs(diff), remaining_turnover) / px))
                    if sa <= 0:
                        continue
                    cash += sa * px * (1 - params.close_cost)
                    shares[code] -= sa
                    trade_turnover_used += sa * px
                elif diff > 0:
                    remaining_turnover = turnover_budget - trade_turnover_used
                    if remaining_turnover <= 0:
                        continue
                    bc = min(cash, diff, remaining_turnover)
                    old_amount = float(shares.get(code, 0.0))
                    old_entry = float(entry_prices.get(code, px))
                    ba = lot_floor(bc / (px * (1 + params.open_cost)))
                    if ba <= 0:
                        continue
                    cash -= ba * px * (1 + params.open_cost)
                    shares[code] += ba
                    trade_turnover_used += ba * px
                    if old_amount <= 0:
                        entry_dates[code] = data_date
                        entry_prices[code] = float(px)
                        highest_since_entry[code] = float(px)
                    else:
                        new_amount = old_amount + ba
                        entry_prices[code] = (old_amount * old_entry + ba * float(px)) / new_amount
                        highest_since_entry[code] = max(float(highest_since_entry.get(code, px)), float(px))

        # 记录
        tiers = (
            pool[pool["code"].isin(target_set)].groupby("tier").size().to_dict()
            if not pool.empty and "tier" in pool.columns
            else {}
        )
        for rank, code in enumerate(targets, start=1):
            rd = {"date": date, "rank": rank, "code": code}
            if not pool.empty and code in pool["code"].values:
                r = pool[pool["code"] == code].iloc[0].to_dict()
                rd.update({k: r.get(k) for k in [
                    "name", "tier", "channel", "serenity_score", "serenity_score_v2",
                    "bottleneck_ind", "financial_ind", "reflexivity_ind", "trend_confirm",
                    "valuation_penalty", "crowding_score", "industry_name",
                    "serenity_score_v2_base", "theme_bucket", "theme_exposure",
                    "industry_heat", "stock_theme_momentum", "theme_score", "theme_boost",
                    "serenity_score_before_sector", "sector_name", "sector_score", "sector_rank",
                    "sector_percentile", "sector_selected", "sector_adjustment",
                    "price_momentum", "breadth_score", "limit_score", "hot_score",
                    "financial_score", "risk_penalty", "topic_code", "topic_name",
                    "topic_score", "topic_rank", "topic_selected", "topic_momentum",
                    "topic_breadth_score", "topic_limit_score", "topic_lhb_score",
                    "topic_hot_score", "topic_etf_score", "topic_financial_score",
                    "topic_risk_penalty", "prosperity_score", "prosperity_source",
                    "prosperity_selected"
                ] if k in r})
            target_rows.append(rd)

        print(f"  [{date.date()}] {len(targets)}只 "
              f"(A:{tiers.get('Pass-A',0)} B:{tiers.get('Pass-B',0)} C:{tiers.get('Pass-C',0)}) "
              f"排除:{len(hard_excl)} 风控卖:{risk_sells} 失效卖:{invalidation_sells} "
              f"持有保护:{min_hold_blocks} 换手阻止:{turnover_blocks}")

        nv = cash + float((shares * stock_close.loc[next_date].fillna(prices)).sum())
        records.append({
            "date": next_date,
            "portfolio_value": nv,
            "cash": cash,
            "position_count": int((shares > 0).sum()),
            "risk_sells": risk_sells,
            "risk_sell_notional": risk_sell_notional,
            "invalidation_sells": invalidation_sells,
            "rebalance_sell_notional": rebalance_sell_notional,
            "min_hold_blocks": min_hold_blocks,
            "turnover_blocks": turnover_blocks,
        })

    # ── 6. 汇总 ──
    equity = pd.DataFrame(records).set_index("date")
    tdf = pd.DataFrame(target_rows)
    bench = bench_close.reindex(equity.index).ffill()
    fb = bench.dropna().iloc[0]
    equity["benchmark_value"] = params.initial_cash * bench / fb
    equity["strategy_return"] = equity["portfolio_value"] / equity["portfolio_value"].iloc[0] - 1
    equity["benchmark_return"] = equity["benchmark_value"] / equity["benchmark_value"].iloc[0] - 1

    OUT_DIR.mkdir(exist_ok=True)
    buffer_tag = "buffer" if params.use_buffer and args.factor_version == "v2" else "nobuffer"
    exp_tag = f"_{args.v2_experiment}" if args.factor_version == "v2" and args.v2_experiment != "base" else ""
    topic_tag = "-topic" if args.sector_model != "none" and not args.no_topic_graph else ""
    sector_tag = f"_sector-{args.sector_model}{topic_tag}" if args.sector_model != "none" else ""
    freq_tag = "" if args.rebalance_frequency == "monthly" else f"_{args.rebalance_frequency}"
    risk_tag = ""
    if args.risk_controls or risk.min_hold_days > 0 or max_turnover_pct < 1.0:
        risk_tag = f"_risk-hold{risk.min_hold_days}-turn{int(max_turnover_pct * 100)}"
    s = f"{args.market}_{args.factor_version}{exp_tag}{sector_tag}_{buffer_tag}{freq_tag}{risk_tag}_{pd.Timestamp(args.start):%Y%m%d}_{pd.Timestamp(args.end):%Y%m%d}"
    ep = OUT_DIR / f"trend_serenity_equity_{s}.csv"
    tp = OUT_DIR / f"trend_serenity_targets_{s}.csv"
    pp = OUT_DIR / f"trend_serenity_returns_{s}.png"
    equity.to_csv(ep); tdf.to_csv(tp, index=False)

    fig, ax = plt.subplots(figsize=(14, 7))
    (equity["strategy_return"] * 100).plot(ax=ax, label=f"Trend-Serenity {args.factor_version.upper()}", linewidth=2)
    (equity["benchmark_return"] * 100).plot(ax=ax, label="CSI 300", linewidth=1.8, alpha=0.7)
    ax.set_title("Trend-Serenity V2 vs CSI 300")
    ax.set_ylabel("Cumulative Return (%)")
    ax.grid(True, alpha=0.3); ax.legend()
    fig.tight_layout(); fig.savefig(pp, dpi=160); plt.close(fig)

    stats = summarize(equity)
    print(f"\n{'='*60}")
    print(f"Trend-Serenity {args.factor_version.upper()} 回测结果 ({args.market})")
    print(f"{'='*60}")
    print(f"区间: {args.start} — {args.end}  股票: {stock_close.shape[1]}只")
    print(f"富集: {'✓' if enrich is not None else '✗'}")
    for k, v in stats.items():
        if v is not None and not np.isnan(v):
            sfx = "%" if "drawdown" not in k else "%"
            print(f"  {k}: {v*100:.2f}%" if "drawdown" in k else f"  {k}: {v*100:.2f}%")
    print(f"  最终资产: {equity['portfolio_value'].iloc[-1]:,.0f}")
    print(f"  基准终值: {equity['benchmark_value'].iloc[-1]:,.0f}")
    print(f"\n  净值: {ep}\n  持仓: {tp}\n  曲叶: {pp}")
    print(f"\n本回测不构成投资建议。")

if __name__ == "__main__":
    main()
