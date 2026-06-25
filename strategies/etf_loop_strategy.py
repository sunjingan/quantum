"""
ETF Loop Momentum Rotation Strategy.

Ported from JoinQuant strategy 七星高照ETF轮动策略 to the project framework.
Core idea: score a pool of ETFs by weighted-regression momentum, apply
volume/RSI/short-momentum filters, hold the top N, and use ATR + fixed %
stop-loss to manage risk.

Data: ETF OHLCV from fund_daily caches via SectorProsperityCache.
Execution: daily rebalancing — sell at day-t close, buy at day-t+1 open.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from strategies._fundamental import tushare_to_qlib
from strategies.sector_prosperity import SectorProsperityCache


# ═══════════════════════════════════════════════════════════════
# JoinQuant → Tushare ETF code mapping
# ═══════════════════════════════════════════════════════════════

def _jq_to_ts(code: str) -> str:
    """518880.XSHG → 518880.SH / 159915.XSHE → 159915.SZ"""
    symbol, exchange = code.split(".")
    if exchange == "XSHG":
        return f"{symbol}.SH"
    elif exchange == "XSHE":
        return f"{symbol}.SZ"
    raise ValueError(f"Unknown exchange: {exchange}")


# ── Default ETF pool (full, as defined in original strategy) ──
FULL_ETF_POOL_JQ = [
    # 大宗商品
    "518880.XSHG",  # 黄金ETF
    "159980.XSHE",  # 有色ETF
    "159985.XSHE",  # 豆粕ETF
    "501018.XSHG",  # 南方原油
    "161226.XSHE",  # 白银LOF
    "159981.XSHE",  # 能源化工ETF
    # 国际ETF
    "513100.XSHG",  # 纳指ETF
    "513500.XSHG",  # 标普500ETF
    "513400.XSHG",  # 道琼斯ETF
    "513520.XSHG",  # 日经225ETF
    "513310.XSHG",  # 中韩半导体ETF
    "513730.XSHG",  # 东南亚ETF
    # 香港ETF
    "159792.XSHE",  # 港股互联ETF
    "513130.XSHG",  # 恒生科技
    "513050.XSHG",  # 中概互联网ETF
    "159920.XSHE",  # 恒生ETF
    "513690.XSHG",  # 港股红利
    # 宽基指数ETF
    "510300.XSHG",  # 沪深300ETF
    "510500.XSHG",  # 中证500ETF
    "159915.XSHE",  # 创业板ETF
    "588080.XSHG",  # 科创50
    "512100.XSHG",  # 中证1000ETF
    "563360.XSHG",  # A500-ETF
    "563300.XSHG",  # 中证2000ETF
    # 风格ETF
    "512890.XSHG",  # 红利低波ETF
    "159583.XSHE",  # 通信ETF
    "512040.XSHG",  # 价值ETF
    "159201.XSHE",  # 自由现金流ETF
    "159516.XSHE",  # 半导体设备ETF
    "159326.XSHE",  # 电网设备ETF
    "159611.XSHE",  # 电力ETF
    "159206.XSHE",  # 卫星ETF
    "159530.XSHE",  # 机器人ETF
    "516310.XSHG",  # 银行ETF
    # 债券ETF
    "511380.XSHG",  # 可转债ETF
    "511010.XSHG",  # 国债ETF
    "511220.XSHG",  # 城投债ETF
    "511880.XSHG",  # 货币ETF(防御)
]




@dataclass
class ETFLoopParams:
    """All tunable parameters from the original JoinQuant strategy."""

    etf_pool_ts: list[str] = field(default_factory=lambda: [_jq_to_ts(c) for c in FULL_ETF_POOL_JQ])
    lookback_days: int = 25
    holdings_num: int = 2
    stop_loss: float = 0.95
    loss: float = 0.97
    min_score_threshold: float = 0
    max_score_threshold: float = 500.0
    enable_volume_check: bool = True
    volume_lookback: int = 5
    volume_threshold: float = 2.0
    volume_return_limit: float = 1.0
    use_short_momentum_filter: bool = True
    short_lookback_days: int = 10
    short_momentum_threshold: float = 0.0
    use_rsi_filter: bool = True
    rsi_period: int = 6
    rsi_lookback_days: int = 1
    rsi_threshold: float = 98
    use_atr_stop_loss: bool = True
    atr_period: int = 14
    atr_multiplier: float = 2
    atr_trailing_stop: bool = False
    initial_cash: float = 500_000.0
    open_cost: float = 0.0001
    close_cost: float = 0.0001
    min_trade_value: float = 5000.0
    slippage: float = 0.0001
    benchmark: str = "sh000300"
    start: str = "2018-01-02"
    end: str = "2026-06-22"
def _build_all_etf_pool(token_path, cache_dir, correlation_threshold=0.75):
    """Fetch all stock-type listed ETFs from Tushare, dedup by benchmark,
    filter by minimum daily amount (>=50000 yuan), then remove highly
    correlated ETFs (correlation > correlation_threshold, 0=disabled).
    Cached to CSV."""
    import tushare as ts
    import pandas as pd
    import numpy as np
    from pathlib import Path
    from strategies.sector_prosperity import SectorProsperityCache

    cache_file = Path(cache_dir) / "sector_prosperity" / "all_etf_pool_dedup.csv"
    if cache_file.exists():
        df = pd.read_csv(cache_file, dtype={"ts_code": str})
        if not df.empty and "cluster_rep" in df.columns:
            return sorted(df[df["cluster_rep"]]["ts_code"].astype(str).tolist())
        elif not df.empty:
            return sorted(df["ts_code"].astype(str).tolist())

    token = Path(token_path).read_text().strip()
    pro = ts.pro_api(token)
    # 1. all stock-type ETFs
    fb = pro.fund_basic(market="E")
    if fb is None or fb.empty:
        return []
    fb_etf = fb[(fb["fund_type"] == "股票型") & (fb["status"] == "L")].copy()
    fb_etf = fb_etf[fb_etf["list_date"].notna() & fb_etf["delist_date"].isna()].copy()
    fb_etf["list_date_dt"] = pd.to_datetime(
        fb_etf["list_date"].astype(str).str.replace(r"\\.0$", "", regex=True),
        format="%Y%m%d", errors="coerce",
    )
    # 2. avg daily amount from cached fund_daily
    cache = SectorProsperityCache(token_path, cache_dir)
    daily = cache.etf_daily()
    daily["td"] = pd.to_datetime(
        daily["trade_date"].astype(str).str.replace(r"\\.0$", "", regex=True),
        format="%Y%m%d", errors="coerce",
    )
    recent = daily[daily["td"] >= pd.Timestamp.today() - pd.DateOffset(years=1)]
    avg_amount = recent.groupby("ts_code")["amount"].mean()
    fb_etf["avg_amount"] = fb_etf["ts_code"].map(avg_amount).fillna(0)
    # 3. dedup: keep most liquid per benchmark
    fb_sorted = fb_etf.sort_values("avg_amount", ascending=False)
    fb_dedup = fb_sorted.drop_duplicates("benchmark", keep="first").copy()
    # 4. filter: avg daily amount >= 50000 yuan
    fb_final = fb_dedup[fb_dedup["avg_amount"] >= 50000].copy()
    # 5. correlation dedup (if threshold > 0)
    if correlation_threshold > 0 and len(fb_final) > 10:
        pool_ts = sorted(fb_final["ts_code"].astype(str).tolist())
        recent_2y = daily[(daily["td"] >= pd.Timestamp.today() - pd.DateOffset(years=2))]
        close_wide = recent_2y.pivot_table(index="td", columns="ts_code", values="close", aggfunc="last")
        available = sorted(set(pool_ts) & set(close_wide.columns))
        if len(available) > 10:
            close_wide = close_wide[available].dropna(how="all")
            returns = close_wide.pct_change(fill_method=None).dropna(how="all")
            valid = returns.columns[returns.count() >= 250]
            returns = returns[valid].dropna()
            if len(valid) > 10:
                corr = returns.corr()
                remaining = set(returns.columns)
                cluster_rep = set()
                while remaining:
                    rep = sorted(remaining)[0]
                    cluster_rep.add(rep)
                    correlated = set(corr.index[corr[rep] > correlation_threshold])
                    remaining -= (correlated & remaining)
                fb_final["cluster_rep"] = fb_final["ts_code"].isin(cluster_rep)
    # 6. cache & return
    save_cols = ["ts_code", "name", "benchmark", "avg_amount", "list_date"]
    if "cluster_rep" in fb_final.columns:
        save_cols.append("cluster_rep")
    fb_final[save_cols].to_csv(cache_file, index=False)
    if "cluster_rep" in fb_final.columns:
        return sorted(fb_final[fb_final["cluster_rep"]]["ts_code"].astype(str).tolist())
    return sorted(fb_final["ts_code"].astype(str).tolist())
    # Universe
    etf_pool_ts: list[str] = field(default_factory=lambda: [_jq_to_ts(c) for c in FULL_ETF_POOL_JQ])

    # Core momentum
    lookback_days: int = 25
    holdings_num: int = 2

    # Risk control
    stop_loss: float = 0.95   # fixed % stop: sell if price <= cost * 0.95
    loss: float = 0.97        # 3-day single-day decline floor
    min_score_threshold: float = 0
    max_score_threshold: float = 500.0

    # Volume filter
    enable_volume_check: bool = True
    volume_lookback: int = 5
    volume_threshold: float = 2.0
    volume_return_limit: float = 1.0

    # Short momentum filter
    use_short_momentum_filter: bool = True
    short_lookback_days: int = 10
    short_momentum_threshold: float = 0.0

    # RSI filter
    use_rsi_filter: bool = True
    rsi_period: int = 6
    rsi_lookback_days: int = 1
    rsi_threshold: float = 98

    # ATR stop
    use_atr_stop_loss: bool = True
    atr_period: int = 14
    atr_multiplier: float = 2
    atr_trailing_stop: bool = False

    # Execution
    initial_cash: float = 500_000.0
    open_cost: float = 0.0001
    close_cost: float = 0.0001
    min_trade_value: float = 5000.0
    slippage: float = 0.0001  # PriceRelatedSlippage, 双边各万分之一
    benchmark: str = "sh000300"

    # Backtest window
    start: str = "2018-01-02"
    end: str = "2026-06-22"


# ═══════════════════════════════════════════════════════════════
# ETF data store — pivot fund_daily into wide OHLCVA DataFrames
# ═══════════════════════════════════════════════════════════════


def _parse_ymd(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str).str.replace(r"\.0$", "", regex=True), format="%Y%m%d", errors="coerce")


class ETFDailyStore:
    """Point-in-time ETF OHLCV + amount for a fixed code list."""

    def __init__(self, cache: SectorProsperityCache, ts_codes: list[str], start: str, end: str):
        daily = cache.etf_daily()
        if daily.empty:
            self.open = self.high = self.low = self.close = self.volume = self.amount = pd.DataFrame()
            self.calendar = pd.DatetimeIndex([])
            self.ts_codes: list[str] = []
            return

        daily = daily.copy()
        daily["trade_date"] = _parse_ymd(daily["trade_date"])
        daily = daily[(daily["trade_date"] >= pd.Timestamp(start)) & (daily["trade_date"] <= pd.Timestamp(end))]
        codes = sorted(set(ts_codes) & set(daily["ts_code"].astype(str).tolist()))
        self.ts_codes = codes
        daily = daily[daily["ts_code"].isin(codes)].copy()

        for col in ["open", "high", "low", "close", "vol", "amount"]:
            wide = daily.pivot_table(index="trade_date", columns="ts_code", values=col, aggfunc="last").sort_index()
            setattr(self, col if col != "vol" else "volume", wide)

        self.calendar = (self.close if not self.close.empty else pd.DataFrame(index=daily["trade_date"].drop_duplicates())).index

    def latest_price(self, code: str, date: pd.Timestamp) -> float:
        """Latest close price on or before `date` for `code`."""
        df = self.close
        ts = code if "." in code else f"{code[2:]}.{code[:2].upper()}"
        if code not in df.columns:
            return np.nan
        col = df[code].loc[:date].dropna()
        return float(col.iloc[-1]) if not col.empty else np.nan

    def price_series(self, ts_code: str, date: pd.Timestamp, lookback: int) -> np.ndarray:
        """Return close price array of length lookback+1 ending at `date`."""
        df = self.close
        if ts_code not in df.columns:
            return np.array([])
        col = df[ts_code].loc[:date].dropna()
        if len(col) < lookback + 1:
            return np.array([])
        return col.iloc[-(lookback + 1):].values

    def ohlc_series(self, ts_code: str, date: pd.Timestamp, lookback: int) -> dict[str, np.ndarray] | None:
        """Return dict of {close, high, low} arrays for ATR calculation."""
        result = {}
        for field in ["close", "high", "low"]:
            df = getattr(self, field)
            if ts_code not in df.columns:
                return None
            col = df[ts_code].loc[:date].dropna()
            if len(col) < lookback:
                return None
            result[field] = col.iloc[-lookback:].values
        return result

    def volume_ratio(self, ts_code: str, date: pd.Timestamp, lookback: int) -> float | None:
        """Today's volume / average volume over `lookback` days."""
        df = self.volume
        if ts_code not in df.columns:
            return None
        col = df[ts_code].loc[:date].dropna()
        if len(col) < lookback + 1:
            return None
        today_vol = col.iloc[-1]
        avg_vol = col.iloc[-(lookback + 1):-1].mean()
        return float(today_vol / avg_vol) if avg_vol > 0 else None


# ═══════════════════════════════════════════════════════════════
# Strategy functions — ported from original JoinQuant code
# ═══════════════════════════════════════════════════════════════


def _annualized_returns(price_series: np.ndarray, lookback_days: int) -> float:
    """Weighted log-regression annualized return."""
    recent = price_series[-(lookback_days + 1):]
    if len(recent) < lookback_days + 1:
        return np.nan
    y = np.log(recent)
    x = np.arange(len(y))
    weights = np.linspace(1, 2, len(y))
    slope, _ = np.polyfit(x, y, 1, w=weights)
    return np.exp(slope * 250) - 1.0


def calculate_rsi(prices: np.ndarray, period: int = 6) -> np.ndarray:
    """Standard RSI calculation — returns array same length as prices (first `period` values are 50)."""
    if len(prices) < period + 1:
        return np.full(len(prices), 50.0)
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gains = np.zeros(len(prices))
    avg_losses = np.zeros(len(prices))
    avg_gains[period] = np.mean(gains[:period])
    avg_losses[period] = np.mean(losses[:period])
    rsi = np.full(len(prices), 50.0)
    for i in range(period + 1, len(prices)):
        avg_gains[i] = (avg_gains[i - 1] * (period - 1) + gains[i - 1]) / period
        avg_losses[i] = (avg_losses[i - 1] * (period - 1) + losses[i - 1]) / period
        if avg_losses[i] == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gains[i] / avg_losses[i]
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))
    return rsi[period:]


def calculate_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
    """Current ATR value."""
    n = len(high)
    if n < period + 1:
        return 0.0
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr_vals = np.zeros(n)
    atr_vals[period] = np.mean(tr[1:period + 1])
    for i in range(period + 1, n):
        atr_vals[i] = (atr_vals[i - 1] * (period - 1) + tr[i]) / period
    return float(atr_vals[-1])


def score_etf(
    store: ETFDailyStore,
    ts_code: str,
    date: pd.Timestamp,
    params: ETFLoopParams,
) -> dict | None:
    """Compute the full momentum score + filter-flags for one ETF.

    Returns None when the ETF fails any hard filter.
    """
    lookback = max(params.lookback_days, params.short_lookback_days,
                   params.rsi_period + params.rsi_lookback_days) + 20
    prices = store.price_series(ts_code, date, lookback)
    if len(prices) < params.lookback_days + 1:
        return None

    current_price = prices[-1]

    # ── Volume check ──
    if params.enable_volume_check:
        vol_ratio = store.volume_ratio(ts_code, date, params.volume_lookback)
        if vol_ratio is not None and vol_ratio > params.volume_threshold:
            annual_ret = _annualized_returns(prices, params.lookback_days)
            if annual_ret > params.volume_return_limit:
                return None  # high volume + high return → potential top

    # ── RSI filter ──
    rsi_filter_pass = True
    current_rsi = 50.0
    max_rsi = 50.0
    if params.use_rsi_filter and len(prices) >= params.rsi_period + params.rsi_lookback_days + 1:
        rsi_vals = calculate_rsi(prices, params.rsi_period)
        if len(rsi_vals) >= params.rsi_lookback_days:
            recent_rsi = rsi_vals[-params.rsi_lookback_days:]
            if len(prices) >= 5:
                ma5 = np.mean(prices[-5:])
            else:
                ma5 = np.nan
            if np.any(recent_rsi > params.rsi_threshold) and (np.isnan(ma5) or current_price < ma5):
                rsi_filter_pass = False
            current_rsi = float(recent_rsi[-1])
            max_rsi = float(np.max(recent_rsi))

    if not rsi_filter_pass:
        return None

    # ── Short momentum ──
    short_ret = np.nan
    short_annualized = np.nan
    if len(prices) >= params.short_lookback_days + 1:
        short_ret = prices[-1] / prices[-(params.short_lookback_days + 1)] - 1.0
        short_annualized = (1.0 + short_ret) ** (250.0 / params.short_lookback_days) - 1.0

    if params.use_short_momentum_filter and not np.isnan(short_annualized) and short_annualized < params.short_momentum_threshold:
        return None

    # ── Long momentum (weighted regression) ──
    recent = prices[-(params.lookback_days + 1):]
    y = np.log(recent)
    x = np.arange(len(y))
    weights = np.linspace(1, 2, len(y))
    slope, intercept = np.polyfit(x, y, 1, w=weights)
    annualized_returns = np.exp(slope * 250) - 1.0

    # R²
    ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)
    ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
    r_squared = 1.0 - ss_res / ss_tot if ss_tot else 0.0

    score = annualized_returns * r_squared

    # ── 3-day single-day decline filter ──
    if len(prices) >= 4:
        day1 = prices[-1] / prices[-2]
        day2 = prices[-2] / prices[-3]
        day3 = prices[-3] / prices[-4]
        if min(day1, day2, day3) < params.loss:
            score = 0.0

    return {
        "ts_code": ts_code,
        "annualized_returns": annualized_returns,
        "r_squared": r_squared,
        "score": score,
        "slope": slope,
        "current_price": current_price,
        "short_return": short_ret,
        "short_annualized": short_annualized,
        "current_rsi": current_rsi,
        "max_recent_rsi": max_rsi,
    }


def get_ranked_etfs(
    store: ETFDailyStore,
    date: pd.Timestamp,
    params: ETFLoopParams,
) -> list[dict]:
    """Return scored & ranked ETF list (filtered, sorted by score desc)."""
    results = []
    for ts_code in store.ts_codes:
        metrics = score_etf(store, ts_code, date, params)
        if metrics is None:
            continue
        if params.min_score_threshold <= metrics["score"] <= params.max_score_threshold:
            results.append(metrics)
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ═══════════════════════════════════════════════════════════════
# Backtest engine
# ═══════════════════════════════════════════════════════════════


def _lot_floor(amount: float) -> int:
    return int(amount // 100) * 100


def run_etf_loop_backtest(
    cache_dir: Path,
    token_path: Path,
    params: ETFLoopParams,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the ETF loop strategy backtest.

    Returns (equity_df, target_df).
    """
    cache = SectorProsperityCache(token_path, cache_dir)
    store = ETFDailyStore(cache, params.etf_pool_ts, params.start, params.end)
    if not store.ts_codes:
        raise RuntimeError("No ETF data found for the requested pool/date range. "
                           "Run backtest_etf_loop.py --fetch to pull fund_daily data first.")

    # Benchmark close from Qlib
    from strategies._utils import QlibDailyReader
    import os
    provider_uri = Path(os.environ.get("QLIB_PROVIDER_URI", Path.cwd() / "data" / "a_share_qlib"))
    reader = QlibDailyReader(provider_uri)
    bench_close = reader.read_field(params.benchmark, "close")
    bench_close = bench_close.loc[pd.Timestamp(params.start):pd.Timestamp(params.end)]

    calendar = store.calendar
    if len(calendar) < params.lookback_days + 1:
        raise RuntimeError(f"Insufficient calendar days: {len(calendar)}")

    cash = params.initial_cash
    shares: dict[str, int] = {}        # ts_code → shares held
    entry_prices: dict[str, float] = {} # ts_code → avg cost
    position_highs: dict[str, float] = {}  # ts_code → highest price since entry

    records: list[dict] = []
    target_rows: list[dict] = []

    for i, data_date in enumerate(calendar[:-1]):
        if i < params.lookback_days:
            continue
        next_date = calendar[i + 1]

        # ── Score & rank ETFs ──
        ranked = get_ranked_etfs(store, data_date, params)
        target_codes = set(r["ts_code"] for r in ranked[:params.holdings_num])


        # ── Buy: open new positions at next-day open ──
        next_open_prices = {}
        for code in target_codes:
            # Use store.open for next_date (or fallback to close)
            df_open = store.open
            if code in df_open.columns:
                col = df_open[code].loc[:next_date].dropna()
                next_open_prices[code] = float(col.iloc[-1]) if not col.empty else np.nan
            else:
                next_open_prices[code] = np.nan
        # ── Sell: exit positions not in target set ──
        sold_any = False
        for code in list(shares.keys()):
            if shares.get(code, 0) <= 0:
                continue
            signal_px = store.latest_price(code, data_date)
            exec_px = next_open_prices.get(code, np.nan)  # sell at next open
            if np.isnan(exec_px) or exec_px <= 0:
                exec_px = signal_px  # fallback
            if np.isnan(exec_px) or exec_px <= 0:
                exec_px = entry_prices.get(code, signal_px)
            if np.isnan(exec_px) or exec_px <= 0:
                continue

            # Fixed % stop
            stop_triggered = False
            if code in entry_prices and signal_px <= entry_prices[code] * params.stop_loss:
                stop_triggered = True

            # ATR stop
            atr_triggered = False
            if params.use_atr_stop_loss:
                ohlc = store.ohlc_series(code, data_date, params.atr_period + 20)
                if ohlc is not None:
                    atr_val = calculate_atr(ohlc["high"], ohlc["low"], ohlc["close"], params.atr_period)
                    if atr_val > 0:
                        if params.atr_trailing_stop:
                            high_since = position_highs.get(code, signal_px)
                            atr_stop = high_since - params.atr_multiplier * atr_val
                        else:
                            atr_stop = entry_prices.get(code, signal_px) - params.atr_multiplier * atr_val
                        if signal_px <= atr_stop:
                            atr_triggered = True

            should_sell = (code not in target_codes) or stop_triggered or atr_triggered
            if should_sell:
                cash += shares[code] * exec_px * (1.0 - params.slippage) * (1.0 - params.close_cost)
                sold_any = True
                reason = []
                if stop_triggered:
                    reason.append("STOP_LOSS")
                if atr_triggered:
                    reason.append("ATR_STOP")
                if code not in target_codes:
                    reason.append("RANK_OUT")
                target_rows.append({
                    "date": data_date, "trade_date": next_date,
                    "ts_code": code, "action": "SELL",
                    "reason": "|".join(reason) if reason else "REBALANCE",
                    "price": exec_px, "shares": shares[code],
                })
                shares[code] = 0
                entry_prices.pop(code, None)
                position_highs.pop(code, None)


        active_set = target_codes | set(c for c in shares if shares.get(c, 0) > 0)
        if active_set:
            n_active = max(1, len(active_set))
            total_value = cash
            for code in shares:
                if shares.get(code, 0) > 0:
                    px = store.latest_price(code, data_date)
                    total_value += shares[code] * (px if not np.isnan(px) and px > 0 else 0)
            per_slot = total_value / n_active

            for code in sorted(target_codes):
                px = next_open_prices.get(code, np.nan)
                if np.isnan(px) or px <= 0:
                    continue
                current_val = shares.get(code, 0) * px
                diff = per_slot - current_val
                if diff <= 0:
                    continue
                buy_cash = min(cash, diff)
                buy_shares = _lot_floor(buy_cash / (px * (1.0 + params.open_cost + params.slippage)))
                if buy_shares <= 0:
                    continue
                trade_value = buy_shares * px
                if trade_value < params.min_trade_value:
                    continue
                cash -= buy_shares * px * (1.0 + params.open_cost + params.slippage)
                old_shares = shares.get(code, 0)
                shares[code] = old_shares + buy_shares
                if old_shares == 0:
                    entry_prices[code] = px
                    position_highs[code] = px
                else:
                    entry_prices[code] = (old_shares * entry_prices[code] + buy_shares * px) / (old_shares + buy_shares)
                target_rows.append({
                    "date": data_date, "trade_date": next_date,
                    "ts_code": code, "action": "BUY",
                    "reason": "RANK_IN",
                    "price": px, "shares": buy_shares,
                    "score": next((r["score"] for r in ranked if r["ts_code"] == code), np.nan),
                    "annualized_returns": next((r["annualized_returns"] for r in ranked if r["ts_code"] == code), np.nan),
                })

        # ── Update position highs ──
        for code in shares:
            if shares.get(code, 0) <= 0:
                continue
            px_close = store.latest_price(code, next_date)
            if not np.isnan(px_close) and px_close > 0:
                position_highs[code] = max(position_highs.get(code, px_close), px_close)

        # ── Record equity ──
        portfolio_value = cash
        for code in shares:
            if shares.get(code, 0) > 0:
                px = store.latest_price(code, next_date)
                if not np.isnan(px) and px > 0:
                    portfolio_value += shares[code] * px
                else:
                    portfolio_value += shares[code] * entry_prices.get(code, 0)

        records.append({
            "date": next_date,
            "portfolio_value": portfolio_value,
            "cash": cash,
            "position_count": sum(1 for s in shares.values() if s > 0),
            "target_count": len(target_codes),
        })

    equity = pd.DataFrame(records).drop_duplicates("date", keep="last").set_index("date")
    if equity.empty:
        raise RuntimeError("No equity records — check date range and data coverage.")

    # Benchmark
    if not bench_close.empty:
        bench = bench_close.reindex(equity.index).ffill()
        fb = bench.dropna().iloc[0]
        equity["benchmark_value"] = params.initial_cash * bench / fb
        equity["benchmark_return"] = equity["benchmark_value"] / equity["benchmark_value"].iloc[0] - 1.0
    else:
        equity["benchmark_value"] = np.nan
        equity["benchmark_return"] = np.nan

    equity["strategy_return"] = equity["portfolio_value"] / equity["portfolio_value"].iloc[0] - 1.0

    return equity, pd.DataFrame(target_rows)


# ═══════════════════════════════════════════════════════════════
# Summary & output helpers
# ═══════════════════════════════════════════════════════════════


def _summarize(equity: pd.DataFrame) -> dict[str, float]:
    """Lightweight performance summary (avoids circular import from _utils)."""
    if equity.empty:
        return {}
    ret = equity["strategy_return"]
    daily_ret = equity["portfolio_value"].pct_change().dropna()
    ann_ret = daily_ret.mean() * 252.0 if len(daily_ret) > 1 else 0.0
    ann_vol = daily_ret.std() * np.sqrt(252.0) if len(daily_ret) > 1 else 0.0
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    cummax = ret.cummax()
    peak = (1.0 + ret).cummax()
    drawdown = ((1.0 + ret) / peak - 1.0).min()
    return {
        "annual_return": ann_ret,
        "annual_volatility": ann_vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": drawdown,
        "total_return": float(ret.iloc[-1]),
        "final_value": float(equity["portfolio_value"].iloc[-1]),
    }


def output_paths(out_dir: Path, start: str, end: str, tag: str = "") -> dict[str, Path]:
    exp_dir = out_dir / "etf_loop"
    exp_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"{pd.Timestamp(start):%Y%m%d}_{pd.Timestamp(end):%Y%m%d}"
    if tag:
        suffix = f"{tag}_{suffix}"
    return {
        "equity": exp_dir / f"etf_loop_equity_{suffix}.csv",
        "targets": exp_dir / f"etf_loop_targets_{suffix}.csv",
        "summary": exp_dir / f"etf_loop_summary_{suffix}.csv",
        "plot": exp_dir / f"etf_loop_returns_{suffix}.png",
    }
