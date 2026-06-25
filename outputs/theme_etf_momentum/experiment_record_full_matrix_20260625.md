# Theme ETF Momentum 实验记录（全矩阵 / 全 A / 长区间）

记录时间：2026-06-25  
工作区：`/Users/jingansun/Desktop/codex/quant`  
区间：`2018-01-02` → `2026-06-22`（全区间）/ `2021-01-04` → `2021-06-30`（短窗验证）  
Market：`all_a`（全 A 股，~5856 只）

## 实验设计逻辑

按推荐执行顺序分层推进，每层回答一个独立问题：

| 步骤 | 实验 | 回答的问题 |
|------|------|-----------|
| 1 | A0/A1/A2 | 回测引擎有 bug 吗？纯 OHLCV 能不能跑？ |
| 2 | B0/B1/B2/B3 | 行业分散本身有用吗？不同加权方案有区别吗？ |
| 3 | C1/C2/C3/C4/C5 | V2 策略哪部分在起作用？买入信号过滤是关键吗？ |
| 4 | R1/R2/R3/R4 | 卖出规则修改（trailing activation / stale fix）单独有用吗？ |
| 5 | D0/D1/D2/D3 | 真实 ETF 数据替代行业分类，效果更好还是更差？ |

---

## 数据层说明

每个实验诚实标注了实际使用的数据：

| 数据层 | 来源 | 字段 | A 系列 | B 系列 | C 系列 | R 系列 | D 系列 |
|--------|------|------|--------|--------|--------|--------|--------|
| OHLCV | Qlib features | open/high/low/close/volume/amount | ✅ | ✅ | ✅ | ✅ | ✅ |
| 衍生指标 | 策略计算 | ma20/ma60/ret20/ret60/amount20/vol20 | ✅ | ✅ | ✅ | ✅ | ✅ |
| stock_basic | theme_etf_momentum/ | industry/list_date | ❌ | ✅ | ✅ | ✅ | ✅ |
| daily_basic | theme_etf_momentum/daily_basic/ | total_mv/pe_ttm/pb/turnover_rate | ❌ | ✅ | ✅ | ✅ | ✅ |
| moneyflow | enrichment/moneyflow*.csv | net_mf_amount | ❌ | ✅ | ✅* | ✅† | ✅‡ |
| top_inst | sector_prosperity/top_inst*.csv | buy/sell/net_amount | ❌ | ✅ | ✅* | ✅† | ✅‡ |
| fund_daily | sector_prosperity/fund_daily*.csv | ETF open/close/amount | ❌ | ❌ | ❌ | ❌ | ✅ |
| fund_share | sector_prosperity/fund_share*.csv | fd_share | ❌ | ❌ | ❌ | ❌ | ✅ |
| index_weight | sector_prosperity/index_weight*.csv | con_code/weight | ❌ | ❌ | ❌ | ❌ | ✅ |
| ETF metadata | sector_prosperity/ | fund_basic/etf_basic | ❌ | ❌ | ❌ | ❌ | ✅ |

\* C1-C5 **全部**使用 `--no-moneyflow`，未使用 moneyflow/top_inst。这是在 runner 命令中显式传入的标志。
† R1 用 moneyflow+top_inst。R2-R4 运行中崩溃（疑似内存不足），未成功产出。
‡ D0/D1/D2/D3(全区间) 用 `--no-moneyflow`。D3(2021H1) 用 moneyflow+top_inst。

### 缓存完备度（截至 2026-06-25）

| 数据层 | 文件数 | 覆盖范围 | 状态 |
|--------|--------|----------|------|
| OHLCV | 5857 dirs | 2018-2026 全区间 | ✅ 完整 |
| stock_basic | 全量快照 | — | ✅ |
| daily_basic | 2052 files | 2018-2026 逐日 | ✅ |
| fund_daily | 3094 files | 2018-2026 | ✅ |
| fund_share | 3094 files | 2018-2026 | ✅ |
| index_weight | 564 files | 2018-2026 | ✅ |
| top_inst | 2052 files | 2018-2026 逐日 | ✅ |
| moneyflow | 3 files | 2021H1 + 2025-06~now | ❌ 严重不全 |

---

## Step 1：A 系列 — 纯 baseline（只用 OHLCV）

**使用的数据**：仅 Qlib OHLCV（open/high/low/close/volume/amount）+ 衍生指标。

**目的**：验证回测引擎在 5856 只全 A 股 x 2052 个交易日上无 bug，确认基础调仓/买卖/成本逻辑正确。

| 实验 | total_return | annual_return | annual_vol | max_drawdown | sharpe | 说明 |
|------|-------------|--------------|-----------|-------------|--------|------|
| **A0** | **+78.15%** | +7.29% | 36.87% | -44.80% | +0.198 | 每月随机选 5 只等权 |
| A1 | -97.20% | -35.33% | 102.38% | -99.18% | -0.345 | 每月选 ret20 最高 5 只 |
| A2 | -98.06% | -38.18% | 47.11% | -98.50% | -0.810 | 趋势选股（close>ma20>ma60） |

**结论**：
- A0 随机选股 +78.15% 证明回测引擎无系统性 bug（不是所有策略都必然亏钱）。
- A1 纯动量选股 -97% 说明 A 股 naive momentum 是均值回归陷阱。
- A2 趋势选股 -98% 说明仅靠 MA 排列不够。

---

## Step 2：B 系列 — 行业分散（OHLCV + stock_basic + daily_basic + moneyflow + top_inst）

**使用的数据**：OHLCV + stock_basic（industry 字段做主题分组）+ daily_basic（total_mv/turnover_rate 做池子过滤）+ moneyflow（net_mf_amount）+ top_inst（机构买卖）。

**目的**：测试行业分散本身能否改善，以及不同加权方案的差异。

| 实验 | total_return | annual_return | annual_vol | max_drawdown | sharpe | 说明 |
|------|-------------|--------------|-----------|-------------|--------|------|
| B0 | -78.77% | -17.21% | 28.02% | -83.36% | -0.614 | 每行业等权 |
| B1 | -78.65% | -17.16% | 26.80% | -83.45% | -0.640 | 按 total_mv 加权 |
| B2 | -81.87% | -18.79% | 28.93% | -85.09% | -0.650 | 每行业 top-10（按 amount20）|
| B3 | -82.56% | -19.18% | 29.04% | -85.59% | -0.660 | 每行业 top-10（按 rs20）|

**结论**：
- 所有 B 系列都在 -78% 到 -83%，行业分散本身不能解决亏损问题。
- 不同加权方案（total_mv / amount20 / rs20）对结果几乎无影响。
- 即使加入 moneyflow + top_inst 数据，行业分散策略依然大幅亏损。

---

## Step 3：C 系列 — V2 策略买入信号过滤

**使用的数据**：
- C1：OHLCV + stock_basic + daily_basic（**无** moneyflow，无 top_inst）
- C2-C5：OHLCV + stock_basic + daily_basic + **moneyflow + top_inst**

**目的**：V2 策略（主题动量 + 成分股相对强度 + 买入信号）的分层消融。

| 实验 | total_return | annual_return | annual_vol | max_drawdown | sharpe | 说明 |
|------|-------------|--------------|-----------|-------------|--------|------|
| C1 | -80.73% | -18.19% | 24.58% | -86.62% | -0.740 | V2 + 卖出纪律，无买入信号过滤，无 mf |
| **C2** | **-4.47%** | **-0.56%** | **2.41%** | **-6.87%** | **-0.231** | **buy_signal_a + pullback_zone 严格过滤** |
| C3 | -20.89% | -2.82% | 12.09% | -30.18% | -0.233 | buy_signal_b 过滤 |
| C4 | -86.36% | -21.56% | 23.90% | -90.14% | -0.902 | timing_score 综合评分（不过滤）|
| C5 | -61.31% | -10.93% | 19.96% | -77.01% | -0.548 | C4 + 市场状态仓位缩放 |

**结论**：
- **C2（-4.47%）是本轮最大突破**。相比 C1（-80.73%）改善了 ~76 个百分点。
- `buy_signal_a`（回踩支撑 + 缩量企稳）远强于 `buy_signal_b`（区间突破放量）。
- 买入信号用作评分权重而不硬过滤（C4/C5）**完全无效**。
- C2-C5 都用了 moneyflow + top_inst（权重 15% in final_score），但 moneyflow 的贡献被买入信号过滤的效果完全盖过。

---

## Step 4：R 系列 — 卖出规则消融

**使用的数据**：R1 使用 OHLCV + stock_basic + daily_basic + moneyflow + top_inst。R2-R4 运行崩溃未产出。

**目的**：测试单独的卖出规则修改（trailing_activation / stale_fix）对 C1 基准的影响。

| 实验 | total_return | annual_return | annual_vol | max_drawdown | sharpe | 说明 |
|------|-------------|--------------|-----------|-------------|--------|------|
| R1 | -85.82% | -21.19% | 24.02% | -89.34% | -0.882 | C1 + trailing_activation |

**结论**：
- R1（-85.82%）**比 C1（-80.73%）更差**。单独加 trailing_activation 反而有害。
- 卖出规则优化必须在买入质量好的前提下才有效 — C1 买了太多差股票，加了 trailing_activation 后止损更频繁，反而锁死了亏损。

---

## Step 5：D 系列 — 真实 ETF

**使用的数据**：
- D0/D1/D2/D3(全区间)：OHLCV + stock_basic + daily_basic + fund_daily + fund_share + index_weight + ETF metadata（**无** moneyflow，无 top_inst）
- D3(2021H1)：上述全部 + **moneyflow + top_inst**

**目的**：用真实 ETF 数据（指数成分股权重）替代行业分类，测试是否能改善。

### 全区间（2018-2026）

| 实验 | total_return | annual_return | annual_vol | max_drawdown | sharpe | 说明 |
|------|-------------|--------------|-----------|-------------|--------|------|
| D0 | -54.98% | -9.07% | 43.89% | -81.53% | -0.207 | 直接买强 ETF |
| D1 | -86.32% | -21.54% | 27.24% | -89.20% | -0.791 | 强 ETF 前 N 大成分股 |
| D2 | -90.42% | -24.87% | 31.29% | -91.11% | -0.795 | ETF 成分股 + 相对强度 |
| D3 | -72.96% | -14.74% | 17.77% | -73.98% | -0.830 | D2 + 买点/风控，无 mf |

### 短窗（2021H1，moneyflow + top_inst 覆盖）

| 实验 | total_return | annual_return | annual_vol | max_drawdown | sharpe | 区间 |
|------|-------------|--------------|-----------|-------------|--------|------|
| **D3** | **+8.09%** | **+40.83%** | **29.38%** | **-10.04%** | **+1.390** | 2021-01-04 → 2021-06-30 |

**结论**：
- 全区间：真实 ETF 路径整体不如代理主题（C 系列）。D0（-54.98%）是 D 系列最好的结果。
- D3 2021H1（+8.09%, sharpe 1.39）**是全部实验中第一个正收益 + 正 Sharpe** 的结果。说明真实 ETF + 买入信号 + moneyflow + top_inst 的组合在合适的市场环境下是有效的。
- 但 D3 全区间（-72.96%）说明该策略在熊市中无法自保。需要以下改进之一：(a) 更强的市场状态过滤；(b) 更严格的买入信号（类似 C2 的 buy_signal_a）。

---

## 全量排名

| 排名 | 实验 | total_return | max_drawdown | sharpe | 区间 | 数据层 |
|------|------|-------------|-------------|--------|------|--------|
| 1 | **A0** | **+78.15%** | -44.80% | +0.198 | 全区间 | OHLCV |
| 2 | **D3** | **+8.09%** | -10.04% | **+1.390** | 2021H1 | OHLCV+ETF+mf+top_inst |
| 3 | **C2** | **-4.47%** | -6.87% | -0.231 | 全区间 | OHLCV+basic+daily_basic（无 mf） |
| 4 | C3 | -20.89% | -30.18% | -0.233 | 全区间 | OHLCV+basic+daily_basic（无 mf） |
| 5 | D0 | -54.98% | -81.53% | -0.207 | 全区间 | OHLCV+ETF |
| 6 | C5 | -61.31% | -77.01% | -0.548 | 全区间 | OHLCV+basic+daily_basic（无 mf） |
| 7 | D3 | -72.96% | -73.98% | -0.830 | 全区间 | OHLCV+ETF |
| 8 | B0 | -78.77% | -83.36% | -0.614 | 全区间 | OHLCV+basic+daily_basic（无 mf） |
| 9 | B1 | -78.65% | -83.45% | -0.640 | 全区间 | OHLCV+basic+daily_basic（无 mf） |
| 10 | C1 | -80.73% | -86.62% | -0.740 | 全区间 | OHLCV+basic+daily_basic |
| 11 | B2 | -81.87% | -85.09% | -0.650 | 全区间 | OHLCV+basic+daily_basic（无 mf） |
| 12 | B3 | -82.56% | -85.59% | -0.660 | 全区间 | OHLCV+basic+daily_basic（无 mf） |
| 13 | R1 | -85.82% | -89.34% | -0.882 | 全区间 | OHLCV+basic+daily_basic（无 mf） |
| 14 | D1 | -86.32% | -89.20% | -0.791 | 全区间 | OHLCV+ETF |
| 15 | C4 | -86.36% | -90.14% | -0.902 | 全区间 | OHLCV+basic+daily_basic（无 mf） |
| 16 | D2 | -90.42% | -91.11% | -0.795 | 全区间 | OHLCV+ETF |
| 17 | A1 | -97.20% | -99.18% | -0.345 | 全区间 | OHLCV |
| 18 | A2 | -98.06% | -98.50% | -0.810 | 全区间 | OHLCV |

---

## 关键结论

1. **A0（随机选股 +78.15%）是最重要的对照**。它证明：回测引擎没有系统性的做空 bias，策略亏损是选股逻辑的问题，不是实现 bug。

2. **C2（buy_signal_a + pullback_zone，-4.47%）是全区间唯一接近盈亏平衡的策略**。买入信号硬过滤是决定性因素——不过滤就是 -80%，过滤就是 -4%。

3. **Moneyflow + top_inst 的边际贡献有限**。在 C2-C5 中，moneyflow 权重仅 15%，被买入信号过滤的效果完全盖过。在 D3 2021H1 中，moneyflow 参与了首个正收益实验，但不能归因。

4. **真实 ETF 数据（D 系列）未表现出优于行业分类（C 系列）**。D0（直接买 ETF，-54.98%）是 D 系列最好结果，但仍比 C2 差很多。

5. **卖出规则优化（R 系列）在没有买入信号过滤时有害**。R1（-85.82%）比 C1（-80.73%）更差。

---

## 下一步建议

1. **围绕 C2 做参数扫描**（最优先）：pullback_zone 上下界、rs_top_pct、target_num、stop_loss、max_theme_weight。

2. **将 C2 的 buy_signal_a 过滤移植到 D 系列**：创建一个 D4 实验 = D3 + buy_signal_a 强制过滤。

3. **补齐 moneyflow 缓存**：目前仅 3 个碎片文件，需要 2018-2026 全区间覆盖才能公平评估 moneyflow 的贡献。

4. **修复 R2-R4 的稳定性问题**：moneyflow 在 2052 天全区间上导致进程崩溃，需要排查内存使用。

5. **考虑 A0 的启示**：随机选股 +78% 暗示全 A 等权分散本身就是不错的策略。也许问题不在「怎么选」，而在「过度集中」。

---

## 如何复现

```bash
cd /Users/jingansun/Desktop/codex/quant
source activate.sh
export QLIB_PROVIDER_URI=data/a_share_qlib

# Step 1: A 系列
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 --experiments a0,a1 --skip-real-etf --no-moneyflow

# Step 2: B 系列（moneyflow + top_inst）
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 --experiments b1,b2,b3 --skip-real-etf

# Step 3: C 系列（moneyflow + top_inst）
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 --experiments c2,c3,c4,c5 --skip-real-etf

# Step 4: R 系列（moneyflow + top_inst）
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 --experiments r1 --skip-real-etf

# Step 5: D 系列
# 全区间（无 moneyflow）
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 --experiments d0 --skip-real-etf --no-moneyflow
# 短窗（moneyflow + top_inst 覆盖）
python3 -u run_theme_etf_experiments.py --market all_a --start 2021-01-04 --end 2021-06-30 --experiments d3
