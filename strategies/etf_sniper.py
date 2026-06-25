#!/usr/bin/env python3
"""
ETF Sniper — 单兵突击 ETF 动量轮动策略

import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
每天从全市场 ETF 中选出一只"涨得又稳又猛"的，全仓买入。
动量衰退或出现危险信号立即换仓/避险。

基于知乎「量化功守道」的策略描述实现。

核心流程:
  1. 双池融合 — 静态核心池(130+) + 动态流动性池(Top100 成交额>5000万)
  2. 三轮筛选 — 趋势确认(MA多头排列) → 动量打分(R²加权回归) → 成交量排雷
  3. 四道防线 — 绝对止损(-8%) / 放量清仓 / 动量衰退换仓 / 防御模式(货基避险)

回测引擎: 日频, 卖出用当日收盘价评分, 买入卖出在次日开盘执行。
"""
from __future__ import annotations
import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from strategies.etf_loop_strategy import (
    SectorProsperityCache, ETFDailyStore, get_ranked_etfs,
    calculate_atr, _lot_floor, _summarize, ETFLoopParams,
    _parse_ymd,
)
from strategies._utils import QlibDailyReader


# ═══════════════════════════════════════════════════════════════
# Static core pool (~130 ETFs — 宽基 + 行业 + 跨境 + 商品 + 债券)
# ═══════════════════════════════════════════════════════════════

CORE_ETF_POOL = [
    # ── A股宽基 ──
    "510050.SH",  # 上证50
    "510300.SH",  # 沪深300
    "510500.SH",  # 中证500
    "512100.SH",  # 中证1000
    "563300.SH",  # 中证2000
    "563360.SH",  # A500
    "159915.SZ",  # 创业板
    "159949.SZ",  # 创业板50
    "588000.SH",  # 科创50
    "588080.SH",  # 科创50ETF
    "588200.SH",  # 科创芯片
    "159845.SZ",  # 中证1000
    "510880.SH",  # 红利ETF
    "512890.SH",  # 红利低波
    "159905.SZ",  # 深证100
    "515180.SH",  # 中证红利
    # ── 行业/主题 ──
    "512480.SH",  # 半导体
    "159516.SZ",  # 半导体设备
    "159995.SZ",  # 芯片ETF
    "159530.SZ",  # 机器人ETF
    "159326.SZ",  # 电网设备
    "159611.SZ",  # 电力ETF
    "159206.SZ",  # 卫星ETF
    "159583.SZ",  # 通信ETF
    "515050.SH",  # 5GETF
    "159869.SZ",  # 游戏ETF
    "516310.SH",  # 银行ETF
    "512070.SH",  # 非银ETF
    "512880.SH",  # 证券ETF
    "512200.SH",  # 房地产ETF
    "516150.SH",  # 稀土ETF
    "159870.SZ",  # 化工ETF
    "512400.SH",  # 有色金属ETF
    "515790.SH",  # 光伏ETF
    "159790.SZ",  # 新能源ETF
    "515030.SH",  # 新能源车ETF
    "512690.SH",  # 酒ETF
    "515880.SH",  # 通信ETF
    "516020.SH",  # 科技ETF
    "516000.SH",  # 大数据ETF
    "515230.SH",  # 软件ETF
    "159819.SZ",  # 人工智能ETF
    "159899.SZ",  # 云计算ETF
    "562500.SH",  # 机器人100
    "512660.SH",  # 军工ETF
    "512670.SH",  # 国防ETF
    "159736.SZ",  # 食品饮料ETF
    "159766.SZ",  # 旅游ETF
    "159838.SZ",  # 医药ETF
    "512010.SH",  # 医药卫生ETF
    "513120.SH",  # 港股创新药ETF
    "159615.SZ",  # 生物科技ETF
    "159839.SZ",  # 生物医药ETF
    "516520.SH",  # 智能驾驶ETF
    "159636.SZ",  # 港股通科技ETF
    "159766.SZ",  # 旅游ETF
    "513060.SH",  # 港股通医疗ETF
    # ── 跨境QDII ──
    "513100.SH",  # 纳指ETF
    "513500.SH",  # 标普500ETF
    "513400.SH",  # 道琼斯ETF
    "513520.SH",  # 日经225ETF
    "513310.SH",  # 中韩半导体
    "513730.SH",  # 东南亚ETF
    "159920.SZ",  # 恒生ETF
    "513050.SH",  # 中概互联
    "513180.SH",  # 恒生科技
    "513330.SH",  # 恒生互联网
    "513690.SH",  # 港股红利
    "159792.SZ",  # 港股通互联网ETF
    "513130.SH",  # 恒生科技指数ETF
    "513300.SH",  # 恒生ETF(华夏)
    "513060.SH",  # 港股医疗
    "159937.SZ",  # 黄金ETF(博时)
    "518800.SH",  # 黄金ETF
    # ── 商品 ──
    "518880.SH",  # 黄金ETF(华安)
    "159980.SZ",  # 有色ETF(大成)
    "159981.SZ",  # 能源化工ETF
    "159985.SZ",  # 豆粕ETF
    "501018.SH",  # 南方原油LOF
    "161226.SZ",  # 白银LOF
    # ── 债券/货币 ──
    "511010.SH",  # 国债ETF
    "511220.SH",  # 城投债ETF
    "511360.SH",  # 短融ETF
    "511380.SH",  # 可转债ETF
    "511880.SH",  # 银华日利(货币ETF)
    "511990.SH",  # 华宝添益(货币ETF)
]

# ── Defensive ETF (money market, for defense mode) ──
DEFENSE_ETF = "511880.SH"  # 银华日利


# ═══════════════════════════════════════════════════════════════
# Parameters
# ═══════════════════════════════════════════════════════════════

@dataclass
class SniperParams:
    """ETF Sniper strategy parameters."""

    # Core pool
    static_pool: list[str] = field(default_factory=lambda: list(CORE_ETF_POOL))
    defense_etf: str = DEFENSE_ETF

    # Dynamic pool
    enable_dynamic_pool: bool = True
    dynamic_top_n: int = 100        # top N by 5d avg volume
    dynamic_min_amount: float = 50_000_000  # min 5d avg amount (5000万)

    # Trend filter (Round 1)
    ma_fast: int = 20   # 20日均线
    ma_slow: int = 60   # 60日均线

    # Momentum scoring (Round 2)
    lookback_days: int = 25

    # Volume filter (Round 3)
    vol_spike_mult: float = 2.5   # 放量阈值 (成交量为过去5日均量的N倍)
    vol_lookback: int = 5

    # Exit layers
    stop_loss: float = 0.92        # 绝对止损线 (-8%)
    vol_exit_mult: float = 2.5     # 放量离场阈值
    # Layer 3 (momentum decay) is automatic — daily re-evaluation

    # Execution
    initial_cash: float = 500_000.0
    open_cost: float = 0.0001
    close_cost: float = 0.0001
    slippage: float = 0.0001
    min_trade_value: float = 5000.0

    # Backtest window
    start: str = "2020-01-02"
    end: str = "2026-06-25"


# ═══════════════════════════════════════════════════════════════
# Trend filter: close > MA_fast > MA_slow
# ═══════════════════════════════════════════════════════════════

def check_trend(closes: np.ndarray, ma_fast: int, ma_slow: int) -> bool:
    """Return True if close > MA_fast > MA_slow (bullish alignment)."""
    if len(closes) < ma_slow + 1:
        return False
    close_now = closes[-1]
    ma_f = np.mean(closes[-ma_fast:])
    ma_s = np.mean(closes[-ma_slow:])
    return close_now > ma_f > ma_s


# ═══════════════════════════════════════════════════════════════
# Volume filter: estimated volume < spike_mult * avg volume
# ═══════════════════════════════════════════════════════════════

def check_volume(volumes: np.ndarray, vol_spike_mult: float) -> bool:
    """Return True if volume is NOT spiking (today_vol < spike * avg)."""
    if len(volumes) < 2:
        return True
    today_vol = volumes[-1]
    avg_vol = np.mean(volumes[-6:-1]) if len(volumes) >= 6 else np.mean(volumes[:-1])
    if avg_vol <= 0:
        return True
    return today_vol < vol_spike_mult * avg_vol


# ═══════════════════════════════════════════════════════════════
# Dynamic pool builder
# ═══════════════════════════════════════════════════════════════

def build_dynamic_pool(
    store: ETFDailyStore,
    date: pd.Timestamp,
    top_n: int = 100,
    min_amount: float = 50_000_000,
) -> set[str]:
    """Scan all ETFs in store, keep top N by 5d avg amount > min_amount."""
    scores = []
    for code in store.ts_codes:
        amt = store.amount
        if code not in amt.columns:
            continue
        col = amt[code].loc[:date].dropna()
        if len(col) < 5:
            continue
        avg_amt = float(col.iloc[-5:].mean())
        if avg_amt >= min_amount:
            scores.append((code, avg_amt))
    scores.sort(key=lambda x: x[1], reverse=True)
    return set(code for code, _ in scores[:top_n])


# ═══════════════════════════════════════════════════════════════
# Main backtest engine
# ═══════════════════════════════════════════════════════════════

def run_sniper_backtest(
    token_path: Path,
    cache_dir: Path,
    params: SniperParams = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the ETF Sniper backtest."""
    if params is None:
        params = SniperParams()

    import os
    BASE_DIR = Path(os.environ.get("QLIB_PROVIDER_URI", str(Path.cwd() / "data" / "a_share_qlib"))).parent
    if str(BASE_DIR) == ".":
        BASE_DIR = Path.cwd()

    cache = SectorProsperityCache(token_path, cache_dir)

    # ── Build store from static pool (dynamic pool computed daily) ──
    # For efficiency, load ALL ETFs from cache into store
    daily = cache.etf_daily()
    daily = daily.copy(); daily["trade_date"] = _parse_ymd(daily["trade_date"])
    daily_all = daily  # keep full range for lookup
    daily = daily_all[(daily_all["trade_date"] >= pd.Timestamp(params.start))
                  & (daily["trade_date"] <= pd.Timestamp(params.end))]
    all_codes = sorted(daily_all["ts_code"].astype(str).unique().tolist())

    store = ETFDailyStore(cache, all_codes, params.start, params.end)
    if not store.ts_codes:
        raise RuntimeError("No ETF data found")

    # ── Benchmark ──
    provider_uri = Path(os.environ.get("QLIB_PROVIDER_URI", str(BASE_DIR / "data" / "a_share_qlib")))
    reader = QlibDailyReader(provider_uri)
    bench_close = reader.read_field("sh000300", "close")
    bench_close = bench_close.loc[pd.Timestamp(params.start):pd.Timestamp(params.end)]

    calendar = store.calendar
    if len(calendar) < params.ma_slow + params.lookback_days:
        raise RuntimeError(f"Insufficient calendar days: {len(calendar)}")

    # ── State ──
    cash = params.initial_cash
    position: dict[str, int] = {}     # held code → shares
    entry_price: dict[str, float] = {}  # code → entry cost
    position_high: dict[str, float] = {}  # code → highest price since entry
    records: list[dict] = []
    trade_rows: list[dict] = []

    for i, data_date in enumerate(calendar[:-1]):
        if i < params.ma_slow + params.lookback_days:
            # Not enough history for trend + momentum
            records.append({
                "date": calendar[i + 1],
                "portfolio_value": params.initial_cash,
                "cash": params.initial_cash,
                "position": "",
                "mode": "warmup",
            })
            continue

        next_date = calendar[i + 1]

        # ── 1. Build today's candidate pool ──
        static_set = set(params.static_pool) & set(store.ts_codes)
        candidate_set = set(static_set)

        if params.enable_dynamic_pool:
            dynamic_set = build_dynamic_pool(
                store, data_date,
                top_n=params.dynamic_top_n,
                min_amount=params.dynamic_min_amount,
            )
            candidate_set |= dynamic_set

        # ── 2. Three-round selection ──
        ranked = []
        for code in sorted(candidate_set):
            # Round 1: Trend filter
            closes = store.price_series(code, data_date, params.ma_slow + 5)
            if not check_trend(closes, params.ma_fast, params.ma_slow):
                continue

            # Round 2: Momentum scoring (same as original etf_loop score_etf)
            from strategies.etf_loop_strategy import score_etf
            # Create a minimal params object for score_etf
            class TempParams:
                pass
            tp = TempParams()
            tp.lookback_days = params.lookback_days
            tp.short_lookback_days = params.lookback_days
            tp.rsi_period = 6
            tp.rsi_lookback_days = 1
            tp.enable_volume_check = False
            tp.use_short_momentum_filter = True
            tp.short_momentum_threshold = 0.0
            tp.use_rsi_filter = False
            tp.rsi_threshold = 98
            tp.loss = 0.97
            tp.volume_lookback = 5
            tp.volume_threshold = 2.0
            tp.volume_return_limit = 1.0
            tp.min_score_threshold = 0.0
            tp.max_score_threshold = 500.0

            metrics = score_etf(store, code, data_date, tp)
            if metrics is None or metrics["score"] <= 0:
                continue

            # Round 3: Volume spike check
            vol_arr = store.volume[code].loc[:data_date].dropna().values if code in store.volume.columns else np.array([])
            if len(vol_arr) >= params.vol_lookback + 1:
                if not check_volume(vol_arr, params.vol_spike_mult):
                    continue

            ranked.append(metrics)

        ranked.sort(key=lambda x: x["score"], reverse=True)

        # Determine target
        if ranked:
            target_code = ranked[0]["ts_code"]
            target_score = ranked[0]["score"]
        else:
            target_code = None
            target_score = None

        # Defense mode: if no ETF passes all filters, hold cash/defense
        if target_code is None:
            target_code = params.defense_etf
            target_score = 0

        # ── 3. Next-day open prices ──
        next_open_prices = {}
        codes_needed = {target_code} | set(position.keys())
        for code in codes_needed:
            if code in store.open.columns:
                col = store.open[code].loc[:next_date].dropna()
                if not col.empty:
                    next_open_prices[code] = float(col.iloc[-1])

        # ── 4. Exit checks for current position ──
        for code in list(position.keys()):
            if position.get(code, 0) <= 0:
                continue

            signal_px = store.latest_price(code, data_date)
            exec_px = next_open_prices.get(code, np.nan)
            if np.isnan(exec_px) or exec_px <= 0:
                exec_px = signal_px
            if np.isnan(exec_px) or exec_px <= 0:
                continue

            # Layer 1: Absolute stop loss (-8%)
            stop_triggered = code in entry_price and signal_px <= entry_price[code] * params.stop_loss

            # Layer 2: Volume spike exit
            vol_exit = False
            vol_arr = store.volume[code].loc[:data_date].dropna().values if code in store.volume.columns else np.array([])
            if len(vol_arr) >= params.vol_lookback + 1:
                if not check_volume(vol_arr, params.vol_spike_mult):
                    vol_exit = True

            # Layer 3: No longer #1 (momentum decay)
            rank_out = (code != target_code)

            should_exit = stop_triggered or vol_exit or rank_out

            if should_exit:
                cash += position[code] * exec_px * (1.0 - params.slippage) * (1.0 - params.close_cost)
                reason = []
                if stop_triggered:
                    reason.append("STOP_LOSS")
                if vol_exit:
                    reason.append("VOL_SPIKE")
                if rank_out:
                    reason.append("RANK_OUT")
                trade_rows.append({
                    "date": data_date, "trade_date": next_date,
                    "ts_code": code, "action": "SELL",
                    "reason": "|".join(reason) if reason else "REBALANCE",
                    "price": exec_px, "shares": position[code],
                })
                position[code] = 0
                entry_price.pop(code, None)
                position_high.pop(code, None)

        # ── 5. Buy target ──
        if target_code and target_code != params.defense_etf and target_score > 0:
            px = next_open_prices.get(target_code, np.nan)
            if not (np.isnan(px) or px <= 0):
                # All-in
                buy_shares = _lot_floor(cash / (px * (1.0 + params.open_cost + params.slippage)))
                if buy_shares > 0:
                    tv = buy_shares * px
                    if tv >= params.min_trade_value:
                        cash -= tv * (1.0 + params.open_cost + params.slippage)
                        position[target_code] = position.get(target_code, 0) + buy_shares
                        entry_price[target_code] = px
                        position_high[target_code] = px
                        trade_rows.append({
                            "date": data_date, "trade_date": next_date,
                            "ts_code": target_code, "action": "BUY",
                            "reason": "TOP_PICK",
                            "price": px, "shares": buy_shares,
                            "score": target_score,
                        })
        elif target_code == params.defense_etf:
            # Defense mode: buy money market ETF
            px = next_open_prices.get(target_code, np.nan)
            if not (np.isnan(px) or px <= 0) and position.get(target_code, 0) == 0:
                buy_shares = _lot_floor(cash / (px * (1.0 + params.open_cost + params.slippage)))
                if buy_shares > 0:
                    tv = buy_shares * px
                    if tv >= params.min_trade_value:
                        cash -= tv * (1.0 + params.open_cost + params.slippage)
                        position[target_code] = position.get(target_code, 0) + buy_shares
                        entry_price[target_code] = px
                        trade_rows.append({
                            "date": data_date, "trade_date": next_date,
                            "ts_code": target_code, "action": "BUY",
                            "reason": "DEFENSE",
                            "price": px, "shares": buy_shares,
                            "score": 0,
                        })

        # ── 6. Record equity ──
        portfolio_value = cash
        for code in position:
            if position.get(code, 0) > 0:
                px = store.latest_price(code, next_date)
                if not np.isnan(px) and px > 0:
                    portfolio_value += position[code] * px
                else:
                    portfolio_value += position[code] * entry_price.get(code, 0)

        held_code = max(position.items(), key=lambda x: x[1])[0] if position else ""
        records.append({
            "date": next_date,
            "portfolio_value": portfolio_value,
            "cash": cash,
            "position": held_code,
            "mode": "active" if target_code != params.defense_etf else "defense",
            "target_code": target_code or "",
            "target_score": target_score or 0,
            "candidate_count": len(candidate_set),
            "ranked_count": len(ranked),
        })

    equity = pd.DataFrame(records).drop_duplicates("date", keep="last").set_index("date")
    if equity.empty:
        raise RuntimeError("No equity records generated")

    if not bench_close.empty:
        bench = bench_close.reindex(equity.index).ffill()
        fb = bench.dropna().iloc[0]
        equity["benchmark_value"] = params.initial_cash * bench / fb
        equity["benchmark_return"] = equity["benchmark_value"] / equity["benchmark_value"].iloc[0] - 1.0
    equity["strategy_return"] = equity["portfolio_value"] / equity["portfolio_value"].iloc[0] - 1.0

    trades = pd.DataFrame(trade_rows)
    return equity, trades


# ═══════════════════════════════════════════════════════════════
# CLI runner
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys, os
    BASE_DIR = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(BASE_DIR))
    os.environ.setdefault("QLIB_PROVIDER_URI", str(BASE_DIR / "data" / "a_share_qlib"))

    token_path = BASE_DIR / "config" / "tushare_token.txt"
    cache_dir = BASE_DIR / "data" / "tushare_cache"
    out_dir = BASE_DIR / "outputs" / "etf_sniper"
    out_dir.mkdir(parents=True, exist_ok=True)

    params = SniperParams(
        start="2024-01-02",
        end="2026-06-25",
        initial_cash=500_000,
    )

    print(f"ETF Sniper 回测: {params.start} → {params.end}")
    print(f"  静态池: {len(params.static_pool)} 只")
    print(f"  动态池: {'启用 (Top' + str(params.dynamic_top_n) + ', min ' + str(int(params.dynamic_min_amount/10000)) + '万)' if params.enable_dynamic_pool else '禁用'}")
    print(f"  止损线: {params.stop_loss*100:.0f}% | 放量阈值: {params.vol_spike_mult:.1f}x")

    equity, trades = run_sniper_backtest(token_path, cache_dir, params)

    stats = _summarize(equity)
    print(f"\n{'='*60}")
    print(f"ETF Sniper 回测结果")
    print(f"{'='*60}")
    print(f"  年化收益: {stats['annual_return']*100:.2f}%")
    print(f"  Sharpe:   {stats['sharpe_ratio']:.2f}")
    print(f"  最大回撤:  {stats['max_drawdown']*100:.2f}%")
    print(f"  总交易数:   {len(trades)}")
    print(f"  防御天数:   {(equity['mode']=='defense').sum()}")
    print(f"  交易天数:   {(equity['position']!='').sum()}")
    print(f"  终值:       ¥{stats['final_value']:,.0f}")

    suffix = f"sniper_{params.start.replace('-','')}_{params.end.replace('-','')}"
    equity.to_csv(out_dir / f"equity_{suffix}.csv")
    trades.to_csv(out_dir / f"trades_{suffix}.csv", index=False)
    pd.DataFrame([stats]).to_csv(out_dir / f"summary_{suffix}.csv", index=False)
    print(f"\n结果已保存到 {out_dir}")
