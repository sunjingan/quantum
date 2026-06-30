# ETF Loop 候选策略严格执行验证报告

生成日期：2026-06-29

## 1. 结论先行

2026-06-29 最终口径更新：`rerun_*`、`fixed_realistic_*`、以及未缩放 `amount` 的中间结果全部废弃。最终执行验证只引用 `amountfix_*` 和最新 `ADVICE` 拆单结果。

本次最终修复点：

- ETF Loop 日线 advice 是复权价格/股数口径；分钟执行层用 `--price-adjustment engine` 把本地分钟 `open/high/low/close/limit_up/limit_down` 缩放到同一复权价格口径。
- 复权分钟 VWAP 使用 `sum(adjusted_close * adjusted_volume_basis_volume) / sum(volume)`，不再使用原始 `amount / volume`。
- `amount` 也按同一复权比例缩放，否则 `order_value / window_turnover` 会把复权订单金额除以原始成交额，容量和冲击滑点会失真。
- 拆单验证已改为 advice replay，只拆原引擎真实 BUY/SELL，不再按每日 target_weight 强制再平衡。

关于是否偏离实盘：

- 回测里缩放分钟价格和 amount 只是为了让 replay 账户、advice 股数、日线估值处在同一个复权单位，不是实盘挂单价。
- 实盘/模拟盘下单必须使用券商盘口的原始价格；复权价格只用于研究回测、收益率连续化和持仓估值对齐。
- 对成交能力判断，本质看的是 `订单金额 / 窗口成交额` 的相对比例。价格和 amount 同比例缩放后，这个比例与原始盘口口径等价；只缩放价格不缩放 amount 才会偏离实盘。

最终复现命令：

```bash
source activate.sh && python runs/etf_loop/run_minute_execution_advice_replay.py --settings WideA,F2_CAP_MA60 --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25 --capitals 1000000 --execution-modes vwap_0935_1030 --roundtrip-cost-bps 5,7,10,15,20 --max-participation 0.10 --price-adjustment engine --replay-mode value --missing-price-policy skip --tag-suffix amountfix_cost_1m_vwap
source activate.sh && python runs/etf_loop/run_minute_execution_advice_replay.py --settings WideA --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25 --capitals 50000,100000,300000,1000000,3000000,10000000 --execution-modes vwap_0935_1030 --roundtrip-cost-bps 7 --max-participation 0.10 --price-adjustment engine --replay-mode value --missing-price-policy skip --tag-suffix amountfix_capacity_widea_vwap_7bp
source activate.sh && python runs/etf_loop/run_split_order_execution_validation.py --settings WideA --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25 --capitals 50000,1000000 --schedules am_4x,am_tail_4x,midday_6x --roundtrip-cost-bp 7 --max-participation 0.10 --child-kind vwap --price-adjustment engine
```

最终输出：

- `outputs/etf_loop/minute_execution_backtest/advice_replay_summary_amountfix_cost_1m_vwap_20130701_20260625.csv`
- `outputs/etf_loop/minute_execution_backtest/advice_replay_summary_amountfix_capacity_widea_vwap_7bp_20130701_20260625.csv`
- `outputs/etf_loop/minute_execution_backtest/split_child_execution_summary_20130701_20260625.csv`
- `outputs/etf_loop/minute_execution_backtest/split_child_execution_report.md`
- `outputs/etf_loop/minute_execution_backtest/advice_replay_summary_amountfix_widea_500k_vwap_7bp_confirm_20130701_20260625.csv`
- `outputs/etf_loop/minute_execution_backtest/advice_replay_summary_amountfix_widea_2020_2026_compare_friend9_20200101_20260625.csv`
- `outputs/etf_loop/friend9_validation/friend9_partial_fill_summary_20200101_20260625.csv`
- `outputs/etf_loop/friend9_validation/friend9_partial_fill_report.md`

### 为什么比旧报告的 50万/100万结果低很多？

旧报告主要有三类口径，不能混用：

| 口径 | 代表报告 | 是否真实处理分钟未成交 | 结果特征 |
|---|---|---|---|
| 日线理想/近似容量 | `docs/etf_loop_pre_live_validation_phase1.md`、`phase2.md` | 否 | 年化较高，部分成交主要是统计/近似，不会把未成交真实留成现金或旧仓 |
| sanity replay | `diagnostic_shares_engine_ignoreblocks_widea_v3` | 否 | 用于验证复权价格和原引擎是否对齐，不能用于实盘收益预期 |
| amountfix realistic replay | 本报告最终口径 | 是 | 超过窗口容量的部分成交失败或部分成交，实际仓位偏离目标，收益显著打折 |

旧 Phase 1 的容量压力写的是“10万/100万/500万/1000万，5%参与率上限仍有 26%-31% 年化”，但那不是现在的分钟级 stateful replay。它没有把每天 09:35-10:30 窗口里没有成交的部分真实滚入后续账户状态，因此仍偏理想。

本轮重新确认：

- `WideA 2013-07-01 → 2026-06-25，50万，双边7bp，T+1 09:35-10:30 VWAP，10%窗口参与率`：年化 `15.37%`，Sharpe `0.89`，DD `-25.23%`。
- `WideA 2020-01-01 → 2026-06-25，50万，同口径`：年化 `26.74%`，Sharpe `1.12`，DD `-31.64%`。

所以“50万曾经很高”有两个原因：

- 区间不同：2020-2026 是策略强区间，WideA 日线理想年化约 `52.51%`；拉长到 2013-2026 后，真实执行后的年化自然下降。
- 执行口径不同：旧报告没有把分钟窗口容量不足导致的未成交真实反馈到账户；当前 amountfix realistic replay 会保留现金/旧仓，所以收益更保守。

这不等于“实盘一定亏成狗”。更准确的解释是：如果照单窗口一次性追求 100% 调仓，回测拿不到日线理想收益；必须用拆单、低资金、未成交保留现金/旧仓、模拟盘 reconciliation 来验证。当前 `midday_6x` 拆单结果比单窗口明显好，说明执行方式是关键变量。

### VWAP 和窗口参与率是什么意思？

`VWAP` 是成交量加权平均价：

```text
VWAP = sum(分钟价格 * 分钟成交量) / sum(分钟成交量)
```

本报告里的 `T+1 09:35-10:30 VWAP` 表示：

```text
T 日收盘后生成信号；
T+1 日 09:35 到 10:30 这个窗口里，用该窗口的 VWAP 作为理论成交价。
```

`窗口参与率` 是订单占该执行窗口成交额的比例：

```text
窗口参与率 = 订单金额 / 09:35-10:30 窗口成交额
```

如果设置 `10%窗口参与率`，含义是：

```text
单笔最多只成交该 ETF 在 09:35-10:30 窗口成交额的 10%。
超过部分不强行成交，保留为现金或旧仓。
```

这个约束会降低回测收益，但更接近实盘。没有这个约束时，回测等于假设你能在窗口 VWAP 无限量成交，容易高估 ETF 轮动策略。

### 成本压力：100万资金，T+1 09:35-10:30 VWAP，10%窗口参与率

| setting | 双边成本 | 年化 | Sharpe | DD | 失败率 | 容量受限 | 均滑点 |
|---|---:|---:|---:|---:|---:|---:|---:|
| WideA | 5bp | 14.01% | 0.81 | -28.24% | 33.20% | 25.17% | 11.66bp |
| WideA | 7bp | 13.86% | 0.80 | -28.32% | 33.13% | 25.17% | 11.89bp |
| WideA | 10bp | 13.54% | 0.79 | -27.00% | 33.69% | 25.17% | 12.36bp |
| WideA | 15bp | 12.91% | 0.76 | -23.73% | 34.29% | 25.17% | 13.28bp |
| WideA | 20bp | 12.37% | 0.73 | -24.35% | 34.51% | 25.17% | 14.20bp |
| F2_CAP_MA60 | 7bp | 14.06% | 0.63 | -63.85% | 32.98% | 19.16% | 10.36bp |

补充确认：`WideA 50万，双边7bp，同执行口径，2013-2026` 年化 `15.37%`，Sharpe `0.89`，DD `-25.23%`。

### 容量曲线：WideA，双边7bp，T+1 09:35-10:30 VWAP

| 资金 | 年化 | Sharpe | DD | 失败率 | 容量受限 | 仓位偏离 |
|---:|---:|---:|---:|---:|---:|---:|
| 5万 | 23.37% | 1.12 | -23.58% | 25.95% | 4.70% | 6.10% |
| 10万 | 21.47% | 1.07 | -25.95% | 27.91% | 8.24% | 5.10% |
| 30万 | 17.36% | 0.91 | -25.72% | 33.66% | 14.94% | 5.98% |
| 100万 | 13.86% | 0.80 | -28.32% | 33.13% | 25.17% | 7.02% |
| 300万 | 14.15% | 0.76 | -42.82% | 33.04% | 38.52% | 8.93% |
| 1000万 | 14.18% | 0.76 | -51.00% | 28.79% | 54.99% | 12.72% |

### 拆单验证：WideA，advice replay，双边7bp

| 资金 | 拆单方案 | 年化 | Sharpe | DD | 失败率 | 容量受限 | 均滑点 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 5万 | am_4x | 22.55% | 1.03 | -44.10% | 49.14% | 12.16% | 7.29bp |
| 5万 | am_tail_4x | 28.09% | 1.31 | -25.01% | 37.05% | 8.15% | 6.20bp |
| 5万 | midday_6x | 29.63% | 1.41 | -25.80% | 35.04% | 6.25% | 5.36bp |
| 100万 | am_4x | 14.97% | 0.76 | -47.47% | 49.01% | 40.31% | 13.55bp |
| 100万 | am_tail_4x | 22.18% | 1.13 | -25.10% | 43.82% | 33.62% | 12.75bp |
| 100万 | midday_6x | 25.47% | 1.39 | -24.01% | 41.14% | 27.70% | 11.40bp |

最终结论：

- `WideA` 的日线 alpha 仍存在，但单窗口真实执行会明显打折；按 100万、10%窗口参与率、双边7bp，年化约 `13.86%`，不应再按日线 `37%` 预期。
- 资金越小越接近日线策略：5万约 `23.37%` 年化，10万约 `21.47%`，30万后明显衰减。
- 拆单显著改善执行路径。`midday_6x` 是当前最合理的模拟盘执行候选：5万年化 `29.63%`、100万年化 `25.47%`，DD 约 `-24%` 到 `-26%`。
- `am_4x` 不建议作为默认执行，早盘集中成交导致回撤恶化，100万 DD 达 `-47.47%`。
- `F2_CAP_MA60` 在执行层仍可作为 baseline，但 DD 约 `-64%`，不适合作为默认模拟盘候选。

### 与 friend9 的同等压力对比

friend9 旧报告已经做了窗口参与率、拆单需求、溢价和流动性标记，但没有把未成交部分反馈到账户净值；因此旧 friend9 的 `47%` 年化不能直接和 WideA 的 realistic replay 比。

本次新增 stateful partial-fill replay：

```bash
source activate.sh && python runs/etf_loop/run_friend9_partial_fill_replay.py --start 2020-01-01 --end 2026-06-25 --capitals 50000,100000,500000,1000000 --fill-modes same_0955_open,next_day_open --max-participation 0.10
```

同区间 `2020-01-01 → 2026-06-25`、同样 `10%窗口参与率`：

| 策略 | 资金 | 执行 | 年化 | Sharpe | DD |
|---|---:|---|---:|---:|---:|
| WideA | 5万 | T+1 09:35-10:30 VWAP | 36.97% | 1.26 | -46.66% |
| WideA | 10万 | T+1 09:35-10:30 VWAP | 34.06% | 1.27 | -35.91% |
| WideA | 50万 | T+1 09:35-10:30 VWAP | 26.74% | 1.12 | -31.64% |
| WideA | 100万 | T+1 09:35-10:30 VWAP | 22.53% | 1.08 | -26.22% |
| friend9 | 5万 | same_0955_open partial-fill | 39.89% | 1.54 | -22.83% |
| friend9 | 10万 | same_0955_open partial-fill | 40.09% | 1.55 | -22.82% |
| friend9 | 50万 | same_0955_open partial-fill | 28.78% | 1.03 | -39.84% |
| friend9 | 100万 | same_0955_open partial-fill | 27.06% | 0.99 | -41.48% |

结论：

- 小资金 `5万-10万` 下，friend9 在同等压力下确实更强，收益更高、回撤也低于 WideA。
- `50万-100万` 下，friend9 收益仍略高，但回撤扩大到约 `-40%`，路径风险明显高于 WideA。
- friend9 可以作为高收益影子盘候选，但不应因为旧报告 `47%` 年化就直接实盘放大；必须用 partial-fill、拆单和真实盘口 reconciliation 继续验证。

以下为历史审计记录，保留用于说明 bug 演进，但不得作为最终结论引用。

2026-06-29 再审计更新：前面一版“长周期执行层验证”仍有价格口径 bug，旧的 `rerun_*_advice_replay` 表和本节下方 `WideA 年化 11%-20%` 的结论暂时废弃，不能用于判断策略实盘可行性。

已修复的问题：

- ETF Loop 日线 advice 使用复权价格/股数口径，本地分钟数据是原始价格；执行层现在支持 `--price-adjustment engine`，按日线引擎口径缩放分钟价格，并用日线引擎复权收盘价做持仓估值。
- 复权分钟数据下，`VWAP` 不能再用原始 `amount / volume`，否则会把未复权价格混进已复权账户。已改为 `sum(adjusted_close * volume) / sum(volume)`。
- `shares` replay 诊断模式现在按原 advice 股数重放；`--ignore-liquidity-blocks` 仅用于价格口径 sanity check，不再引入参与率冲击滑点。

修复后 sanity check：

```bash
source activate.sh && python runs/etf_loop/run_minute_execution_advice_replay.py --settings WideA --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25 --capitals 500000 --execution-modes open_0935,vwap_0935_1030,tail_vwap_1430_1455 --roundtrip-cost-bps 0,7 --commission-bp 0 --max-participation 999 --price-adjustment engine --replay-mode shares --ignore-liquidity-blocks --missing-price-policy skip --tag-suffix diagnostic_shares_engine_ignoreblocks_widea_v3
```

输出：

- `outputs/etf_loop/minute_execution_backtest/advice_replay_summary_diagnostic_shares_engine_ignoreblocks_widea_v3_20130701_20260625.csv`
- `outputs/etf_loop/minute_execution_backtest/advice_replay_report_diagnostic_shares_engine_ignoreblocks_widea_v3_20130701_20260625.md`

| setting | mode | 双边成本 | 年化 | CAGR | Sharpe | DD | failed |
|---|---|---:|---:|---:|---:|---:|---:|
| WideA | open_0935 | 0bp | 35.99% | 40.19% | 1.72 | -21.35% | 2.60% |
| WideA | open_0935 | 7bp | 35.29% | 38.75% | 1.57 | -21.96% | 5.90% |
| WideA | vwap_0935_1030 | 0bp | 35.87% | 40.16% | 1.75 | -23.24% | 2.31% |
| WideA | vwap_0935_1030 | 7bp | 35.47% | 39.10% | 1.60 | -24.59% | 3.54% |
| WideA | tail_vwap_1430_1455 | 0bp | 36.39% | 40.58% | 1.69 | -24.03% | 2.47% |
| WideA | tail_vwap_1430_1455 | 7bp | 34.46% | 37.46% | 1.50 | -25.49% | 5.41% |

成交价/advice 价比率也已恢复合理：`vwap_0935_1030` 中位数 `1.0001`、95% 分位 `1.0135`；`tail_vwap_1430_1455` 中位数 `1.0001`、95% 分位 `1.0255`。因此，之前 `WideA` 执行层年化大幅降到 `11%-20%` 不是策略本身结论，而是执行回放口径错误。下一步需要在修复后的 replay 上重新跑真实容量/冲击/拆单验证。

追加审计结论：本报告当前 advice replay 表仍不能作为最终策略结论。后续复查发现，ETF Loop 日线引擎输出的 advice price / shares 使用复权价格口径，而本地分钟执行层直接使用未复权分钟价格。典型例子是 `513100.SH` 在 2024-2026 年 advice price 约为分钟 raw price 的 `5x`，`159901.SZ` 则约为 `0.2x`。这会导致 replay 账户的现金、股数、卖出持仓和原日线引擎严重错位。因此，下面 `WideA` 年化被压到 `11%-20%` 的结果不能解释为“真实执行后策略只剩这些收益”，必须先修复分钟价格复权/股数换算口径再重跑。

重要更新：本报告早期版本引用的长周期分钟执行层表，使用了 `target_weight` 每日强制贴权重的执行层口径。复审后确认这会额外制造非原策略交易，放大换手、成本和容量压力。旧的“长周期执行方式 / 成本 / 容量压力”结果不能再作为最终结论。

本次已按新口径重跑完成：

```text
信号和交易动作：原引擎 etf_loop_advice_*.csv
执行层：只重放原引擎真实 BUY/SELL，不按每日 target_weight 强制再平衡
成交：T+1/T+2 分钟 VWAP/容量/滑点/涨跌停/停牌约束
脚本：runs/etf_loop/run_minute_execution_advice_replay.py
```

复现命令：

```bash
source activate.sh && python runs/etf_loop/run_minute_execution_advice_replay.py --settings WideA,F2_CAP_MA60 --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25 --capitals 1000000 --execution-modes vwap_0935_1030,twap_0935_1030,tail_vwap_1430_1455,open_0935,t2_open_0935 --roundtrip-cost-bps 7 --tag-suffix rerun_exec_modes_advice_replay
source activate.sh && python runs/etf_loop/run_minute_execution_advice_replay.py --settings WideA,F2_CAP_MA60 --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25 --capitals 1000000 --execution-modes vwap_0935_1030 --roundtrip-cost-bps 5,7,10,15,20 --tag-suffix rerun_cost_1m_advice_replay
source activate.sh && python runs/etf_loop/run_minute_execution_advice_replay.py --settings WideA,F2_CAP_MA60 --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25 --capitals 1000000,3000000,5000000,10000000,30000000 --execution-modes vwap_0935_1030 --roundtrip-cost-bps 7 --tag-suffix rerun_capacity_7bp_advice_replay
source activate.sh && python runs/etf_loop/run_minute_execution_advice_replay.py --settings WideA,F2_CAP_MA60 --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25 --capitals 1000000 --execution-modes t2_open_0935 --roundtrip-cost-bps 7 --tag-suffix rerun_t2_delay_fixed_advice_replay
```

输出文件：

- `outputs/etf_loop/minute_execution_backtest/advice_replay_summary_rerun_exec_modes_fixed_delay_20130701_20260625.csv`
- `outputs/etf_loop/minute_execution_backtest/advice_replay_report_rerun_exec_modes_fixed_delay_20130701_20260625.md`
- `outputs/etf_loop/minute_execution_backtest/advice_replay_summary_rerun_t2_delay_fixed_advice_replay_20130701_20260625.csv`
- `outputs/etf_loop/minute_execution_backtest/advice_replay_summary_rerun_cost_1m_advice_replay_20130701_20260625.csv`
- `outputs/etf_loop/minute_execution_backtest/advice_replay_summary_rerun_capacity_7bp_advice_replay_20130701_20260625.csv`

注意：`run_minute_execution_advice_replay.py` 初版没有应用 `EXECUTION_MODES["t2_open_0935"]["delay"]`，导致 `T+2 open` 和 `T+1 open` 完全相同。本次已修复该验证脚本，并单独重跑 `rerun_t2_delay_fixed_advice_replay`。这只影响新验证脚本，不影响原策略引擎。

`F2_CAP_MA60` / `WideA` / `Exph_v3_exp_looser` 的旧分钟执行验证记录仍可作为历史材料，但其中按 `target_weight` 每日贴权重的长周期表不得继续用于最终判断：

- `outputs/etf_loop/minute_execution_backtest/minute_execution_long_report_zh.md`
- `outputs/etf_loop/minute_execution_backtest/minute_execution_master_table.md`
- `outputs/etf_loop/minute_execution_backtest/minute_execution_master_table.csv`
- `outputs/etf_loop/minute_execution_backtest/minute_execution_report_F2_CAP_MA60_20130701_20260625.md`
- `outputs/etf_loop/minute_execution_backtest/minute_execution_report_WideA_20130701_20260625.md`
- `outputs/etf_loop/minute_execution_backtest/minute_execution_report_Exph_v3_exp_looser_20130701_20260625.md`

严格执行层验证后的结论和日线理想回测明显不同：

- `WideA` 仍然是候选策略里更值得做模拟盘的主线，但不能再按日线理想回测的 `37%+` 年化来预期。
- 在 `100万资金 + T+1 09:35-10:30 VWAP/TWAP + 双边7bp + 10%窗口参与率上限` 下，`WideA` 长周期年化约 `11.8%-11.9%`，Sharpe 约 `0.70-0.71`，DD 约 `-31.5%-32.2%`。
- 在 `100万资金 + T+1 14:30-14:55 VWAP` 下，`WideA` 年化 `19.10%`、Sharpe `1.11`、DD `-23.68%`，但容量受限率更高，不能只看收益。
- 在 `5万资金` 下，容量压力明显下降，`WideA + midday_6x` 的长周期拆单年化 `25.55%`，Sharpe `1.21`，DD `-35.15%`。
- `F2_CAP_MA60` 更适合作为 baseline，不适合作为当前最优模拟盘候选。`T+1 09:35-10:30 VWAP` 下它的 DD 达到 `-63.41%`，但尾盘执行可显著改善。
- `Exph_v3_exp_looser` 的旧 target-weight 执行表不再作为结论，需要按 advice replay 新口径补跑后再决定是否保留。
- `open_0935` 不建议作为默认执行方式，容量受限和回撤明显恶化。
- 修复延迟后，`T+2 open` 年化不一定低，但 Sharpe 很差、DD 接近 `-50%`，属于路径风险很高的压力测试结果，不应作为默认执行。

本次已补充两项验证：

- 拆单执行状态机：`outputs/etf_loop/minute_execution_backtest/split_child_execution_report.md`
- 溢价率逐笔审计：`outputs/etf_loop/premium_audit/candidate_premium_audit_report_CAP1000000.md`

拆单执行现在已有 `2013-07-01 → 2026-06-25` 长周期结果，见 `outputs/etf_loop/minute_execution_backtest/split_child_execution_summary_20130701_20260625.csv` 和 `split_child_execution_report.md`。

## 2. 已覆盖的验证项目

| 验证项 | 是否已覆盖 | 证据 |
|---|---|---|
| T+1 分钟执行 | 已覆盖 | `vwap_0935_1030`、`twap_0935_1030`、`tail_vwap_1430_1455`、`split_0935_1455` |
| T+2 延迟执行 | 已覆盖 | `t2_open_0935` |
| 开盘一次性成交压力 | 已覆盖 | `open_0935` |
| 成本压力 | 已覆盖 | 双边 `5bp / 7bp / 10bp / 15bp / 20bp` |
| 容量压力 | 已覆盖 | `100万 / 300万 / 500万 / 1000万 / 3000万`，另有 `5万` 小资金专项 |
| 参与率限制 | 已覆盖 | 默认单笔不超过执行窗口成交额 `10%` |
| 停牌/无分钟数据/无成交 | 已覆盖 | `NO_MINUTE_DATA`、`SUSPENDED_OR_NO_TURNOVER` |
| 涨跌停阻断 | 已覆盖 | `LIMIT_UP_BUY_BLOCKED`、`LIMIT_DOWN_SELL_BLOCKED` |
| 部分成交 | 已覆盖 | `PARTIAL_CAPACITY`、`PARTIAL_LOT_OR_CASH` |
| actual exposure 跟踪 | 已覆盖 | `actual_exposure`、`target_exposure`、`avg_abs_exposure_gap` |
| 连续滑点模型 | 已覆盖 | `sqrt` 模型和 `tiered` 模型对照 |
| 跨境/商品/开盘/价差惩罚 | 部分覆盖 | `cross_border_penalty_bp`、`commodity_penalty_bp`、`open_penalty_bp`、`spread_penalty_mult` |
| 逐笔净值溢价审计 | 已补充 | `outputs/etf_loop/premium_audit/candidate_premium_audit_report_CAP1000000.md` |
| 拆单执行状态机 | 已覆盖长周期 | `outputs/etf_loop/minute_execution_backtest/split_child_execution_report.md` |

## 3. 验证实现口径

主验证脚本：`runs/etf_loop/run_minute_execution_advice_replay.py`

被废弃的旧验证脚本口径：`runs/etf_loop/run_minute_execution_backtest.py` 会从每日 target weight 重建订单，并强制贴近目标权重。这适合测试“理想目标组合执行层”，但不等于 ETF Loop 原引擎真实交易行为，因此不能用于候选策略最终执行验证。

信号层不变：

```text
T 日收盘后由原 ETF Loop 日线引擎生成 advice BUY/SELL
不修改 ETF score
不修改候选池
不修改动态持仓逻辑
```

执行层 advice replay：

```text
T+1 或 T+2 读取本地 1分钟 ETF 数据
按 open / VWAP / TWAP / split 窗口生成可执行价格
卖出先于买入
只重放原引擎 advice 里的 BUY/SELL
不因为 target_weight 每日漂移而额外再平衡
检查窗口成交额、涨跌停、停牌、无成交
按最大参与率截断，允许部分成交
成交后记录 actual_exposure 与 target_exposure 偏差
```

滑点模型：

```text
单边佣金 = 1.5bp
基础滑点 = roundtrip_cost_bp / 2 - 1.5bp
```

分层冲击滑点：

| 订单额 / 执行窗口成交额 | 单边滑点下限 |
|---|---:|
| `<= 0.5%` | 基础滑点 |
| `0.5% - 1%` | 至少 5bp |
| `1% - 3%` | 至少 10bp |
| `> 3%` | 至少 20bp，并触发容量风险 |

连续冲击滑点：

```text
slippage = base_slippage + sqrt_k * sqrt(order_value / window_turnover)
```

额外惩罚：

```text
跨境 ETF 惩罚
商品 ETF 惩罚
09:35 开盘窗口惩罚
分钟 high-low/close 盘口价差代理惩罚
接近涨跌停容量折减
```

## 4. 复现命令

advice replay 长周期执行方式验证：

```bash
source activate.sh && python runs/etf_loop/run_minute_execution_advice_replay.py --settings WideA,F2_CAP_MA60 --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25 --capitals 1000000 --execution-modes vwap_0935_1030,twap_0935_1030,tail_vwap_1430_1455,open_0935,t2_open_0935 --roundtrip-cost-bps 7 --tag-suffix rerun_exec_modes_advice_replay
source activate.sh && python runs/etf_loop/run_minute_execution_advice_replay.py --settings WideA,F2_CAP_MA60 --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25 --capitals 1000000 --execution-modes t2_open_0935 --roundtrip-cost-bps 7 --tag-suffix rerun_t2_delay_fixed_advice_replay
```

advice replay 长周期成本和容量压力：

```bash
source activate.sh && python runs/etf_loop/run_minute_execution_advice_replay.py --settings WideA,F2_CAP_MA60 --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25 --capitals 1000000 --execution-modes vwap_0935_1030 --roundtrip-cost-bps 5,7,10,15,20 --tag-suffix rerun_cost_1m_advice_replay
source activate.sh && python runs/etf_loop/run_minute_execution_advice_replay.py --settings WideA,F2_CAP_MA60 --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25 --capitals 1000000,3000000,5000000,10000000,30000000 --execution-modes vwap_0935_1030 --roundtrip-cost-bps 7 --tag-suffix rerun_capacity_7bp_advice_replay
```

长周期拆单专项：

```text
outputs/etf_loop/minute_execution_backtest/split_child_execution_report.md
outputs/etf_loop/minute_execution_backtest/split_child_execution_summary_20130701_20260625.csv
```

## 5. 长周期默认 advice replay 结果

口径：

```text
区间：2013-07-01 到 2026-06-25
执行：T+1 09:35-10:30 VWAP
资金：100万
双边成本：7bp
最大参与率：10% 执行窗口成交额
```

| setting | 年化 | CAGR | Sharpe | DD | 完全失败率 | 容量受限 | 无分钟数据 | 无成交/停牌 | 涨跌停阻断 | 均滑点 | 均参与率 | 仓位偏离 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `WideA` | 11.76% | 10.92% | 0.70 | -32.20% | 35.15% | 25.97% | 2.13% | 1.04% | 0.02% | 11.96bp | 2.91% | 6.94% |
| `F2_CAP_MA60` | 13.05% | 11.12% | 0.58 | -63.41% | 34.40% | 19.32% | 1.88% | 0.98% | 0.04% | 10.43bp | 2.55% | 2.97% |

解释：

- 这张表和旧报告差异很大，原因是旧口径每天按 target weight 强制再平衡，新口径只重放原引擎 advice。
- `WideA` 的 DD 明显好于 `F2_CAP_MA60`，但完全失败率、容量受限率和仓位偏离都较高。
- `F2_CAP_MA60` 在该默认执行口径下 DD 达到 `-63.41%`，不适合作为默认模拟盘候选。
- “完全失败率”是按订单行统计的 `filled_value <= 0`，其中包含整手、现金、无分钟数据、无成交、容量截断后的零成交等情况；它不是券商层面的最终拒单率。

## 6. 执行方式敏感性

口径：

```text
区间：2013-07-01 到 2026-06-25
资金：100万
双边成本：7bp
```

| setting | 执行方式 | 年化 | Sharpe | DD | 完全失败率 | 容量受限 | 均滑点 | 均参与率 | 仓位偏离 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `F2_CAP_MA60` | `tail_vwap_1430_1455` | 18.44% | 0.99 | -32.41% | 29.08% | 32.29% | 12.96bp | 3.47% | 4.26% |
| `F2_CAP_MA60` | `twap_0935_1030` | 13.22% | 0.59 | -63.45% | 33.36% | 19.32% | 10.37bp | 2.53% | 2.98% |
| `F2_CAP_MA60` | `vwap_0935_1030` | 13.05% | 0.58 | -63.41% | 34.40% | 19.32% | 10.43bp | 2.55% | 2.97% |
| `F2_CAP_MA60` | `open_0935` | 11.28% | 0.63 | -35.53% | 33.77% | 58.94% | 18.00bp | 5.14% | 7.35% |
| `F2_CAP_MA60` | `t2_open_0935` | 17.13% | 0.44 | -47.98% | 31.34% | 58.63% | 17.90bp | 5.54% | 7.27% |
| `WideA` | `tail_vwap_1430_1455` | 19.10% | 1.11 | -23.68% | 29.96% | 40.55% | 14.25bp | 3.91% | 9.06% |
| `WideA` | `twap_0935_1030` | 11.94% | 0.71 | -31.53% | 35.36% | 25.97% | 11.97bp | 2.93% | 6.95% |
| `WideA` | `vwap_0935_1030` | 11.76% | 0.70 | -32.20% | 35.15% | 25.97% | 11.96bp | 2.91% | 6.94% |
| `WideA` | `open_0935` | 11.93% | 0.64 | -46.35% | 34.86% | 66.09% | 18.60bp | 5.47% | 12.85% |
| `WideA` | `t2_open_0935` | 19.60% | 0.49 | -49.54% | 31.56% | 66.41% | 18.53bp | 5.97% | 11.88% |

解释：

- `tail_vwap_1430_1455` 在 advice replay 口径下表现最好，但容量受限率也更高，且需要进一步用拆单状态机确认真实可成交性。
- `open_0935` 不适合作为默认执行：年化不一定最低，但回撤、容量受限、滑点和仓位偏离都明显恶化。
- `T+2 open` 修复 delay 后年化可能变高，但 Sharpe 很差、DD 接近 `-50%`，说明延迟改变了路径而不是提高了策略质量。
- 模拟盘默认建议从 `tail_vwap_1430_1455` 和 `midday/split` 拆单方案中选择，而不是 09:35 一次性追单。

## 7. 成本压力

口径：

```text
区间：2013-07-01 到 2026-06-25
资金：100万
执行：T+1 09:35-10:30 VWAP
```

| setting | 双边成本 | 年化 | Sharpe | DD | 完全失败率 | 容量受限 | 均滑点 | 均参与率 | 仓位偏离 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `F2_CAP_MA60` | 5bp | 13.36% | 0.60 | -63.47% | 33.71% | 19.32% | 10.04bp | 2.54% | 2.98% |
| `F2_CAP_MA60` | 7bp | 13.05% | 0.58 | -63.41% | 34.40% | 19.32% | 10.43bp | 2.55% | 2.97% |
| `F2_CAP_MA60` | 10bp | 12.75% | 0.57 | -63.35% | 34.73% | 19.32% | 10.97bp | 2.55% | 2.96% |
| `F2_CAP_MA60` | 15bp | 11.93% | 0.53 | -63.16% | 34.46% | 19.32% | 12.04bp | 2.49% | 2.92% |
| `F2_CAP_MA60` | 20bp | 11.33% | 0.50 | -63.48% | 35.63% | 19.32% | 13.23bp | 2.49% | 2.86% |
| `WideA` | 5bp | 11.94% | 0.71 | -31.82% | 35.24% | 25.97% | 11.70bp | 2.92% | 6.94% |
| `WideA` | 7bp | 11.76% | 0.70 | -32.20% | 35.15% | 25.97% | 11.96bp | 2.91% | 6.94% |
| `WideA` | 10bp | 11.48% | 0.69 | -32.56% | 36.00% | 25.97% | 12.47bp | 2.92% | 6.92% |
| `WideA` | 15bp | 11.01% | 0.66 | -32.93% | 35.77% | 25.97% | 13.27bp | 2.87% | 6.88% |
| `WideA` | 20bp | 10.79% | 0.64 | -32.56% | 36.65% | 25.97% | 14.25bp | 2.88% | 6.83% |

解释：

- 双边成本从 `7bp` 拉到 `20bp` 后，`WideA` 年化从 `11.76%` 降到 `10.79%`；成本敏感性存在，但不是主要矛盾。
- 主要矛盾是成交质量和容量约束：即使低成本，`WideA` 在 100万口径下完全失败率也约 `35%`，容量受限约 `26%`。
- `F2_CAP_MA60` 对成本更敏感，且默认早盘 VWAP 的长周期 DD 很差。

## 8. 容量压力

口径：

```text
区间：2013-07-01 到 2026-06-25
执行：T+1 09:35-10:30 VWAP
双边成本：7bp
最大参与率：10% 执行窗口成交额
```

| setting | 资金 | 年化 | Sharpe | DD | 完全失败率 | 容量受限 | 均滑点 | 均参与率 | 仓位偏离 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `F2_CAP_MA60` | 100万 | 13.05% | 0.58 | -63.41% | 34.40% | 19.32% | 10.43bp | 2.55% | 2.97% |
| `F2_CAP_MA60` | 300万 | 12.57% | 0.69 | -37.72% | 31.24% | 31.65% | 12.96bp | 3.46% | 4.40% |
| `F2_CAP_MA60` | 500万 | 12.17% | 0.71 | -28.27% | 27.68% | 37.93% | 14.02bp | 3.94% | 5.91% |
| `F2_CAP_MA60` | 1000万 | 12.24% | 0.75 | -29.01% | 24.35% | 47.09% | 15.55bp | 4.70% | 8.33% |
| `F2_CAP_MA60` | 3000万 | 13.94% | 0.76 | -35.38% | 19.89% | 61.35% | 17.57bp | 5.87% | 11.76% |
| `WideA` | 100万 | 11.76% | 0.70 | -32.20% | 35.15% | 25.97% | 11.96bp | 2.91% | 6.94% |
| `WideA` | 300万 | 13.67% | 0.70 | -45.58% | 35.31% | 39.53% | 14.21bp | 3.70% | 8.97% |
| `WideA` | 500万 | 14.04% | 0.72 | -45.36% | 32.24% | 46.95% | 15.20bp | 4.19% | 10.43% |
| `WideA` | 1000万 | 14.34% | 0.76 | -50.67% | 29.52% | 55.61% | 16.55bp | 4.84% | 12.69% |
| `WideA` | 3000万 | 15.87% | 0.75 | -51.96% | 21.81% | 69.05% | 18.26bp | 6.16% | 15.49% |

解释：

- 这张表不能解释为“资金越大越好”。资金变大后，容量截断会改变实际持仓路径，年化可能反而上升，但这不是可控 alpha。
- `WideA` 从 100万到 3000万，容量受限率从 `25.97%` 升到 `69.05%`，DD 从 `-32.20%` 恶化到 `-51.96%`，说明当前简单早盘 VWAP 执行不支持直接放大。
- `F2_CAP_MA60` 的大资金 DD 看似改善，是因为容量约束让它偏离原策略路径；这不是策略本身变稳。
- 如果初始资金只有 `5万`，容量压力会明显小很多，但整百份、现金残差和缺分钟数据仍会造成部分成交/失败记录。

## 9. 5万资金拆单专项

口径：

```text
区间：2013-07-01 到 2026-06-25
资金：5万
双边成本：7bp
订单：原引擎 advice replay
执行：逐子单拆单，最大参与率 10%
```

| setting | 拆单方案 | 年化 | Sharpe | DD | 完全失败率 | 容量受限 | 均滑点 | 均参与率 | 仓位偏离 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `WideA` | `am_4x` | 21.55% | 1.05 | -32.85% | 35.52% | 7.89% | 6.01bp | 1.51% | 6.19% |
| `WideA` | `am_tail_4x` | 24.76% | 1.18 | -32.57% | 33.29% | 5.17% | 5.09bp | 1.15% | 4.68% |
| `WideA` | `midday_6x` | 25.55% | 1.21 | -35.15% | 35.71% | 3.72% | 4.46bp | 0.89% | 4.32% |
| `F2_CAP_MA60` | `am_4x` | 19.79% | 1.02 | -32.85% | 42.12% | 6.31% | 5.40bp | 1.26% | 5.62% |
| `F2_CAP_MA60` | `am_tail_4x` | 21.52% | 1.09 | -32.57% | 40.31% | 4.04% | 4.58bp | 0.95% | 4.78% |
| `F2_CAP_MA60` | `midday_6x` | 21.52% | 1.09 | -35.15% | 44.09% | 2.93% | 4.07bp | 0.73% | 4.65% |

解释：

- 小资金下容量受限率显著低于 100万，但完全失败率仍然高，主要来自整手、现金残差、无分钟数据和无成交。
- `WideA` 小资金长周期拆单结果优于 `F2_CAP_MA60`。
- `midday_6x` 仓位偏离最低、滑点最低，但 DD 略高；`am_tail_4x` 是收益和回撤更均衡的方案。

## 10. 当前候选排序

严格执行层口径下，候选排序调整为：

| 排名 | 策略 | 用途 | 理由 |
|---:|---|---|---|
| 1 | `WideA + am_tail_4x/midday_6x` | 主模拟盘候选 | advice replay + 长周期拆单下收益最好；小资金更可控；需要接受 30%+ DD 压力 |
| 2 | `F2_CAP_MA60 + tail/midday` | baseline / 观察候选 | 默认早盘 VWAP 很差，但尾盘或拆单后可改善；适合作为对照影子盘 |
| 3 | `Exph_v3_exp_looser` | 待复核观察候选 | 旧严格执行表显示 Sharpe 较稳，但尚未按 advice replay 新口径重跑 |
| 4 | `friend9` | 高收益小资金影子盘 | 收益高，但容量、同日信号成交、溢价和订单拆分风险更大，需要独立验证 |

## 11. 模拟盘执行建议

`WideA` 默认模拟盘执行：

```text
T 日收盘后生成明日 advice BUY/SELL
T+1 执行，不追求每日贴 target_weight
卖出优先，买入其次
单笔不超过窗口预估成交额 10%，更保守可用 5%
未成交部分不追价，保留现金或旧仓
```

当前更推荐的执行窗口：

```text
保守默认：midday_6x，10:00-14:30 分 6 笔
收益/回撤折中：am_tail_4x，09:35-10:30 + 14:30-14:55 分 4 笔
仅做对照：14:30-14:55 VWAP
```

不建议：

```text
09:35 一次性按开盘价追单
T+2 延迟后再机械执行
无盘口保护的市价单
为了贴近日线目标仓位而强行补齐
```

## 12. 仍需补的严格验证

本次已补充溢价率逐笔审计和拆单执行验证。候选策略进入模拟盘前，剩余建议如下：

1. `Exph_v3_exp_looser advice replay`：旧表显示它可能更稳，但需要按本报告新 advice replay 口径重跑执行方式、成本和容量。
2. `高溢价交易 PnL 连接`：当前溢价审计只判断买入前可见溢价是否过高，下一步应把 `signal_premium >= 5%` 的交易连接到逐笔卖出收益，确认高溢价是否实际伤害收益。
3. `模拟盘实盘日志接入`：把 `am_tail_4x` / `midday_6x` 拆单计划写入每日 paper trading order plan，并在次日用真实盘口回填成交、未成交和滑点。
4. `真实盘口价差`：当前仍用分钟 OHLCV 估算价差和成交能力，实盘前最好接入 Level-1 bid/ask 或券商成交回报做 reconciliation。

这些缺口不会推翻现有“WideA 优于 F2_CAP_MA60”的严格执行层结论，但会影响可实盘资金上限和实际挂单规则。

## 13. 拆单执行验证

报告：`outputs/etf_loop/minute_execution_backtest/split_child_execution_report.md`

本次已完成长周期验证：

```text
区间：2013-07-01 到 2026-06-25
策略：WideA / F2_CAP_MA60
资金：5万 / 100万
成本：双边 7bp
拆单：am_4x / am_tail_4x / midday_6x
```

复现命令：

```bash
source activate.sh && python runs/etf_loop/run_split_order_execution_validation.py --settings WideA,F2_CAP_MA60 --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25 --capitals 50000,1000000 --schedules am_4x,am_tail_4x,midday_6x --roundtrip-cost-bp 7
```

结果摘要：

| setting | 资金 | 拆单方案 | 年化 | Sharpe | DD | 失败率 | 容量受限 | 仓位偏离 |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| `WideA` | 5万 | `am_4x` | 21.55% | 1.05 | -32.85% | 35.52% | 7.89% | 6.19% |
| `WideA` | 5万 | `am_tail_4x` | 24.76% | 1.18 | -32.57% | 33.29% | 5.17% | 4.68% |
| `WideA` | 5万 | `midday_6x` | 25.55% | 1.21 | -35.15% | 35.71% | 3.72% | 4.32% |
| `WideA` | 100万 | `am_4x` | 16.11% | 0.82 | -31.56% | 17.35% | 27.37% | 11.24% |
| `WideA` | 100万 | `am_tail_4x` | 18.63% | 0.91 | -31.26% | 13.65% | 22.97% | 8.33% |
| `WideA` | 100万 | `midday_6x` | 20.15% | 0.98 | -34.20% | 14.32% | 18.79% | 6.99% |
| `F2_CAP_MA60` | 5万 | `am_4x` | 19.79% | 1.02 | -32.85% | 42.12% | 6.31% | 5.62% |
| `F2_CAP_MA60` | 5万 | `am_tail_4x` | 21.52% | 1.09 | -32.57% | 40.31% | 4.04% | 4.78% |
| `F2_CAP_MA60` | 5万 | `midday_6x` | 21.52% | 1.09 | -35.15% | 44.09% | 2.93% | 4.65% |
| `F2_CAP_MA60` | 100万 | `am_4x` | 14.80% | 0.78 | -30.77% | 18.69% | 23.33% | 8.10% |
| `F2_CAP_MA60` | 100万 | `am_tail_4x` | 17.05% | 0.88 | -31.26% | 15.34% | 19.10% | 5.84% |
| `F2_CAP_MA60` | 100万 | `midday_6x` | 17.89% | 0.91 | -34.00% | 16.27% | 15.39% | 4.92% |

拆单结论：

- `am_4x` 仓位贴合明显差，不适合作为默认执行。
- `midday_6x` 收益和仓位偏离综合最好，但 DD 略高。
- `am_tail_4x` 回撤略低，更适合收益/回撤折中。
- 模拟盘建议优先用 `midday_6x`；如果特别担心午盘慢执行错过行情，可用 `am_tail_4x`。

## 14. 溢价率逐笔审计

报告：`outputs/etf_loop/premium_audit/candidate_premium_audit_report_CAP1000000.md`

口径：

```text
订单：100万资金，T+1 09:35-10:30 VWAP，双边7bp
溢价：signal_date 的收盘价 / 单位净值 - 1
无未来函数：只使用 T 日收盘后已知净值，不使用 T+1 日未知净值作为过滤依据
```

注意：货币 ETF 存在 `100元报价 / 1元净值` 尺度问题，审计脚本已按 `close > 10 且 unit_nav < 10` 自动除以 `100` 标准化，避免虚假 `9900%` 溢价。

结果摘要：

| setting | 范围 | 匹配率 | 平均溢价 | P95溢价 | 最大溢价 | >=5%单数 | >=5%成交额 |
|---|---|---:|---:|---:|---:|---:|---:|
| `WideA` | 全部买入 | 86.05% | 0.38% | 2.33% | 31.09% | 179 | 39,902,753 |
| `WideA` | 跨境/商品 | 86.05% | 1.20% | 8.04% | 31.09% | 178 | 39,301,359 |
| `F2_CAP_MA60` | 全部买入 | 85.67% | 0.35% | 2.26% | 31.09% | 199 | 27,904,382 |
| `F2_CAP_MA60` | 跨境/商品 | 85.67% | 1.14% | 7.52% | 31.09% | 199 | 27,904,382 |
| `Exph_v3_exp_looser` | 全部买入 | 86.11% | 0.38% | 2.35% | 31.09% | 181 | 24,784,236 |
| `Exph_v3_exp_looser` | 跨境/商品 | 86.11% | 1.22% | 8.05% | 31.09% | 180 | 24,678,575 |

溢价结论：

- 普通 ETF 买入的平均溢价不高，整体约 `0.35%-0.38%`。
- 风险集中在跨境/商品/QDII：平均约 `1.1%-1.2%`，P95 约 `7.5%-8.0%`，最高 `31.09%`。
- 实盘规则应增加：跨境/商品 ETF 若 `signal_premium >= 5%`，默认禁买或至少降权；`>= 8%` 应强制跳过，除非人工确认。
- 高溢价 Top 记录主要集中在 `513500.SH`、`513100.SH`、`159529.SZ` 等 QDII/跨境 ETF。
