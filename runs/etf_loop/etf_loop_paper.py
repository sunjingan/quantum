#!/usr/bin/env python3
"""Local lightweight paper trading for ETF Loop.

This module deliberately stays independent from Qlib online serving.  It uses
Tushare to update local ETF daily bars, generates next-day paper orders from
data visible at signal-date close, and simulates execution at the exact
trade-date open.  If a trade-date open is missing, the order is skipped.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from strategies.etf_loop_engine import (  # noqa: E402
    EngineParams,
    _apply_dynamic_overheat_penalty,
    _get_active_pool,
    _select_targets,
    execute_buy,
    execute_sell,
)
from strategies.etf_loop_strategy import (  # noqa: E402
    ETFDailyStore,
    FULL_ETF_POOL_JQ,
    _jq_to_ts,
    calculate_atr,
    get_ranked_etfs,
)
from strategies.sector_prosperity import SectorProsperityCache, _ETF_DAILY_PROCESS_CACHE  # noqa: E402


DEFAULT_OUT = PROJECT_ROOT / "outputs" / "etf_loop_paper"
DEFAULT_CACHE = PROJECT_ROOT / "data" / "tushare_cache"
DEFAULT_TOKEN = PROJECT_ROOT / "config" / "tushare_token.txt"
PIT_NAME = "etf_pool_G2_PIT_monthly.pkl"


@dataclass
class PaperPosition:
    shares: int
    avg_cost: float
    entry_date: str
    high_price: float


@dataclass
class PaperAccount:
    version: int
    profile: str
    initial_cash: float
    cash: float
    positions: dict[str, dict[str, Any]]
    pending_orders: list[dict[str, Any]]
    created_at: str
    updated_at: str
    last_signal_date: str | None = None
    last_trade_date: str | None = None


def now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ymd(date: str | pd.Timestamp) -> str:
    return pd.Timestamp(date).strftime("%Y%m%d")


def iso(date: str | pd.Timestamp) -> str:
    return pd.Timestamp(date).strftime("%Y-%m-%d")


def history_start(date: str | pd.Timestamp, days: int) -> str:
    return iso(pd.Timestamp(date).to_pydatetime() - timedelta(days=int(days)))


def account_path(out_dir: Path) -> Path:
    return out_dir / "account.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def load_account(out_dir: Path) -> PaperAccount:
    path = account_path(out_dir)
    if not path.exists():
        raise FileNotFoundError(f"Paper account not found: {path}. Run `init` first.")
    return PaperAccount(**load_json(path))


def save_account(out_dir: Path, account: PaperAccount) -> None:
    account.updated_at = now_str()
    save_json(account_path(out_dir), asdict(account))


def reset_generated_outputs(out_dir: Path) -> None:
    for path in [out_dir / "orders.csv", out_dir / "trades.csv", out_dir / "nav.csv"]:
        if path.exists():
            path.unlink()
    for subdir, pattern in [("signals", "*.csv"), ("reports", "*.md")]:
        base = out_dir / subdir
        if not base.exists():
            continue
        for path in base.glob(pattern):
            if path.is_file():
                path.unlink()


def append_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    if path.exists():
        df.to_csv(path, mode="a", header=False, index=False)
    else:
        df.to_csv(path, index=False)


def load_pickle(path: Path) -> Any:
    with open(path, "rb") as f:
        return pickle.load(f)


def load_pit_pool(cache_dir: Path) -> dict[pd.Timestamp, list[str]]:
    path = cache_dir / "sector_prosperity" / PIT_NAME
    pools = load_pickle(path)
    return {pd.Timestamp(k): list(v) for k, v in pools.items()}


def load_f2_pool(cache_dir: Path) -> list[str]:
    path = cache_dir / "sector_prosperity" / "etf_pool_F2_v3.csv"
    return sorted(pd.read_csv(path, dtype={"ts_code": str})["ts_code"].astype(str).tolist())


def load_orig38_pool() -> list[str]:
    return sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)


def load_fund_names(cache_dir: Path) -> dict[str, str]:
    path = cache_dir / "sector_prosperity" / "fund_basic_etf.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype={"ts_code": str})
    if "ts_code" not in df.columns or "name" not in df.columns:
        return {}
    return dict(zip(df["ts_code"].astype(str), df["name"].fillna("").astype(str), strict=False))


def normalize_ts_code(code: str) -> str:
    """Accept 6-digit, Tushare, or JoinQuant ETF code and return Tushare code."""
    code = str(code).strip().upper()
    if not code:
        raise ValueError("Empty ETF code")
    if code.endswith(".XSHG") or code.endswith(".XSHE"):
        return _jq_to_ts(code)
    if code.endswith(".SH") or code.endswith(".SZ"):
        return code
    symbol = "".join(ch for ch in code if ch.isdigit())
    if len(symbol) != 6:
        raise ValueError(f"Cannot infer exchange for ETF code: {code}")
    if symbol.startswith(("5", "58")):
        return f"{symbol}.SH"
    if symbol.startswith(("15", "16")):
        return f"{symbol}.SZ"
    raise ValueError(f"Cannot infer exchange for ETF code: {code}")


def read_manual_pool_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=str)
        if df.empty:
            return []
        code_col = next((c for c in ["ts_code", "code", "symbol"] if c in df.columns), df.columns[0])
        raw = df[code_col].dropna().astype(str).tolist()
    else:
        raw = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            raw.extend(part.strip() for part in line.replace("，", ",").split(",") if part.strip())
    return sorted({normalize_ts_code(c) for c in raw})


def parse_manual_dynamic_pool(args: argparse.Namespace) -> list[str]:
    codes: list[str] = []
    if getattr(args, "manual_dynamic_pool", None):
        parts = str(args.manual_dynamic_pool).replace("，", ",").split(",")
        codes.extend(part.strip() for part in parts if part.strip())
    if getattr(args, "manual_dynamic_pool_file", None):
        codes.extend(read_manual_pool_file(Path(args.manual_dynamic_pool_file)))
    return sorted({normalize_ts_code(c) for c in codes})


def apply_manual_dynamic_pool(
    params: EngineParams,
    signal_date: pd.Timestamp,
    manual_codes: list[str],
    mode: str = "merge",
) -> tuple[EngineParams, set[str], set[str]]:
    if not manual_codes:
        return params, set(), set()
    if params.pit_pools is None:
        params.pit_pools = {}
    pool_months = sorted(params.pit_pools.keys())
    original_active = _get_active_pool(params.pit_pools, pool_months, signal_date) if pool_months else set()
    manual_set = set(manual_codes)
    if mode == "replace":
        effective = manual_set
    elif mode == "merge":
        effective = set(original_active) | manual_set
    else:
        raise ValueError(f"Unknown manual dynamic pool mode: {mode}")
    month_key = signal_date.to_period("M").to_timestamp()
    params.pit_pools = dict(params.pit_pools)
    params.pit_pools[month_key] = sorted(effective)
    return params, original_active, effective


def build_profile(profile: str, cache_dir: Path, start: str, end: str, initial_cash: float) -> EngineParams:
    f2 = load_f2_pool(cache_dir)
    orig38 = load_orig38_pool()
    f2_orig = sorted(set(f2) | set(orig38))
    g2_pit = load_pit_pool(cache_dir)

    common = {
        "holdings_num": 5,
        "start": start,
        "end": end,
        "initial_cash": initial_cash,
        "exp_tag": f"PAPER_{profile}",
    }
    if profile == "static_f2":
        return EngineParams(etf_pool_ts=f2, **common)
    if profile == "static_f2_orig38":
        return EngineParams(etf_pool_ts=f2_orig, **common)
    if profile == "old_union_f2":
        return EngineParams(pit_pools=g2_pit, core_pool=f2, **common)
    if profile == "old_union_f2_orig38":
        return EngineParams(pit_pools=g2_pit, core_pool=f2_orig, **common)
    if profile == "capped_f2":
        return EngineParams(
            pit_pools=g2_pit,
            core_pool=f2,
            dynamic_fusion_mode="capped",
            dynamic_max_slots=1,
            dynamic_max_total_weight=0.10,
            dynamic_score_margin=0.05,
            dynamic_overheat_threshold=0.10,
            dynamic_overheat_penalty=0.50,
            **common,
        )
    if profile == "capped_f2_orig38":
        return EngineParams(
            pit_pools=g2_pit,
            core_pool=f2_orig,
            dynamic_fusion_mode="capped",
            dynamic_max_slots=1,
            dynamic_max_total_weight=0.20,
            dynamic_score_margin=0.10,
            dynamic_overheat_threshold=0.10,
            dynamic_overheat_penalty=0.50,
            **common,
        )
    raise ValueError(f"Unknown profile: {profile}")


def all_pool_codes(params: EngineParams) -> list[str]:
    if params.pit_pools is not None:
        pool = set(c for p in params.pit_pools.values() for c in p)
        if params.core_pool:
            pool |= set(params.core_pool)
        return sorted(pool)
    return sorted(params.etf_pool_ts)


def get_cache(token_path: Path, cache_dir: Path) -> SectorProsperityCache:
    return SectorProsperityCache(token_path, cache_dir)


def clear_etf_daily_cache() -> None:
    _ETF_DAILY_PROCESS_CACHE.clear()


def fetch_fund_basic(cache: SectorProsperityCache, force: bool = False) -> Path:
    path = cache.sector_dir / "fund_basic_etf.csv"
    if path.exists() and not force:
        return path
    if cache.pro is None:
        raise RuntimeError("Tushare token is missing; cannot fetch fund_basic.")
    df = cache.pro.fund_basic(market="E")
    if df is None:
        df = pd.DataFrame()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def fetch_fund_daily(cache: SectorProsperityCache, date: pd.Timestamp, force: bool = False) -> Path:
    y = ymd(date)
    path = cache.sector_dir / f"fund_daily_{y}.csv"
    if path.exists() and not force:
        return path
    if cache.pro is None:
        raise RuntimeError("Tushare token is missing; cannot fetch fund_daily.")
    df = cache.pro.fund_daily(trade_date=y)
    if df is None:
        df = pd.DataFrame()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    clear_etf_daily_cache()
    return path


def trade_calendar(cache: SectorProsperityCache, start: str, end: str) -> list[pd.Timestamp]:
    if cache.pro is None:
        return [pd.Timestamp(d) for d in pd.date_range(start, end, freq="B")]
    df = cache.pro.trade_cal(exchange="", start_date=ymd(start), end_date=ymd(end), is_open="1")
    if df is None or df.empty:
        return [pd.Timestamp(d) for d in pd.date_range(start, end, freq="B")]
    col = "cal_date" if "cal_date" in df.columns else "trade_date"
    return sorted(pd.to_datetime(df[col].astype(str), format="%Y%m%d", errors="coerce").dropna().tolist())


def latest_cached_trade_date(cache_dir: Path) -> pd.Timestamp:
    files = sorted((cache_dir / "sector_prosperity").glob("fund_daily_*.csv"))
    dates = []
    for path in files:
        stem = path.stem.replace("fund_daily_", "")
        try:
            dates.append(pd.Timestamp(stem))
        except Exception:
            continue
    if not dates:
        raise RuntimeError("No cached fund_daily files found.")
    return max(dates)


def next_trade_date(cache: SectorProsperityCache, signal_date: pd.Timestamp) -> pd.Timestamp:
    dates = trade_calendar(cache, iso(signal_date + pd.Timedelta(days=1)), iso(signal_date + pd.Timedelta(days=20)))
    dates = [d for d in dates if d > signal_date]
    if not dates:
        raise RuntimeError(f"Cannot find next trading date after {signal_date.date()}")
    return dates[0]


def avg_amount(store: ETFDailyStore, code: str, date: pd.Timestamp, lookback: int) -> float:
    if code not in store.amount.columns:
        return 0.0
    col = store.amount[code].loc[:date].dropna()
    if len(col) < 5:
        return 0.0
    return float(col.iloc[-min(lookback, len(col)):].mean())


def market_value(account: PaperAccount, store: ETFDailyStore, date: pd.Timestamp) -> float:
    value = 0.0
    for code, pos in account.positions.items():
        shares = int(pos.get("shares", 0))
        if shares <= 0:
            continue
        px = store.latest_price(code, date)
        if np.isnan(px) or px <= 0:
            px = float(pos.get("avg_cost", 0.0))
        value += shares * px
    return value


def build_store(params: EngineParams, token_path: Path, cache_dir: Path, start: str, end: str) -> ETFDailyStore:
    cache = get_cache(token_path, cache_dir)
    codes = all_pool_codes(params)
    return ETFDailyStore(cache, codes, start, end)


def select_targets(
    store: ETFDailyStore,
    params: EngineParams,
    signal_date: pd.Timestamp,
) -> tuple[list[dict], set[str], dict[str, float], set[str], set[str]]:
    core_set: set[str] | None = None
    dynamic_only: set[str] = set()
    active_pool: set[str]

    if params.pit_pools is not None:
        pool_months = sorted(params.pit_pools.keys())
        pit_active = _get_active_pool(params.pit_pools, pool_months, signal_date)
        active_pool = set(pit_active)
        if params.core_pool is not None:
            core_set = set(params.core_pool) & set(store.ts_codes)
            active_pool |= core_set
            dynamic_only = active_pool - core_set
        temp_codes = store.ts_codes
        store.ts_codes = [c for c in temp_codes if c in active_pool]
        ranked = get_ranked_etfs(store, signal_date, params)
        store.ts_codes = temp_codes
    elif params.core_pool is not None:
        core_set = set(params.core_pool) & set(store.ts_codes)
        active_pool = set(core_set)
        temp_codes = store.ts_codes
        store.ts_codes = list(active_pool)
        ranked = get_ranked_etfs(store, signal_date, params)
        store.ts_codes = temp_codes
    else:
        active_pool = set(store.ts_codes)
        ranked = get_ranked_etfs(store, signal_date, params)

    ranked = _apply_dynamic_overheat_penalty(ranked, dynamic_only, store, signal_date, params)
    targets, weights = _select_targets(ranked, params, core_set, dynamic_only)
    return ranked, targets, weights, active_pool, dynamic_only


def build_orders(
    account: PaperAccount,
    params: EngineParams,
    store: ETFDailyStore,
    signal_date: pd.Timestamp,
    trade_date: pd.Timestamp,
    ranked: list[dict],
    targets: set[str],
    weights: dict[str, float],
    dynamic_only: set[str],
    name_map: dict[str, str],
) -> list[dict]:
    orders: list[dict] = []
    rank_by_code = {r["ts_code"]: r for r in ranked}

    for code, pos in list(account.positions.items()):
        shares = int(pos.get("shares", 0))
        if shares <= 0:
            continue
        signal_px = store.latest_price(code, signal_date)
        stop_triggered = (
            not np.isnan(signal_px)
            and signal_px <= float(pos.get("avg_cost", 0.0)) * params.stop_loss
        )
        atr_triggered = False
        if params.use_atr_stop_loss:
            ohlc = store.ohlc_series(code, signal_date, params.atr_period + 20)
            if ohlc is not None:
                atr_val = calculate_atr(ohlc["high"], ohlc["low"], ohlc["close"], params.atr_period)
                if atr_val > 0 and not np.isnan(signal_px):
                    atr_triggered = signal_px <= float(pos.get("avg_cost", signal_px)) - params.atr_multiplier * atr_val

        should_sell = code not in targets or stop_triggered or atr_triggered
        if should_sell:
            reason = []
            if code not in targets:
                reason.append("RANK_OUT")
            if stop_triggered:
                reason.append("STOP_LOSS")
            if atr_triggered:
                reason.append("ATR_STOP")
            orders.append({
                "signal_date": iso(signal_date),
                "trade_date": iso(trade_date),
                "ts_code": code,
                "name": name_map.get(code, ""),
                "action": "SELL",
                "reason": "|".join(reason),
                "shares": shares,
                "target_weight": weights.get(code, 0.0),
                "is_dynamic_only": code in dynamic_only,
            })

    for code in sorted(targets):
        r = rank_by_code.get(code, {})
        orders.append({
            "signal_date": iso(signal_date),
            "trade_date": iso(trade_date),
            "ts_code": code,
            "name": name_map.get(code, ""),
            "action": "BUY",
            "reason": "RANK_IN",
            "shares": None,
            "target_weight": weights.get(code, np.nan),
            "score": r.get("score", np.nan),
            "dynamic_prior_return": r.get("dynamic_prior_return", np.nan),
            "dynamic_overheat_penalized": bool(r.get("dynamic_overheat_penalized", False)),
            "is_dynamic_only": code in dynamic_only,
        })
    return orders


def write_report(out_dir: Path, name: str, lines: list[str]) -> Path:
    path = out_dir / "reports" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def cmd_init(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    path = account_path(out_dir)
    if path.exists() and not args.force:
        raise FileExistsError(f"Account already exists: {path}. Use --force to overwrite.")
    if args.force:
        reset_generated_outputs(out_dir)
    account = PaperAccount(
        version=1,
        profile=args.profile,
        initial_cash=float(args.cash),
        cash=float(args.cash),
        positions={},
        pending_orders=[],
        created_at=now_str(),
        updated_at=now_str(),
    )
    save_account(out_dir, account)
    print(f"Initialized paper account: {path}")


def cmd_update_data(args: argparse.Namespace) -> None:
    cache = get_cache(Path(args.token_path), Path(args.cache_dir))
    fetch_fund_basic(cache, force=args.force_basic)
    dates = trade_calendar(cache, args.start, args.end)
    for d in dates:
        path = fetch_fund_daily(cache, d, force=args.force)
        print(f"fund_daily {d.date()} -> {path}")
    print(f"Updated {len(dates)} trading days.")


def cmd_generate(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    token_path = Path(args.token_path)
    cache_dir = Path(args.cache_dir)
    account = load_account(out_dir)
    cache = get_cache(token_path, cache_dir)
    signal_date = latest_cached_trade_date(cache_dir) if args.signal_date == "latest" else pd.Timestamp(args.signal_date)
    trade_date = next_trade_date(cache, signal_date) if args.trade_date == "next" else pd.Timestamp(args.trade_date)

    # Refresh signal-day data if requested; trade-day data is intentionally not fetched here.
    if args.fetch_signal:
        fetch_fund_daily(cache, signal_date, force=args.force_fetch)

    start = history_start(signal_date, args.history_days)
    end = iso(signal_date)
    params = build_profile(account.profile, cache_dir, start, end, account.initial_cash)
    manual_dynamic_pool = parse_manual_dynamic_pool(args)
    params, original_dynamic_pool, effective_dynamic_pool = apply_manual_dynamic_pool(
        params,
        signal_date,
        manual_dynamic_pool,
        args.manual_dynamic_pool_mode,
    )
    store = build_store(params, token_path, cache_dir, start, end)
    name_map = load_fund_names(cache_dir)
    ranked, targets, weights, active_pool, dynamic_only = select_targets(store, params, signal_date)
    orders = build_orders(account, params, store, signal_date, trade_date, ranked, targets, weights, dynamic_only, name_map)

    account.pending_orders = orders
    account.last_signal_date = iso(signal_date)
    save_account(out_dir, account)

    signal_rows = []
    for rank, r in enumerate(ranked[:30], start=1):
        code = r["ts_code"]
        signal_rows.append({
            "signal_date": iso(signal_date),
            "rank": rank,
            "ts_code": code,
            "name": name_map.get(code, ""),
            "score": r.get("score"),
            "annualized_returns": r.get("annualized_returns"),
            "r_squared": r.get("r_squared"),
            "target": code in targets,
            "target_weight": weights.get(code, 0.0),
            "is_dynamic_only": code in dynamic_only,
            "dynamic_prior_return": r.get("dynamic_prior_return"),
            "dynamic_overheat_penalized": r.get("dynamic_overheat_penalized", False),
        })
    signal_path = out_dir / "signals" / f"signal_{ymd(signal_date)}.csv"
    signal_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(signal_rows).to_csv(signal_path, index=False)
    append_csv(out_dir / "orders.csv", orders)

    nav = account.cash + market_value(account, store, signal_date)
    lines = [
        f"# ETF Loop Paper Signal {iso(signal_date)}",
        "",
        f"- profile: `{account.profile}`",
        f"- signal_date: `{iso(signal_date)}`",
        f"- planned_trade_date: `{iso(trade_date)}`",
        f"- cash: `{account.cash:.2f}`",
        f"- estimated_nav_at_signal_close: `{nav:.2f}`",
        f"- active_pool_size: `{len(active_pool)}`",
        f"- manual_dynamic_pool_mode: `{args.manual_dynamic_pool_mode}`",
        f"- manual_dynamic_pool_size: `{len(manual_dynamic_pool)}`",
        f"- original_pit_dynamic_pool_size: `{len(original_dynamic_pool)}`",
        f"- effective_dynamic_pool_size: `{len(effective_dynamic_pool)}`",
        f"- targets: `{', '.join(sorted(targets))}`",
        "",
        "## Manual Dynamic Pool",
    ]
    if manual_dynamic_pool:
        lines.extend(f"- {code} {name_map.get(code, '')}" for code in manual_dynamic_pool)
    else:
        lines.append("- not provided")
    lines.extend([
        "",
        "## Effective Dynamic Pool",
    ])
    if effective_dynamic_pool:
        lines.extend(f"- {code} {name_map.get(code, '')}" for code in sorted(effective_dynamic_pool))
    else:
        lines.append("- empty")
    lines.extend([
        "",
        "## Orders",
    ])
    if orders:
        lines.extend(
            f"- {o['action']} {o['ts_code']} {o.get('name', '')} weight={o.get('target_weight', '')} reason={o.get('reason', '')} dynamic={o.get('is_dynamic_only', False)}"
            for o in orders
        )
    else:
        lines.append("- no orders")
    report = write_report(out_dir, f"signal_{ymd(signal_date)}.md", lines)
    print(f"Generated {len(orders)} pending orders for {trade_date.date()}. Report: {report}")


def cmd_execute(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    token_path = Path(args.token_path)
    cache_dir = Path(args.cache_dir)
    account = load_account(out_dir)
    if not account.pending_orders:
        raise RuntimeError("No pending orders. Run `generate` first.")
    trade_date = pd.Timestamp(args.trade_date) if args.trade_date else pd.Timestamp(account.pending_orders[0]["trade_date"])
    signal_date = pd.Timestamp(account.pending_orders[0]["signal_date"])
    if any(pd.Timestamp(o["trade_date"]) != trade_date for o in account.pending_orders):
        raise RuntimeError("Pending orders contain multiple trade dates; clear or regenerate orders.")

    cache = get_cache(token_path, cache_dir)
    if args.fetch_trade:
        fetch_fund_daily(cache, trade_date, force=args.force_fetch)

    start = history_start(signal_date, args.history_days)
    end = iso(trade_date)
    params = build_profile(account.profile, cache_dir, start, end, account.initial_cash)
    store = build_store(params, token_path, cache_dir, start, end)

    execution_rows: list[dict] = []
    orders = list(account.pending_orders)
    sell_orders = [o for o in orders if o["action"] == "SELL"]
    buy_orders = [o for o in orders if o["action"] == "BUY"]

    for order in sell_orders:
        code = order["ts_code"]
        pos = account.positions.get(code)
        if not pos or int(pos.get("shares", 0)) <= 0:
            continue
        exec_px = store.open_price(code, trade_date)
        liq = avg_amount(store, code, signal_date, params.liquidity_lookback)
        result = execute_sell(
            code,
            int(pos["shares"]),
            store.latest_price(code, signal_date),
            exec_px,
            float(pos.get("avg_cost", 0.0)),
            liq,
            params,
        )
        if result is None:
            execution_rows.append({**order, "status": "SKIPPED_NO_OPEN_OR_LIQUIDITY", "price": exec_px})
            continue
        account.cash += result["net_proceeds"]
        sold = int(result["shares"])
        remaining = int(pos["shares"]) - sold
        if remaining <= 0:
            account.positions.pop(code, None)
        else:
            pos["shares"] = remaining
            account.positions[code] = pos
        execution_rows.append({
            **order,
            "status": "FILLED",
            "price": result["price"],
            "shares": sold,
            "gross_proceeds": result["gross_proceeds"],
            "cost": result["cost_total"],
            "net_proceeds": result["net_proceeds"],
            "partial": result["partial"],
        })

    # Size buys after sells using exact trade-date opens; no price fallback.
    current_value = account.cash
    for code, pos in account.positions.items():
        px = store.open_price(code, trade_date)
        if not np.isnan(px) and px > 0:
            current_value += int(pos.get("shares", 0)) * px

    target_weights = {o["ts_code"]: float(o.get("target_weight", 0.0) or 0.0) for o in buy_orders}
    for order in buy_orders:
        code = order["ts_code"]
        exec_px = store.open_price(code, trade_date)
        if np.isnan(exec_px) or exec_px <= 0:
            execution_rows.append({**order, "status": "SKIPPED_NO_OPEN", "price": exec_px})
            continue
        target_value = current_value * target_weights.get(code, 0.0)
        current_pos_value = int(account.positions.get(code, {}).get("shares", 0)) * exec_px
        diff = target_value - current_pos_value
        if diff <= 0:
            execution_rows.append({**order, "status": "SKIPPED_ALREADY_AT_TARGET", "price": exec_px})
            continue
        liq = avg_amount(store, code, signal_date, params.liquidity_lookback)
        result = execute_buy(code, min(account.cash, diff), diff, exec_px, liq, params)
        if result is None:
            execution_rows.append({**order, "status": "SKIPPED_CASH_OR_LIQUIDITY", "price": exec_px})
            continue
        account.cash -= result["net_cost"]
        old = account.positions.get(code)
        if old:
            old_shares = int(old["shares"])
            new_shares = old_shares + int(result["shares"])
            avg_cost = (old_shares * float(old["avg_cost"]) + int(result["shares"]) * exec_px) / new_shares
            old.update({"shares": new_shares, "avg_cost": avg_cost, "high_price": max(float(old.get("high_price", exec_px)), exec_px)})
            account.positions[code] = old
        else:
            account.positions[code] = asdict(PaperPosition(
                shares=int(result["shares"]),
                avg_cost=exec_px,
                entry_date=iso(trade_date),
                high_price=exec_px,
            ))
        execution_rows.append({
            **order,
            "status": "FILLED",
            "price": result["price"],
            "shares": int(result["shares"]),
            "gross_cost": result["gross_cost"],
            "cost": result["cost_total"],
            "net_cost": result["net_cost"],
            "partial": result["partial"],
        })

    # Update high watermark using trade-date close where available.
    for code, pos in account.positions.items():
        px = store.latest_price(code, trade_date)
        if not np.isnan(px) and px > 0:
            pos["high_price"] = max(float(pos.get("high_price", px)), px)

    nav = account.cash + market_value(account, store, trade_date)
    account.pending_orders = []
    account.last_trade_date = iso(trade_date)
    save_account(out_dir, account)
    append_csv(out_dir / "trades.csv", execution_rows)
    append_csv(out_dir / "nav.csv", [{
        "date": iso(trade_date),
        "cash": account.cash,
        "market_value": nav - account.cash,
        "portfolio_value": nav,
        "position_count": len(account.positions),
    }])

    lines = [
        f"# ETF Loop Paper Execution {iso(trade_date)}",
        "",
        f"- profile: `{account.profile}`",
        f"- signal_date: `{iso(signal_date)}`",
        f"- trade_date: `{iso(trade_date)}`",
        f"- cash_after: `{account.cash:.2f}`",
        f"- nav_after_close_mark: `{nav:.2f}`",
        "",
        "## Executions",
    ]
    lines.extend(
        f"- {r.get('status')} {r.get('action')} {r.get('ts_code')} shares={r.get('shares')} price={r.get('price')} cost={r.get('cost', '')}"
        for r in execution_rows
    )
    report = write_report(out_dir, f"execution_{ymd(trade_date)}.md", lines)
    print(f"Executed {sum(1 for r in execution_rows if r.get('status') == 'FILLED')} fills. NAV={nav:.2f}. Report: {report}")


def cmd_status(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    token_path = Path(args.token_path)
    cache_dir = Path(args.cache_dir)
    account = load_account(out_dir)
    date = latest_cached_trade_date(cache_dir) if args.date == "latest" else pd.Timestamp(args.date)
    start = history_start(date, args.history_days)
    params = build_profile(account.profile, cache_dir, start, iso(date), account.initial_cash)
    store = build_store(params, token_path, cache_dir, start, iso(date))
    name_map = load_fund_names(cache_dir)
    mv = market_value(account, store, date)
    nav = account.cash + mv
    print(f"profile: {account.profile}")
    print(f"date: {date.date()}")
    print(f"cash: {account.cash:.2f}")
    print(f"market_value: {mv:.2f}")
    print(f"nav: {nav:.2f}")
    print(f"pending_orders: {len(account.pending_orders)}")
    print("positions:")
    for code, pos in account.positions.items():
        px = store.latest_price(code, date)
        value = int(pos["shares"]) * px if not np.isnan(px) else np.nan
        print(f"  {code} {name_map.get(code, '')}: shares={pos['shares']} avg={pos['avg_cost']:.4f} px={px:.4f} value={value:.2f}")


def cmd_run_day(args: argparse.Namespace) -> None:
    cmd_update_data(args)
    args.signal_date = args.signal_date or args.end
    args.trade_date = args.trade_date or "next"
    cmd_generate(args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Local paper trading for ETF Loop")
    p.set_defaults(func=None)
    p.add_argument("--out-dir", default=str(DEFAULT_OUT))
    p.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    p.add_argument("--token-path", default=str(DEFAULT_TOKEN))
    p.add_argument("--history-days", type=int, default=500)

    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--profile", default="capped_f2", choices=[
        "static_f2", "static_f2_orig38", "old_union_f2", "old_union_f2_orig38",
        "capped_f2", "capped_f2_orig38",
    ])
    init.add_argument("--cash", type=float, default=500_000.0)
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    upd = sub.add_parser("update-data")
    upd.add_argument("--start", required=True)
    upd.add_argument("--end", required=True)
    upd.add_argument("--force", action="store_true")
    upd.add_argument("--force-basic", action="store_true")
    upd.set_defaults(func=cmd_update_data)

    gen = sub.add_parser("generate")
    gen.add_argument("--signal-date", default="latest")
    gen.add_argument("--trade-date", default="next")
    gen.add_argument("--fetch-signal", action="store_true")
    gen.add_argument("--force-fetch", action="store_true")
    gen.add_argument("--manual-dynamic-pool", help="Comma-separated ETF codes to merge/replace this signal month's PIT dynamic pool.")
    gen.add_argument("--manual-dynamic-pool-file", help="CSV/text file containing ETF codes for this signal month's PIT dynamic pool.")
    gen.add_argument("--manual-dynamic-pool-mode", choices=["merge", "replace"], default="merge")
    gen.set_defaults(func=cmd_generate)

    exe = sub.add_parser("execute")
    exe.add_argument("--trade-date")
    exe.add_argument("--fetch-trade", action="store_true")
    exe.add_argument("--force-fetch", action="store_true")
    exe.set_defaults(func=cmd_execute)

    status = sub.add_parser("status")
    status.add_argument("--date", default="latest")
    status.set_defaults(func=cmd_status)

    run_day = sub.add_parser("run-day")
    run_day.add_argument("--start", required=True)
    run_day.add_argument("--end", required=True)
    run_day.add_argument("--signal-date")
    run_day.add_argument("--trade-date")
    run_day.add_argument("--force", action="store_true")
    run_day.add_argument("--force-basic", action="store_true")
    run_day.add_argument("--fetch-signal", action="store_true")
    run_day.add_argument("--force-fetch", action="store_true")
    run_day.add_argument("--manual-dynamic-pool", help="Comma-separated ETF codes to merge/replace this signal month's PIT dynamic pool.")
    run_day.add_argument("--manual-dynamic-pool-file", help="CSV/text file containing ETF codes for this signal month's PIT dynamic pool.")
    run_day.add_argument("--manual-dynamic-pool-mode", choices=["merge", "replace"], default="merge")
    run_day.set_defaults(func=cmd_run_day)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.func is None:
        parser.print_help()
        raise SystemExit(2)
    args.func(args)


if __name__ == "__main__":
    main()
