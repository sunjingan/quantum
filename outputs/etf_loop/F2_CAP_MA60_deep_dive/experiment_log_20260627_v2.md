# F2_CAP_MA60 实验记录（完整版）— 2026-06-27

## 零、执行模型说明

### 我们的默认执行模型
```
信号日(T)收盘 → 计算动量排名 → 确定5个目标ETF → 次日(T+1)开盘成交
```
- **信号到执行延迟**：1 天
- **信号数据**：今日收盘价
- **优点**：保守、无未来函数

### 朋友的执行模型（`friend_mode`）
```
信号日(T) 9:50AM → 用昨日收盘+今日盘中实时价算排名 → 确定1个目标ETF → 当日成交
```
- **信号到执行延迟**：0 天（T+0）
- **信号数据**：昨日收盘 + 今日盘中价
- **差异**：比我们快 1 天，动量策略中 1 天延迟复利后差距巨大

---

## 一、代码改动清单

### 1. `strategies/etf_loop_engine.py` — EngineParams 新增参数

#### 1.1 无预热交易起始日 (`trading_start`)，第 147 行
```python
trading_start: str = ""  # 设 "2026-01-02" 则在此时开始交易，之前只记平仓现金
```
- 配合 `start="2025-10-01"` → 数据从 2025-10 加载，MA60/动量有充足上下文
- 交易从 2026-01-02 开始，第一笔 1 月 6 日

#### 1.2 朋友策略复现开关 (`friend_mode`)，第 149 行
```python
friend_mode: bool = False  # T+0信号模型：昨日收盘+今日开盘→当日开盘执行
```
- `True` 时：信号用昨日收盘 + 今日开盘；溢价惩罚改为减法（score -= 1）
- `False` 时：保持原有逻辑不变

#### 1.3 动态回溯窗口 (`use_dynamic_lookback` 等 6 个)，第 81-86 行
| 参数 | 默认值 | 说明 |
|---|---|
| `use_dynamic_lookback` | `False` | 启用 |
| `dyn_lookback_min` | `10` (vol法) / `20` (ATR法) | 最小窗口 |
| `dyn_lookback_max` | `60` | 最大窗口 |
| `dyn_lookback_vol_ratio_cap` | `0.9` | 比率上界 |
| `dyn_lookback_short_window` | `10` | 短窗口 |
| `dyn_lookback_long_window` | `60` | 长窗口 |
| `dyn_lookback_use_atr` | `True` | AT法 vs 波动率法 |

#### 1.4 溢价惩罚 (`use_premium_penalty` 等 4 个)，第 89-92 行
| 参数 | 默认值 | 说明 |
|---|---|
| `use_premium_penalty` | `False` | 启用 |
| `premium_lookback` | `20` | MA 窗口 |
| `premium_threshold` | `0.05` | 阈值（5%溢价） |
| `premium_penalty` | `0.5` | 乘因子（friend_mode 下为减分值） |

#### 1.5 回撤过滤 (`use_drawdown_filter` 等 5 个)，第 95-99 行
| 参数 | 默认值 | 说明 |
|---|---|
| `use_drawdown_filter` | `False` | 启用 |
| `dd_lookback` | `20` | 回撤窗口 |
| `dd_max_drawdown_threshold` | `-0.15` | 最大回撤阈值 |
| `dd_consecutive_decline_days` | `5` | 连续阴线天数 |
| `dd_use_enhanced` | `True` | 朋友增强版 (con1/con2/con3) |

#### 1.6 反转过滤 (`use_reversal_filter` 等 4 个)，第 98-102 行
#### 1.7 波动率过滤 + 趋势过滤 + 波动率加权 (`use_vol_filter` 等 7 个)，第 105-121 行

### 2. `strategies/etf_loop_strategy.py` — 信号端修改

- `_compute_volatility()` 辅助函数
- `score_etf()` 内新增 6 个过滤逻辑（按顺序：动态回溯 → 回撤 → 波动率 → 趋势 → 溢价惩罚 → 反转）
- `friend_mode` 下：价格用昨日收盘+今日开盘构建；溢价惩罚改为 subtract-1 模式
- `friend_mode` 下：`get_ranked_etfs()` 接受 `exec_date` 参数

### 3. 新增脚本

| 脚本 | 功能 |
|---|
| `analyze_2026_comprehensive.py` | 2026 综合分析（图表+月度+归因+崩溃+代码审计） |
| `run_2026_nowarmup.py` | 无预热 2026 回测 |
| `replicate_friend_strategy.py` | 朋友策略第一次复现 |
| `replicate_friend_baseline.py` | 朋友策略严格复现（含 friend_mode） |
| `run_long_period_optimization_compare.py` | 长周期优化对比 |

---

## 二、实验 1：无预热回测 vs 有预热回测（2026 H1）

| 实验 | 数据起点 | 第一笔交易 | 原因 |
|---|---|---|
| 有预热（旧） | 2026-01-01 | 2026-03-18 | warmup 25天 + 春节 |
| 无预热（新） | 2025-10-01 | 2026-01-06 | `trading_start="2026-01-02"` |

| 指标 | 有预热 | 无预热 |
|---|---:|---:|
| 年化 | 56.06% | **87.46%** |
| Sharpe | 2.10 | **3.18** |
| DD | -14.17% | -14.20% |
| 2026 总收益 | 25.24% | **74.58%** |
| 交易 ETF 数 | 26 | 38 |

### 月度对比

| 月份 | 有预热 | 无预热 |
|---|---:|---:|
| 1月 | 0%（warmup） | **+18.99%** |
| 2月 | 0%（warmup） | **+5.95%** |
| 3月 | -0.93% | **+11.56%** |
| 4月 | +9.01% | +9.00% |
| 5月 | +16.11% | +16.13% |
| 6月 | +0.09% | +0.08% |

---

## 三、实验 2：无预热逐月胜率

| 月份 | 交易 | 胜率 | 盈亏比 | 日胜率 | 月内 MDD |
|---|---:|---:|---:|---:|---:|
| 1月 | 25 | 56.0% | 2.9 | 73.7% | -3.32% |
| 2月 | 35 | 42.9% | 1.4 | 71.4% | -1.10% |
| 3月 | 38 | 52.6% | 3.7 | 68.2% | -4.36% |
| 4月 | 29 | 48.3% | 1.2 | 61.9% | -3.13% |
| 5月 | 23 | **87.0%** | 1.7 | 55.6% | -6.87% |
| 6月 | 35 | 40.0% | 0.9 | 53.3% | -8.84% |

> 胜率和日胜率持续下滑。6 月盈亏比跌破 1.0。

---

## 四、实验 3：三种改进 vs 基准（2026 H1）

| 配置 | 年化 | Sharpe | DD | Δ年化 |
|---|---:|---:|---:|---:|
| Baseline（无预热） | 87.46% | 3.18 | -14.20% | — |
| Premium(soft) 溢价>8% ×0.8 | **89.63%** | **3.34** | **-13.30%** | **+2.2%** |
| Dynamic Lookback | 87.46% | 3.18 | -14.20% | 0% |
| DD Filter(soft) | 87.46% | 3.18 | -14.20% | 0% |
| Reversal 5d>2σ ×0.3 | **83.14%** | 3.08 | -13.24% | **-4.3%** |

---

## 五、实验 4：波动率/趋势/仓位管理（2026 H1）

| 配置 | 年化 | DD | 交易 |
|---|---:|---:|---:|
| Baseline | 87.46% | -14.20% | 342 |
| Vol Filter (vol>0.5) | 25.75% | -15.25% | 305 |
| Vol Filter (vol>0.8) | 46.42% | -14.88% | 335 |
| Trend Filter (MA50) | 87.46% | -14.20% | 342 |
| VolWeight (1/vol) | 87.46% | -14.20% | 342 |
| Premium + VolWeight | 89.63% | -13.30% | 350 |
| All 3 combined | 50.65% | -13.92% | 335 |

> 硬过滤（Vol/Trend Filter）对动量策略有害。仓位微调（VolWeight）效果极小。

---

## 六、实验 5：动量崩溃检测

| 指标 | Baseline | Premium | Reversal |
|---|---:|---:|---:|
| 总崩溃 | 340 | 348 | **425** |
| BUY >90%分位 | 128 | 130 | **160** |
| BUY >95%分位 | 74 | 74 | 88 |
| BUY DD>10% | 33 | 36 | 41 |
| SELL后+10% | 24 | 24 | 34 |

> Premium Penalty 不减少崩溃（是收益增强器不是崩溃防护器）。Reversal 反增崩溃。
> 崩溃是动量策略的成本，128 次高位买入但年化 87%——崩溃被更多成功交易覆盖。

---

## 七、实验 6：长周期优化对比（2013-2026）

### 四个池配置

| 配置 | 年化 | Sharpe | DD |
|---|---:|---:|---:|
| **F2_CAP_MA60** Baseline | **31.53%** | 1.59 | -18.34% |
| F2_CAP_MA60 + Premium(soft) | 31.49% | 1.59 | -18.36% |
| F2_STATIC_BASE | 29.99% | 1.54 | -18.36% |
| F2_STATIC_MA60 | 30.52% | 1.58 | -18.35% |
| ORIG38_STATIC | 23.46% | 1.52 | -15.44% |

> **Premium Penalty 在长周期中性偏负**（Δ -0.04% 到 -0.87%）。长牛市中溢价是动量特征而非反转信号。
> F2_CAP_MA60 年化最高（31.53%），静态池 23-30%。

---

## 八、实验 7：朋友策略复现（9 ETF，1 仓位，2020-2025）

### 严格复现（friend's cost: 2bp+10bp）

| 配置 | 年化 | Sharpe | DD |
|---|---:|---:|---:|
| Simple 25d（无开关） | 18.96% | 0.76 | -28.24% |
| friend_mode 空跑 | 20.20% | 0.81 | -36.16% |
| **friend_mode + 全逻辑** | **24.86%** | 1.10 | **-20.92%** |
| 无 friend_mode + 全逻辑 | 21.52% | 0.96 | -23.97% |
| 朋友声称 | 66.04% | — | -16.53% |

### 无法完全复现的原因
1. **盘中信息（~25-30pp）**：朋友用 9:50 AM 实时价，我们只能拿到开盘价
2. **真实 IOPV（~5-8pp）**：朋友用聚宽 `unit_net_value`
3. **TA-Lib ATR（~3-5pp）**：与我们的 `calculate_atr` 算法不同

### 执行频率对比（2020-2025）

| | 朋友（1ETF） | 我们（5ETF） |
|---|---:|---:|
| 总交易 | 757 | 6744 |
| 日均 | 1.8 笔 | 3.7 笔 |
| 单日最多 | 2 笔 | 10 笔 |
| 换仓日 | 338 天 | 1741 天 |

---

## 九、实验 8：朋友策略可借鉴项

| 借鉴项 | 对我们效果 | 说明 |
|---|:---:|---|
| Score 范围过滤 (0<score<6) | ✅ +6pp | 最有价值的借鉴 |
| ATR 动态回溯 | ❌ 0 | 对我们 44-ETF 大池无效果 |
| 增强回撤过滤 (con1/con2/con3) | → 微正 | DD 微改善 |
| 精简池 9 ETF | — | 可尝试减少池规模 |
| 单仓位 | — | 降低换手，但牺牲分散 |

---

## 十、成本压力测试

| 档位 | 佣金 | 滑点 | 单边 | 年化(2013-2026) | Sharpe | DD |
|---|---:|---:|---:|---:|---:|---:|
| 乐观 | 0.5bp | 1bp | 1.5bp | 31.97% | 1.61 | -18.20% |
| 原始 | 1bp | 1bp | 2bp | 31.53% | 1.59 | -18.34% |
| 基准 | 1bp | 2bp | 3bp | 30.64% | 1.54 | -18.68% |
| 保守 | 2bp | 5bp | 7bp | 26.98% | 1.36 | -20.58% |

### 国内量化通道费用参考
- 佣金：机构可谈至 **万0.5–万1**
- 滑点：流动性好的 ETF ~万0.5-1，差的万2-5
- **ETF 免印花税**
- 建议以基准档（1bp+2bp）作保守参考

---

## 十一、代码审计

| 检查项 | 状态 | 说明 |
|---|---|---|
| 复权因子 | ✅ | `signal_close` 由 `pct_chg` 累积乘积构建 |
| 停牌处理 | ✅ | `pct_chg.fillna(0.0)` → forward fill |
| 未来函数 | ✅ | 全部 `loc[:date]`，信号→执行延迟 1.0天，0 违规 |

---

## 十二、复现命令

```bash
cd /Users/jingansun/Desktop/codex/quant
source activate.sh

# 无预热 2026 回测
python3 run_2026_nowarmup.py

# 2026 综合分析（图表 + 月度 + 崩溃 + ETF 归因）
python3 analyze_2026_comprehensive.py

# 成本压力测试
python3 run_cost_stress_f2_cap_ma60.py
python3 run_cost_stress_f2_cap_ma60_tiers.py

# 长周期优化对比（2013-2026, 4池×3变体）
python3 run_long_period_optimization_compare.py

# 朋友策略严格复现（friend_mode 开关）
python3 replicate_friend_baseline.py

# V3/V4/V5 改进对比数据在：
# outputs/etf_loop/etf_loop_summary_ABL_V3_*.csv
# outputs/etf_loop/etf_loop_summary_ABL_V4_*.csv
# outputs/etf_loop/etf_loop_summary_V5_*.csv
# outputs/etf_loop/etf_loop_summary_FR_*.csv
```

---

## 十三、结论

1. ✅ **保留**：Premium Penalty（溢价>8% ×0.8）——唯一经 2026 验证有效的改进，长周期中性
2. ✅ **默认用**：`trading_start` 无预热机制——年度回测必须
3. ✅ **开关已就绪**：`friend_mode` 可随时启用做 T+0 信号近似
4. ❌ **移除**：Reversal Filter（-4.3%）、Vol Filter（-40%+）
5. → **建议**：评分加权仓控（信号强弱 → 权重差异）+ Score 范围过滤

---

## 十四、实验 9：仓位管理（Score-weighted / Kelly-vol / Dynamic Holdings）

### 新增参数（EngineParams）

| 参数 | 默认值 | 说明 |
|---|---|
| `use_score_weighting` | `False` | 按信号分加权替代等权 |
| `use_dynamic_holdings` | `False` | 根据信号离散度动态调整持仓数 |
| `dyn_holdings_min` | `3` | 最小持仓数 |
| `dyn_holdings_max` | `8` | 最大持仓数 |

### 逻辑说明

**Score-weighted**：
```
weight_i = score_i / sum(score_j)  for j in targets
```
信号强的 ETF 多配，信号弱的少配。在 `_apply_switch_score_margin` 之后计算（避免被等权重写覆盖）。

**Kelly-vol（Score+Vol）**：
```
weight_i = (score_i / vol_i) / sum(score_j / vol_j)
```
高信号 + 低波动 = 大仓位，凯利公式的简化近似。

**Dynamic holdings**：
```
dispersion = (score_1 - score_5) / score_1
N = max(3, min(8, 8 * (1 - dispersion)))
```
信号集中时减仓到 3 只，信号分散时加到 8 只。

### 结果

#### 长周期（2013-2026，有 warmup）

| 变体 | 年化 | Sharpe | DD | 终值 | Δ年化 |
|---|---:|---:|---:|---:|---:|
| Baseline（等权 5） | 30.54% | 1.54 | -18.45% | ¥17.8M | — |
| **Score-weighted** | **36.71%** | 1.51 | -21.27% | **¥34.1M** | **+6.2%** |
| Score+Vol (Kelly) | 33.83% | 1.55 | -18.96% | ¥25.6M | +3.3% |
| Dynamic (3-8) | 35.11% | 1.50 | -26.99% | ¥28.6M | +4.6% |

#### 2026 无预热

| 变体 | 年化 | Sharpe | DD | 终值 | Δ年化 |
|---|---:|---:|---:|---:|---:|
| Baseline | 93.34% | 3.35 | -15.61% | ¥907K | — |
| Score-weighted | 81.89% | 2.40 | -18.29% | ¥830K | -11.5% |
| Score+Vol | 69.17% | 2.21 | -18.51% | ¥767K | -24.2% |
| **Dynamic (3-8)** | **114.62%** | 3.34 | -16.86% | **¥1.03M** | **+21.3%** |

### 结论

1. **Score-weighted**：长牛市中最佳（+6.2% 年化），震荡市中反噬（-11.5%）。因为牛市中强者恒强，震荡市中"最强"正好是反转前夜。

2. **Dynamic holdings**：震荡市中最佳（+21.3%），牛市中也有正贡献（+4.6%）。缺点是 DD 放大（-27% vs -18%）。

3. **Score+Vol（凯利版）**：两边都不如纯 Score-weighted——高动量 ETF 天然波动大，你给它高分又嫌它波动大，互相矛盾。

4. **两者不能同时在所有市场有效**——这是策略的基本 trade-off：集中度提高→牛市中收益放大，震荡市中亏损放大。

### 复现命令
```bash
python3 run_position_mgmt_experiments.py
# 数据在 outputs/etf_loop/etf_loop_summary_POSMGT_*.csv
```

---

## 十五、实验 10：Wyckoff V1 区间过滤（派发区检测）

### 新增参数
| 参数 | 默认值 | 说明 |
|---|---|
| `use_wyckoff_filter` | `False` | 派发区：价格在60日区间上方80%+成交量萎缩→降分×0.6 |
| `wyckoff_range_days` | `60` | 区间天数 |
| `wyckoff_dist_threshold` | `0.8` | 派发区阈值 |
| `wyckoff_vol_penalty` | `0.6` | 降分因子 |

### 结果

| 周期 | Baseline | Wyckoff V1 | Wyckoff V1 + Premium |
|---|---:|---:|---:|
| 2026 NW | 93.34% | 93.34% | **97.52%** (+4.2%) |
| 长周期 | 30.54% | 30.54% | 30.78% (+0.24%) |

> Wyckoff V1 单独无效。与 Premium 组合后 2026 +4.2%，长周期 +0.24%。崩溃指标未改善。

---

## 十六、实验 11：Wyckoff V2 箱体突破检测（三层过滤）

### 逻辑
```
Layer 1: Wyckoff 结构过滤（箱体盘整+放量突破+MA60上方）
Layer 2: 动量排序（Sharpe/Slope/R²）
Layer 3: 风险过滤（派发区、跌破箱体、放量滞涨）
```

新增 `_detect_wyckoff_breakout()` 函数，扫描 40/60/80/100/120 日窗口，检测：
1. 箱体整理（区间幅度 < 20%）
2. 突破箱体上沿 +1%
3. 成交量放大 > 1.3x 均值
4. MA60 上方（硬性要求）

### 新增参数
| 参数 | 默认值 | 说明 |
|---|---|
| `use_wyckoff_v2` | `False` | 启用箱体突破检测 |
| `wyckoff_v2_range_threshold` | `0.20` | 箱体幅度阈值 |
| `wyckoff_v2_vol_ratio` | `1.3` | 突破量比 |
| `wyckoff_v2_require_ma60` | `True` | MA60 硬性过滤 |

### 结果（2026 无预热，全池）

| 池配置 | Baseline | Wyckoff V2 + Premium | Δ |
|---|---:|---:|---:|
| **F2_CAP_MA60** | 93.34% | **97.52%** | **+4.2%** |
| F2_STATIC | 90.92% | 91.94% | +1.0% |
| ORIG38_STATIC | 68.83% | 65.89% | -2.9% |

### 结果（长周期 2013-2026）

| 池配置 | Baseline | Wyckoff V2 + Premium | Δ |
|---|---:|---:|---:|
| F2_CAP_MA60 | 30.54% | 30.78% | +0.24% |
| F2_STATIC | 28.59% | 28.36% | -0.23% |
| ORIG38_STATIC | 22.34% | 21.71% | -0.63% |

> Wyckoff V2 单独无效（触发太稀疏），+Premium 组合仅在 F2_CAP_MA60 上有效。

---

## 十七、实验 12：Wyckoff 预筛选（Layer1→Layer2 两层架构）

### 逻辑
```
全市场 ETF（44只）
    │
    ▼
Layer 1: Wyckoff 预筛选（_wyckoff_prefilter）
  - 价格 > MA60（上行趋势）
  - 不在派发区（60日区间上方15%+量缩 → 跳过）
  - 20日收益 > -5%（排除持续下跌）
    │
    ▼ 剩余 30~50 只
Layer 2: 动量排序 → Top 5
```

### 新增参数
| 参数 | 默认值 | 说明 |
|---|---|
| `use_wyckoff_prefilter` | `False` | 启用两层架构 |

### 预筛选函数：`_wyckoff_prefilter(store, date, params)`
- 遍历全部 ETF
- 三个硬性条件全部通过才保留
- 最少保留 5 只（不足时退回全池）

### 结果（2026 无预热）

| 池配置 | Baseline | Wyckoff Prefilter | Δ | DD Δ |
|---|---:|---:|---:|---:|
| **F2_CAP_MA60** | 93.34% | **98.81%** | **+5.5%** | DD -1.0% |
| F2_STATIC | 90.92% | 76.89% | -14.0% | DD -2.3% |
| ORIG38_STATIC | 68.83% | 69.32% | +0.5% | DD -2.6% |

### 结果（长周期 2013-2026）

| 池配置 | Baseline | Wyckoff Prefilter | Δ |
|---|---:|---:|---:|
| F2_CAP_MA60 | 30.54% | 28.93% | -1.6% |
| F2_STATIC | **28.59%** | **9.91%** | **-18.7%** |
| ORIG38_STATIC | 22.34% | 10.16% | -12.2% |

### 结论
- **F2_CAP_MA60 + 2026 短周期：+5.5%，目前最优单信号改善**
- 静态池长周期：交易数暴跌 90%（6000+→682），过滤过激→收益崩盘
- 两层架构仅建议 F2_CAP_MA60 + 高波动环境启用
- 开关：`use_wyckoff_prefilter=True`

### 复现命令
```bash
# Wyckoff V1
# 数据：outputs/etf_loop/etf_loop_summary_WYCKOFF_*.csv

# Wyckoff V2 (箱体突破)
python3 run_wyckoff_v2_tests.py

# Wyckoff 预筛选（两层架构）
python3 run_wyckoff_prefilter_tests.py
```
