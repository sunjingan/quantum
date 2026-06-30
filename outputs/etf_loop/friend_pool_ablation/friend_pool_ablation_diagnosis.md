# Friend-style 池子单因素消融诊断

生成日期：2026-06-28

## 实验目的

固定 friend-style 策略逻辑，只替换 ETF 池子，判断 friend 初始策略优于 F2/PIT 版本的原因是否主要来自池子。

固定项：

- 信号：09:50，使用前一交易日前的日线历史 + 当日 09:50 可见价格。
- 打分：friend 的加权 log-linear momentum × R2，ATR 动态 lookback 20-60 日。
- 成交：同日 09:55 open。
- 成本：佣金 1.5bp/边 + 滑点 2bp/边，双边 7bp。
- 样本：2020-01-01 到 2026-06-25。

变化项只包括 ETF 池子：

- `friend9`：原始 friend 9 只跨资产 ETF。
- `f2_static`：我们的 F2_v3 静态池。
- `f2_pit_union`：F2_v3 静态池 + G2 PIT 动态池。
- `pit_pure`：纯 G2 PIT 动态池。

## 关键结果

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

完整结果：

- `outputs/etf_loop/friend_pool_ablation/friend_pool_ablation_summary_20200101_20260625.csv`
- `outputs/etf_loop/friend_pool_ablation/friend_pool_ablation_report_20200101_20260625.md`

## 结论

1. friend 初始版本的强表现高度依赖 `friend9` 这个小而分散的跨资产池。

在相同逻辑下，`friend9` Top1 年化约 48.45%，Sharpe 1.71，DD -24.69%。这和之前复现 friend 9-ETF 初始版本的 49%左右年化非常接近，说明这次消融口径有效。

2. F2_v3 静态池不适合直接套 friend-style Top1 动量。

`f2_static` Top1 年化还有 22.21%，但 DD 达到 -68.98%，Sharpe 只有 0.55。说明问题不是完全没有收益，而是 friend-style Top1 会在大主题池里不断追最极端的主题 ETF，趋势反转时回撤极大。

3. F2_v3 静态池做 Top3 分散后明显改善，但仍不如 friend9 的风险收益比。

`f2_static` Top3 年化 35.68%，Sharpe 1.29，DD -30.08%。这说明“分散持有”能救一部分，但回撤仍高于 friend9。

4. PIT 动态池在 friend-style 逻辑下不是加分项。

`f2_pit_union` Top1 年化 20.59%，DD -64.83%；Top3 guarded 年化 30.80%，DD -34.63%。相比 `f2_static`，加入 PIT 没有提高收益质量，反而带来更多交易和更多动态标的买入。

5. 纯 PIT 动态池最差。

`pit_pure` Top1 年化 6.34%，DD -76.30%，说明 PIT 动态池本身非常噪声化，不能直接用 friend-style Top1 动量去轮动。

## 原因判断

friend-style 策略本质是高敏感度的 Top momentum 追随。它适合原始 `friend9` 这种小池子，因为池子内部资产差异大：美股、日股、德国、黄金、有色、原油、长债、红利低波、创业板。不同资产之间相关性较低，Top1 切换更像跨资产择强。

F2_v3 和 PIT 则主要是 A 股行业/主题 ETF。池子大、相关性高、主题轮动快，Top1 分数经常选到已经短期过热的主题。这个环境下 friend-style 会变成“追最热主题”，所以换手更高，买在高点/卖在低点的风险更高。

## 后续建议

- 不建议把 friend-style Top1 直接作为 F2/PIT 实盘候选。
- 如果继续研究 friend-style，应固定为 Top3 或 Top5，并加入持仓分散和分数差换仓门槛。
- PIT 动态池只能做小预算补漏，不应和静态池完全平权竞争。
- 对 F2/PIT，更适合我们当前 ETF Loop 的动态持仓/风险暴露框架，而不是 friend 的单仓追强框架。
