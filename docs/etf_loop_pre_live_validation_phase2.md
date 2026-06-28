# ETF Loop 上实盘前验证 Phase 2

日期：2026-06-26

本轮按要求继续执行：

- 交易点可视化优化：图片更宽、点更小。
- 执行模式压力：次日 VWAP、次日收盘、延迟 2 天、不利滑点。
- 更多基准对比。
- 收益归因。
- 信号稳定性。
- 模拟盘/实盘 reconciliation 工具。
- 实盘风控熔断规则草案。

Walk-forward 按要求留到最后。

## 交易点可视化

脚本：

```bash
source activate.sh
python analysis/etf_loop/visualize_etf_trade_points.py --top-n 3
python analysis/etf_loop/visualize_etf_trade_points.py --tags PERMHOLD_NASDAQ100_HOLDONLY --codes 513100.SH
python analysis/etf_loop/visualize_etf_trade_points.py --tags PERMHOLD_GOLD_HOLDONLY --codes 518880.SH
```

修改：

- 图片尺寸改为 `22 x 7`。
- 买卖点大小从 `42` 降到 `18`。
- ETF 曲线改为基于 `pct_chg` 的复权收益曲线，避免拆分/除权造成视觉断崖。

输出目录：

`outputs/etf_loop/figures/trade_points/`

## 执行模式压力

脚本：

```bash
source activate.sh
python runs/etf_loop/run_execution_mode_experiments.py
```

输出：

- `outputs/etf_loop/execution_mode_manifest.csv`
- `outputs/etf_loop/execution_mode_report.md`

配置：`F2_CAP_MA60`，窗口 `2018-01-01` 到 `2026-06-25`。

| label | 年化 | Sharpe | 最大回撤 | 结论 |
|---|---:|---:|---:|---|
| 次日开盘 | 37.02% | 1.60 | -21.58% | 当前理想执行假设 |
| 次日 VWAP | 34.41% | 1.50 | -22.44% | 仍可接受，但明显下降 |
| 次日收盘 | 33.85% | 1.44 | -23.58% | 下降更明显 |
| 延迟 2 天开盘 | 33.08% | 1.41 | -23.19% | 动量仍存在，但收益下降 |
| 延迟 2 天 VWAP | 27.80% | 1.20 | -20.82% | 明显削弱 |
| 次日开盘 + 20bp 不利滑点 | 16.62% | 0.72 | -39.85% | 成本/滑点高时不可接受 |
| 延迟 2 天 + 20bp 不利滑点 | 12.50% | 0.53 | -43.03% | 不适合实盘放大 |

结论：

- 策略不是只靠“次日开盘”才能赚钱，但执行价格和延迟会显著削弱收益。
- 20bp 级别不利滑点会让策略风险收益大幅恶化，这是实盘前必须重点验证的部分。

## 基准对比

脚本：

```bash
source activate.sh
python runs/etf_loop/run_benchmark_comparison.py
```

输出：

- `outputs/etf_loop/benchmark_comparison_manifest.csv`
- `outputs/etf_loop/benchmark_comparison_report.md`

注意：ETF 基准使用 `pct_chg` 复权收益矩阵，避免 ETF 拆分/除权污染。

| rank | benchmark | 年化 | Sharpe | 最大回撤 | 总收益 |
|---:|---|---:|---:|---:|---:|
| 1 | 货基 `511880` | 2.03% | 7.93 | -0.20% | 18.00% |
| 2 | 策略 `F2_CAP_MA60` 中性成本 | 31.65% | 1.37 | -22.30% | 955.92% |
| 3 | 黄金 `518880` | 15.59% | 0.97 | -28.54% | 220.13% |
| 4 | 纳指 `513100` | 22.78% | 0.95 | -28.57% | 403.59% |
| 5 | 标普 `513500` | 15.74% | 0.84 | -29.67% | 212.25% |
| 6 | F2 传统 20 日动量 Top3 | 24.29% | 0.74 | -36.56% | 363.75% |
| 7 | F2 传统 20 日动量 Top1 | 30.66% | 0.65 | -56.37% | 385.18% |
| 8 | F2 等权 | 10.06% | 0.62 | -23.61% | 103.52% |
| 9 | 创业板 ETF `159915` | 16.41% | 0.54 | -56.58% | 162.90% |
| 10 | 沪深300 ETF `510300` | 6.41% | 0.33 | -42.16% | 44.21% |
| 11 | HS300 指数 | 4.48% | 0.23 | -45.60% | 23.79% |

结论：

- 策略显著优于 F2 等权、传统 20 日动量 Top1/Top3 和宽基持有。
- 货基 Sharpe 极高但年化只有 2.03%，不应只按 Sharpe 排名。
- Qlib 本地指数数据目前只成功读取 HS300；中证全指、创业板指、中证1000等指数需要确认代码或补齐 Qlib 数据。

## 归因

脚本：

```bash
source activate.sh
python analysis/etf_loop/analyze_etf_loop_attribution.py
```

输出：

- `outputs/etf_loop/attribution_summary.csv`
- `outputs/etf_loop/attribution_report.md`

结果摘要：

| tag | round trips | 正收益年份 | 负收益年份 | top5 ETF PnL 占比 |
|---|---:|---:|---:|---:|
| `ABL_F2_CAP_MA_OVERHEAT_MR60_T114_P50` | 2786 | 13 | 1 | 52.90% |
| `ABL_F2O_CAP_SHORT_MOM_SM0p25` | 2728 | 13 | 1 | 59.87% |
| `EXEC_F2_CAP_MA60_OPEN_D1` | 2253 | 8 | 1 | 55.27% |

结论：

- top5 ETF 贡献 53%-60% 的已实现 PnL，收益集中度偏高。
- 这不是立即否定策略，但说明必须继续看 top 贡献 ETF 是否是后验主题暴露或少数极端交易。

## 信号稳定性

脚本：

```bash
source activate.sh
python analysis/etf_loop/analyze_signal_stability.py
```

输出：

- `outputs/etf_loop/signal_stability_manifest.csv`
- `outputs/etf_loop/signal_stability_report.md`

窗口：`2023-01-01` 到 `2026-06-25`

摘要：

- 交易日数：740。
- top1/top2 分数差中位数：29.37%。
- top1/top2 分数差 10 分位：3.35%。
- top1/top2 分数差小于 5% 的天数：107。
- top5 日换手中位数：33.33%。
- 2% 分数噪声下，top1 改变率中位数：0%。
- 2% 分数噪声下，top1 改变率 90 分位：11.10%。

结论：

- 大部分时间信号稳定，但有 107 天 top1/top2 分差低于 5%，这些天容易被噪声驱动。
- 应测试“分数差不足不换仓”或“新 ETF 分数必须高于当前持仓一定阈值”的规则。

## 模拟盘/实盘 Reconciliation

脚本：

```bash
source activate.sh
python analysis/etf_loop/reconcile_paper_vs_backtest.py
```

输出：

`outputs/etf_loop_paper/reconciliation_report.md`

当前没有持续模拟盘真实日志，因此 reconciliation 报告主要列出必须记录的字段。等 `runs/etf_loop/etf_loop_paper.py` 每日运行后，可把 paper orders/trades 与回测 target/trade CSV 按 `signal_date + trade_date + ts_code + action` 对齐。

## 风控熔断

文档：

`docs/etf_loop_live_risk_controls.md`

已写入：

- 数据缺失不交易。
- PIT 池日期异常停止交易。
- 单 ETF 仓位限制。
- 动态池权重和席位限制。
- 单笔参与率限制。
- 单日换手限制。
- 分数差不足不换仓。
- 单日亏损、组合回撤、连续亏损熔断。
- 实际滑点超过阈值暂停放大。
- 券商接口异常、行情异常、持仓不一致时停止交易。
- 人工 kill switch。

## 新发现的数据口径风险

在做基准可视化和基准动量时发现：

- Tushare `fund_daily.close` 对部分 ETF 存在拆分/除权断点。
- `pct_chg` 是连续收益口径，能解释这些断点。
- 本轮可视化和基准已经改为使用 `pct_chg` 复权收益曲线。

仍需处理：

- 主策略当前信号仍主要基于 `ETFDailyStore.close` 原始 close。
- 如果核心池内 ETF 存在拆分断点，动量、均线、ATR、止损会被污染。
- 下一步必须决定是否把策略信号价格切换为基于 `pct_chg` 构造的 adjusted close，同时保留真实 open/close 用于成交。

这项风险优先级高于继续调参。

## 当前未完成项

- Walk-forward 滚动测试。
- 主引擎 adjusted signal price 修复和重跑核心实验。
- PIT 池生成脚本审计。
- 分数差不足不换仓规则实验。
- 更多指数基准数据补齐。
- 持续模拟盘运行后的真实 reconciliation。
