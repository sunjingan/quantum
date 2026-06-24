# Trend-Serenity 量化策略 — 完整实验记录

**实验日期**: 2026-06-23  
**工作目录**: `/Users/jingansun/Desktop/codex/quant/`  
**数据源**: `data/a_share_qlib`（5856 只 A 股，2000-2026）  
**方法框架**: [method.md](/Users/jingansun/Desktop/codex/skills/trend-serenity-investing/references/method.md) / [framework.md](/Users/jingansun/Desktop/codex/skills/serenity/references/framework.md) / [a-share-research-agent](/Users/jingansun/Desktop/codex/skills/a-share-research-agent/SKILL.md)

---

## 目录

1. [项目背景](#1-项目背景)
2. [文件结构总览](#2-文件结构总览)
3. [阶段一：数据基础设施](#3-阶段一数据基础设施)
4. [阶段二：V1 策略与回测](#4-阶段二v1-策略与回测)
5. [阶段三：富集数据与风控](#5-阶段三富集数据与风控)
6. [阶段四：研究框架与因子分析](#6-阶段四研究框架与因子分析)
7. [阶段五：V2 策略与实验矩阵](#7-阶段五v2-策略与实验矩阵)
8. [所有回测结果汇总](#8-所有回测结果汇总)
9. [三个 Bug 及其修复](#9-三个-bug-及其修复)
10. [核心结论](#10-核心结论)

---

## 1. 项目背景

### 目标

将用户建立的 a-share 和 trend-serenity 研究框架抽象成可执行的量化投资策略，使用 qlib 作为回测框架。

### 研究框架来源

四个核心方法文件：

| 文件 | 内容 |
|---|---|
| `skills/trend-serenity-investing/references/method.md` | 双通道准入、四梯队分类、硬排除规则、多模价格强度、拥挤度量化 |
| `skills/serenity/references/framework.md` | 供应链瓶颈研究：终端需求→架构迁移→反向供应链→瓶颈识别→证据账本→财务兑现→催化→反论→评分卡 |
| `skills/a-share-research-agent/references/research-methods.md` | A 股搜索验证方法：假说驱动、证据三角化、来源层级 |
| `skills/a-share-research-agent/references/agent-framework.md` | 投研框架路由、agent 角色、阶段 harness |

### 数据源

- **行情**: `data/a_share_qlib` — Qlib 二进制特征文件（`features/<code>/close.day.bin`），5856 只 A 股，日历 2000-01-04 → 2026-06-22
- **基础财务**: Tushare API — `fina_indicator`, `income`, `cashflow`, `balancesheet`, `daily_basic`, `stock_basic`
- **富集数据**: Tushare API — `stk_holdertrade`(内幕交易), `fina_audit`(审计意见), `pledge_stat`(质押比例), `dc_hot`(人气榜), `limit_list_d`(涨跌停), `ths_daily`(概念指数), `moneyflow`(资金流向), `margin_detail`(融资融券)

---

## 2. 文件结构总览

```
quant/
├── strategies/                     # 策略核心模块
│   ├── __init__.py                 # 包导出（74行）
│   ├── _fundamental.py             # Tushare 基础财务数据缓存（220行）
│   ├── _enrichment.py              # Tushare P0/P1 富集数据缓存（708行）
│   ├── _utils.py                   # 共享工具（行情读取/评分/HS300权重/回测统计，222行）
│   ├── _risk.py                    # 风控模块（止损/止盈/组合回撤/失效纪律，237行）
│   ├── trend_serenity.py           # V1 因子 + 选股管线（731行）
│   ├── trend_serenity_v2.py        # V2 因子（行业中性化/加速/惩罚/Buffer，327行）
│   ├── poe_pb_roe.py              # POE PB+ROE 策略（含富集校验，617行）
│   └── run.py                      # 手动回测 CLI（242行）
│
├── research/                       # 研究分析模块
│   └── ic_analysis.py              # IC/RankIC/分组收益（295行）
│
├── backtest_v2.py                  # V1 回测 CLI（218行）
├── backtest_risk.py                # 风控对比回测（338行）
├── run_research.py                 # 因子研究报告生成器（377行）
├── run_experiments_v2.py           # V2 实验矩阵跑器（239行）
├── prefetch_enrichment.py          # 富集数据预拉取（146行）
└── prefetch_fundamental.py         # 基础财务数据预拉取（30行）
```

---

## 3. 阶段一：数据基础设施

### 3.1 基础财务数据缓存 (`_fundamental.py`)

**目的**: 将 Tushare 逐只股票的基本面数据磁盘缓存，避免重复 API 调用。

**实现**:
- 类 `FundamentalCache` — 管理 4 个 Tushare 端点的缓存
- `stock_basic()` — 全量股票基础信息
- `daily_basic()` — 每日 PE/PB/市值/换手率
- `statement()` — 逐只股票的财务数据（`fina_indicator`, `income`, `cashflow`, `balancesheet`）
- `latest_visible_row()` — 按 `ann_date <= data_date` 获取最近可见财报
- `snapshot()` — 生成全字段宽表用于 Trend-Serenity 打分
- `fundamentals()` — 生成 PB+ROE 策略专用 DataFrame

**关键设计**:
- `.through` 文件标记缓存覆盖范围，避免每次检查全部文件
- `ann_date` 过滤确保 point-in-time 正确性

### 3.2 富集数据缓存 (`_enrichment.py`)

**目的**: 拉取 `method.md` 要求的 8 个 P0/P1 富集接口，全部磁盘缓存。

**接口覆盖**:

| 接口 | 用途 | 数据量 |
|---|---|---|
| `stk_holdertrade` | 内幕交易（最强置信度信号）| 逐只股票拉取 |
| `fina_audit` | 审计意见（非标 = 排除）| 逐只股票拉取 |
| `pledge_stat` | 质押比例（>50% = 降级）| 全量一次拉取 |
| `dc_hot` | 东财人气排名 | 每日拉取（仅近3月） |
| `limit_list_d` | 涨跌停列表 | 每日拉取（仅近6月） |
| `moneyflow` | 主力资金流向 | 每日拉取（仅近1年） |
| `margin_detail` | 融资融券余额变化 | 每日拉取（仅近1年） |
| `ths_daily` | 概念指数趋势 | 概念指数日线 |

**关键类**:
- `EnrichmentCache` — 统一缓存管理
- `InsiderSignal` — 内幕交易信号数据类（含硬排除判定）
- `AuditSignal` — 审计意见信号
- `PledgeSignal` — 质押风险信号
- `CrowdingMetrics` — 拥挤度量化指标（加权评分 0-5）

**全量 A 股预拉取结果**（2000-01-04 → 2026-06-22）:

| 端点 | 记录数 | 耗时 |
|---|---|---|
| `stk_holdertrade` | 23,931 条（从缓存加载） | 82s |
| `fina_audit` | 253 条 | — |
| `pledge_stat` | 3,000 条 | — |
| `dc_hot` | 191,083 条 | — |
| `limit_list_d` | 4,158 条 | — |
| `moneyflow` | 834,793 条 | — |
| `margin_detail` | 682,963 条 | — |
| `ths_daily` | 4,440 条 | — |
| **总计** | **1,744,621 条** | **84 秒** |

### 3.3 基础财务全量预拉取 (`prefetch_fundamental.py`)

**执行**: 对 `data/a_share_qlib/instruments/all_a.txt` 中的 5856 只股票，逐只拉取 4 个 Tushare 端点。

**结果**:

| 端点 | CSV 文件数 | through 标记数 |
|---|---|---|
| `fina_indicator` | 5,856 | 5,856 ✅ |
| `income` | 5,856 | 5,856 ✅ |
| `cashflow` | 5,856 | 5,856 ✅ |
| `balancesheet` | 5,856 | 5,856 ✅ |

**时间**: 后台运行约 2 小时（Tushare API 限速 200次/分钟）。

### 3.4 共享工具 (`_utils.py`)

| 类/函数 | 功能 |
|---|---|
| `QlibDailyReader` | 从 Qlib `.bin` 文件读取日行情 |
| `load_hs300_weights()` | 从 Tushare 加载 HS300 历史成分股权重 |
| `Hs300HistoryUniverse` | 历史 HS300 成分股动态切换 |
| `price_strength_multi_mode()` | 多模价格强度打分（Strong/Healthy/Uncertain/Broken） |
| `market_state()` | 市场状态检测（STRONG/WEAK/NEUTRAL + 高回撤/中回撤/正常） |
| `pct_rank()` | 百分位排名 |
| `score_high_is_good()` / `score_low_is_good()` | 方向化评分 |
| `monthly_rebalance_dates()` | 月度调仓日期生成 |
| `lot_floor()` | 手数取整 |
| `summarize()` | 回测统计（总收益/年化/波动/回撤/Sharpe） |
| `read_instrument_codes()` | 从 Qlib instruments 文件读取股票池 |

---

## 4. 阶段二：V1 策略与回测

### 4.1 V1 因子公式 (`trend_serenity.py`)

```text
serenity_score =
  0.30 × bottleneck_authenticity
  + 0.30 × financial_translation
  + 0.20 × expectation_gap
  + 0.20 × reflexivity_risk_control
```

**四维度定义**:

| 维度 | 子成分 | 权重 |
|---|---|---|
| bottleneck_authenticity | 毛利率排名 + 研发费用率排名 + 合同负债率排名 + 价格强度排名 | 0.35/0.25/0.25/0.15 |
| financial_translation | 收入增速排名 + 利润增速排名 + 净利率排名 + OCF/利润排名 | 0.30/0.25/0.20/0.25 |
| expectation_gap | PE排名 + PB排名 + 非过热排名 + 收入增速排名 | 0.30/0.30/0.25/0.15 |
| reflexivity_risk_control | 负债率排名 + 存货/收入排名 + 应收/收入排名 + 换手率排名 | 0.30/0.25/0.25/0.20 |

**注意**: 所有排名均为**全市场**百分位排名（V2 改为行业内排名）。

### 4.2 选股管线

```text
1. 富集数据 → 硬排除 (内幕卖出主导、非标审计)
2. 基础财务过滤 (上市天数、ST、科创板、净利润>0、PE>0、PB>0、负债<85%)
3. 价格强度多模打分
4. 四维度 Serenity 评分
5. 双通道准入 (Channel A: 超增长 / Channel B: 瓶颈质量)
6. 四梯队分类 (Pass-A/B/C / Near miss / Reject)
7. 行业分散选股 (每行业上限 3 只)
```

### 4.3 HS300 全区间回测 (`backtest_v2.py`)

**配置**:
- 股票池: HS300 历史成分股（509 只）
- 调仓: 月度（每月首个交易日）
- 选股: Top 10 等权
- 成本: 买入 0.05%, 卖出 0.15%
- 初始资金: 1,000,000
- 风控: 无

**结果**:
```
总收益: -5.98%
年化收益: -0.73%
年化波动: 26.88%
最大回撤: -71.71%
Sharpe: -0.027
CSI300: +23.06%
```

**分析**: 无风控、等权月度调仓、49% 选到 Pass-C（Red Flag），在 2021-2024 熊市中大幅回撤。

### 4.4 风控对比 (`backtest_risk.py`)

新增 `_risk.py` 风控模块:

| 风控规则 | 参数 |
|---|---|
| 单只止损 | 从入场价跌超 20% → 强制卖出 |
| 移动止盈 | 盈利超 30% 后，从最高回撤 15% → 卖出 |
| 失效纪律 | 毛利率 <15%、内幕卖出、审计非标、拥挤度 >4 |
| 组合回撤控制 | 组合回撤 >25% → 仓位降至 50% |
| 最小持仓期 | 40 个交易日（约2个月） |
| 选股过滤 | 最低梯队 Pass-B（排除 Pass-C） |

**三版对比结果** (HS300, 2018-2026):

| 版本 | 总收益 | 最大回撤 | 描述 |
|---|---:|---:|---|
| Risk-OFF (无风控) | -3.20% | -76.24% | 原始管线 |
| Risk-ON v1 (止损+失效) | -12.75% | -73.66% | 止损锁亏，反而更差 |
| **Risk-ON v2 (弱市空仓)** | **+0.95%** | **-41.65%** | 弱市空仓是唯一有效的风控 |

**结论**: 止损在熊市中连锁触发、锁死亏损。弱市空仓（WEAK → 100%现金）是唯一显著改善回撤的风控手段。

---

## 5. 阶段三：富集数据与风控

### 5.1 富集数据验证

在沪深300成分股子集上测试（10只）：

| 结果 | 说明 |
|---|---|
| 万科A (000002) | 被审计意见「带强调事项段的无保留意见」**自动硬排除** ✅ |
| 平安银行 (000001) | 通过全部检查：标准无保留意见、无内幕卖出、质押0%、拥挤度1.4/5 ✅ |

### 5.2 风控设计演进

```
v0: 无风控 → maxDD -76%
v1: 止损+失效纪律 → 164次止损触发，锁死亏损 → maxDD -74%，收益 -12.75%
v2: 弱市空仓 → 56次止损触发 → maxDD -42%，收益 +0.95%
```

**核心认知**: A 股长期熊市中，纯多头策略的风控做得越多，割肉越频，收益越差。真正的解法是空仓等待而非频繁止损。

---

## 6. 阶段四：研究框架与因子分析

### 6.1 IC 分析模块 (`research/ic_analysis.py`)

实现了 6 个研究问题中的 Step 1（因子有效性）：

- IC / RankIC（Pearson / Spearman 相关性）
- 20/60/120 日三个时间窗口
- Q1-Q5 分组收益
- 四维度消融实验

### 6.2 因子研究报告 (`run_research.py`)

输出 10 张核心表：

| 表号 | 内容 |
|---|---|
| 1 | 因子 IC 汇总（RankIC / ICIR / t-stat） |
| 2 | 分组收益（Q1-Q5，Top-Bottom Spread） |
| 3 | 维度消融（四维度独立 IC） |
| 4 | 年度表现 |
| 5 | 市场状态表现 |
| 6 | 行业归因 |
| 7 | 个股归因 |
| 8 | 成本压力测试 |
| 9 | 换手率统计 |
| 10 | 基本面一致性 |

### 6.3 V1 因子有效性核心发现

**HS300, 2019-2026, 509只**:

| 因子 | 最优窗口 | RankIC | ICIR | t_stat | 判断 |
|---|---:|---:|---:|---:|:---:|
| serenity_score | 60日 | **0.1218** | 0.673 | 2.86 | ✅ 有效 |
| bottleneck_authenticity | 60日 | **0.0974** | **0.798** | 3.38 | ✅ 最强维度 |
| financial_translation | 60日 | 0.0551 | 0.301 | 1.28 | ⚠️ 弱有效 |
| expectation_gap | 120日 | **-0.0651** | -0.213 | -0.93 | ❌ 反向！ |
| reflexivity_risk_control | 20日 | 0.0266 | 0.191 | 0.85 | ❌ 无效 |

**分组收益（60日）**: Q5（最高20%）= +4.98%, Q1（最低20%）= -0.95%, **Spread = +5.93%**。

**核心结论**: 
- `expectation_gap` RankIC 为负——低PE/PB的股票在A股反而跑输（低估值陷阱）
- `bottleneck_authenticity` 是最强且最稳定的维度

### 6.4 年度表现

| 年份 | 策略 | CSI300 | 超额 |
|---|---:|---:|---:|
| 2019 | +32.9% | +38.2% | -5.3% |
| 2020 | **+39.5%** | +25.5% | **+14.0%** |
| 2021 | -19.3% | -6.2% | -13.1% |
| 2022 | -3.4% | -21.3% | **+17.9%** |
| 2023 | -5.3% | -11.8% | +6.4% |
| 2024 | -3.8% | +16.2% | -20.0% |
| 2025 | +22.0% | +21.2% | +0.9% |
| 2026 | +18.5% | +7.2% | +11.3% |

**8 年中有 5 年跑赢（62.5% 胜率）**，熊市防御优于牛市进攻。

### 6.5 选股画像

**被选中次数 Top 15**（V1 因子，88 次调仓）:

三环集团(30次)、东鹏饮料(28次)、恒瑞医药(25次)、药明康德(23次)、新和成(22次)、古井贡酒(20次)、福耀玻璃(19次)、川投能源(17次)、上港集团(16次)、汇川技术(15次)、兆易创新(14次)、恒立液压(13次)、泸州老窖(13次)、欧派家居(12次)、三一重工(12次)。

**全部是各行业质量龙头**——高ROE、强现金流、品牌/技术壁垒。与 Serenity 框架一致。

**梯队分布**: Pass-A: 726 (96.4%), Pass-B: 27 (3.6%), Pass-C: 0（被过滤）

---

## 7. 阶段五：V2 策略与实验矩阵

### 7.1 V2 改动清单

根据用户反馈（12 条详细建议），实施了 5 个优先级改动：

**P1: expectation_gap → 估值惩罚**

不再给正向 Alpha 权重，改为极端估值的风险惩罚：
- PE/PB 行业内前 10% → 扣分
- PE 行业内后 5% → 轻微扣分（可能价值陷阱）
- 惩罚上限 0.15

**P2: 行业中性化**

所有财务指标改为 `industry_name` 分组排名：

| 原方法 | 新方法 |
|---|---|
| `df["gross_margin"].rank(pct=True)` | `industry_rank(df, "gross_margin")` |

优先级：行业内排名 > 全市场排名。如果行业列缺失，退化为全市场排名。

**P3: 瓶颈维度拆解**

从单一 `bottleneck_authenticity` 拆分为 5 个子因子：
- `bottleneck_sub_gm` — 毛利率
- `bottleneck_sub_rd` — 研发费用率
- `bottleneck_sub_cl` — 合同负债率
- `bottleneck_sub_roe` — ROE
- `bottleneck_sub_accel` — 收入增速加速

新增 `bottleneck_pure`（不含价格强度的纯基本面瓶颈），用于判断趋势因子贡献。

**P4: 景气加速指标**

新增 `compute_acceleration_metrics()` — 二阶变化量：
- `sales_accel` — 收入增速同比变化
- `profit_accel` — 利润增速同比变化
- `margin_change_yoy` — 毛利率同比变化
- `ocf_change_yoy` — OCF/收入同比变化
- `debt_change_yoy` — 负债率同比变化

**P5: 组合 Buffer 机制**

不再每月机械换仓。实现 `apply_portfolio_buffer()`:
- 买入池: Top 15
- 保留池: Top 30
- 卖出条件: 排名跌出 Top 30

### 7.2 V2 因子公式

```text
serenity_score_v2 =
  0.40 × bottleneck_ind       (行业内分位: GM 30% + RD 20% + CL 20% + ROE 15% + 加速 15%)
  + 0.30 × financial_ind       (行业内分位: 收入增速 25% + 利润增速 20% + 净利率 15% + OCF 15% + 加速 15% + 毛利变化 10%)
  + 0.15 × reflexivity_ind     (行业内分位: 负债 25% + 存货 25% + 应收 20% + 换手 15% + 负债改善 15%)
  + 0.15 × trend_confirm       (多模价格强度，独立因子)
  - valuation_penalty           (极端估值惩罚)
```

### 7.3 V1 vs V2 选股画像变化

测试日期: 2019-10-31, HS300 成分股 300 只:

| | V1 Top 3 | V2 (Industry Rank) Top 3 |
|---|---|---|
| 1 | 恒瑞医药 (医药) | 宋城演艺 (旅游) |
| 2 | 长春高新 (医药) | 乐普医疗 (医疗) |
| 3 | 海天味业 (食品) | 海康威视 (安防) |

- **Rank 相关性**: 0.07（几乎独立）
- **Top 10 交集**: 0/10

行业中性化彻底改变了选股画像——不再集中在医药/白酒/消费，而是分散到各行业。

### 7.4 瓶颈分解初步结果

V2 因子中瓶颈维度的子成分与总分相关性:

| 子因子 | corr with V2 | 均值 | 判断 |
|---:|---:|---|
| 毛利率 (gm) | 0.5765 | 0.6317 | ✅ 最强贡献 |
| ROE (roe) | 0.5290 | 0.6318 | ✅ 强贡献 |
| 研发费用率 (rd) | 0.4737 | 0.6136 | ✅ 中等 |
| 合同负债率 (cl) | 0.1745 | 0.5604 | ⚠️ 贡献弱 |

**解读**: 毛利率和 ROE 是瓶颈维度的核心驱动。合同负债率（订单/预收）对非白酒/非工程行业的区分力有限。

---

## 8. 所有回测结果汇总

### 8.1 完整版本对照

HS300 成分股, 2019-01-02 → 2026-06-22, 509 只, Top 10 等权, 初始 100万:

| 版本 | 因子 | 风控 | 总收益 | 年化 | 最大回撤 | Sharpe | 超额(vs CSI300) |
|---|---:|---:|---:|---:|---:|---:|---:|
| V1_NoCash | V1 | 无 | +14.96% | +1.89% | -79.59% | 0.071 | -55.69% |
| V1_Cash | V1 | 弱市空仓 | +31.00% | +3.68% | -63.24% | 0.166 | -39.66% |
| V2_NoCash | V2 | 无 | +92.24% | +9.15% | -48.71% | 0.356 | +21.58% |
| V2_Cash | V2 | 弱市空仓 | +74.21% | +7.72% | **-40.36%** | 0.353 | +3.55% |

**CSI300 基准**: 总收益 +70.66%, 年化 +7.48%, 最大回撤 -39.76%

### 8.2 改进幅度

| 指标 | V1_NoCash → V2_NoCash | V1_Cash → V2_Cash |
|---|---:|---:|
| 年化收益 | +1.89% → +9.15% (+7.26pp) | +3.68% → +7.72% (+4.04pp) |
| 最大回撤 | -79.59% → -48.71% (+30.88pp) | -63.24% → -40.36% (+22.88pp) |
| Sharpe | 0.071 → 0.356 (+0.285) | 0.166 → 0.353 (+0.187) |

### 8.3 关键发现

1. **行业中性化是最大的单次改进**: V2_NoCash 年化收益是 V1_NoCash 的 4.8 倍，回撤降低 31 个百分点

2. **V2 无空仓版本（V2_NoCash）表现最好**（年化 9.15%），优于带空仓的版本（7.72%）。二元空仓（满/空）在保护回撤的同时牺牲了反弹机会

3. **V2_Cash 回撤最低**（-40.36%）但收益不如 V2_NoCash（-48.71% vs +21.58% 超额）

4. **V1 因子本身有横截面选股能力**（RankIC 0.12, t=2.86），但组合表达（全市场排名、Pass-C 占比 49%、无行业中性化）拖累了实际收益

---

## 9. 三个 Bug 及其修复

### Bug 1: 成本压力测试公式错误

**位置**: `run_research.py` line 347

**原代码**:
```python
adj_ret = stats["annual_return"] - (bc + sc) * 12 / 2
```

**问题**: 公式无意义。`(bc + sc) * 6` 与换手率无关，导致成本测试收益（7.97%）与总览年化（9.17%）不一致。

**修复**:
```python
cost_drag = ann_turnover * (bc + sc)       # 年化换手 × 往返成本
adj_ret = stats["annual_return"] - cost_drag
```

### Bug 2: 市场状态收益口径错误

**位置**: `run_research.py` lines 296-308

**原代码**:
```python
ret_s = rg["portfolio_value"].iloc[-1] / rg["portfolio_value"].iloc[0] - 1
```

**问题**: 对非连续日期做累计复利。当状态切换时（STRONG→WEAK→STRONG），两个 STRONG 段的净值被错误拼接。导致三个状态都 ≈67%，但总和 ≠ 总收益 92%。

**修复**:
```python
daily_ret = rg["portfolio_value"].pct_change().dropna()
ann_ret = daily_ret.mean() * 252
```

**修复后结果**:
| 状态 | 年化收益 | 日胜率 |
|---|---:|---:|
| STRONG | +24.55% | 53.3% |
| WEAK | +1.08% | 49.9% |
| NEUTRAL | +0.62% | 49.1% |

### Bug 3: 年化口径不一致

**原因**: Bug 1 导致成本压力测试中的年化收益使用错误公式，与总览中的正确年化不一致。

**修复**: 统一使用 `stats["annual_return"]`（从总收益年化计算），成本测试叠加正确的成本拖累公式。

---

## 10. 核心结论

### 10.1 因子层面

| 结论 | 证据 |
|---|---|
| V1 因子有显著的横截面选股能力，但不是线性的 | RankIC 60日 = 0.122, t = 2.86; Q5-Q1 spread = +5.93% |
| `bottleneck_authenticity` 是最强维度 | ICIR 0.798, t = 3.38 |
| `expectation_gap` RankIC 为负 | -0.065, 低 PE/PB 是陷阱而非 Alpha |
| 瓶颈有效但 `price_score`（趋势）贡献可能大于基本面 | 待 P3 分解验证 |
| 行业中性化将因子从"质量行业选股"变成"行业内选优" | V1-V2 Rank 相关性仅 0.07 |

### 10.2 策略层面

| 结论 | 证据 |
|---|---|
| 纯多头在 A 股的最大敌人是回撤 | 无风控版本 maxDD = -80% |
| 弱市空仓是唯一显著有效的风控 | 比止损 + 失效纪律版本改善 35pp |
| 月度换仓 + Top 10 集中度过高 | 路径依赖强，个股事件风险大 |
| V2 行业中性化 + 加速指标将年化从 1.89% 提升到 9.15% | 单次改进最大 |
| 二元空仓（满/空）不如连续风险预算 | V2_NoCash 收益 > V2_Cash |

### 10.3 策略画像

> **V2 策略 ≈ 行业内质量龙头 + 财务加速确认 + 趋势跟进 + 极端估值排除 + 弱市空仓**
>
> 它还不是完整的"产业链瓶颈投资系统"，而是一个"质量+景气+趋势+风控"的四因子模型。
>
> Serenity 的瓶颈位置、供需映射、证据账本、人工研究验证，目前还没有完全量化到策略里。

### 10.4 待完成

| 优先级 | 任务 | 状态 |
|---|---|---|
| P0 | V2_NoCash 作为新基线 | ✅ 完成 |
| P1 | 空仓升级为风险预算（非二元） | 待实施 |
| P2 | 加密 IC 采样至全量月度数据 | 待实施 |
| P3 | 拆分 bottleneck 的 price_score vs 纯基本面贡献 | ✅ 数据结构已建，待全量跑 |
| P4 | 全 A 股流动性过滤后回测 | 待实施（数据已就绪） |
| P5 | Buffer 组合机制跑完整对比 | ✅ 代码已建，待全量跑 |
| — | 未来函数审计（T+1/公告日/Shift） | 待实施 |
| — | 人工研究标签库 | 待建立 |
| — | 风格归因（控制 size/value/momentum） | 待实施 |

---

> ⚠️ **本实验记录不构成投资建议。** 所有数据来自公开接口（Tushare / Qlib 本地行情），回测结果受幸存者偏差、成本假设、数据质量等多种因素影响。实盘前需独立验证当前价格、流动性、持仓风险和监管政策。

*记录生成: 2026-06-23 | 项目路径: [`/Users/jingansun/Desktop/codex/quant/`](/Users/jingansun/Desktop/codex/quant/)*
