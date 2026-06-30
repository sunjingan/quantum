# Friend 日内交易与池子替换实验总览

生成日期：2026-06-28

## 1. 结论先行

我们之前的判断需要更精确地表述：

- friend 原始 9-ETF 池 + friend 日内交易逻辑表现很强，2020-2026 年化约 47%-49%，Sharpe 约 1.65-1.73。
- 把 friend 的日内 Top momentum 逻辑换到我们的 F2_v3 / G2 PIT 池后，效果明显下降，尤其 Top1 回撤极大。
- 反过来，把我们的日线 ETF Loop 逻辑换成 friend 原始 9-ETF 池，也没有复现 friend 原始效果。
- 因此差异不是单一因素，而是“friend9 小而低相关的跨资产池 + 09:50 日内信号/成交 + Top1/Top3 机制”的组合效应。
- 我们当前候选 `F2_CAP_MA60` / `WideA` 在 2020-2026 的日线次日开盘执行下，风险收益比仍明显优于 friend-style F2/PIT 日内版本。

## 2. 复现命令

### 我们候选策略日线对照

```bash
source activate.sh && python - <<'PY'
from pathlib import Path
import sys
import pandas as pd
PROJECT = Path.cwd()
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "runs" / "etf_loop"))
from run_detailed_trade_log import build_params
from strategies.etf_loop_engine import run_and_save
out = PROJECT / "outputs" / "etf_loop" / "friend_intraday_comparison"
out.mkdir(parents=True, exist_ok=True)
rows = []
for setting in ["F2_CAP_MA60", "WideA"]:
    params = build_params(setting, "2020-01-01", "2026-06-25", "2020-01-01", 20)
    params.exp_tag = f"DAILYCTRL_{setting}_20200101_20260625"
    _, trades, audit = run_and_save(params, out)
    rows.append({"setting": setting, "period": "2020-2026", "execution": "T_close_signal_T1_open", "trade_count": len(trades), **audit["stats"]})
pd.DataFrame(rows).to_csv(out / "daily_candidate_controls_20200101_20260625.csv", index=False)
PY
```

### friend 原始 9-ETF 日内复现

```bash
source activate.sh && python runs/etf_loop/run_friend_intraday_replication.py --start 2020-01-01 --end 2026-06-25 --frequency 1min --adjust none --ranking-modes jq_auto,jq_simple --fill-modes same_0950_close,same_0951_open,same_0955_open,next_day_open
```

### friend-style 逻辑替换为 F2_v3 + G2 PIT 池

```bash
source activate.sh && python runs/etf_loop/run_friend_f2pit_strategy.py --start 2020-01-01 --end 2026-06-25
```

### 只换池子的单因素消融

```bash
source activate.sh && python runs/etf_loop/run_friend_pool_ablation.py --start 2020-01-01 --end 2026-06-25
```

### 我们 ETF Loop 逻辑换 friend9 池

```bash
source activate.sh && python runs/etf_loop/run_etf_loop_friend9_pool.py --start 2020-01-01 --end 2026-06-25
```

### G2 PIT 月度池从 2013 起重建

```bash
source activate.sh && python tools/data_prep/build_g2_pit_monthly_pool.py --start 2013-01-01 --end 2026-06-25
```

## 3. 我们候选策略日线对照

设置：

- 池子：`F2_CAP_MA60` = F2_v3 静态核心池 + G2 PIT capped 动态补漏 + MA60 过热惩罚。
- `WideA` = 在 `F2_CAP_MA60` 基座上加入 15d HS300 return 动态持仓规则。
- 信号：T 日收盘后。
- 成交：T+1 开盘。
- 成本：佣金 1.5bp/边 + 滑点 2bp/边，双边 7bp。
- 窗口：2020-01-01 到 2026-06-25。

| setting | execution | 年化 | Sharpe | DD | 总收益 | trades |
|---|---|---:|---:|---:|---:|---:|
| F2_CAP_MA60 | T close signal, T+1 open | 39.45% | 1.72 | -18.99% | 879.58% | 4438 |
| WideA | T close signal, T+1 open | 52.51% | 1.91 | -18.17% | 1953.30% | 3281 |

解读：

- 这是判断 friend-style F2/PIT 是否有价值的主参照。
- 在同样 2020-2026 窗口，`WideA` 明显优于 friend-style F2/PIT 的所有版本。

## 4. Friend 原始 9-ETF 日内复现

设置：

- 池子：friend 原始 9 只跨资产 ETF。
- 信号：前一交易日日线历史 + 当日 09:50 可见分钟价。
- 打分：friend weighted log-linear momentum × R2；`jq_auto` 使用 ATR 动态 lookback 20-60。
- 成交：同日 09:50/09:51/09:55 或次日开盘。
- 成本：JoinQuant 近似成本，固定价格滑点 0.001 元/份 + 基金佣金 2bp。

代码对照审计见：`outputs/etf_loop/friend_intraday_comparison/friend9_original_code_diff_audit.md`。
需要特别注意：`same_0950_close` 偏乐观，如果本地分钟时间戳代表完整 09:50 K 线收盘，则存在同分钟 bar lookahead 风险；更适合作为模拟盘近似的是 `same_0951_open` / `same_0955_open`。

| variant | rank | fill mode | 年化 | Sharpe | DD | 总收益 | trades |
|---|---|---|---:|---:|---:|---:|---:|
| simple25d | jq_simple | same_0950_close | 49.19% | 1.65 | -25.47% | 1521.58% | 417 |
| simple25d | jq_simple | same_0951_open | 49.45% | 1.66 | -25.23% | 1547.47% | 417 |
| simple25d | jq_simple | same_0955_open | 49.49% | 1.66 | -25.01% | 1548.89% | 417 |
| simple25d | jq_simple | next_day_open | 27.63% | 0.93 | -37.64% | 322.94% | 417 |
| full_friend_logic | jq_auto | same_0950_close | 46.96% | 1.67 | -24.30% | 1349.60% | 467 |
| full_friend_logic | jq_auto | same_0951_open | 47.07% | 1.67 | -24.45% | 1359.93% | 467 |
| full_friend_logic | jq_auto | same_0955_open | 47.71% | 1.69 | -24.62% | 1419.36% | 467 |
| full_friend_logic | jq_auto | next_day_open | 46.57% | 1.59 | -21.43% | 1283.93% | 467 |

解读：

- friend9 原始池在日内执行下确实很强。
- `simple25d` 对执行延迟敏感，次日开盘后年化从约 49% 降到 27.63%。
- `full_friend_logic` 在本地复现中对次日开盘没有崩，但它仍依赖 friend9 小池结构。
- 复现值低于对方声称的 66.04% 年化、-16.53% DD，差异可能来自 JoinQuant 精确成交、`current_data` 时间点、单位净值源、未公开细节。

## 5. Friend-style 逻辑套 F2_v3 + G2 PIT 池

设置：

- 池子：F2_v3 静态核心池 + 当月 G2 PIT 动态池。
- 信号：friend-style 09:50 日内信号。
- 成交：same-day 09:55 open 或 next-day open。
- 动态 lookback：ATR 20-60。
- 溢价惩罚：`unit_nav` 溢价 >= 5% 时 score 减 1。
- 近期大跌过滤：friend `con1/con2/con3`。
- 成本：双边 7bp。

| variant | fill mode | N | 年化 | Sharpe | DD | 总收益 | trades | dynamic buys |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| friend_f2pit_guarded | same_0955_open | 1 | 15.18% | 0.37 | -69.41% | 43.11% | 1029 | 112 |
| friend_f2pit_base | same_0955_open | 3 | 27.43% | 0.98 | -37.04% | 331.63% | 2109 | 255 |
| friend_f2pit_guarded | same_0955_open | 3 | 30.80% | 1.11 | -34.63% | 434.34% | 2041 | 136 |
| friend_f2pit_guarded | next_day_open | 1 | 18.69% | 0.45 | -60.77% | 74.55% | 1029 | 112 |
| friend_f2pit_base | next_day_open | 3 | 27.79% | 1.01 | -32.44% | 342.85% | 2107 | 255 |
| friend_f2pit_guarded | next_day_open | 3 | 31.87% | 1.17 | -32.24% | 474.54% | 2041 | 136 |

解读：

- friend-style Top1 套到 F2/PIT 池后几乎不可用，DD 接近 -60% 到 -70%。
- Top3 后明显改善，但仍不如我们的日线候选：`WideA` 2020-2026 年化 52.51%、Sharpe 1.91、DD -18.17%。
- 这说明 friend-style 不是“更高级的执行层”可以直接替换我们的候选策略，它和池子结构高度绑定。

## 6. 固定 friend-style 逻辑，只换池子

设置：

- 信号：09:50。
- 成交：同日 09:55 open。
- 打分：friend 动态 ATR lookback + premium + 近期大跌过滤。
- 成本：双边 7bp。
- 变化项只有池子。

| pool | logic | N | 年化 | Sharpe | DD | trades | dynamic buys |
|---|---|---:|---:|---:|---:|---:|---:|
| friend9 | friend_like | 1 | 48.45% | 1.71 | -24.69% | 465 | 0 |
| friend9 | guarded | 1 | 48.40% | 1.73 | -19.61% | 443 | 0 |
| friend9 | friend_like | 3 | 30.42% | 1.67 | -18.14% | 768 | 0 |
| f2_static | friend_like | 1 | 22.21% | 0.55 | -68.98% | 1035 | 0 |
| f2_static | friend_like | 3 | 35.68% | 1.29 | -30.08% | 1921 | 0 |
| f2_pit_union | friend_like | 1 | 20.59% | 0.49 | -64.83% | 1127 | 122 |
| f2_pit_union | guarded | 3 | 30.80% | 1.11 | -34.63% | 2041 | 136 |
| pit_pure | friend_like | 1 | 6.34% | 0.16 | -76.30% | 915 | 458 |
| pit_pure | friend_like | 3 | 18.71% | 0.76 | -32.46% | 1799 | 901 |

解读：

- friend9 强表现高度依赖小而分散的跨资产池。
- F2_v3 / PIT 这种大主题池套 Top1 追强会追到极端主题，回撤巨大。
- PIT 作为平权大池加入 friend-style 逻辑不是加分项。

## 7. 我们 ETF Loop 逻辑换 friend9 池

设置：

- 池子：friend 原始 9 只。
- 引擎：我们的日线 ETF Loop。
- 信号：T 日收盘。
- 成交：T+1 开盘。
- 成本：双边 7bp。

| variant | N | 年化 | Sharpe | DD | 总收益 | trades |
|---|---:|---:|---:|---:|---:|---:|
| base | 1 | 31.93% | 1.16 | -21.45% | 472.57% | 731 |
| ma60 | 1 | 30.54% | 1.12 | -26.12% | 428.01% | 777 |
| widea | 1 | 24.87% | 1.29 | -25.13% | 315.91% | 1653 |
| base | 5 | 19.29% | 1.18 | -19.29% | 204.48% | 1822 |
| ma60 | 5 | 19.29% | 1.18 | -19.29% | 204.48% | 1822 |
| widea | 5 | 24.87% | 1.29 | -25.13% | 315.91% | 1653 |

解读：

- 只把池子换成 friend9，不能复现 friend 原始高收益。
- friend9 的优势需要配合其 09:50 日内信号/执行和 Top1/Top3 机制。

## 8. 相关性过滤实验补充

设置：

- 对 `F2_CAP_MA60` / `WideA` 在 score 排序后做 250 日收益相关性过滤。
- `correlation_backfill=False`：高相关 ETF 被剔除后不强行补低分低相关 ETF。
- 结果显示该方案不能直接作为候选。

| setting | period | corr | lookback | backfill | 年化 | Sharpe | DD | trades |
|---|---|---:|---:|---|---:|---:|---:|---:|
| F2_CAP_MA60 | long | OFF | 250 | False | 29.01% | 1.47 | -18.98% | 7562 |
| F2_CAP_MA60 | long | 0.85 | 250 | False | 20.61% | 1.22 | -22.36% | 6854 |
| F2_CAP_MA60 | long | 0.90 | 250 | False | 22.55% | 1.26 | -22.77% | 7187 |
| F2_CAP_MA60 | 2026_nowarmup | OFF | 250 | False | 91.86% | 3.30 | -15.76% | 347 |
| F2_CAP_MA60 | 2026_nowarmup | 0.85 | 250 | False | 0.00% | 0.00 | 0.00% | 0 |
| F2_CAP_MA60 | 2026_nowarmup | 0.90 | 250 | False | 0.00% | 0.00 | 0.00% | 0 |
| WideA | long | OFF | 250 | False | 37.12% | 1.62 | -19.66% | 5877 |
| WideA | long | 0.85 | 250 | False | 29.68% | 1.45 | -26.74% | 5357 |
| WideA | long | 0.90 | 250 | False | 30.35% | 1.44 | -26.89% | 5589 |
| WideA | 2026_nowarmup | OFF | 250 | False | 115.15% | 3.39 | -16.33% | 288 |
| WideA | 2026_nowarmup | 0.85 | 250 | False | 0.00% | 0.00 | 0.00% | 0 |
| WideA | 2026_nowarmup | 0.90 | 250 | False | 0.00% | 0.00 | 0.00% | 0 |

解读：

- 不回填的 250 日相关性过滤会导致 2026 nowarmup 因 warmup 不足直接空仓。
- 长周期也明显损伤收益和回撤。
- 如果继续做相关性约束，应改成“桶/簇级预算”或“有 warmup 的相关性上限”，不能简单剔除后不补。

## 9. G2 PIT 月度池重建状态

新增脚本：

- `tools/data_prep/build_g2_pit_monthly_pool.py`

输出：

- `data/tushare_cache/sector_prosperity/etf_pool_G2_PIT_monthly_rebuilt_2013.pkl`
- `data/tushare_cache/sector_prosperity/etf_pool_G2_PIT_monthly_rebuilt_2013_detail.csv`
- `data/tushare_cache/sector_prosperity/etf_pool_G2_PIT_monthly_rebuilt_2013_report.md`
- `data/tushare_cache/sector_prosperity/etf_pool_G2_PIT_monthly_rebuilt_2013_compare_existing.csv`

重建规则：

- 从 2013-01-01 到 2026-06-25。
- 每个月最后一个本地 ETF 交易日构建月度池。
- 上市满 365 日。
- 过去 180 个有效交易记录计算平均成交额。
- 同 benchmark 去重。
- 8 桶配额：`defensive=4, commodity=5, overseas_us=4, hk_china=3, other_overseas=2, broad_a=6, style=6, theme=5`。
- `pool_score = 0.50 * canonical + 0.40 * liquidity_rank + 0.10 * maturity_rank`。
- 默认不覆盖生产用 `etf_pool_G2_PIT_monthly.pkl`。

重建结果：

| 项目 | 数值 |
|---|---:|
| 月份数 | 162 |
| 第一月 | 2013-01-31 |
| 最后一月 | 2026-06-22 |
| 池大小 min / median / max | 0 / 35 / 35 |
| 与旧 2018 起 pickle 重合月份 | 63 |
| mean Jaccard | 0.382 |
| median Jaccard | 0.388 |

需要注意：

- 这个脚本恢复了旧报告里的主要 G2 规则，但和旧 pickle 重合度不高。
- 说明旧 pickle 可能还有未恢复的细节，比如精确 canonical 列表、最低流动性阈值、候选 ETF 过滤、benchmark 标准化、不同数据版本。
- 暂时不能直接用 rebuilt pickle 替换当前生产 pickle；应先做一轮 rebuilt-pool 回测对比。

## 10. 待补 / 查漏补缺清单

1. 用 `etf_pool_G2_PIT_monthly_rebuilt_2013.pkl` 跑一版 `F2_CAP_MA60` / `WideA`，和当前生产 G2 PIT 做 A/B。
2. 恢复旧 G2 PIT 的精确 canonical code 列表和最低流动性阈值，解释 rebuilt 与旧 pickle Jaccard 偏低的原因。
3. 如果要继续相关性约束，改成“桶/簇预算”，而不是 250 日相关性直接剔除。
4. friend-style 可以继续作为独立策略研究，但不建议替换当前 ETF Loop 候选。
5. 对 friend9 的高收益，应继续做分钟成交容量、滑点、溢价、T+0 可交易性验证，否则不能直接迁移到实盘。
