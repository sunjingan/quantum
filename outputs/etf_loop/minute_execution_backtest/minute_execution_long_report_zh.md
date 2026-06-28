# ETF Loop 长周期分钟级执行回测中文报告

## 1. 本轮做了什么

- 回测区间：`2013-07-01` 到 `2026-06-25`。
- 信号层：仍使用现有日线 ETF Loop 候选策略，不改 ETF score、不改选池、不改动态持仓逻辑。
- 执行层：新增独立分钟级撮合，用本地 1 分钟 ETF 数据重新模拟成交。
- 默认实盘化假设：`T+1 09:35-10:30 VWAP`。
- 成本压力：双边 `5bp / 7bp / 10bp / 15bp / 20bp`。
- 容量压力：`100万 / 300万 / 500万 / 1000万 / 3000万`。
- 额外执行方式敏感性：`100万 + 7bp` 下比较 `09:35 open`、早盘 VWAP、早盘 TWAP、尾盘 VWAP、`T+2 09:35 open`。

## 2. 成交和滑点模型

分钟执行层不是用固定开盘价直接成交，而是按以下顺序处理：

1. `T` 日收盘后生成目标组合。
2. `T+1` 进入执行窗口。
3. 对每笔订单读取对应 ETF 的分钟窗口成交额和价格。
4. 如果买入触及涨停、卖出触及跌停、无分钟数据、窗口成交额为 0，则拒单或部分无法成交。
5. 单笔订单最大参与率默认限制为窗口成交额的 `10%`。
6. 成交价使用窗口 VWAP/TWAP 或指定分钟 open，再加真实化滑点。

滑点估计采用参与率分层：

| 订单额 / 执行窗口成交额 | 单边滑点下限 |
|---|---:|
| `<= 0.5%` | 基础滑点 |
| `0.5% - 1%` | 至少 5bp |
| `1% - 3%` | 至少 10bp |
| `> 3%` | 至少 20bp，并可能被 10% 最大参与率截断 |

这里的 `roundtrip_cost_bp` 是双边成本。单边佣金固定为 `1.5bp`，单边基础滑点为 `roundtrip_cost_bp / 2 - 1.5bp`，随后再和参与率分层滑点取较大值。

## 3. 长周期默认 VWAP + 7bp 容量曲线

| setting | initial_cash | annual_return | sharpe | max_drawdown | failed_rate | capacity_limited_rate | no_minute_data_rate | no_turnover_rate | limit_block_rate | avg_slippage_bp | p95_slippage_bp | avg_participation | p95_participation | avg_abs_exposure_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Exph_v3_exp_looser | 1000000 | 16.12% | 0.92 | -32.13% | 9.81% | 15.87% | 2.93% | 1.24% | 0.02% | 7.40 | 20.00 | 2.36% | 9.99% | 6.38% |
| Exph_v3_exp_looser | 3000000 | 13.79% | 0.80 | -32.59% | 8.23% | 25.31% | 2.79% | 1.19% | 0.04% | 9.63 | 20.00 | 3.48% | 10.00% | 9.06% |
| Exph_v3_exp_looser | 5000000 | 12.52% | 0.73 | -35.69% | 7.09% | 30.26% | 2.73% | 1.16% | 0.04% | 10.64 | 20.00 | 3.99% | 10.00% | 10.83% |
| Exph_v3_exp_looser | 10000000 | 10.48% | 0.62 | -40.08% | 6.22% | 36.69% | 2.62% | 1.12% | 0.04% | 12.00 | 20.00 | 4.71% | 10.00% | 12.96% |
| Exph_v3_exp_looser | 30000000 | 11.03% | 0.59 | -49.61% | 4.79% | 51.23% | 2.40% | 1.03% | 0.04% | 14.71 | 20.00 | 6.24% | 10.00% | 18.74% |
| F2_CAP_MA60 | 1000000 | 16.43% | 0.85 | -32.26% | 11.84% | 15.44% | 2.82% | 1.15% | 0.03% | 7.30 | 20.00 | 2.31% | 9.99% | 5.93% |
| F2_CAP_MA60 | 3000000 | 13.69% | 0.72 | -33.23% | 9.98% | 24.84% | 2.69% | 1.11% | 0.03% | 9.46 | 20.00 | 3.39% | 10.00% | 8.76% |
| F2_CAP_MA60 | 5000000 | 12.30% | 0.65 | -37.75% | 8.97% | 29.55% | 2.63% | 1.14% | 0.03% | 10.42 | 20.00 | 3.89% | 10.00% | 10.58% |
| F2_CAP_MA60 | 10000000 | 9.80% | 0.53 | -49.06% | 7.75% | 36.02% | 2.53% | 1.10% | 0.03% | 11.75 | 20.00 | 4.59% | 10.00% | 13.02% |
| F2_CAP_MA60 | 30000000 | 10.13% | 0.51 | -58.00% | 5.86% | 50.79% | 2.31% | 1.00% | 0.03% | 14.48 | 20.00 | 6.15% | 10.00% | 20.32% |
| WideA | 1000000 | 17.79% | 0.88 | -32.13% | 10.74% | 19.08% | 3.10% | 1.33% | 0.02% | 8.39 | 20.00 | 2.80% | 10.00% | 8.33% |
| WideA | 3000000 | 14.83% | 0.75 | -33.58% | 9.22% | 29.21% | 2.94% | 1.28% | 0.03% | 10.62 | 20.00 | 3.95% | 10.00% | 12.17% |
| WideA | 5000000 | 13.65% | 0.70 | -37.10% | 8.09% | 34.21% | 2.87% | 1.24% | 0.03% | 11.60 | 20.00 | 4.46% | 10.00% | 14.52% |
| WideA | 10000000 | 11.76% | 0.61 | -40.01% | 7.17% | 40.92% | 2.76% | 1.21% | 0.03% | 12.91 | 20.00 | 5.18% | 10.00% | 17.70% |
| WideA | 30000000 | 10.84% | 0.54 | -56.65% | 5.65% | 54.52% | 2.52% | 1.10% | 0.02% | 15.34 | 20.00 | 6.58% | 10.00% | 25.93% |

## 4. 长周期成本压力：100万资金 + 早盘 VWAP

| setting | roundtrip_cost_bp | annual_return | sharpe | max_drawdown | avg_slippage_bp | failed_rate |
| --- | --- | --- | --- | --- | --- | --- |
| Exph_v3_exp_looser | 5 | 16.56% | 0.95 | -31.80% | 6.87 | 9.64% |
| Exph_v3_exp_looser | 7 | 16.12% | 0.92 | -32.13% | 7.40 | 9.81% |
| Exph_v3_exp_looser | 10 | 15.44% | 0.88 | -32.60% | 8.21 | 9.63% |
| Exph_v3_exp_looser | 15 | 14.20% | 0.81 | -33.75% | 9.70 | 9.71% |
| Exph_v3_exp_looser | 20 | 12.73% | 0.73 | -36.26% | 11.30 | 9.76% |
| F2_CAP_MA60 | 5 | 16.88% | 0.88 | -31.84% | 6.76 | 11.69% |
| F2_CAP_MA60 | 7 | 16.43% | 0.85 | -32.26% | 7.30 | 11.84% |
| F2_CAP_MA60 | 10 | 15.72% | 0.81 | -32.99% | 8.14 | 11.62% |
| F2_CAP_MA60 | 15 | 14.34% | 0.74 | -34.21% | 9.67 | 11.90% |
| F2_CAP_MA60 | 20 | 12.82% | 0.66 | -35.45% | 11.28 | 12.15% |
| WideA | 5 | 18.20% | 0.90 | -31.80% | 7.92 | 10.61% |
| WideA | 7 | 17.79% | 0.88 | -32.13% | 8.39 | 10.74% |
| WideA | 10 | 17.09% | 0.85 | -32.60% | 9.11 | 10.53% |
| WideA | 15 | 15.75% | 0.78 | -33.88% | 10.43 | 10.76% |
| WideA | 20 | 14.17% | 0.70 | -36.53% | 11.88 | 10.80% |

## 5. 长周期执行方式敏感性：100万资金 + 7bp

| setting | execution_mode | annual_return | sharpe | max_drawdown | failed_rate | avg_abs_exposure_gap |
| --- | --- | --- | --- | --- | --- | --- |
| Exph_v3_exp_looser | open_0935 | 11.04% | 0.60 | -49.85% | 23.01% | 20.78% |
| Exph_v3_exp_looser | t2_open_0935 | 11.84% | 0.55 | -47.74% | 22.32% | 20.16% |
| Exph_v3_exp_looser | tail_vwap_1430_1455 | 14.48% | 0.81 | -36.95% | 9.05% | 8.14% |
| Exph_v3_exp_looser | twap_0935_1030 | 16.30% | 0.93 | -32.00% | 9.59% | 6.41% |
| Exph_v3_exp_looser | vwap_0935_1030 | 16.12% | 0.92 | -32.13% | 9.81% | 6.38% |
| F2_CAP_MA60 | open_0935 | 9.81% | 0.50 | -58.59% | 24.65% | 22.02% |
| F2_CAP_MA60 | t2_open_0935 | 11.53% | 0.51 | -51.42% | 23.55% | 21.96% |
| F2_CAP_MA60 | tail_vwap_1430_1455 | 15.55% | 0.80 | -37.69% | 11.28% | 7.87% |
| F2_CAP_MA60 | twap_0935_1030 | 16.61% | 0.86 | -32.08% | 11.73% | 5.96% |
| F2_CAP_MA60 | vwap_0935_1030 | 16.43% | 0.85 | -32.26% | 11.84% | 5.93% |
| WideA | open_0935 | 11.74% | 0.59 | -52.94% | 23.76% | 28.28% |
| WideA | t2_open_0935 | 11.54% | 0.50 | -52.83% | 22.84% | 27.48% |
| WideA | tail_vwap_1430_1455 | 16.76% | 0.81 | -36.98% | 9.38% | 11.07% |
| WideA | twap_0935_1030 | 17.89% | 0.89 | -32.00% | 10.69% | 8.39% |
| WideA | vwap_0935_1030 | 17.79% | 0.88 | -32.13% | 10.74% | 8.33% |

## 6. 拒单/失败原因拆解：默认 VWAP + 7bp

| setting | initial_cash | reason | rate |
| --- | --- | --- | --- |
| Exph_v3_exp_looser | 1000000 | PARTIAL_LOT_OR_CASH | 41.54% |
| Exph_v3_exp_looser | 1000000 | FILLED_OR_LOT_OK | 33.20% |
| Exph_v3_exp_looser | 1000000 | PARTIAL_CAPACITY | 15.87% |
| Exph_v3_exp_looser | 1000000 | LOT_TOO_SMALL | 5.20% |
| Exph_v3_exp_looser | 1000000 | NO_MINUTE_DATA | 2.93% |
| Exph_v3_exp_looser | 1000000 | SUSPENDED_OR_NO_TURNOVER | 1.24% |
| Exph_v3_exp_looser | 1000000 | LIMIT_UP_BUY_BLOCKED | 0.01% |
| Exph_v3_exp_looser | 1000000 | LIMIT_DOWN_SELL_BLOCKED | 0.01% |
| Exph_v3_exp_looser | 30000000 | PARTIAL_CAPACITY | 51.23% |
| Exph_v3_exp_looser | 30000000 | FILLED_OR_LOT_OK | 26.65% |
| Exph_v3_exp_looser | 30000000 | PARTIAL_LOT_OR_CASH | 17.79% |
| Exph_v3_exp_looser | 30000000 | NO_MINUTE_DATA | 2.40% |
| Exph_v3_exp_looser | 30000000 | SUSPENDED_OR_NO_TURNOVER | 1.03% |
| Exph_v3_exp_looser | 30000000 | LOT_TOO_SMALL | 0.86% |
| Exph_v3_exp_looser | 30000000 | LIMIT_DOWN_SELL_BLOCKED | 0.03% |
| Exph_v3_exp_looser | 30000000 | LIMIT_UP_BUY_BLOCKED | 0.01% |
| F2_CAP_MA60 | 1000000 | PARTIAL_LOT_OR_CASH | 45.42% |
| F2_CAP_MA60 | 1000000 | FILLED_OR_LOT_OK | 27.80% |
| F2_CAP_MA60 | 1000000 | PARTIAL_CAPACITY | 15.44% |
| F2_CAP_MA60 | 1000000 | LOT_TOO_SMALL | 7.34% |
| F2_CAP_MA60 | 1000000 | NO_MINUTE_DATA | 2.82% |
| F2_CAP_MA60 | 1000000 | SUSPENDED_OR_NO_TURNOVER | 1.15% |
| F2_CAP_MA60 | 1000000 | LIMIT_DOWN_SELL_BLOCKED | 0.02% |
| F2_CAP_MA60 | 1000000 | LIMIT_UP_BUY_BLOCKED | 0.01% |
| F2_CAP_MA60 | 30000000 | PARTIAL_CAPACITY | 50.79% |
| F2_CAP_MA60 | 30000000 | FILLED_OR_LOT_OK | 23.42% |
| F2_CAP_MA60 | 30000000 | PARTIAL_LOT_OR_CASH | 20.61% |
| F2_CAP_MA60 | 30000000 | NO_MINUTE_DATA | 2.31% |
| F2_CAP_MA60 | 30000000 | LOT_TOO_SMALL | 1.84% |
| F2_CAP_MA60 | 30000000 | SUSPENDED_OR_NO_TURNOVER | 1.00% |
| F2_CAP_MA60 | 30000000 | LIMIT_DOWN_SELL_BLOCKED | 0.02% |
| F2_CAP_MA60 | 30000000 | LIMIT_UP_BUY_BLOCKED | 0.01% |
| WideA | 1000000 | PARTIAL_LOT_OR_CASH | 39.05% |
| WideA | 1000000 | FILLED_OR_LOT_OK | 31.66% |
| WideA | 1000000 | PARTIAL_CAPACITY | 19.08% |
| WideA | 1000000 | LOT_TOO_SMALL | 5.76% |
| WideA | 1000000 | NO_MINUTE_DATA | 3.10% |
| WideA | 1000000 | SUSPENDED_OR_NO_TURNOVER | 1.33% |
| WideA | 1000000 | LIMIT_UP_BUY_BLOCKED | 0.01% |
| WideA | 1000000 | LIMIT_DOWN_SELL_BLOCKED | 0.01% |
| WideA | 30000000 | PARTIAL_CAPACITY | 54.52% |
| WideA | 30000000 | FILLED_OR_LOT_OK | 22.18% |
| WideA | 30000000 | PARTIAL_LOT_OR_CASH | 18.27% |
| WideA | 30000000 | NO_MINUTE_DATA | 2.52% |
| WideA | 30000000 | LOT_TOO_SMALL | 1.40% |
| WideA | 30000000 | SUSPENDED_OR_NO_TURNOVER | 1.10% |
| WideA | 30000000 | LIMIT_UP_BUY_BLOCKED | 0.01% |
| WideA | 30000000 | LIMIT_DOWN_SELL_BLOCKED | 0.01% |

## 7. 失败订单最多的 ETF：默认 VWAP + 7bp

| setting | initial_cash | ts_code | reject_reason | count |
| --- | --- | --- | --- | --- |
| Exph_v3_exp_looser | 1000000 | 511880.SH | LOT_TOO_SMALL | 504 |
| Exph_v3_exp_looser | 1000000 | 501018.SH | NO_MINUTE_DATA | 199 |
| Exph_v3_exp_looser | 1000000 | 150197.SZ | NO_MINUTE_DATA | 64 |
| Exph_v3_exp_looser | 1000000 | 511990.SH | LOT_TOO_SMALL | 64 |
| Exph_v3_exp_looser | 1000000 | 513310.SH | SUSPENDED_OR_NO_TURNOVER | 63 |
| Exph_v3_exp_looser | 1000000 | 150153.SZ | NO_MINUTE_DATA | 62 |
| Exph_v3_exp_looser | 1000000 | 160723.SZ | SUSPENDED_OR_NO_TURNOVER | 56 |
| Exph_v3_exp_looser | 1000000 | 150201.SZ | NO_MINUTE_DATA | 32 |
| Exph_v3_exp_looser | 1000000 | 160723.SZ | PARTIAL_CAPACITY | 31 |
| Exph_v3_exp_looser | 1000000 | 150228.SZ | NO_MINUTE_DATA | 30 |
| Exph_v3_exp_looser | 1000000 | 511360.SH | LOT_TOO_SMALL | 29 |
| Exph_v3_exp_looser | 1000000 | 510880.SH | LOT_TOO_SMALL | 28 |
| Exph_v3_exp_looser | 30000000 | 501018.SH | NO_MINUTE_DATA | 199 |
| Exph_v3_exp_looser | 30000000 | 150197.SZ | NO_MINUTE_DATA | 64 |
| Exph_v3_exp_looser | 30000000 | 513310.SH | SUSPENDED_OR_NO_TURNOVER | 63 |
| Exph_v3_exp_looser | 30000000 | 150153.SZ | NO_MINUTE_DATA | 62 |
| Exph_v3_exp_looser | 30000000 | 160723.SZ | SUSPENDED_OR_NO_TURNOVER | 57 |
| Exph_v3_exp_looser | 30000000 | 150201.SZ | NO_MINUTE_DATA | 32 |
| Exph_v3_exp_looser | 30000000 | 511880.SH | LOT_TOO_SMALL | 32 |
| Exph_v3_exp_looser | 30000000 | 160723.SZ | PARTIAL_CAPACITY | 31 |
| Exph_v3_exp_looser | 30000000 | 150228.SZ | NO_MINUTE_DATA | 30 |
| Exph_v3_exp_looser | 30000000 | 150152.SZ | NO_MINUTE_DATA | 26 |
| Exph_v3_exp_looser | 30000000 | 161226.SZ | SUSPENDED_OR_NO_TURNOVER | 24 |
| Exph_v3_exp_looser | 30000000 | 510880.SH | PARTIAL_CAPACITY | 19 |
| F2_CAP_MA60 | 1000000 | 511880.SH | LOT_TOO_SMALL | 632 |
| F2_CAP_MA60 | 1000000 | 501018.SH | NO_MINUTE_DATA | 205 |
| F2_CAP_MA60 | 1000000 | 511990.SH | LOT_TOO_SMALL | 107 |
| F2_CAP_MA60 | 1000000 | 511360.SH | LOT_TOO_SMALL | 105 |
| F2_CAP_MA60 | 1000000 | 150153.SZ | NO_MINUTE_DATA | 76 |
| F2_CAP_MA60 | 1000000 | 150197.SZ | NO_MINUTE_DATA | 64 |
| F2_CAP_MA60 | 1000000 | 513310.SH | SUSPENDED_OR_NO_TURNOVER | 63 |
| F2_CAP_MA60 | 1000000 | 160723.SZ | SUSPENDED_OR_NO_TURNOVER | 61 |
| F2_CAP_MA60 | 1000000 | 511010.SH | LOT_TOO_SMALL | 43 |
| F2_CAP_MA60 | 1000000 | 513500.SH | LOT_TOO_SMALL | 43 |
| F2_CAP_MA60 | 1000000 | 513100.SH | LOT_TOO_SMALL | 40 |
| F2_CAP_MA60 | 1000000 | 160723.SZ | PARTIAL_CAPACITY | 34 |
| F2_CAP_MA60 | 30000000 | 501018.SH | NO_MINUTE_DATA | 205 |
| F2_CAP_MA60 | 30000000 | 150153.SZ | NO_MINUTE_DATA | 76 |
| F2_CAP_MA60 | 30000000 | 160723.SZ | SUSPENDED_OR_NO_TURNOVER | 73 |
| F2_CAP_MA60 | 30000000 | 150197.SZ | NO_MINUTE_DATA | 64 |
| F2_CAP_MA60 | 30000000 | 513310.SH | SUSPENDED_OR_NO_TURNOVER | 63 |
| F2_CAP_MA60 | 30000000 | 511880.SH | LOT_TOO_SMALL | 50 |
| F2_CAP_MA60 | 30000000 | 150152.SZ | NO_MINUTE_DATA | 34 |
| F2_CAP_MA60 | 30000000 | 160723.SZ | PARTIAL_CAPACITY | 33 |
| F2_CAP_MA60 | 30000000 | 150201.SZ | NO_MINUTE_DATA | 32 |
| F2_CAP_MA60 | 30000000 | 150228.SZ | NO_MINUTE_DATA | 30 |
| F2_CAP_MA60 | 30000000 | 513500.SH | LOT_TOO_SMALL | 27 |
| F2_CAP_MA60 | 30000000 | 511990.SH | LOT_TOO_SMALL | 26 |
| WideA | 1000000 | 511880.SH | LOT_TOO_SMALL | 434 |
| WideA | 1000000 | 501018.SH | NO_MINUTE_DATA | 199 |
| WideA | 1000000 | 511990.SH | LOT_TOO_SMALL | 64 |
| WideA | 1000000 | 513310.SH | SUSPENDED_OR_NO_TURNOVER | 63 |
| WideA | 1000000 | 150197.SZ | NO_MINUTE_DATA | 62 |
| WideA | 1000000 | 150153.SZ | NO_MINUTE_DATA | 58 |
| WideA | 1000000 | 160723.SZ | SUSPENDED_OR_NO_TURNOVER | 56 |
| WideA | 1000000 | 510880.SH | LOT_TOO_SMALL | 41 |
| WideA | 1000000 | 160723.SZ | PARTIAL_CAPACITY | 33 |
| WideA | 1000000 | 150201.SZ | NO_MINUTE_DATA | 32 |
| WideA | 1000000 | 510500.SH | LOT_TOO_SMALL | 28 |
| WideA | 1000000 | 150228.SZ | NO_MINUTE_DATA | 26 |
| WideA | 30000000 | 501018.SH | NO_MINUTE_DATA | 199 |
| WideA | 30000000 | 513310.SH | SUSPENDED_OR_NO_TURNOVER | 63 |
| WideA | 30000000 | 150197.SZ | NO_MINUTE_DATA | 62 |
| WideA | 30000000 | 150153.SZ | NO_MINUTE_DATA | 58 |
| WideA | 30000000 | 160723.SZ | SUSPENDED_OR_NO_TURNOVER | 57 |
| WideA | 30000000 | 511880.SH | LOT_TOO_SMALL | 34 |
| WideA | 30000000 | 150201.SZ | NO_MINUTE_DATA | 32 |
| WideA | 30000000 | 160723.SZ | PARTIAL_CAPACITY | 31 |
| WideA | 30000000 | 150228.SZ | NO_MINUTE_DATA | 26 |
| WideA | 30000000 | 161226.SZ | SUSPENDED_OR_NO_TURNOVER | 24 |
| WideA | 30000000 | 150152.SZ | NO_MINUTE_DATA | 22 |
| WideA | 30000000 | 511990.SH | LOT_TOO_SMALL | 20 |

## 8. 关键结论

- 长周期分钟执行结果显著低于日线回测。核心原因不是单纯手续费，而是分钟级执行约束、早期分钟数据覆盖、无成交窗口和 actual exposure 偏离。
- 在 `T+1 09:35-10:30 VWAP + 7bp` 下，100万资金长周期年化大约在 `16%-18%`，明显低于日线回测里的 27%-37% 年化。
- 容量从 100万增加到 1000万后，收益和回撤明显恶化；3000万时最大回撤接近或超过 50%，当前执行模型下不能直接按 3000万规模实盘。
- 成本从双边 5bp 到 20bp 会持续伤害收益，但不是唯一问题。更大的问题是无分钟数据、执行窗口无成交额、lot/cash 残差和实际仓位无法贴近目标仓位。
- 长周期里 VWAP/TWAP 明显优于 09:35 单点成交和 T+2 延迟成交。2026 单年尾盘 VWAP 很强，但长周期并不稳定，不能据此把尾盘执行作为默认优化结论。
- `WideA` 在长周期默认 VWAP 下略好于 `F2_CAP_MA60` 和 `Exph_v3_exp_looser`，但三者都被分钟执行约束明显削弱。
- 这份结果应该被看作“执行可得性压力测试”，不是对日线 alpha 的否定。下一步必须先审计分钟数据覆盖和无成交窗口，再决定实盘默认执行模型。

## 9. 下一步建议

1. 按 ETF/date 审计 `NO_MINUTE_DATA` 和 `SUSPENDED_OR_NO_TURNOVER`，区分真实停牌/无流动性和本地数据缺失。
2. 对 2013-2017、2018-2020、2021-2023、2024-2026 分段跑分钟执行，判断是早期数据拖累还是策略本身容量不足。
3. 引入“未成交订单延续到下午/次日”的状态机，而不是当前窗口失败后直接放弃。
4. 对跨境 ETF、商品 ETF 单独建模溢价率和盘口风险，不能只用统一参与率滑点。
5. 在模拟盘中记录真实盘口价、实际可成交量、滑点和回测撮合差异，用来校准当前分层滑点模型。