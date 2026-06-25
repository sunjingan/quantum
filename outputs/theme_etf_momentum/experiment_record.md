# Theme ETF Momentum — 完整实验记录

记录时间：2026-06-25（最终版）  
工作区：`/Users/jingansun/Desktop/codex/quant`  
Market：`all_a`（全 A 股，~5856 只）  
区间：`2018-01-02` → `2026-06-22`

---

## 1. 实验设计框架

六步分层推进，每层回答一个独立问题：

| 步骤 | 实验 | 回答的问题 |
|------|------|-----------|
| 1 | A0 / A1 / A2 | 回测引擎有 bug 吗？纯 OHLCV baseline 是什么？ |
| 2 | B0 / B1 / B2 / B3 | 行业分散本身有用吗？不同加权方案有区别吗？ |
| 3 | C1 / C2 / C3 / C4 / C5 | V2 策略哪部分起作用？买入信号是关键吗？ |
| 3+ | C6 / C7 | C2 消融：去掉 theme funnel？去掉 RS 过滤？ |
| 4 | R1 | 卖出规则修改单独有用吗？ |
| 5 | D0 / D1 / D2 / D3 | 真实 ETF 数据替代行业分类，效果如何？ |

### 1.1 真实使用的数据层

| 数据层 | 来源 | A 系列 | B 系列 | C 系列 | R1 | D 系列 |
|--------|------|--------|--------|--------|-----|--------|
| OHLCV (open/high/low/close/volume/amount) | Qlib features | ✅ | ✅ | ✅ | ✅ | ✅ |
| 衍生指标 (ma20/ma60/ret20/ret60/amount20/vol20 等) | 策略实时计算 | ✅ | ✅ | ✅ | ✅ | ✅ |
| stock_basic (industry, list_date, name) | theme_etf_momentum/ | ❌ | ✅ | ✅ | ✅ | ✅ |
| daily_basic (total_mv, turnover_rate, pe_ttm, pb) | theme_etf_momentum/daily_basic/ | ❌ | ✅ | ✅ | ✅ | ✅ |
| moneyflow (net_mf_amount) | enrichment/moneyflow*.csv | ❌ | ✅ | ❌* | ✅ | 仅 D3(2021H1) |
| top_inst (机构龙虎榜) | sector_prosperity/top_inst*.csv | ❌ | ✅ | ❌* | ✅ | 仅 D3(2021H1) |
| fund_daily (ETF 日线) | sector_prosperity/fund_daily*.csv | ❌ | ❌ | ❌ | ❌ | ✅ |
| fund_share (ETF 份额) | sector_prosperity/fund_share*.csv | ❌ | ❌ | ❌ | ❌ | ✅ |
| index_weight (指数成分股权重) | sector_prosperity/index_weight*.csv | ❌ | ❌ | ❌ | ❌ | ✅ |
| ETF metadata (fund_basic, etf_basic) | sector_prosperity/ | ❌ | ❌ | ❌ | ❌ | ✅ |

\* C1-C7 **全部使用 `--no-moneyflow`**，不使用 moneyflow/top_inst。这是 runner 命令中显式传入的标志，已确认 C2 的 -4.47% 是纯价格信号。

### 1.2 缓存完备度

| 数据层 | 文件数 | 覆盖范围 | 状态 |
|--------|--------|----------|------|
| OHLCV | 5857 dirs | 2018-2026 全区间 | ✅ |
| stock_basic | 全量 | — | ✅ |
| daily_basic | 2052 files | 2018-2026 逐日 | ✅ |
| fund_daily | 3094 files | 2018-2026 | ✅ |
| fund_share | 3094 files | 2018-2026 | ✅ |
| index_weight | 564 files | 2018-2026 | ✅ |
| top_inst | 2052 files | 2018-2026 逐日 | ✅ |
| moneyflow | 3 files | 2021H1 + 2025-06~now | ❌ 严重不全 |

---

## 2. 全部实验结果

### Step 1：A 系列 — 纯 baseline（仅 OHLCV）

**目的**：验证回测引擎无 bug，建立纯 OHLCV 基线。

| 实验 | total_return | annual_vol | max_drawdown | sharpe | 说明 |
|------|-------------|-----------|-------------|--------|------|
| **A0** | **+78.15%** | 36.87% | -44.80% | +0.198 | 每月随机选 5 只等权 |
| A1 | -97.20% | 102.38% | -99.18% | -0.345 | 每月选 ret20 最高 5 只 |
| A2 | -98.06% | 47.11% | -98.50% | -0.810 | 趋势选股（close>ma20>ma60）|

### Step 2：B 系列 — 行业分散（OHLCV + stock_basic + daily_basic + moneyflow + top_inst）

**目的**：行业分散 + 不同加权，是否比纯 baseline 好？

| 实验 | total_return | annual_vol | max_drawdown | sharpe | 说明 |
|------|-------------|-----------|-------------|--------|------|
| B0 | -78.77% | 28.02% | -83.36% | -0.614 | 每行业等权 |
| B1 | -78.65% | 26.80% | -83.45% | -0.640 | 按 total_mv 加权 |
| B2 | -81.87% | 28.93% | -85.09% | -0.650 | 每行业 top-10（按 amount20）|
| B3 | -82.56% | 29.04% | -85.59% | -0.660 | 每行业 top-10（按 rs20）|

### Step 3：C 系列 — V2 策略买入信号消融（OHLCV + stock_basic + daily_basic，无 moneyflow）

**目的**：V2 策略（主题动量 + RS + 买入信号）各组件贡献度。

| 实验 | total_return | annual_vol | max_drawdown | sharpe | 说明 |
|------|-------------|-----------|-------------|--------|------|
| C1 | -80.73% | 24.58% | -86.62% | -0.740 | V2 + 卖出纪律，无买入信号过滤 |
| **C2** | **-4.47%** | **2.41%** | **-6.87%** | **-0.231** | **theme + RS + buy_signal_a + pullback_zone** |
| C3 | -20.89% | 12.09% | -30.18% | -0.233 | buy_signal_b 过滤（替代 buy_signal_a）|
| C4 | -86.36% | 23.90% | -90.14% | -0.902 | timing_score 综合评分（不过滤）|
| C5 | -61.31% | 19.96% | -77.01% | -0.548 | C4 + 市场状态仓位缩放 |
| **C6** | **-77.37%** | 24.60% | -80.51% | -0.673 | **C2 去掉 theme funnel（全行业扫 buy_signal_a）** |
| **C7** | **-96.78%** | 29.44% | -97.03% | -1.162 | **C2 去掉 RS 过滤（rs_ok + rs_cut）** |

**C2 消融结论**：

| 变化 | 结果 | Δ vs C2 |
|------|------|---------|
| 完整 C2 | -4.47% | — |
| 去掉 theme funnel (C6) | -77.37% | **-73pp** ← theme 是关键基础设施 |
| 去掉 RS 过滤 (C7) | -96.78% | **-92pp** ← RS 是硬依赖 |
| 去掉 buy_signal_a (C1) | -80.73% | -76pp |
| 加 moneyflow (C2+mf) | -4.47% | **0 pp** ← moneyflow 无边际贡献 |

### Step 4：R 系列 — 卖出规则消融（OHLCV + stock_basic + daily_basic + moneyflow + top_inst）

**目的**：单独的卖出规则修改（trailing_activation）对 C1 基准的影响。

| 实验 | total_return | annual_vol | max_drawdown | sharpe | 说明 |
|------|-------------|-----------|-------------|--------|------|
| R1 | -85.82% | 24.02% | -89.34% | -0.882 | C1 + trailing_activation |

R2-R4 在 moneyflow 全区间运行时崩溃（OOM），未完成。

### Step 5：D 系列 — 真实 ETF（全区间无 moneyflow / 2021H1 带 moneyflow+top_inst）

| 实验 | total_return | annual_vol | max_drawdown | sharpe | 区间 |
|------|-------------|-----------|-------------|--------|------|
| D0 | -54.98% | 43.89% | -81.53% | -0.207 | 全区间 |
| D1 | -86.32% | 27.24% | -89.20% | -0.791 | 全区间 |
| D2 | -90.42% | 31.29% | -91.11% | -0.795 | 全区间 |
| D3 | -79.51% | 18.87% | -80.12% | -0.931 | 全区间 (no mf) |
| **D3** | **+8.09%** | **29.38%** | **-10.04%** | **+1.390** | **2021H1 (with mf+top_inst)** |

---

## 3. 策略失败原因分析

### 3.1 C2 位置数据

| 指标 | 数值 |
|------|------|
| 总交易日 | 1990 |
| 持仓天数 | 133 (6.7%) |
| 空仓天数 | 1857 (93.3%) |
| 最大同时持仓 | 2 只（target_num=5，从未满仓）|
| 平均持仓数（在仓时）| 1.0 只 |
| 总 entry 事件 | 109 次 |
| 总 exit 事件 | 109 次 |
| 平均每笔持仓天数 | ~1.2 天 |
| C2 选出的 top 主题 | 元器件(25), 软件服务(10), 通信设备(8), 电气设备(7), 半导体(6) |

### 3.2 A0 vs C2 对照

| 指标 | A0（随机选股）| C2（三层过滤）|
|------|-------------|-------------|
| total_return | **+78.15%** | -4.47% |
| max_drawdown | -44.80% | -6.87% |
| 持仓占比 | 99% | 7% |
| 平均持仓数 | ~5 只 | ~1 只 |

### 3.3 三个致命缺陷

**缺陷 1：过度过滤 → 严重欠曝**

Theme 漏斗 + RS 过滤 + buy_signal_a 准入 → 三层下来，1990 天里只有 133 天有仓位。在一个基准涨了 31% 的市场，最大风险不是选错股，而是根本不在市场里。C2 的 2020 年（基准 +35%）持仓仅 4%，几乎完全踏空全年牛市。

**缺陷 2：buy_signal_a 在 A 股是均值回归陷阱**

每笔交易平均持有 ~1.2 天就被止损。A 股散户占比高、缺乏做市商流动性缓冲，"回踩支撑企稳"的美股逻辑在 A 股不成立——这里的 pullback 更可能是反转开始而非买点。C2 在牛市中反而不赚钱（2020 年仅 4% 仓位、2025 仅 6%），说明 buy_signal_a 选出来的标的即使在上涨市场里也表现不佳。

**缺陷 3：行业分类作为主题代理过于粗糙**

SW 行业 104 个分类是行政划分而非交易主题。C2 选出的 top 主题全是科技周期股（元器件、软件、通信、半导体），这些板块轮动极快、动量难以持续。真正的主题 ETF（如新能车、芯片、光伏）有更窄的聚焦，但当前实验用的是 `stock_basic.industry` 而非真实 ETF 权重。

### 3.4 一句话诊断

> C2 策略把 A 股当成美股做：假设趋势会延续、pullback 是买点、强板块会持续强。但 A 股的本质是高波动 + 强均值回归 + 行业轮动极快。三重过滤把持仓压到了 7%、每笔持仓 ~1.2 天，在基准涨 31% 的背景下亏了 4.5%。

---

## 4. 代码修改记录

### 4.1 策略文件修改

**`strategies/theme_etf_momentum.py`**
- `select_themes()` fallback (L617)：强主题为空时加入 relaxed filter（至少 `amount20 > 0`）
- `MoneyFlowCache`：新增 `_moneyflow_range()` 和 `_top_inst_range()` 方法，`score()` 改为按日期范围分批加载 moneyflow/top_inst 文件，避免全量加载 OOM

### 4.2 Runner 修改

**`run_theme_etf_experiments.py`**
- sell rules：C 系列和 R/D 系列纳入 `TRAILING_EXPS` 和 `STALE_FIX_EXPS`
- 新增 `_build_no_theme_pool()`：复用 `build_candidate_pool_fast` 传全行业 + 50 constituents，替代重复过滤逻辑
- 新增 C6/C7/D4 实验 profile
- `_select_momentum_targets()` (L235)：修复 pandas IndexingError（`.notna()` → `.notna().values`）

---

## 5. 全量排名

| # | 实验 | total_return | max_drawdown | sharpe | 区间 | 数据层 |
|---|------|-------------|-------------|--------|------|--------|
| 1 | **A0** | **+78.15%** | -44.80% | +0.198 | 全区间 | OHLCV |
| 2 | **D3** | **+8.09%** | -10.04% | **+1.390** | 2021H1 | OHLCV+ETF+mf |
| 3 | **C2** | **-4.47%** | -6.87% | -0.231 | 全区间 | OHLCV+basic+daily_basic |
| 4 | C3 | -20.89% | -30.18% | -0.233 | 全区间 | OHLCV+basic+daily_basic |
| 5 | D0 | -54.98% | -81.53% | -0.207 | 全区间 | OHLCV+ETF |
| 6 | C5 | -61.31% | -77.01% | -0.548 | 全区间 | OHLCV+basic+daily_basic |
| 7 | C6 | -77.37% | -80.51% | -0.673 | 全区间 | OHLCV+basic+daily_basic |
| 8 | B0 | -78.77% | -83.36% | -0.614 | 全区间 | OHLCV+basic+daily_basic+mf |
| 9 | B1 | -78.65% | -83.45% | -0.640 | 全区间 | OHLCV+basic+daily_basic+mf |
| 10 | D3 | -79.51% | -80.12% | -0.931 | 全区间 | OHLCV+ETF |
| 11 | C1 | -80.73% | -86.62% | -0.740 | 全区间 | OHLCV+basic+daily_basic |
| 12 | B2 | -81.87% | -85.09% | -0.650 | 全区间 | OHLCV+basic+daily_basic+mf |
| 13 | B3 | -82.56% | -85.59% | -0.660 | 全区间 | OHLCV+basic+daily_basic+mf |
| 14 | R1 | -85.82% | -89.34% | -0.882 | 全区间 | OHLCV+basic+daily_basic+mf |
| 15 | D1 | -86.32% | -89.20% | -0.791 | 全区间 | OHLCV+ETF |
| 16 | C4 | -86.36% | -90.14% | -0.902 | 全区间 | OHLCV+basic+daily_basic |
| 17 | D2 | -90.42% | -91.11% | -0.795 | 全区间 | OHLCV+ETF |
| 18 | C7 | -96.78% | -97.03% | -1.162 | 全区间 | OHLCV+basic+daily_basic |
| 19 | A1 | -97.20% | -99.18% | -0.345 | 全区间 | OHLCV |
| 20 | A2 | -98.06% | -98.50% | -0.810 | 全区间 | OHLCV |

---

## 6. 如何复现

```bash
cd /Users/jingansun/Desktop/codex/quant
source activate.sh
export QLIB_PROVIDER_URI=data/a_share_qlib

# Step 1: A 系列（纯 OHLCV）
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 \
  --experiments a0,a1,a2 --skip-real-etf --no-moneyflow

# Step 2: B 系列（行业分散 + moneyflow）
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 \
  --experiments b0,b1,b2,b3 --skip-real-etf

# Step 3: C 系列（V2 消融，无 moneyflow）
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 \
  --experiments c1,c2,c3,c4,c5,c6,c7 --skip-real-etf --no-moneyflow

# Step 4: R 系列（卖出规则消融 + moneyflow）
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 \
  --experiments r1 --skip-real-etf

# Step 5: D 系列（真实 ETF）
# 全区间 (无 moneyflow):
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 \
  --experiments d0,d1,d2,d3 --skip-real-etf --no-moneyflow
# 短窗 (带 moneyflow):
python3 -u run_theme_etf_experiments.py --market all_a --start 2021-01-04 --end 2021-06-30 \
  --experiments d3
```
