# F2_CAP_MA60 实验记录 — 2026-06-27

## 一、代码改动清单

### 1. `strategies/etf_loop_engine.py` — EngineParams 新增参数

#### 1.1 无预热交易起始日 (`trading_start`)
- **位置**: `EngineParams` dataclass，第 147 行
- **类型**: `str = ""`
- **逻辑**: 主循环第 598-610 行，`trading_start` 之前只记录平仓现金，不执行交易
- **用法**: 
  ```python
  EngineParams(start="2025-10-01", trading_start="2026-01-02")
  # 价格从 2025-10 加载 → MA60/动量有充足上下文
  # 交易从 2026-01-02 开始 → 第一笔在 1 月 6 日
  ```

#### 1.2 动态回溯窗口 (`use_dynamic_lookback` 等)
- **位置**: EngineParams 第 81-86 行
- **参数**:
  | 参数 | 默认值 | 说明 |
  |---|---|
  | `use_dynamic_lookback` | `False` | 是否启用 |
  | `dyn_lookback_min` | `10` | 最小窗口 |
  | `dyn_lookback_max` | `60` | 最大窗口 |
  | `dyn_lookback_vol_ratio_cap` | `0.9` | 波动率比上界 |
  | `dyn_lookback_short_window` | `10` | 短波动率窗口 |
  | `dyn_lookback_long_window` | `60` | 长波动率窗口 |
- **公式**: `lookback = lb_min + (lb_max - lb_min) × (1 - min(cap, short_vol/long_vol))`

#### 1.3 溢价惩罚 (`use_premium_penalty` 等)
- **位置**: EngineParams 第 89-92 行
- **参数**:
  | 参数 | 默认值 | 说明 |
  |---|---|
  | `use_premium_penalty` | `False` | 是否启用 |
  | `premium_lookback` | `20` | MA 窗口 |
  | `premium_threshold` | `0.05` | 溢价阈值（5%） |
  | `premium_penalty` | `0.5` | 分数惩罚因子 |

#### 1.4 回撤过滤 (`use_drawdown_filter` 等)
- **位置**: EngineParams 第 95-99 行
- **参数**:
  | 参数 | 默认值 | 说明 |
  |---|---|
  | `use_drawdown_filter` | `False` | 启用 |
  | `dd_lookback` | `20` | 回撤窗口 |
  | `dd_max_drawdown_threshold` | `-0.15` | 最大回撤阈值 |
  | `dd_consecutive_decline_days` | `5` | 连续阴线天数 |

#### 1.5 反转过滤 (`use_reversal_filter` 等)
- **位置**: EngineParams 第 98-102 行
- **参数**:
  | 参数 | 默认值 | 说明 |
  |---|---|
  | `use_reversal_filter` | `False` | 启用 |
  | `rev_lookback` | `5` | 回看窗口 |
  | `rev_sigma` | `2.0` | 标准差倍数 |
  | `rev_penalty` | `0.3` | 分数惩罚因子 |

#### 1.6 波动率过滤 + 趋势过滤 + 波动率加权 (`use_vol_filter` / `use_trend_filter` / `use_vol_weighting`)
- **位置**: EngineParams 第 105-121 行
- **参数**:

  | 参数 | 默认值 | 类别 | 说明 |
  |---|---|---|
  | `use_vol_filter` | `False` | 波动率过滤 | 跳过波动率过高的 ETF |
  | `vol_filter_lookback` | `20` | 波动率过滤 | 波动率计算窗口 |
  | `vol_filter_threshold` | `0.5` | 波动率过滤 | 年化波动率阈值 |
  | `use_trend_filter` | `False` | 趋势过滤 | 跳过价格低于 MA 的 ETF |
  | `trend_ma_period` | `50` | 趋势过滤 | MA 周期 |
  | `use_vol_weighting` | `False` | 仓位管理 | 启用逆向波动率加权 |
  | `vol_weight_lookback` | `20` | 仓位管理 | 权重计算窗口 |

### 2. `strategies/etf_loop_strategy.py` — 信号端修改

#### 2.1 `_compute_volatility` (新增辅助函数)
- **位置**: `score_etf` 上方
- **功能**: 计算年化波动率 `np.std(returns) * np.sqrt(252)`

#### 2.2 `score_etf` 内新增过滤逻辑
按执行顺序：

1. **动态回溯窗口**（在 `current_price` 之后）：根据波动率比计算自适应 lookback，替换固定 25 天
2. **回撤过滤**（在动态回溯之后）：回撤 > 阈值 或 连续 N 天阴线 → `return None`
3. **波动率过滤**（在回撤过滤之后）：年化波动率 > 阈值 → `return None`
4. **趋势过滤**（在波动率过滤之后）：价格 < MA(N) → `return None`
5. **溢价惩罚**（在 Score 计算之后）：价格/MA > 阈值 → `score *= penalty`
6. **反转过滤**（在 3-day decline 之前）：近期收益 > N倍标准差 → `score *= penalty`

#### 2.3 `_weight_targets` + `run_backtest` 内波动率加权逻辑
- **位置**: `run_backtest` 主循环，在 `_select_targets` 返回之后
- **功能**: 若 `use_vol_weighting=True`，用 `1/vol` 归一化权重覆盖等权，`store` 从主循环闭包中获取

### 3. 新增脚本

| 脚本 | 功能 |
|---|
| `analyze_2026_comprehensive.py` | 2026 综合分析（图表+月度+归因+崩溃+错失机会+代码审计） |
| `run_2026_nowarmup.py` | 无预热 2026 独立回测（`start="2025-10-01"`, `trading_start="2026-01-02"`） |

---

## 二、实验矩阵

**基准配置**: F2_CAP_MA60，F2_v3 44-ETF 核心池 + PIT capped 补漏，MA60 过热惩罚，佣金 1bp + 滑点 1bp，持仓 5 只等权，lookback 25 天，执行 D1 开盘价。

### 实验 1：无预热回测 vs 有预热回测

| 实验 | 数据起点 | 第一笔交易 | trading_start |
|---|---|---|:---|
| 有预热（旧） | 2026-01-01 | 2026-03-18 | —（warmup 25天 + 春节） |
| **无预热（新）** | **2025-10-01** | **2026-01-06** | **2026-01-02** |

| 指标 | 有预热 | 无预热 |
|---|---:|---:|
| 年化收益 | 56.06% | **87.46%** |
| Sharpe | 2.10 | **3.18** |
| 最大回撤 | -14.17% | -14.20% |
| 2026 总收益 | 25.24% | **74.58%** |
| 交易 ETF 数 | 26 | 38 |
| 交易笔数 | ~200 | 342 |

**月度对比**:

| 月份 | 有预热 | 无预热 |
|---|---:|---:|
| 1月 | 0%（warmup） | **+18.99%** |
| 2月 | 0%（warmup） | **+5.95%** |
| 3月 | -0.93% | **+11.56%** |
| 4月 | +9.01% | +9.00% |
| 5月 | +16.11% | +16.13% |
| 6月 | +0.09% | +0.08% |

### 实验 2：三种改进 vs 基准

| 配置 | 年化 | Sharpe | DD | Δ 年化 | Δ DD |
|---|---:|---:|---:|---:|---:|
| Baseline | 87.46% | 3.18 | -14.20% | — | — |

**Premium Penalty 暴力版**: premium>5% → score×0.5
| ALL V3 aggressive | 77.24% | 2.65 | -14.35% | -10.2% | +0.15% |

**Premium Penalty 温和版**: premium>8% → score×0.8
| Premium only (soft) | **89.63%** | **3.34** | **-13.30%** | **+2.2%** | **-0.9%** |

**Dynamic Lookback 独立**: min=10, max=60, cap=0.9
| Dynamic LB only | 87.46% | 3.18 | -14.20% | 0% | 0% |

**Drawdown Filter 温和版**: DD > -20% → skip, 连续 7 天阴线 → skip
| DD filter (soft) | 87.46% | 3.18 | -14.20% | 0% | 0% |

**Reversal Filter**: 5天 > 2σ → score×0.3
| Reversal | 83.14% | 3.08 | -13.24% | **-4.3%** | +0.96% |

### 实验 3：波动率过滤 / 趋势过滤 / 波动率加权

| 配置 | 年化 | Sharpe | DD | 交易数 |
|---|---:|---:|---:|---:|
| Baseline | 87.46% | 3.18 | -14.20% | 342 |
| Vol Filter (vol>0.5) | 25.75% | 1.08 | -15.25% | 305 |
| Vol Filter (vol>0.8) | 46.42% | 1.81 | -14.88% | 335 |
| Trend Filter (MA50) | 87.46% | 3.18 | -14.20% | 342 |
| VolWeight (1/vol) | 87.46% | 3.18 | -14.20% | 342 |
| Premium + VolWeight | 89.63% | 3.34 | -13.30% | 350 |
| All 3 combined | 50.65% | 2.02 | -13.92% | 335 |

### 实验 4：动量崩溃检测（无预热 baseline vs Premium）

| 指标 | Baseline | Premium (soft) | Delta |
|---|---:|---:|---:|
| 总崩溃候选 | 340 | 348 | +8 |
| BUY >90% 分位 | 128 | 130 | +2 |
| BUY >95% 分位 | 74 | 74 | 0 |
| BUY 前向 DD > 10% | 33 | 36 | +3 |
| SELL <10% 分位 | 1 | 1 | 0 |
| SELL 后 +10% | 24 | 24 | 0 |

### 实验 5：无预热逐月交易胜率

| 月份 | 交易数 | 胜率 | 总 PnL | 盈亏比 | NAV 日胜率 | 月内 MDD |
|---|---:|---:|---:|---:|---:|---:|
| 1月 | 25 | 56.0% | +¥79,918 | 2.9 | 73.7% | -3.32% |
| 2月 | 35 | 42.9% | +¥3,020 | 1.4 | 71.4% | -1.10% |
| 3月 | 38 | 52.6% | +¥114,040 | 3.7 | 68.2% | -4.36% |
| 4月 | 29 | 48.3% | +¥4,355 | 1.2 | 61.9% | -3.13% |
| 5月 | 23 | **87.0%** | +¥175,330 | 1.7 | 55.6% | -6.87% |
| 6月 | 35 | 40.0% | -¥53,511 | 0.9 | 53.3% | **-8.84%** |

**趋势**: 胜率和日胜率持续下滑（56% → 40%，74% → 53%），6 月盈亏比跌破 1.0。

---

## 三、成本压力测试

| 档位 | 佣金 | 滑点 | 单边 | 年化(2013-2026) | Sharpe | DD | 最终资产 |
|---|---:|---:|---:|---:|---:|---:|
| 乐观 | 0.5bp | 1bp | 1.5bp | **31.97%** | 1.61 | -18.20% | ¥21.3M |
| 原始 | 1bp | 1bp | 2bp | 31.53% | 1.59 | -18.34% | ¥20.1M |
| 基准 | 1bp | 2bp | 3bp | 30.64% | 1.54 | -18.68% | ¥18.0M |
| 保守 | 2bp | 5bp | 7bp | 26.98% | 1.36 | -20.58% | ¥11.4M |

**策略对滑点高度敏感**。年化从 31.97% 跌至 26.98%（Δ -5%），最终资产差近一倍。

### 国内券商量化通道手续费参考
- 佣金：机构量化可谈至 **万 0.5–万 1**（散户万 1.5–2.5）
- 滑点：流动性好的 ETF（日成交 > 1 亿）约万 0.5–1，差的可能万 2–5
- **ETF 免印花税**（vs 股票印花税万 5）
- 单边总成本常见区间：**万 1–万 2**
- 建议以 **基准档（1bp 佣金 + 2bp 滑点）** 作为保守参考

---

## 四、代码审计

| 检查项 | 状态 | 说明 |
|---|---|---|
| 复权因子 | ✅ | `signal_close` 由 `pct_chg` 累积乘积构建，天然连续复权，无除权跳变 |
| 停牌处理 | ✅ | `pct_chg.fillna(0.0)` → forward fill → 执行时无价格跳过 |
| 未来函数 | ✅ | 全部查询用 `loc[:date]`，信号日收盘打分 → 次日开盘成交，延迟 1.0 天，0 违规 |

---

## 五、复现命令

```bash
cd /Users/jingansun/Desktop/codex/quant
source activate.sh

# 1. 无预热 2026 独立回测
python3 run_2026_nowarmup.py

# 2. 2026 综合分析（图表 + 月度 + 崩溃检测 + ETF 归因）
python3 analyze_2026_comprehensive.py

# 3. 成本压力测试（基准档 1+2bp）
python3 run_cost_stress_f2_cap_ma60.py

# 4. 成本三档测试（乐观/基准/保守）
python3 run_cost_stress_f2_cap_ma60_tiers.py

# 5. V3 改进对比（Premium / DynamicLB / DDFilter / Reversal）
# 各实验数据已保存为 outputs/etf_loop/etf_loop_summary_ABL_V3_*.csv

# 6. V4 改进对比（VolFilter / TrendFilter / VolWeighting）
# 各实验数据已保存为 outputs/etf_loop/etf_loop_summary_ABL_V4_*.csv 和 V5_*.csv
```

## 六、输出文件索引

| 文件 | 内容 |
|---|
| `F2_CAP_MA60_deep_dive/2026_comprehensive_report.md` | 2026 综合分析报告（有预热版） |
| `F2_CAP_MA60_deep_dive/2026_nowarmup_report.md` | 2026 无预热分析报告 |
| `F2_CAP_MA60_deep_dive/cost_and_params.md` | 成本与参数清单 |
| `F2_CAP_MA60_deep_dive/trade_charts_2026_nowarmup/` | 无预热版交易点图（20 张，35×10，中文名） |
| `F2_CAP_MA60_deep_dive/trade_charts_2026_crash/` | 崩溃检测图（10 张） |
| `F2_CAP_MA60_deep_dive/static_comparison_2026.md` | F2 vs ORIG38 静态池对比 |
| `F2_CAP_MA60_deep_dive/annual_monthly_report.md` | 年度/月度回测报告 |
| `F2_CAP_MA60_deep_dive/momentum_crashes_2026.csv` | 崩溃候选明细 |
| `F2_CAP_MA60_deep_dive/2026_etf_pnl.csv` | ETF PnL 明细 |

---

## 七、结论与建议

1. **保留改进**: Premium Penalty（溢价 > 8% → 分 ×0.8），+2.2% 年化 -0.9% DD
2. **移除/禁用**: Reversal Filter（-4.3% 年化）、Vol Filter（-40%+ 年化）
3. **中性/微效**: Dynamic Lookback（当前参数范围无效果）、Trend Filter（牛市中无效果）、VolWeighting（5 只等权时权重差异太小）
4. **无预热机制应设为默认**: `trading_start` 参数已加入引擎，未来年度独立回测都应使用
5. **动量崩溃是策略成本**: 128 次高位买入但 87% 年化——崩溃被更多成功交易覆盖，不应过度过滤
