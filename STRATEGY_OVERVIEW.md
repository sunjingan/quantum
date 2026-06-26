# ETF 动量轮动策略 —— 代码与理解

## 一、策略文件全景

| 文件 | 行数 | 用途 |
|------|------|------|
| `strategies/etf_loop_strategy.py` | ~730 | 核心策略引擎：`score_etf()` 打分、`run_etf_loop_backtest()` 回测 |
| `strategies/etf_loop_engine.py` | ~710 | **K0 统一引擎**：px bug 已修复、NAV 逐日对账零误差。支持 PIT 池、双池融合、防御模式、多因子 |
| `strategies/etf_pool_classify.py` | ~220 | ETF 分类器：8 桶分类（defensive/commodity/overseas_us/hk_china/other_overseas/broad_a/style/theme） |
| `strategies/etf_sniper.py` | ~555 | 单兵狙击策略：H=1，MA 趋势过滤，四道防线 |
| `backtest_etf_loop.py` | ~193 | CLI 回测入口（原始版，有 px bug） |

### 数据文件

| 文件 | 说明 |
|------|------|
| `data/tushare_cache/sector_prosperity/etf_pool_G2_PIT_monthly.pkl` | G2 PIT 月度池（96 个月，12→35 ETFs） |
| `data/tushare_cache/sector_prosperity/etf_pool_F2_v3.csv` | F2_v3 规则化静态池（44 ETFs） |
| `data/tushare_cache/sector_prosperity/etf_pool_M_2020core50.pkl` | 2020 锚定核心池 43 只 |
| `data/tushare_cache/sector_prosperity/etf_pool_M_2020core100.pkl` | 2020 锚定核心池 60 只 |
| `data/tushare_cache/sector_prosperity/etf_pool_G2_PIT_corrpruned.pkl` | G2 PIT 相关性去重版（56 ETFs） |

### 实验记录

| 文件 | 行数 | 说明 |
|------|------|------|
| `outputs/etf_loop/experiment_record.md` | ~2720 | **完整实验记录**：F/G/J/K/R/D/M/ORIG 全系列，含结论、表格、附录 |

---

## 二、核心策略引擎 — G2 Loop

### 2.1 买卖流程（日频）

```
T 日收盘：score_etf() 对候选池内每只 ETF 打分
  ↓
T+1 日开盘：卖出不在 Top H 的持仓 + 止损触发
         买入 Top H（等权分配资金）
  ↓
T+1 日收盘：记净值（现金 + Σ持仓×收盘价）
```

### 2.2 评分函数 `score_etf(store, code, date, params)`

```python
def score_etf(...):
    # ── 三道硬门槛（不通过 → return None）──
    # ① 成交量异常：当日量 > 过去5日均量×2.0 且 25日年化收益 > 1.0 → 疑似顶部
    # ② RSI过热：RSI(6) > 98 且价格 < MA5 → 超买反转
    # ③ 短期动量不足：10日年化收益 < 0 → 短线弱势

    # ── 核心评分 ──
    # 过去25日收盘价取对数 → 加权线性回归（越近权重越高）
    # 年化收益 = exp(斜率 × 250) - 1
    # R² = 1 - SS_res / SS_tot  （拟合优度，衡量趋势有多"平滑"）
    # score = 年化收益 × R²

    # ── 归零惩罚 ──
    # ④ 3日急跌：过去3天任一天跌幅 > 3% → score = 0
    
    return {"score": score, "annualized_returns": ..., "r_squared": ...}
```

**设计哲学**：选"涨得又稳又猛"的——年化收益高但过程颠簸（R²低）的被惩罚，稳步上涨（R²高）的被放大。

### 2.3 卖出条件（四道防线）

| 防线 | 条件 | 价格 |
|------|------|------|
| 换仓 | 已不在 Top H | T+1 日开盘价 |
| 固定止损 | 现价 ≤ 成本价 × 0.95 | T+1 日开盘价 |
| ATR 动态止损 | 现价 ≤ 成本价 - ATR(14) × 2.0 | T+1 日开盘价 |

### 2.4 关键参数

```python
holdings_num = 5        # 持仓数
lookback_days = 25      # 动量回溯天数
stop_loss = 0.95        # 固定止损线
open_cost = 0.0001      # 买入佣金（双边各万分之一）
close_cost = 0.0001     # 卖出佣金
slippage = 0.0001       # 固定滑点
```

---

## 三、ETF 池构造体系

### 3.1 三种池模式

```
┌──────────────────────────────────────────────────────┐
│                     ETF 池输入                         │
├───────────────┬──────────────────┬───────────────────┤
│  静态池        │  PIT 月度池       │  每日动态池        │
│  (固定不变)     │  (每月重建)       │  (每日扫描)        │
├───────────────┼──────────────────┼───────────────────┤
│ ORIG38 (38只)  │ G2 PIT (12→35只) │ 流动性 Top100      │
│ F2_v3  (44只)  │ G1 PIT (12→35只) │ (5日成交额>5000万)  │
│ core43 (43只)  │                  │                   │
│ core60 (60只)  │                  │                   │
└───────────────┴──────────────────┴───────────────────┘
```

### 3.2 G2 PIT 月度池构造门槛

| 门槛 | 数值 |
|------|------|
| 上市时间 | ≥ 365 日（≈250 交易日） |
| 流动性 | 过去 180 日日均成交额 |
| Benchmark 去重 | 同指数只留上市最早的 |
| 分类 | 8 桶（defensive/commodity/overseas_us/hk_china/other_overseas/broad_a/style/theme） |
| 桶配额 | 每桶固定名额（defensive 4, commodity 5, ...） |
| Canonical priority | 关键 ETF（513100 纳指/513500 标普/518880 黄金/511880 货币）永不掉池 |
| 更新频率 | **月度**（每月末重建，次月生效） |

### 3.3 每日流动性 Top100（`_build_dynamic_pool`）

| 门槛 | 数值 |
|------|------|
| 数据存在 | ≥ 5 交易日 |
| 流动性 | 过去 5 日日均成交额 ≥ 5000 万 |
| 排名 | 全市场 Top 100 |
| 分类 | 无 |
| 桶配额 | 无 |
| 更新频率 | **每日** |

### 3.4 融合实验执行方式

```python
# 方式 A：K0 引擎（静态池 + 每日流动性 Top100）
p = EngineParams(
    etf_pool_ts=all_ts,          # 需要包含动态池可能出现的 ETF
    core_pool=pool_static,       # 静态核心池
    use_dynamic_pool=True,       # 启用每日流动性 Top100
    holdings_num=5,
)

# 方式 B：内联 Python（静态池 ∪ G2 PIT 月度池）
for signal_date in calendar:
    active_pit = g2_pools[last_month_end <= signal_date]
    # 候选池 = 静态池 ∪ 当月 PIT 池
    active_pool = pool_static | active_pit
    store.ts_codes = list(active_pool)  # 临时替换
    ranked = get_ranked_etfs(store, signal_date, params)
    store.ts_codes = original_codes     # 恢复
```

---

## 四、K0 统一引擎（strategies/etf_loop_engine.py）

### 4.1 设计目标

```text
同一参数 + 同一池子 + 同一成本 → 无论从哪个入口运行，结果完全一致。
误差容忍：年化差 < 0.1pp，交易数差 < 1%。
```

### 4.2 引擎特性

| 特性 | 实现 |
|------|------|
| NAV 对账 | 每天 `portfolio_value = cash + Σ(shares × close)`，全周期零误差 |
| PIT 模式 | `pit_pools` 参数，月度池切换 |
| 静态池模式 | `etf_pool_ts` 参数 |
| 双池融合 | `core_pool` + `use_dynamic_pool` |
| 防御模式 | `defense_ma_period` + `defense_exposure` |
| 多因子 | `mf_vol_penalty` + `mf_rev_penalty`（代码未生效，待修复） |
| 调仓频率 | `rebalance_interval` |
| Cooldown | `cooldown_days` + `cooldown_override_top_n` |
| 动态成本 | `use_dynamic_cost` + `slip_tiers` + 参与率惩罚 |

### 4.3 已知 Bug 及修复

| Bug | 位置 | 状态 |
|-----|------|------|
| **px 变量引用错误** | `run_etf_loop_backtest` 卖出行 | ✅ 已修复（`00c68fd`） |
| 多因子代码未生效 | K0 引擎 patch 静默失败 | ❌ 待修复 |
| 防御模式 MA20 永不开仓 | `in_defense` 触发后无法恢复 | ⚠️ MA40/MA60 可用 |

### 4.4 px Bug 详解

**原始代码（有 bug）**：
```python
# sell loop
exec_px = next_open_prices.get(code, np.nan)
if np.isnan(exec_px) or exec_px <= 0:
    exec_px = signal_px    # fallback
if np.isnan(px) or px <= 0:   # ← BUG: px 是买入循环的变量！
    continue                    #   不是 exec_px！
```

`px` 是**上一个买入循环**里最后一个 ETF 的买入价，和当前要卖的 ETF 毫无关系。但因为 Python 不报错（for 循环无新作用域），这个 bug 静默存在。后果：即使当前 ETF 没有有效卖价，卖出也永远不会被跳过——用了一个不相关的价格做判断。

**修复后**：
```python
if np.isnan(exec_px) or exec_px <= 0:
    exec_px = signal_px
if np.isnan(exec_px) or exec_px <= 0:
    exec_px = entry_prices.get(code, signal_px)  # 增加 fallback
if np.isnan(exec_px) or exec_px <= 0:
    continue  # 正确变量
```

---

## 五、实验结论速查

### 5.1 全量最终对照

| 池子 | 年化 | DD | Sharpe | 推荐 |
|------|------|-----|--------|------|
| **ORIG38** | **29.86%** | **-14.99%** | **1.68** | ✅ 风控最优 |
| F2_v3 ∪ ORIG38 (64只) | 35.39% | -19.87% | 1.58 | ✅ 收益最优 |
| F2_v3 (44只) | 36.15% | -25.12% | 1.57 | 收益高但 DD 高 |
| G2 PIT 月度 | 18.16% | -25.75% | 0.87 | 规则化基线 |

### 5.2 关键发现

| 发现 | 详情 |
|------|------|
| 每日流动性 Top100 无效 | 加到任何精选池上年化变化 < 0.05pp——score_etf 的三道门槛把动态池 ETF 全筛掉了 |
| G2 PIT 月度池融合有偏 | 对 ORIG38 有效（+2.1pp），对 F2_v3 无效（重叠率 93%）——取决于重叠率 |
| H 越小 DD 越大 | H=5 的 DD 最小，分散持仓是最好的风控 |
| 止损收紧无效 | 0.93→0.97 对 DD 几乎无影响 |
| 相关性去重全面恶化 | 年化腰斩，同 benchmark 多只 ETF 提供了流动性备胎 |
| 防御模式有效但代价高 | MA60 防御把 DD 从 -25.75% 压到 -14.40%，年化从 18.16% 降到 7.23% |
| 静态池 > 动态池 | 在所有实验中，纯静态精选池优于任何融合方案 |

### 5.3 不做的事

| 方案 | 结论 |
|------|------|
| 多周期动量融合 | G5 证伪：破坏 25d 信号 |
| NAV 均线防御 | G4 证伪：反应太慢、适得其反 |
| 严格桶限制 | H1 证伪：和短线哲学冲突 |
| 逆波权重 | G3 证伪：削弱最强信号 |

---

## 六、复现实验

### 6.1 环境

```bash
source env_qlib/bin/activate
export QLIB_PROVIDER_URI=$(pwd)/data/a_share_qlib
```

### 6.2 K0 引擎实验

```python
from strategies.etf_loop_engine import EngineParams, run_backtest

p = EngineParams(
    etf_pool_ts=pool_codes,   # 静态池
    holdings_num=5,
    stop_loss=0.95,
    start='2018-06-01', end='2026-06-25',
)
equity, trades, audit = run_backtest(p)
stats = audit['stats']  # annual_return, sharpe_ratio, max_drawdown
```

### 6.3 融合实验（静态 ∪ G2 PIT）

```python
# 关键逻辑：临时替换 store.ts_codes 来限制候选池
store.ts_codes = list(active_pool)         # 替换
ranked = get_ranked_etfs(store, date, p)   # 评分（只看候选池）
store.ts_codes = original_all_codes        # 恢复
```

完整的融合实验代码见 `experiment_record.md` 附录 B。
