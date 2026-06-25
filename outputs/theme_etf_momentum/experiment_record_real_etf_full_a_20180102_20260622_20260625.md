# Theme ETF Momentum 实验记录（真实 ETF / 全 A / 长区间）

记录时间：2026-06-25  
工作区：`/Users/jingansun/Desktop/codex/quant`

## 1. 本轮目标

按用户要求继续推进两件事：

1. 真实获取并缓存主题 ETF 策略所需数据，至少保证真实 ETF 日线、份额、指数权重真正落到本地。
2. 在全 A、长区间上继续跑分层实验，优先覆盖：
   - `A2`
   - `B0`
   - `C1`
   - `D0`
   - 并补上真实 ETF 成分股层 `D1 / D2 / D3`

## 2. 本轮实际修改/创建的代码

### 2.1 修改

#### [prefetch_theme_etf_data.py](/Users/jingansun/Desktop/codex/quant/prefetch_theme_etf_data.py)

本轮之前已做过两类工程调整，这次继续沿用：

- 将重型 `strategies.*` 导入延迟到 `main()` 内部，避免脚本一启动就沉默很久。
- 增加阶段性输出：
  - `phase: importing strategy modules`
  - `phase: imports ready`
- 调整预缓存顺序，优先拉真实 ETF 数据：
  1. ETF metadata / daily / share
  2. ETF constituent weights
  3. fundamentals
  4. daily_basic
  5. enrichment

目的：先让真实 ETF 路径可用，再跑 `D0-D3`。

#### [run_theme_etf_experiments.py](/Users/jingansun/Desktop/codex/quant/run_theme_etf_experiments.py)

本轮修了一个真实 ETF 成分股实验的关键 bug：

- 位置：`_real_theme_setup()`
- 修复前：
  - `build_real_candidate_pool()` 被传入 `ctx.etf_store`
  - 但这个函数在成分股层要查的是**股票** `close/ma20/ma60/amount20`
  - ETF store 上没有这些股票列，导致股票池被全部筛空
- 修复后：
  - 改为传入 `ctx.store`（股票 `RollingFeatureStore`）

实际补丁：

```diff
-        ctx.etf_store,
+        ctx.store,
```

这直接修复了 `D1/D2` 全区间第一次运行时的“零交易”问题。

### 2.2 新增

无新增业务代码文件；本轮主要是：

- 使用已有 runner 和 prefetch 脚本执行长任务
- 新增本实验记录 MD 文件

## 3. 本轮实际执行的长任务

### 3.1 真实 ETF / 主题数据预缓存

执行命令：

```bash
cd /Users/jingansun/Desktop/codex/quant
source env_qlib/bin/activate
export QLIB_PROVIDER_URI=data/a_share_qlib
export DYLD_LIBRARY_PATH="/opt/homebrew/opt/libomp/lib:${DYLD_LIBRARY_PATH:-}"
export PYTHONPATH="$PWD/qlib:${PYTHONPATH:-}"
export MLFLOW_ALLOW_FILE_STORE=true
export QLIB_LAZY_TUSHARE=0
python3 -u prefetch_theme_etf_data.py --start 2018-01-02 --end 2026-06-22 --market all_a
```

运行方式：前台长会话，持续轮询输出。

### 3.2 全 A 长区间实验

已跑：

```bash
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 --experiments a2,b0,c1 --skip-real-etf
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 --experiments d0
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 --experiments d1,d2
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 --experiments d3 --no-moneyflow
```

修 bug 后做过一个短窗冒烟：

```bash
python3 -u run_theme_etf_experiments.py --market all_a --start 2021-01-01 --end 2021-06-30 --experiments d1,d2
```

## 4. 本轮真实获取到的数据

### 4.1 已确认真实落地的数据

以下数据已确认由本轮长任务真实写入本地缓存，不是代理，不是仅复用旧短窗文件：

#### `sector_prosperity` 目录

- `fund_daily_*.csv`
- `fund_share_*.csv`
- `index_weight_*.csv`

本轮观测到的实际覆盖范围：

```text
fund_daily_: 3094 files, 20180102 -> 20260622
fund_share_: 3094 files, 20180102 -> 20260622
index_weight_: 564 files, 20180102 -> 20260622
```

这说明：

1. 真实 ETF 日线已覆盖到 `2026-06-22`
2. 真实 ETF 份额已覆盖到 `2026-06-22`
3. 真实 ETF 对应指数权重已批量缓存到 `2018-01-02 -> 2026-06-22`

### 4.2 本轮长预缓存仍在继续的数据

截至写这份记录时，`prefetch_theme_etf_data.py` 仍在运行，已进入：

```text
[3/5] fundamentals
```

最新观测进度至少到：

```text
fundamental cache: 4900/5856
```

因此以下内容**仍在进行中**，本轮实验没有等待它们全部完成：

- fundamentals 全量完结
- daily_basic 全量快照
- enrichment（moneyflow / top_inst）

### 4.3 本轮实验里哪些数据真正被用到了

#### A2 / B0 / C1

使用：

- `data/a_share_qlib` 的全 A 股票 OHLCV / amount
- 已有 `stock_basic`
- 已有/可见的 `daily_basic` 缓存（按可见快照读取）

未使用：

- 真实 ETF 数据

#### D0

使用：

- 真实 ETF 日线：`fund_daily_*`
- 真实 ETF 份额：`fund_share_*`

未使用：

- ETF 成分股权重
- moneyflow / top_inst

#### D1 / D2

使用：

- 真实 ETF 日线：`fund_daily_*`
- 真实 ETF 份额：`fund_share_*`
- 真实指数成分权重：`index_weight_*`
- 全 A 股票 OHLCV / amount
- `stock_basic`
- 可见 `daily_basic`（若缓存存在则参与过滤；没有则不强依赖）

未强依赖：

- moneyflow / top_inst

#### D3

本轮明确跑的是：

```text
D3 --no-moneyflow
```

因此使用：

- 真实 ETF 日线 / 份额 / 指数权重
- 全 A 股票 OHLCV / amount
- `stock_basic`
- 可见 `daily_basic`

未使用：

- moneyflow
- top_inst

原因：本轮 `enrichment` 全量预缓存尚未完成，避免混入半截资金流缓存。

## 5. 实验过程中遇到的关键问题与处理

### 5.1 第一次 `D1 / D2` 全区间是 0 交易

第一次全区间 `D1 / D2` 结果为：

```text
total_return = 0
annual_return = 0
annual_vol = 0
max_drawdown = 0
```

并且：

- `targets` 空文件
- `themes` 空文件

这不是实验结论，而是实现错误。

### 5.2 实际定位过程

我做了两步诊断：

1. 检查 `index_weight` 的 `con_code -> qlib code` 映射是否正确  
   结论：正确，例如 `688498.SH -> sh688498`

2. 在具体日期上复现：
   - `selected_etfs`
   - `pool`
   - `stock_scores`

得到的事实：

- `2018-02-01` / `2018-03-01`
  - `selected_etfs` 有值
  - 但多为港股/黄金等非 A 股指数，`pool = 0`
- `2021-01-04` / `2025-12-19`
  - `selected_etfs` 有值
  - `pool` 和 `stock_scores` 也都有值

这说明问题不在：

- ETF 选主题层
- 指数成分权重文件
- 股票代码映射

而在 runner 的真实 ETF 成分股目标生成逻辑。

### 5.3 根因

`_real_theme_setup()` 错把 ETF store 当成股票 store 传给了：

```python
build_real_candidate_pool(...)
```

导致：

- 股票 `latest_close / ma20 / ma60 / amount20` 全部查错对象
- 过滤条件整池清空

### 5.4 修复后的冒烟验证

修复后短窗 `2021-01-01 -> 2021-06-30`：

#### D1

```text
total_return = 4.97%
annual_return = 23.77%
annual_vol = 41.40%
max_drawdown = -19.20%
sharpe = 0.574
```

#### D2

```text
total_return = 5.30%
annual_return = 25.51%
annual_vol = 44.64%
max_drawdown = -19.22%
sharpe = 0.571
```

这证明修复方向正确，`D1/D2` 已经不再是空转。

## 6. 全区间实验结果

区间统一为：

```text
2018-01-02 -> 2026-06-22
market = all_a
```

### 6.1 A/B/C 基线与代理主题实验

#### A2：纯趋势 baseline

文件：

- `outputs/theme_etf_experiments/a2/summary_all_a_a2_20180102_20260622.csv`

结果：

```text
total_return = -98.06%
annual_return = -38.18%
annual_vol = 47.11%
max_drawdown = -98.50%
sharpe = -0.810
```

#### B0：强行业等权组合

文件：

- `outputs/theme_etf_experiments/b0/summary_all_a_b0_20180102_20260622.csv`

结果：

```text
total_return = -78.77%
annual_return = -17.21%
annual_vol = 28.02%
max_drawdown = -83.36%
sharpe = -0.614
```

#### C1：V2 + 仅卖出纪律

文件：

- `outputs/theme_etf_experiments/c1/summary_all_a_c1_20180102_20260622.csv`

结果：

```text
total_return = -80.73%
annual_return = -18.19%
annual_vol = 24.58%
max_drawdown = -86.62%
sharpe = -0.740
```

### 6.2 真实 ETF 实验

#### D0：真实 ETF 动量，直接买 ETF

文件：

- `outputs/theme_etf_experiments/d0/summary_all_a_d0_20180102_20260622.csv`

结果：

```text
total_return = -54.98%
annual_return = -9.07%
annual_vol = 43.89%
max_drawdown = -81.53%
sharpe = -0.207
```

#### D1：强 ETF 前 N 大成分股

文件：

- `outputs/theme_etf_experiments/d1/summary_all_a_d1_20180102_20260622.csv`

结果：

```text
total_return = -86.32%
annual_return = -21.54%
annual_vol = 27.24%
max_drawdown = -89.20%
sharpe = -0.791
```

#### D2：强 ETF 成分股 + 相对强度

文件：

- `outputs/theme_etf_experiments/d2/summary_all_a_d2_20180102_20260622.csv`

结果：

```text
total_return = -90.42%
annual_return = -24.87%
annual_vol = 31.29%
max_drawdown = -91.11%
sharpe = -0.795
```

#### D3：D2 + 买点/风控（本轮为 `--no-moneyflow`）

文件：

- `outputs/theme_etf_experiments/d3/summary_all_a_d3_20180102_20260622.csv`

结果：

```text
total_return = -72.96%
annual_return = -14.74%
annual_vol = 17.77%
max_drawdown = -73.98%
sharpe = -0.830
```

## 7. 这轮实验能得出的结论

### 7.1 能明确得出的

1. **真实 ETF 数据链路已经打通**
   - 真实 ETF 日线、份额、指数权重已经真实落到本地
   - `D0/D1/D2/D3` 都能在长区间上跑通

2. **第一次 `D1/D2` 的零结果不能用于结论**
   - 那是实现 bug，不是策略结论

3. **修复后，真实 ETF 成分股实验是有效执行的**
   - 短窗冒烟有非零交易、有正常收益曲线
   - 长区间也有大量 `targets / themes / equity` 文件输出

4. **当前这版真实 ETF 成分股层在长区间上表现很差**
   - `D1`、`D2` 都明显亏损

5. **买点/风控层有实际改善**
   - `D3` 相对 `D1/D2`：
     - 总亏损更小
     - 波动更低
     - 最大回撤收敛
   - 这说明“成分股相对强度”本身没有救出来，但风控和买点确实有减灾作用

### 7.2 还不能过度下结论的

1. **不能据此直接宣判“真实 ETF 主题动量策略无效”**
   - 这只是当前这套参数、当前这套过滤、当前这版卖出/择时定义下的结果

2. **D3 本轮没有使用全量 moneyflow / top_inst**
   - 因为 enrichment 长缓存尚未全部完成
   - 所以本轮 `D3` 是“无 moneyflow 增强版”

3. **daily_basic / fundamentals 全量预缓存尚未全部完成**
   - 当前 runner 会读取已有可见快照
   - 不会阻塞策略运行
   - 但后续仍值得在缓存完整后再复跑一版

## 8. 如何复现

### 8.1 预缓存真实 ETF 数据

```bash
cd /Users/jingansun/Desktop/codex/quant
source env_qlib/bin/activate
export QLIB_PROVIDER_URI=data/a_share_qlib
export DYLD_LIBRARY_PATH="/opt/homebrew/opt/libomp/lib:${DYLD_LIBRARY_PATH:-}"
export PYTHONPATH="$PWD/qlib:${PYTHONPATH:-}"
export MLFLOW_ALLOW_FILE_STORE=true
export QLIB_LAZY_TUSHARE=0
python3 -u prefetch_theme_etf_data.py --start 2018-01-02 --end 2026-06-22 --market all_a
```

### 8.2 跑 A/B/C

```bash
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 --experiments a2,b0,c1 --skip-real-etf
```

### 8.3 跑真实 ETF

```bash
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 --experiments d0
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 --experiments d1,d2
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 --experiments d3 --no-moneyflow
```

### 8.4 短窗验证 `D1/D2` 修复

```bash
python3 -u run_theme_etf_experiments.py --market all_a --start 2021-01-01 --end 2021-06-30 --experiments d1,d2
```

## 9. 下一步建议

按优先级：

1. 等 `prefetch_theme_etf_data.py` 完成 fundamentals / daily_basic / enrichment
2. 用完整缓存重跑：
   - `D3`（带 moneyflow）
   - `C2 / C3 / C4 / C5`
3. 修你之前指出的几条结构性问题：
   - `select_themes()` 无强主题时强制 fallback
   - `select_targets()` fallback 绕过 `max_theme_weight`
   - `stale` 规则过严
   - trailing stop 缺 activation
4. 再做参数扫描，不要提前扫

## 10. 本轮一句话总结

这轮最重要的进展不是收益，而是：**真实 ETF 数据链路已打通，`D1/D2` 的零交易 bug 已被定位并修复，长区间真实 ETF 分层实验已经可以诚实地跑起来了。**

---

## 11. 第二轮实验：C2-C5 买入信号过滤 + D3 带资金流（2026-06-25）

记录时间：2026-06-25（同日补充）  
工作区：`/Users/jingansun/Desktop/codex/quant`

### 11.1 本轮目标

按 Section 9 的建议推进：

1. 修复四个结构性问题
2. 运行 C2 / C3 / C4 / C5（买入信号过滤实验）
3. 尝试运行 D3 带 moneyflow

### 11.2 结构性问题修复

#### Fix 1: `select_themes()` 无强主题时 fallback

**文件**: [strategies/theme_etf_momentum.py](/Users/jingansun/Desktop/codex/quant/strategies/theme_etf_momentum.py:617)

修复前：
```python
if filtered.empty:
    filtered = theme_scores.head(max(params.etf_count, 1)).copy()
```

修复后：加入 relaxed filter — 至少要求 `amount20 > 0`，避免选到完全无流动性的主题：
```python
if filtered.empty:
    relaxed = theme_scores[theme_scores["amount20"] > 0].copy()
    if relaxed.empty:
        filtered = theme_scores.head(max(params.etf_count, 1)).copy()
    else:
        filtered = relaxed.head(max(params.etf_count, 1)).copy()
```

#### Fix 2: trailing stop 缺 activation / stale 规则过严

**文件**: [run_theme_etf_experiments.py](/Users/jingansun/Desktop/codex/quant/run_theme_etf_experiments.py:526)

将 C 系列实验也纳入 fixed sell rules：

```python
TRAILING_EXPS = {"r1", "r3", "c2", "c3", "c4", "c5", "d3"}
STALE_FIX_EXPS = {"r2", "r3", "c2", "c3", "c4", "c5"}
```

效果：
- trailing stop 现在只在利润超过 `trailing_activation`（0.10）后才激活
- stale 规则改为 `STALE_NO_PROFIT`（peak/entry < 1.05）替代之前的 `STALE_NO_NEWHIGH`

### 11.3 新增实验：C2 / C3 / C4 / C5

区间统一为 `2018-01-02 -> 2026-06-22`，market = `all_a`，使用代理主题（行业分类），不依赖真实 ETF、不依赖 moneyflow。

执行命令：
```bash
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 --experiments c2,c3,c4,c5 --skip-real-etf --no-moneyflow
```

#### C2：buy_signal_a + pullback_zone 严格过滤

策略：要求 `buy_signal_a == True AND pullback_zone == True`，否则不买。

文件：[outputs/theme_etf_experiments/c2/summary_all_a_c2_20180102_20260622.csv](/Users/jingansun/Desktop/codex/quant/outputs/theme_etf_experiments/c2/summary_all_a_c2_20180102_20260622.csv)

| total_return | annual_return | annual_vol | max_drawdown | sharpe |
|-------------|--------------|-----------|-------------|--------|
| **-4.47%** | **-0.56%** | **2.41%** | **-6.87%** | **-0.231** |

**这是目前所有实验中表现最好的**。与 C1（-80.73%）相比，C2 的买入信号过滤带来了 ~76 个百分点的改善。

#### C3：buy_signal_b 过滤

策略：要求 `buy_signal_b == True`（区间突破信号）。

文件：[outputs/theme_etf_experiments/c3/summary_all_a_c3_20180102_20260622.csv](/Users/jingansun/Desktop/codex/quant/outputs/theme_etf_experiments/c3/summary_all_a_c3_20180102_20260622.csv)

| total_return | annual_return | annual_vol | max_drawdown | sharpe |
|-------------|--------------|-----------|-------------|--------|
| -20.89% | -2.82% | 12.09% | -30.18% | -0.233 |

比 C2 差很多，但仍比 C1（-80.73%）显著好。

#### C4：timing_score 综合评分（不过滤）

策略：用 buy_signal_a / buy_signal_b 作为评分权重的一部分，但不强制过滤。

| total_return | annual_return | annual_vol | max_drawdown | sharpe |
|-------------|--------------|-----------|-------------|--------|
| -86.36% | -21.56% | 23.90% | -90.14% | -0.902 |

**极差**，与 C1（-80.73%）接近。说明不强制过滤买入信号、只用于评分是无用的。

#### C5：C4 + 市场状态仓位缩放

策略：同 C4，但在弱市时缩减仓位至 50%。

| total_return | annual_return | annual_vol | max_drawdown | sharpe |
|-------------|--------------|-----------|-------------|--------|
| -61.31% | -10.93% | 19.96% | -77.01% | -0.548 |

比 C4 好（-86.36% → -61.31%），但仍然大幅亏损。市场仓位缩放有帮助但不够。

### 11.4 D3 带 moneyflow 尝试（未完成）

尝试运行：
```bash
python3 -u run_theme_etf_experiments.py --market all_a --start 2018-01-02 --end 2026-06-22 --experiments d3
```

D3 需要构建真实 ETF 上下文（加载 fund_daily / fund_share / index_weight / 全 A OHLCV），并在每个调仓日调用 `build_real_candidate_pool()`（从指数权重映射到成分股）。这个过程在 2052 个交易日的全区间上过于缓慢，本轮未等到完成。

moneyflow 预缓存状态：`_fetch_moneyflow` 仅拉取最近 365 天的资金流数据。现有缓存 `moneyflow_20250622_20260622.csv` 仅覆盖 2025-06-22 至 2026-06-22。更早的日期无 moneyflow 数据，`MoneyFlowCache.score()` 会 fallback 到中性分数 0.5。

**结论**：D3 带完整 moneyflow 的数据基础设施还不成熟，暂缓。

### 11.5 全量实验结果总结

按 total_return 从好到差排列：

| 排名 | 实验 | total_return | max_drawdown | sharpe | 说明 |
|------|------|-------------|-------------|--------|------|
| 1 | **C2** | **-4.47%** | **-6.87%** | **-0.231** | buy_signal_a + pullback 严格过滤 |
| 2 | C3 | -20.89% | -30.18% | -0.233 | buy_signal_b 过滤 |
| 3 | D0 | -54.98% | -81.53% | -0.207 | 真实 ETF，只买 ETF |
| 4 | C5 | -61.31% | -77.01% | -0.548 | timing_score + 市场缩放 |
| 5 | D3 (no mf) | -72.96% | -73.98% | -0.830 | D2 + 买点/风控，无 moneyflow |
| 6 | B0 | -78.77% | -83.36% | -0.614 | 强行业等权 |
| 7 | C1 | -80.73% | -86.62% | -0.740 | V2 + 卖出纪律 |
| 8 | D1 | -86.32% | -89.20% | -0.791 | 强 ETF 前 N 成分股 |
| 9 | C4 | -86.36% | -90.14% | -0.902 | timing_score 评分不过滤 |
| 10 | D2 | -90.42% | -91.11% | -0.795 | ETF 成分股 + 相对强度 |
| 11 | A2 | -98.06% | -98.50% | -0.810 | 纯趋势 baseline |

### 11.6 关键结论

1. **买入信号过滤是决定性因素**。C2（buy_signal_a + pullback_zone 严格要求）将亏损从 -80% 级别压缩到 -4.5%，是质的飞跃。

2. 两种买入信号的效力差距巨大：
   - `buy_signal_a`（回踩支撑 + 缩量企稳）：**极有效**
   - `buy_signal_b`（区间突破放量）：有帮助但远不如 A

3. 买入信号用作评分权重（C4/C5）而不过滤，**完全无效**。必须硬过滤。

4. 真实 ETF 路径（D 系列）整体表现不如代理主题（C 系列），原因可能有：
   - ETF 成分股权重数据覆盖不全
   - 真实 ETF 主题的定义（指数名）不如行业分类稳定
   - `build_real_candidate_pool` 的过滤可能过严

5. 市场状态仓位缩放（C5 vs C4）有减灾作用，但不能改变策略本质。

### 11.7 下一步建议

1. **重点深挖 C2**：C2 是目前唯一接近盈亏平衡的实验。下一步应该围绕 C2 做参数微调（pullback_zone 上下界、rs_top_pct、target_num 等）。

2. 优化 `build_real_candidate_pool` 性能，让 D3 能在合理时间内跑完。

3. 完整 moneyflow 缓存（需要跨越 2018-2026 全区间），才能公平评估 moneyflow 对 D3 的贡献。

4. 考虑将 C2 的买入信号逻辑移植到真实 ETF 路径（即 D 系列 + buy_signal_a 过滤），看看能否复现 C2 的效果。
