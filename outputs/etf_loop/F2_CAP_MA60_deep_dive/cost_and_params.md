# F2_CAP_MA60 成本与参数清单

## 执行/成本设置
| 参数 | 值 |
|---|---|
| open_cost | 0.0001 |
| close_cost | 0.0001 |
| slippage | 0.0001 |
| use_dynamic_cost | False |
| participation_cap | None |
| execution_price_mode | open |
| execution_delay_days | 1 |

## 策略参数
| 参数 | 值 |
|---|---|
| 池 | F2_v3 44 ETFs 核心 + PIT 动态 capped 补漏 |
| dynamic_max_slots | 1 |
| dynamic_max_total_weight | 0.2 |
| dynamic_score_margin | 0.05 |
| dynamic_overheat_lookback | 20 |
| dynamic_overheat_threshold | 0.1 |
| dynamic_overheat_penalty | 0.5 |
| 持仓数 | 5 |
| lookback_days | 25 |
| mr_ma_period | 60 |
| mr_threshold | 1.14 |
| mr_penalty | 0.5 |
| short_momentum_threshold | 0.0 |
| ATR | ATR14 × 2.0 |
| 固定止损 | 0.95 |
| 执行 | 信号日收盘 → 次日开盘, 不fallback |
| 成本总览 | 双边佣金各 1bp + 固定滑点 1bp = 单边 2bp, 双边约 4bp |

## 成本说明

- 佣金 (open_cost/close_cost): 双边各 1bp (万分之一) = 0.01%
- 固定滑点 (slippage): 1bp (万分之一) = 0.01%
- **单边总成本: 佣金 1bp + 滑点 1bp = 2bp (万分之二)**
- 双边买卖合计: 佣金 2bp + 滑点 2bp = 4bp
- 没有启用分层流动滑点 (use_dynamic_cost=False)
- 没有启用参与度限制 (participation_cap=None)
- 执行价格: 信号日收盘后, 次日开盘价成交 (execution_price_mode=open, execution_delay_days=1)
- ADJCORE 使用的是连续复权 OHLC/VWAP 价格, 估值基于复权 close

## 图表修复

- 估值曲线使用 forward-fill 填补跨市场停牌/非交易日造成的缺口, 消除视觉断点
- 每张图表标题包含该 ETF 的累计 PnL 贡献 (FIFO 计算)