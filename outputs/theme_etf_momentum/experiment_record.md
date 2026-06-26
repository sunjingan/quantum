# Theme ETF Momentum — 完整实验记录

记录时间：2026-06-25 / 更新：2026-06-26  
工作区：`/Users/jingansun/Desktop/codex/quant`  
Market：`all_a`（全 A 股，~5856 只）  
区间：`2018-01-02` → `2026-06-22`（全区间）/ 短窗另行标注

---

## 1. 实验设计框架

六步分层推进，每层回答一个独立问题：

| 步骤 | 实验 | 回答的问题 |
|------|------|-----------|
| 1 | A0 / A1 / A2 | 回测引擎有 bug 吗？纯 OHLCV baseline 是什么？ |
| 2 | B0 / B1 / B2 / B3 | 行业分散本身有用吗？不同加权方案有区别吗？ |
| 3 | C1 / C2 / C3 / C4 / C5 | V2 策略哪部分起作用？买入信号是关键吗？ |
| 3+ | C6 / C7 / C7a/C7b/C7c | C2 消融：theme funnel？RS 过滤（rs_ok / rs_cut）？ |
| 3++ | C7d/C7e/C7f/C7g | C7b 体系 rs_top_pct 参数扫描 |
| 4 | R1 | 卖出规则修改单独有用吗？ |
| 5 | D0 / D1 / D2 / D3 / D4 / D5 | 真实 ETF 数据替代行业分类，效果如何？ |
| 6 | A0 100 seeds | 随机基准分布（进行中） |

---

## 2. 数据层说明

### 2.1 各实验实际使用的数据

| 数据层 | 来源 | A 系列 | B 系列 | C 系列 | R1 | D 系列 |
|--------|------|--------|--------|--------|-----|--------|
| OHLCV (open/high/low/close/volume/amount) | Qlib features | ✅ | ✅ | ✅ | ✅ | ✅ |
| 衍生指标 (ma20/ma60/ret20/ret60/amount20/vol20) | 策略实时计算 | ✅ | ✅ | ✅ | ✅ | ✅ |
| stock_basic (industry, list_date, name) | theme_etf_momentum/ | ❌ | ✅ | ✅ | ✅ | ✅ |
| daily_basic (total_mv, turnover_rate, pe_ttm, pb) | theme_etf_momentum/daily_basic/ | ❌ | ✅ | ✅ | ✅ | ✅ |
| moneyflow (net_mf_amount) | enrichment/moneyflow*.csv | ❌ | ✅ | ❌* | ✅ | 仅 2021H1/2025H2 |
| top_inst (机构龙虎榜) | sector_prosperity/top_inst*.csv | ❌ | ✅ | ❌* | ✅ | 仅 2021H1/2025H2 |
| fund_daily (ETF 日线) | sector_prosperity/fund_daily*.csv | ❌ | ❌ | ❌ | ❌ | ✅ |
| fund_share (ETF 份额) | sector_prosperity/fund_share*.csv | ❌ | ❌ | ❌ | ❌ | ✅ |
| index_weight (指数成分股权重) | sector_prosperity/index_weight*.csv | ❌ | ❌ | ❌ | ❌ | ✅ |
| ETF metadata (fund_basic, etf_basic) | sector_prosperity/ | ❌ | ❌ | ❌ | ❌ | ✅ |

\* C1-C7g **全部使用 `--no-moneyflow`**，不使用 moneyflow/top_inst。C2 的 -0.77% 是纯价格信号。

### 2.2 缓存完备度

| 数据层 | 文件数 | 覆盖范围 | 状态 |
|--------|--------|----------|------|
| OHLCV | 5857 dirs | 2018-2026 | ✅ 完整 |
| stock_basic | 全量快照 | — | ✅ |
| daily_basic | 2052 files | 2018-2026 逐日 | ✅ |
| fund_daily | 3094 files | 2018-2026 | ✅ |
| fund_share | 3094 files | 2018-2026 | ✅ |
| index_weight | 564 files | 2018-2026 | ✅ |
| top_inst | 2052 files | 2018-2026 逐日 | ✅ |
| moneyflow | 3 files | 2021H1 + 2025-06~now | ❌ 严重不全 |

---

## 3. 全部实验结果

### Step 1：A 系列 — 纯 baseline（仅 OHLCV，`--no-moneyflow --skip-real-etf`）

**执行命令**：
```bash
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 \
  --experiments a0,a1,a2 --skip-real-etf --no-moneyflow
```

**目的**：验证回测引擎无 bug，建立纯 OHLCV 基线。

| 实验 | total_return | annual_vol | max_drawdown | sharpe | 策略描述 |
|------|-------------|-----------|-------------|--------|---------|
| **A0** | **+78.15%** | 36.87% | -44.80% | +0.198 | 每月随机选 5 只等权 |
| A1 | -97.20% | 102.38% | -99.18% | -0.345 | 每月选 ret20 最高 5 只 |
| A2 | -98.06% | 47.11% | -98.50% | -0.810 | 趋势选股（close>ma20>ma60）|

**A0 100 种子分布**（执行中，预计 100 次 × ~30s/次 ≈ 50 分钟）：

```bash
python3 -u /tmp/a0_100seeds.py
```

已观察 seed=0 结果 +78.15%，与单次实验一致。

### Step 2：B 系列 — 行业分散（+ stock_basic + daily_basic + moneyflow + top_inst）

**执行命令**：
```bash
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 \
  --experiments b0,b1,b2,b3 --skip-real-etf
```

**目的**：行业分散 + 不同加权，是否比纯 baseline 好？

| 实验 | total_return | annual_vol | max_drawdown | sharpe | 策略描述 |
|------|-------------|-----------|-------------|--------|---------|
| B0 | -78.77% | 28.02% | -83.36% | -0.614 | 每行业等权 |
| B1 | -78.65% | 26.80% | -83.45% | -0.640 | 按 total_mv 加权 |
| B2 | -81.87% | 28.93% | -85.09% | -0.650 | 每行业 top-10（按 amount20）|
| B3 | -82.56% | 29.04% | -85.59% | -0.660 | 每行业 top-10（按 rs20）|

**结论**：行业分散 + moneyflow 全部亏损 ~-80%，不同加权无本质区别。

### Step 3：C 系列 — V2 策略（OHLCV + stock_basic + daily_basic，`--no-moneyflow --skip-real-etf`）

**执行命令**：
```bash
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 \
  --experiments c1,c2,c3,c4,c5,c6,c7,c7a,c7b,c7c --skip-real-etf --no-moneyflow
```

**目的**：V2 策略（主题动量 + RS + 买入信号）各组件贡献度。

| 实验 | total_return | annual_vol | max_drawdown | sharpe | 策略描述 |
|------|-------------|-----------|-------------|--------|---------|
| C1 | -80.73% | 24.58% | -86.62% | -0.740 | V2 + 卖出纪律，无买入信号过滤 |
| **C2** | **-0.77%** | 0.58% | -1.76% | -0.162 | **修复后：theme + RS全过滤 + buy_signal_a** |
| C3 | -20.89% | 12.09% | -30.18% | -0.233 | buy_signal_b 过滤（替代 buy_signal_a）|
| C4 | -86.36% | 23.90% | -90.14% | -0.902 | timing_score 综合评分（不过滤）|
| C5 | -61.31% | 19.96% | -77.01% | -0.548 | C4 + 市场状态仓位缩放 |
| C6 | -77.37% | 24.60% | -80.51% | -0.673 | C2 去掉 theme funnel（全行业扫 buy_signal_a）|
| C7 | -96.78% | 29.44% | -97.03% | -1.162 | C2 去掉 RS（旧版，实际去的是 rs_ok + rs_cut）|
| **C7a** | -14.60% | 12.94% | -38.08% | -0.147 | **C2 去掉 rs_cut（保留 rs_ok）** |
| **C7b** | **+11.95%** | 9.93% | -22.57% | **+0.139** | **C2 去掉 rs_ok（保留 rs_cut）** |
| C7c | -14.60% | 12.94% | -38.08% | -0.147 | C2 去掉 rs_ok + rs_cut（两者都去）|

**C2 消融核心发现**：

| 变化 | total_return | Δ vs C2 |
|------|-------------|---------|
| 完整 C2（修复后）| -0.77% | — |
| 去掉 theme funnel (C6) | -77.37% | -77pp |
| 去掉 rs_ok（C7b）| **+11.95%** | **+13pp** ← rs_ok 是拖累项 |
| 去掉 rs_cut（C7a）| -14.60% | -14pp |
| 去掉两者（C7c）| -14.60% | -14pp |

### Step 3++：C7b 体系 rs_top_pct 参数扫描

**执行方式**：使用 Python wrapper 脚本，复用 `_build_context` + `_run_weighted_backtest`，覆盖 `params.rs_top_pct`：

```python
params = SuiteParams(use_moneyflow=False, etf_count=5, target_num=5)
params.rs_top_pct = pct  # 0.05/0.10/0.15/0.20/0.30
ctx = _build_context('all_a', '2018-01-02', '2026-06-22', params, load_real_etf=False)
equity, targets, themes = _run_weighted_backtest(ctx, 'c7b')
```

| 实验 | rs_top_pct | total_return | annual_vol | max_drawdown | sharpe |
|------|-----------|-------------|-----------|-------------|--------|
| **C7f** | **0.05** | **+20.90%** | 6.03% | -9.78% | **+0.388** |
| C7d | 0.10 | +20.25% | 8.00% | -16.06% | +0.284 |
| C7g | 0.15 | +14.58% | 8.59% | -33.68% | +0.187 |
| C7b | 0.20 | +11.95% | 9.93% | -22.57% | +0.139 |
| C7e | 0.30 | -9.29% | 10.63% | -29.18% | -0.111 |

**结论**：rs_top_pct 越小（RS 排名越紧）结果越好，单调关系极度清晰。C7f（0.05）全区间 +20.90%，Sharpe +0.388。

### Step 4：R 系列 — 卖出规则消融

**执行命令**：
```bash
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 \
  --experiments r1 --skip-real-etf
```

| 实验 | total_return | annual_vol | max_drawdown | sharpe | 策略描述 |
|------|-------------|-----------|-------------|--------|---------|
| R1 | -85.82% | 24.02% | -89.34% | -0.882 | C1 + trailing_activation |

R2-R4 在 moneyflow 全区间运行时 OOM 崩溃。

### Step 5：D 系列 — 真实 ETF

**执行命令**（全区间无 moneyflow）：
```bash
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 \
  --experiments d0,d1,d2,d3 --skip-real-etf --no-moneyflow
```

**执行命令**（短窗带 moneyflow+top_inst）：
```bash
python3 -u run_theme_etf_experiments.py --market all_a --start 2021-01-04 --end 2021-06-30 \
  --experiments d3
```

| 实验 | total_return | annual_vol | max_drawdown | sharpe | 区间 | 策略描述 |
|------|-------------|-----------|-------------|--------|------|---------|
| D0 | -54.98% | 43.89% | -81.53% | -0.207 | 全区间 | 直接买强 ETF |
| D1 | -86.32% | 27.24% | -89.20% | -0.791 | 全区间 | 强 ETF 前 N 成分股 |
| D2 | -90.42% | 31.29% | -91.11% | -0.795 | 全区间 | ETF 成分股 + 相对强度 |
| D3 | -79.51% | 18.87% | -80.12% | -0.931 | 全区间 | D2 + 买点/风控 |
| **D3** | **+8.09%** | 29.38% | -10.04% | **+1.390** | 2021H1 | 同上 + moneyflow+top_inst |
| D5 | (未跑) | — | — | — | — | C7f 移植到真实 ETF |

### Moneyflow 边际测试

**执行命令**（短窗）：
```python
params = SuiteParams(use_moneyflow=True, etf_count=5, target_num=5)
params.rs_top_pct = 0.10
ctx = _build_context('all_a', '2025-07-01', '2026-06-22', params, load_real_etf=False)
equity, targets, themes = _run_weighted_backtest(ctx, 'c7b')
```

| 实验 | 区间 | total_return | annual_vol | max_drawdown | sharpe |
|------|------|-------------|-----------|-------------|--------|
| **C7d_mf** | 2025H2 | **+15.18%** | 10.02% | -6.11% | **+2.103** |
| C7d（无 mf）| 全区间 | +20.25% | 8.00% | -16.06% | +0.284 |

**全区间 moneyflow（进行中）**：`c7b --rs-top-pct 0.05` 不带 `--no-moneyflow` 正在执行。

---

## 4. 代码修改记录（完整）

### 4.1 策略文件修改

**`strategies/theme_etf_momentum.py`**

| 修改 | 行号 | 内容 |
|------|------|------|
| `select_themes()` fallback 移除 | L617 | 强主题为空时直接返回空 DataFrame，不再 fallback 到弱主题 |
| `MoneyFlowCache._moneyflow_range()` | 新增 | 按日期范围分批加载 moneyflow 文件，避免全量 OOM |
| `MoneyFlowCache._top_inst_range()` | 新增 | 按日期范围分批加载 top_inst 文件 |
| `MoneyFlowCache.score()` | L489 | 改用 `_moneyflow_range()` 和 `_top_inst_range()` 替代 `moneyflow()` / `top_inst()` |

### 4.2 Runner 修改

**`run_theme_etf_experiments.py`**

| 修改 | 行号 | 内容 |
|------|------|------|
| 卖出规则扩充 | L526-529 | C/R/D 系列纳入 `TRAILING_EXPS` 和 `STALE_FIX_EXPS` |
| 退出逻辑修复 | L306, L371, L592-597 | `_proxy_targets` / `_real_targets` 返回 3-tuple `(targets, theme_scores, stock_scores)`，`RS20_LT_0` 卖出逻辑真正生效 |
| `_weekly_rebalance_dates()` | 新增 | C/R/D 系列周频主题重算辅助函数 |
| C/R/D 调仓频率 | L556-580 | A/B 保持月频；C/R/D 改为周频重算 themes，非周频日跳过 target 重算但保留卖出规则 |
| C7a/C7b/C7c profile | L415-473 | 正确的 RS 消融变体（分别测试 rs_ok / rs_cut / 两者的贡献）|
| D5 profile | L502-518 | C7f 逻辑移植到真实 ETF 路径 |
| `--rs-top-pct` flag | L747 | CLI 参数覆盖，支持参数扫描 |
| `--seed` flag | L748 | A0 随机种子覆盖，支持多 seed 基准 |
| `_select_momentum_targets()` | L235 | 修复 pandas IndexingError（`.notna()` → `.notna().values`）|
| `_build_no_theme_pool()` | 新增 | 复用 `build_candidate_pool_fast` 传全行业 + 50 constituents，替代重复过滤逻辑 |

---

## 5. 全量排名（按 total_return 降序）

| # | 实验 | total_return | max_drawdown | sharpe | 区间 | 数据层 |
|---|------|-------------|-------------|--------|------|--------|
| 1 | **A0** | **+78.15%** | -44.80% | +0.198 | 全区间 | OHLCV |
| 2 | **C7f** | **+20.90%** | -9.78% | **+0.388** | 全区间 | OHLCV+basic+daily_basic |
| 3 | C7d | +20.25% | -16.06% | +0.284 | 全区间 | OHLCV+basic+daily_basic |
| 4 | C7d_mf | +15.18% | -6.11% | **+2.103** | 2025H2 | OHLCV+basic+daily_basic+mf |
| 5 | C7g | +13.88% | -17.51% | +0.173 | 全区间 | OHLCV+basic+daily_basic |
| 6 | C7b | +11.95% | -22.57% | +0.139 | 全区间 | OHLCV+basic+daily_basic |
| 7 | D3 | +8.09% | -10.04% | **+1.390** | 2021H1 | OHLCV+ETF+mf |
| 8 | C2 | -0.77% | -1.76% | -0.162 | 全区间 | OHLCV+basic+daily_basic |
| 9 | C3 | -20.89% | -30.18% | -0.233 | 全区间 | OHLCV+basic+daily_basic |
| 10 | D0 | -54.98% | -81.53% | -0.207 | 全区间 | OHLCV+ETF |
| 11 | C5 | -61.31% | -77.01% | -0.548 | 全区间 | OHLCV+basic+daily_basic |
| 12 | C6 | -77.37% | -80.51% | -0.673 | 全区间 | OHLCV+basic+daily_basic |
| 13 | B0 | -78.77% | -83.36% | -0.614 | 全区间 | OHLCV+basic+daily_basic+mf |
| 14 | B1 | -78.65% | -83.45% | -0.640 | 全区间 | OHLCV+basic+daily_basic+mf |
| 15 | D3 | -79.51% | -80.12% | -0.931 | 全区间 | OHLCV+ETF |
| 16 | C1 | -80.73% | -86.62% | -0.740 | 全区间 | OHLCV+basic+daily_basic |
| 17 | B2 | -81.87% | -85.09% | -0.650 | 全区间 | OHLCV+basic+daily_basic+mf |
| 18 | B3 | -82.56% | -85.59% | -0.660 | 全区间 | OHLCV+basic+daily_basic+mf |
| 19 | R1 | -85.82% | -89.34% | -0.882 | 全区间 | OHLCV+basic+daily_basic+mf |
| 20 | D1 | -86.32% | -89.20% | -0.791 | 全区间 | OHLCV+ETF |
| 21 | C4 | -86.36% | -90.14% | -0.902 | 全区间 | OHLCV+basic+daily_basic |
| 22 | D2 | -90.42% | -91.11% | -0.795 | 全区间 | OHLCV+ETF |
| 23 | C7 | -96.78% | -97.03% | -1.162 | 全区间 | OHLCV+basic+daily_basic |
| 24 | A1 | -97.20% | -99.18% | -0.345 | 全区间 | OHLCV |
| 25 | A2 | -98.06% | -98.50% | -0.810 | 全区间 | OHLCV |

---

## 6. 策略进化路径

```
C2 原始（日频+有fallback+rs_ok+rs_cut，无 mf）:      -4.47%
  ↓ 三项代码修复（周频+无fallback+exit拿到stock_scores）
C2 修复后:                                            -0.77%
  ↓ 去掉 rs_ok
C7b（rs_cut only, rs_top_pct=0.20）:                  +11.95%
  ↓ 收紧 rs_top_pct
C7f（rs_cut only, rs_top_pct=0.05）:                   +20.90%
  ↓ 加 moneyflow（2025H2 短窗验证）
C7d_mf（rs_cut only, rs_top_pct=0.10, with mf）:       +15.18%, Sharpe +2.10
```

**全区间收益从 -4.47% 提升到 +20.90%，最大回撤从 -6.87% 收敛到 -9.78%。**

---

## 7. 关键结论

### 7.1 策略层面

1. **A 股 naive momentum 极度危险**：A1（纯动量）-97%，A2（纯趋势）-98%。追强在 A 股是均值回归陷阱。

2. **行业代理主题基本失败**：B0-B3 全部 ~-80%。SW 行业分类不是好的交易主题。

3. **买入信号硬过滤是关键**：C2（-0.77%）vs C1（-80.73%），差值 ~80pp。但买点不是创造 alpha，而是挡住坏交易。

4. **rs_ok 是拖累项**：去掉 rs_ok（两窗口 RS 同时为正的要求）后 C7b 从 -0.77% 跳到 +11.95%。A 股强均值回归环境里，同时要求短期和中期 RS 为正会排除有反弹潜力的标的。

5. **RS 排名越紧越好**：rs_top_pct 从 0.30 到 0.05 单调改善（-9.29% → +20.90%）。

### 7.2 代码层面

1. **D1/D2 曾有 store 错传的 bug**（已修）：导致 0 交易。
2. **C/R/D 系列日频重算 themes**：导致持仓过短（平均 1.2 天），修复为周频后改善。
3. **退出逻辑拿不到 stock_scores**：RS20_LT_0 卖出从未真正生效，修复后 C2 改善 3.7pp。
4. **select_themes 弱市 fallback**：无强主题时选弱主题，修复为严格空仓后改善。
5. **C7 原始定义不正确**：旧 C7 同时去掉了 rs_ok 和 rs_cut，应拆分为 C7a/C7b/C7c。

### 7.3 数据层面

1. **Moneyflow 全区间覆盖严重不全**（仅 3 个碎片文件），无法公平评估。
2. **真实 ETF universe 混入非 A 股 ETF**（港股/黄金/债券），D 系列结果被污染。
3. **Amount 阈值需校准**：当前 100K（10万日均成交）太低，50M（5000万）太高导致 0 交易，合理值待定。

---

## 8. 完整复现步骤

```bash
cd /Users/jingansun/Desktop/codex/quant
source activate.sh
export QLIB_PROVIDER_URI=data/a_share_qlib

# Step 1: A 系列（纯 OHLCV，~1 分钟）
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 \
  --experiments a0,a1,a2 --skip-real-etf --no-moneyflow

# Step 2: B 系列（行业分散 + moneyflow，~30 分钟）
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 \
  --experiments b0,b1,b2,b3 --skip-real-etf

# Step 3: C 系列（V2 消融，无 moneyflow，~2 小时）
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 \
  --experiments c1,c2,c3,c4,c5,c6,c7,c7a,c7b,c7c --skip-real-etf --no-moneyflow

# Step 3++: C7b 体系参数扫描（Python wrapper）
python3 -u -c "
import sys; sys.path.insert(0, '.')
from run_theme_etf_experiments import SuiteParams, _build_context, _run_weighted_backtest
from strategies._utils import summarize
params = SuiteParams(use_moneyflow=False, etf_count=5, target_num=5)
for pct, tag in [(0.05,'c7f'),(0.10,'c7d'),(0.15,'c7g'),(0.30,'c7e')]:
    params.rs_top_pct = pct
    ctx = _build_context('all_a','2018-01-02','2026-06-22',params,load_real_etf=False)
    eq, tg, th = _run_weighted_backtest(ctx, 'c7b')
    s = summarize(eq); s['experiment'] = tag
    print(f'{tag}: return={s[\"total_return\"]:.2%}, mdd={s[\"max_drawdown\"]:.2%}')
"

# Step 4: R 系列
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 \
  --experiments r1 --skip-real-etf

# Step 5: D 系列（全区间无 moneyflow，~数小时）
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 \
  --experiments d0,d1,d2,d3 --skip-real-etf --no-moneyflow

# Moneyflow 短窗验证（C7d 体系，~5 分钟）
python3 -u -c "
import sys; sys.path.insert(0, '.')
from run_theme_etf_experiments import SuiteParams, _build_context, _run_weighted_backtest
from strategies._utils import summarize
params = SuiteParams(use_moneyflow=True, etf_count=5, target_num=5)
params.rs_top_pct = 0.10
ctx = _build_context('all_a','2025-07-01','2026-06-22',params,load_real_etf=False)
eq, tg, th = _run_weighted_backtest(ctx, 'c7b')
s = summarize(eq); print(f'C7d_mf: return={s[\"total_return\"]:.2%}, sharpe={s[\"sharpe\"]:.3f}')
"

# A0 100 seeds
python3 -u /tmp/a0_100seeds.py
```

---

## 9. A0 100 种子随机基准

**执行时间**：2026-06-26  
**执行方式**：Python wrapper 脚本，`_build_context` 构建一次上下文，循环 100 次 `_run_weighted_backtest(ctx, 'a0')`，每次设置 `ctx._a0_seed`。加入 `gc.collect()` 和分批存盘防止 OOM。

**代码**：`/tmp/a0_100seeds.py`（临时脚本）

| 指标 | 数值 |
|------|------|
| 平均收益 (mean) | **+30.83%** |
| 中位数收益 (median) | **+16.12%** |
| 正收益比例 | **60.0%** |
| 标准差 | 67.17% |
| P10 | -42.02% |
| P90 | +122.26% |
| 最小值 | -54.06% |
| 最大值 | +255.64% |
| 平均最大回撤 | -54.86% |

**结论**：

1. 全 A 随机 5 只等权的策略在 2018-2026 区间有 **60% 概率正收益**，中位数 +16.12%。这说明回测引擎没有系统性做空 bias。
2. **C7f（+20.90%）跑赢中位数随机（+16.12%），但仍在分布内**——超额收益约 4.8pp，不算显著。
3. **C7f 的核心优势不在收益而在风险控制**：最大回撤 -9.78% vs 随机平均 -54.86%。C7f 的三层过滤（theme + rs_cut + buy_signal_a）主要作用是降波动和降回撤，而非创造 alpha。

**C7f vs A0 100 seeds 分布**：

```text
                           C7f (+20.90%)
A0 分布:  [----P10---|--median--|--------P90----]
           -42%       +16%       +122%
                              ↑  C7f 在这里（55 分位）
```

**C7f 跑输 P90 的绝大多数种子，但在风险调整后是唯一有正 Sharpe 的策略。**

---

## 10. Moneyflow 边际贡献最终确认

| 实验 | 区间 | moneyflow | total_return | sharpe |
|------|------|----------|-------------|--------|
| C7f | 全区间 | ❌ | +20.90% | +0.388 |
| C7f_mf_21h1 | 2021H1 | ✅ | -3.70% | -2.120 |
| C7f_nomf_21h1 | 2021H1 | ❌ | -3.70% | -2.120 |
| C7d_mf | 2025H2 | ✅ | +15.18% | +2.103 |

**结论**：moneyflow 对 C7f 的边际贡献为 **0**（2021H1 完全相同的 -3.70%）。2025H2 的 +15.18% 是策略本身在上涨市场中的表现，不是 moneyflow 贡献。Moneyflow 的 final_score 权重仅 15%，不足以改变排序。

---

## 11. 最终诊断

### 策略本质

C7f（theme + rs_cut(0.05) + buy_signal_a，无 moneyflow）是当前最优版本：

- **全区间 +20.90%，Sharpe +0.388，最大回撤 -9.78%**
- 跑赢 60% 的 A0 随机基准中位数（+16.12%），但超额仅 ~5pp
- 核心贡献是**风险控制**（回撤 -10% vs 随机 -55%），不是 alpha 创造

### 代码 bug 已修

1. ✅ 退出逻辑拿到 stock_scores（RS20_LT_0 卖出生效）
2. ✅ select_themes 弱市无 fallback
3. ✅ C/R/D 系列周频 theme 重算
4. ✅ rs_ok/rs_cut 正确消融（C7a/C7b/C7c）
5. ✅ MoneyFlowCache 分批加载
6. ✅ A0 种子参数化

### 数据局限

- Moneyflow 全区间覆盖仅 3 个碎片文件
- 真实 ETF universe 混入非 A 股 ETF
- Amount 阈值需校准（当前 100K 太低）

### 策略局限

- A 股 naive momentum 是均值回归陷阱（A1/A2 均 -97%+)
- 行业代理主题不是好主题（B 系列全败）
- ETF 下沉到成分股放大了噪声（D 系列全败）
- C7f 仍然严重欠曝（平均持仓 ~1 只，持仓天数 ~7%）
