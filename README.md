# ETF Loop 量化研究仓库

这个仓库的主线是 ETF 轮动策略研究。当前最重要的原则是：

- 日线信号层负责回答“买什么、买多少”。
- 执行层负责回答“什么时候成交、能否成交、成交价格是多少”。
- 分钟级数据只能用于执行回测、容量测试、成交质量分析，不能反向污染当前已经验证过的日线候选策略。

完整实验历史见 [`docs/etf_loop_project_history.md`](docs/etf_loop_project_history.md)，参数词典见 [`docs/etf_loop_setting_glossary.md`](docs/etf_loop_setting_glossary.md)，脚本索引见 [`docs/etf_loop_script_catalog.md`](docs/etf_loop_script_catalog.md)。

## 1. 当前策略核心

当前 ETF Loop 不是一个纯静态池策略，也不是纯动态池策略。主线基座是 `F2_CAP_MA60`：

```text
F2_v3 静态核心池
+ G2 PIT 月度动态补漏池
+ capped 动态池融合
+ MA60 过热惩罚
+ 次日执行、无信号日价格 fallback
```

核心思想：

- 用静态精选池保证长期稳定性。
- 用 PIT 动态池补漏，避免错过新上市或新热点 ETF。
- 动态池不能和平权静态池竞争，只能作为受限补充。
- 对过热 ETF 降权，避免热点后期追高。
- 市场弱时不一定打满 5 只，动态持仓层可以降低总仓位或降低持仓数量。

## 2. 交易规则

默认日线回测遵守以下约束：

| 环节 | 规则 |
|---|---|
| 信号时间 | `T` 日收盘后，根据 `T` 日及以前可见数据计算 ETF 分数 |
| 买入时间 | `T+1` 日执行 |
| 买入价格 | 默认使用 `T+1 open`，没有 next open 就跳过，不回退到信号日收盘 |
| 卖出时间 | `T+1` 日执行 |
| 卖出价格 | 默认使用 `T+1 open`，没有 next open 就跳过 |
| 排名逻辑 | 从候选池中选 top ETF，已有持仓仍在目标组合内则继续持有 |
| 调仓逻辑 | 不在目标组合的持仓卖出，新进入目标组合的 ETF 买入 |
| 成本 | 默认按实验配置设置佣金、滑点、流动性压力 |
| 未来函数 | 禁止使用信号日之后的价格、均线、动量、成交额、排名 |

简单理解：

```text
T 日收盘后出信号
T+1 日按指定执行价格成交
无法成交就跳过
不得使用信号日之后的数据参与信号计算
```

## 3. F2_CAP_MA60 参数

`F2_CAP_MA60` 是当前研究基线，它的池子配置如下：

| 参数 | 当前设置 | 含义 |
|---|---|---|
| `core_pool` | `F2_v3` | 静态核心 ETF 池 |
| `pit_pools` | G2 PIT 月度池 | 每月可见的动态补漏池 |
| `dynamic_fusion_mode` | `capped` | 动态池只做受限补漏，不做简单并集 |
| `dynamic_max_slots` | `1` | 动态池最多插入 1 个席位 |
| `dynamic_max_total_weight` | `0.10` | 动态池总权重最多 10% |
| `dynamic_score_margin` | `0.05` | 动态 ETF 分数必须比静态池弱入选者高 5% 才可替换 |
| `dynamic_overheat_lookback` | `20` | 用过去 20 日收益判断动态 ETF 是否过热 |
| `dynamic_overheat_threshold` | `0.10` | 20 日涨幅超过 10% 视为过热 |
| `dynamic_overheat_penalty` | `0.50` | 过热动态 ETF 分数打 5 折 |
| `mr_ma_period` | `60` | MA60 过热判断 |
| `mr_threshold` | `1.14` | 价格 / MA60 超过 1.14 触发过热惩罚 |
| `mr_penalty` | `0.50` | 过热 ETF 分数打 5 折 |

这组参数的目标是：让动态池成为“补漏机制”，而不是把整个策略变成热点追涨。

## 4. 动态持仓与 V3

早期动态持仓把市场强弱直接映射成持仓数量 `N`。后来发现这会导致弱市里集中押 1 只或 2 只 ETF，反而更容易踩踏。

V3 把 `N` 拆成两个变量：

| 变量 | 含义 |
|---|---|
| `target_holdings` | 持有几只 ETF，控制分散度 |
| `target_exposure` | 总仓位比例，控制风险暴露 |

常用 V3 设置示例：

```text
adaptive_window=15
adaptive_tiers_ret=0.05,0.02,0.00,-0.03,-0.06
adaptive_tiers_n=5,5,4,4,3,0
adaptive_tiers_exposure=1,1,0.85,0.65,0.45,0
```

这里的 `ret_20d` 是历史命名，实际由 `adaptive_window` 决定：

```text
ret = benchmark_close[t] / benchmark_close[t - adaptive_window] - 1
```

当 `adaptive_window=15` 时，它实际是基准过去 15 个交易日收益。

上面三组梯子一一对应：

| 基准 15 日收益 | 目标持仓数 | 目标总仓位 |
|---|---:|---:|
| `>= 5%` | 5 | 100% |
| `>= 2%` 且 `< 5%` | 5 | 100% |
| `>= 0%` 且 `< 2%` | 4 | 85% |
| `>= -3%` 且 `< 0%` | 4 | 65% |
| `>= -6%` 且 `< -3%` | 3 | 45% |
| `< -6%` | 0 | 0% |

这样弱市时可以降低总仓位，但不必把持仓数量过度压缩。

## 5. 当前候选策略

以下候选均来自修复后可复现结果，旧的信号日成交、next open fallback、旧动态池、旧 friend mode 结果不再作为当前结论。

| 候选 | 定位 | 长周期年化 | Sharpe | 最大回撤 | 2026 nowarmup 年化 | 备注 |
|---|---|---:|---:|---:|---:|---|
| `F2_CAP_MA60` | 稳定 baseline | 30.54% | 1.54 | -18.45% | 93.34% | 当前主对照 |
| `Current` | V3 高收益候选 | 39.81% | 1.57 | -25.44% | 144.20% | 收益强，但回撤偏大 |
| `WideA` | 保守候选 | 37.12% | 1.62 | -19.66% | 115.15% | 更稳健，2018 仍需注意 |
| `Exph_v3_exp_looser` | 暴露拆分候选 | 27.33% | 1.51 | -17.30% | 81.43% | 降仓位但不过度压缩持仓数 |

详细候选排序和年度表现见 [`docs/etf_loop_research_index.md`](docs/etf_loop_research_index.md)。

## 6. 复现入口

先激活环境：

```bash
source activate.sh
```

常用复现命令：

```bash
# 核心实验主线
python runs/etf_loop/run_adaptive_sequence_v3.py

# V3 逐年收益 / N 分布 / 最大回撤路径三张诊断表
python runs/etf_loop/run_v3_attribution_tables.py

# 单因素扰动，保证只改一个变量
python runs/etf_loop/run_single_factor_followups_v1.py

# 固定样本外、逐年、成本和容量验证
python runs/etf_loop/run_etf_loop_validation_suite.py

# 2026 no-warmup 回测
python runs/etf_loop/run_2026_nowarmup.py

# 详细交易日志
python runs/etf_loop/run_detailed_trade_log.py --setting WideA --start 2025-10-01 --trading-start 2026-01-02 --end 2026-06-25 --signal-top-n 20

# 分钟级执行层回测，不改变日线信号，只重撮合成交
python runs/etf_loop/run_minute_execution_backtest.py --setting WideA --start 2025-10-01 --trading-start 2026-01-02 --end 2026-06-25
```

输出主要在：

```text
outputs/etf_loop/
outputs/etf_loop/F2_CAP_MA60_deep_dive/
```

## 7. 分钟级数据的定位

现在本地已有 ETF 1 分钟 / 5 分钟数据，路径包括：

```text
data/local_etf_data/2000-2025/1min
data/local_etf_data/2000-2025/5min
data/local_etf_data/2026/2026_1分钟
data/local_etf_data/2026/2026_5分钟
data/local_etf_data/全部份额
data/local_etf_data/全部复权因子
data/local_etf_data/etf.csv
```

分钟数据的价值不是提高日线选 ETF 的准确率，而是验证：

- T+1 真实能否成交。
- 实际成交价格和日线假设差多少。
- 滑点是否远高于固定 2bp。
- 目标仓位和实际仓位是否一致。
- 策略能容纳多少资金。
- 换仓是否发生在流动性差、开盘冲高或急跌时段。

### 不允许的用法

为了保护当前候选策略的可复现性，分钟级数据不能直接进入当前日线信号层：

- 不用分钟数据改变 ETF score。
- 不用分钟数据重新定义候选池。
- 不用分钟数据优化 `adaptive_tiers_ret`。
- 不用分钟数据回看未来成交质量后反向调参。
- 不在现有 `F2_CAP_MA60` / `WideA` / `Exph_v3` 实现里直接混入分钟逻辑。

如果要使用分钟级数据，必须新增独立执行层或独立实验脚本，保持日线候选策略原样。

## 8. 推荐的分钟级执行回测设计

推荐升级为两层结构：

```text
日线信号层：
    T 日收盘后计算 ETF score
    得到 target_weight / target_exposure / target_holdings

分钟执行层：
    T+1 盘中生成订单
    用分钟成交额和价格模拟成交
    更新 actual_position / actual_exposure
    记录成交失败、部分成交、滑点、冲击成本
```

建议先实现中等保守版本：

| 项目 | 默认假设 |
|---|---|
| 信号 | T 日收盘后生成 |
| 执行日 | T+1 |
| 执行窗口 | 09:35-10:30 |
| 成交价格 | 窗口 VWAP 或 TWAP |
| 最大参与率 | 执行窗口成交额的 10% |
| 单笔容量 | 不超过过去 20 日日均成交额的 3% |
| 流动性过滤 | 过去 20 日日均成交额 > 3000 万 |
| 涨停买入 | 失败或部分失败 |
| 跌停卖出 | 失败或部分失败 |
| 停牌 / 无成交 | 不交易 |
| 佣金 | 1.5bp / 边 |
| 基础滑点 | 2bp / 边 |
| 冲击滑点 | 随参与率增加 |

执行日志至少应输出：

```text
signal_date
trade_date
ts_code
side
target_weight
current_weight
order_value
filled_value
unfilled_value
fill_ratio
target_exposure
actual_exposure
execution_start_time
execution_end_time
execution_vwap
actual_fill_price
daily_turnover
execution_window_turnover
participation_rate
slippage_bp
commission_bp
is_limit_up
is_limit_down
is_suspended
```

## 9. 分钟级实验优先级

在不改现有候选策略信号的前提下，按以下顺序做：

1. 固定候选策略，比如 `F2_CAP_MA60`、`WideA`、`Exph_v3_exp_looser`。
2. 用日线引擎生成 `target_position`。
3. 新增独立分钟执行回测，测试 `T+1 open`、`09:35`、`09:35-10:30 VWAP`、全天 VWAP、尾盘 VWAP、`T+2 open`。
4. 加入成交额、参与率、涨跌停、停牌、部分成交约束。
5. 输出 `target_exposure` vs `actual_exposure`。
6. 做成本压力测试：双边 5bp、7bp、10bp、15bp、20bp。
7. 做容量测试：100 万、300 万、500 万、1000 万、3000 万。
8. 比较不同执行方式下的年化、回撤、Sharpe、Calmar、成交失败率、平均滑点。

一句话：

```text
日线回测回答策略有没有 alpha；
分钟级回测回答这个 alpha 能不能被实盘拿到。
```

当前独立分钟执行层入口：

```bash
source activate.sh
python runs/etf_loop/run_minute_execution_backtest.py --setting F2_CAP_MA60 --start 2025-10-01 --trading-start 2026-01-02 --end 2026-06-25
python runs/etf_loop/run_minute_execution_backtest.py --setting WideA --start 2025-10-01 --trading-start 2026-01-02 --end 2026-06-25
python runs/etf_loop/run_minute_execution_backtest.py --setting Exph_v3_exp_looser --start 2025-10-01 --trading-start 2026-01-02 --end 2026-06-25
```

输出报告：

- [`outputs/etf_loop/minute_execution_backtest/minute_execution_comparison_2026_nowarmup.md`](outputs/etf_loop/minute_execution_backtest/minute_execution_comparison_2026_nowarmup.md)
- [`outputs/etf_loop/minute_execution_backtest/minute_execution_report_F2_CAP_MA60_20251001_20260625.md`](outputs/etf_loop/minute_execution_backtest/minute_execution_report_F2_CAP_MA60_20251001_20260625.md)
- [`outputs/etf_loop/minute_execution_backtest/minute_execution_report_WideA_20251001_20260625.md`](outputs/etf_loop/minute_execution_backtest/minute_execution_report_WideA_20251001_20260625.md)
- [`outputs/etf_loop/minute_execution_backtest/minute_execution_report_Exph_v3_exp_looser_20251001_20260625.md`](outputs/etf_loop/minute_execution_backtest/minute_execution_report_Exph_v3_exp_looser_20251001_20260625.md)

## 10. Friend 策略分钟级复现

`runs/etf_loop/run_friend_intraday_replication.py` 是独立分钟级复现脚本，不属于当前 ETF Loop 候选策略实现。

复现命令：

```bash
source activate.sh
python runs/etf_loop/run_friend_intraday_replication.py --start 2020-01-01 --end 2025-12-31 --frequency 1min --adjust none --ranking-modes jq_simple,jq_auto --fill-modes same_0950_close,same_0951_open,same_0955_open,next_day_open
```

报告：

- [`outputs/etf_loop/friend_intraday_replication/friend_intraday_replication_report_20200101_20251231.md`](outputs/etf_loop/friend_intraday_replication/friend_intraday_replication_report_20200101_20251231.md)
- [`outputs/etf_loop/friend_intraday_replication/friend_intraday_replication_report_20200101_20260625.md`](outputs/etf_loop/friend_intraday_replication/friend_intraday_replication_report_20200101_20260625.md)

当前结论：本地 1 分钟数据能基本复现对方声称的最大回撤，但收益仍低于对方声称结果，差异可能来自聚宽撮合细节、`current_data.last_price` 精确时间点、`unit_net_value` 数据源或未披露设置。
