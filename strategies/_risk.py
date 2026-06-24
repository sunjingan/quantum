"""
风控模块 — 仓位管理 / 止损止盈 / 组合回撤控制 / 市场状态仓位调节。

量化指标:
  - 单只移动止损: 从最高点回撤超过 stop_distance → 强制卖出
  - 组合回撤控制: 组合从高点回撤 > max_portfolio_dd → 仓位× reduction_ratio
  - 市场状态缓冲: 弱市+高回撤 → 现金比例 = cash_buffer
  - 最小持仓期: 买入未满 min_hold_days 不卖出（降低换手）
  
所有参数可配置, 纯函数, 无框架依赖。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class RiskParams:
    """风控参数"""
    # 单只止损
    stop_loss_pct: float = -0.20          # 固定止损：入场价跌超 20% → 卖出
    trailing_stop_activation: float = 0.30  # 移动止盈启动：盈利超 30% 后启用
    trailing_stop_distance: float = 0.15    # 移动止盈回撤距离：从最高点回撤 15% → 卖出
    max_single_position_pct: float = 0.15   # 单只最大仓位 15%

    # 失效纪律 (method.md)
    invalidation_gross_margin: float = 15.0  # 毛利率 < 15% → 失效
    invalidation_ocf_to_np: float = 0.5      # OCF/NP < 0.5 → 失效
    invalidation_crowding: float = 4.0       # 拥挤度 > 4 → 失效
    invalidation_inventory_growth: float = 2.0  # 存货增速/营收增速 > 2 → 失效

    # 组合回撤控制
    max_portfolio_drawdown: float = -0.25    # 组合回撤超 25% → 减仓
    drawdown_reduce_exposure: float = 0.50   # 减仓至当前仓位 × 50%

    # 市场状态仓位调节
    cash_buffer_strong: float = 0.05         # 强市：保留 5% 现金
    cash_buffer_neutral: float = 0.15        # 中性：保留 15% 现金
    cash_buffer_weak: float = 0.30           # 弱市：保留 30% 现金
    cash_buffer_high_dd: float = 0.50        # 弱市+高回撤：保留 50% 现金

    # 持仓保护
    min_hold_days: int = 40                  # 最小持仓 40 个交易日 ≈ 2 个月
    max_positions: int = 12                  # 最大持仓数

    # 选股过滤
    min_tier: str = "Pass-B"                 # 最低准入梯队
    allow_pass_c: bool = False               # 是否允许 Pass-C
    exclude_pledge_high: bool = True         # 排除质押 > 50%
    exclude_crowding_high: bool = True       # 排除拥挤度 > 3


# ═══════════════════════════════════════════════════════════════════
# 单只止损 / 移动止盈
# ═══════════════════════════════════════════════════════════════════

def check_single_stop_loss(
    code: str,
    entry_price: float,
    current_price: float,
    highest_since_entry: float,
    risk: RiskParams,
) -> Tuple[bool, str]:
    """
    检查单只股票是否触发止损/止盈。

    返回 (should_sell, reason)
    """
    if current_price <= 0 or entry_price <= 0:
        return False, ""

    pnl_pct = current_price / entry_price - 1

    # 固定止损
    if pnl_pct <= risk.stop_loss_pct:
        return True, f"止损: {pnl_pct*100:.1f}%"

    # 移动止盈
    if pnl_pct >= risk.trailing_stop_activation:
        drawdown_from_peak = current_price / highest_since_entry - 1
        if drawdown_from_peak <= -risk.trailing_stop_distance:
            return True, f"移动止盈: 最高+{highest_since_entry/entry_price-1:.1%}, 当前+{pnl_pct:.1%}"

    return False, ""


# ═══════════════════════════════════════════════════════════════════
# 组合回撤控制
# ═══════════════════════════════════════════════════════════════════

def check_portfolio_drawdown(
    equity_curve: pd.Series,
    risk: RiskParams,
) -> Tuple[float, bool]:
    """
    检查组合回撤。
    
    返回 (current_drawdown_pct, should_reduce)
    """
    if len(equity_curve) < 2:
        return 0.0, False

    peak = equity_curve.cummax().iloc[-1]
    current = equity_curve.iloc[-1]
    dd = current / peak - 1

    return dd, (dd <= risk.max_portfolio_drawdown)


# ═══════════════════════════════════════════════════════════════════
# 市场状态仓位调节
# ═══════════════════════════════════════════════════════════════════

def compute_exposure_ratio(
    market_state_str: str,
    risk_state_str: str,
    portfolio_dd: float,
    risk: RiskParams,
) -> float:
    """
    根据市场状态 + 组合回撤，计算目标仓位比例。

    返回 [0, 1] 之间的权重，1 = 满仓，0 = 空仓。
    
    核心规则: 弱市完全空仓，强市/中性正常持有。
    """
    # 弱市 → 完全空仓，不冒险
    if market_state_str == "MARKET_WEAK":
        return 0.0

    # 中性市场
    if market_state_str == "MARKET_NEUTRAL":
        base_ratio = 1 - risk.cash_buffer_neutral
        # 但组合本身回撤太大 → 也空仓
        if portfolio_dd <= risk.max_portfolio_drawdown:
            return 0.0
        return base_ratio

    # 强市 → 正常持有，留少量现金备用
    if market_state_str == "MARKET_STRONG":
        base_ratio = 1 - risk.cash_buffer_strong
        if portfolio_dd <= risk.max_portfolio_drawdown:
            base_ratio *= risk.drawdown_reduce_exposure
        return max(base_ratio, 0.30)

    return 1.0  # UNKNOWN fallback


# ═══════════════════════════════════════════════════════════════════
# 选股过滤
# ═══════════════════════════════════════════════════════════════════

def filter_pool_by_risk(pool: pd.DataFrame, risk: RiskParams) -> pd.DataFrame:
    """
    根据风控规则过滤候选池。

    - 排除低于 min_tier 的股票
    - 排除质押高风险
    - 排除拥挤度过高
    """
    if pool.empty:
        return pool

    # 梯队过滤
    tier_order = {"Pass-A": 0, "Pass-B": 1, "Pass-C": 2}
    min_order = tier_order.get(risk.min_tier, 1)
    pool = pool[pool["tier"].map(tier_order).fillna(99) <= min_order].copy()

    if risk.exclude_pledge_high and "is_pledge_high_risk" in pool.columns:
        pool = pool[~pool["is_pledge_high_risk"].fillna(False).astype(bool)]

    if risk.exclude_crowding_high and "crowding_score" in pool.columns:
        pool = pool[pool["crowding_score"].fillna(0).astype(float) <= 3.0]

    # Also filter by insider sells if available
    if "insider_sells_3m" in pool.columns and "Pass-C" not in str(risk.min_tier):
        pool = pool[pool["insider_sells_3m"].fillna(0).astype(int) == 0]

    return pool


# ═══════════════════════════════════════════════════════════════════
# 失效纪律增强版 (method.md)
# ═══════════════════════════════════════════════════════════════════

def check_invalidation_enhanced(
    code: str,
    entry_price: float,
    current_price: float,
    highest_since_entry: float,
    entry_date: pd.Timestamp,
    data_date: pd.Timestamp,
    fund_cache,
    enrich_cache,
    risk: RiskParams,
) -> Tuple[bool, List[str]]:
    """
    增强版失效检查 — method.md 全部失效条件。

    返回 (is_invalidated, reasons)
    """
    reasons = []

    # 1. 止损/止盈
    should_sell, reason = check_single_stop_loss(
        code, entry_price, current_price, highest_since_entry, risk
    )
    if should_sell:
        reasons.append(reason)

    # 2. 毛利恶化
    from strategies._fundamental import qlib_to_tushare
    ts_code = qlib_to_tushare(code)
    fina = fund_cache.latest_visible_row("fina_indicator", ts_code, data_date)
    if fina is not None:
        gm = pd.to_numeric(fina.get("grossprofit_margin"), errors="coerce")
        if pd.notnull(gm) and gm < risk.invalidation_gross_margin:
            reasons.append(f"毛利{gm:.1f}%<{risk.invalidation_gross_margin}%")

    # 3. 内幕/审计/拥挤度（复用已有 check_invalidation）
    if enrich_cache is not None:
        from strategies.trend_serenity import check_invalidation
        inval = check_invalidation(code, fund_cache, enrich_cache, data_date, entry_date)
        if inval["invalidated"]:
            reasons.extend(inval["signals"])

    # 4. 拥挤度 > 阈值
    if enrich_cache is not None:
        crowding = enrich_cache.get_crowding(ts_code, data_date)
        if crowding.crowding_score >= risk.invalidation_crowding:
            reasons.append(f"拥挤度{crowding.crowding_score:.1f}>={risk.invalidation_crowding}")

    return len(reasons) > 0, reasons
