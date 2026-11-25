<div align="center">

# 📊 vlab — 资产配置回测实验室

### Zero-Dependency Portfolio Backtesting Lab

**诚实的回测实验室，而不是漂亮的回撤曲线。**

[![CI](https://github.com/aazh2026/vlab/actions/workflows/ci.yml/badge.svg)](https://github.com/aazh2026/vlab/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Deps](https://img.shields.io/badge/dependencies-0-success.svg)](https://pypi.org/)
[![Pages](https://img.shields.io/badge/demo-live-brightgreen.svg)](https://aazh2026.github.io/vlab/)

[English](#english) · [中文](#中文)

</div>

---

## ⚠️ 免责声明 / Disclaimer

> **本项目为量化研究与教学用途。所有结果均为基于历史数据的回测，不预示未来收益，不构成任何投资建议、要约或推荐。历史表现不代表未来表现。投资有风险，决策需自负。**
>
> *For research and education only. All results are backtests on historical data. Past performance does not predict future returns, and nothing here is investment advice, an offer, or a recommendation. Investing involves risk — you are solely responsible for your own decisions.*

---

## 这个项目在解决什么问题 / The problem

大多数"资产配置回测"的坑不在代码里，而在**口径**里。

我做了这个项目，起因是发现自己报出去的数字**被自己的引擎 bug 改过**，而且我事先完全不知道：

| 我最初报的数字 | 修复后的真实数字 | 差异 |
|---|---|---|
| 年化 6.78%，最大回撤 -13% | 见下方真实口径 | **回撤被低估了 4 倍** |
| "回测覆盖 2015–2026" | 实际用了 2001–2026 数据 | **穿越了时空** |

三个缺陷，每一个都足以让结论**完全反转**：

| 缺陷 | 后果 | 修复 |
|---|---|---|
| **跨市场休市日未对齐** | 休市日持仓被计为 0 → 测出 **-90% 回撤**、1618% 波动 | forward-fill 对齐 |
| **货币 ETF 收益蒸发** | 净值恒定 100、收益以份额派发 → "全现金"年化显示 **0%**（真实 1.67%） | 按 1.8% 年化合成 |
| **权重过度归一化** | 未上市资产的权重被挤到少数可交易资产 → 制造出虚假的 **-30% 单年跌幅** | 超额权重留在现金 |

**这些 bug 现在每一个都有专门的回归测试钉死**（`tests/test_regressions.py`，17 个测试，0.02 秒跑完）。

这不是"顺手加的测试"，这是这个项目**最有价值的资产**。因为如果这些测试不存在，下一个人随时可能把它们改回去，而你永远不会知道。

还有第 4 个问题，是**口径**而非代码：**窗口偏差**。用后来才上市的 ETF 从 2001 年开始回测，等于让未来的资产提前入场。所以本项目强制区分两个窗口：

- **窗口 A｜投资现实口径（2019-01-18 ~ 2026-11-25）** — 起点是所有可投标的均已上市的最早交易日。这是现实中能执行的口径，**对外结论的主口径**。
- **窗口 B｜指数代理长口径（2008-07-01 ~ 2026-11-25）** — 用中证红利等**指数**代理早期尚不存在的 ETF，覆盖 2008 金融危机。用于回答"这套配置在极端行情里到底扛不扛得住"。

**两个窗口的结论必须分开陈述，混用即为误导。**

---

## 真实结论 / What the backtest actually says

初始本金 100 万元，佣金 5bp + 滑点 3bp，月度调仓。

**窗口 A（2019–2026，可执行口径）**

| 策略 | 年化 | 最大回撤 | 夏普 | 期末净值 |
|---|---|---|---|---|
| 纯标普500 | **13.75%** | -33.90% | 0.64 | ¥2,934,283 |
| 纯黄金 ETF | 11.68% | -39.73% | 0.60 | ¥2,517,320 |
| 纯红利低波 | 11.35% | -16.53% | 0.60 | ¥2,456,330 |
| 12 资产等权 | 10.15% | -16.34% | **0.97** | ¥2,243,635 |
| **Steve 配置 + 黄金择时** | 8.15% | **-8.90%** | 0.89 | ¥1,924,031 |
| **Steve 配置（静态）** | 7.85% | **-8.97%** | 0.84 | ¥1,880,971 |
| 60/40 组合 | 6.63% | -10.47% | 0.57 | ¥1,709,619 |
| 纯沪深300 ETF | 4.93% | -44.64% | 0.16 | ¥1,494,993 |

**窗口 B（2008–2026，含金融危机）**

| 策略 | 年化 | 最大回撤 | 夏普 | 期末净值 |
|---|---|---|---|---|
| 纯标普500 | **10.56%** | -47.27% | 0.46 | ¥7,144,859 |
| 12 资产等权 | 7.83% | -16.34% | 0.77 | ¥4,375,060 |
| 7 资产等权（指数代理） | 5.18% | -32.16% | 0.30 | ¥2,691,229 |
| **Steve 配置 + 黄金择时** | 4.86% | **-9.39%** | 0.56 | ¥2,534,940 |
| **Steve 配置（静态）** | 4.77% | **-9.96%** | 0.54 | ¥2,490,449 |
| 纯沪深300 ETF | 5.47% | -52.89% | 0.17 | ¥2,840,483 |

### 结论说实话就是

**这套配置的价值是压回撤，不是提收益。**

- 窗口 B 跨 18 年含 2008 危机：Steve 配置回撤 **-9.96%**，同期纯沪深300 是 **-52.89%**、纯标普500 是 **-47.27%**
- 代价是年化少赚 **5.7 个百分点**（4.77% vs 10.56%）
- **黄金分档择时只小幅改善**（年化 +0.3pp），回撤几乎没变
- **MA200 趋势风控层无效**，对 2008 年回撤无任何改善

如果你要的是最高收益，这套配置是错的答案。如果你要的是"18 年不被打爆"，它可能是。

---

## 特性 / Features

- **零第三方依赖** — 核心只用 Python 标准库，`git clone` 就能跑
- **零 CDN 前端** — 面板是单个 HTML + 手写 SVG，断网也能打开
- **真实行情数据** — 腾讯 ifzq（A股/港股）+ 新浪（美股全历史），自动分页 + 本地缓存
- **完整绩效指标** — CAGR / Vol / Sharpe / Sortino / Calmar / 最大回撤区间定位 / 年度收益链式还原
- **双窗口诚实口径** — 强制区分"可执行"与"长周期代理"
- **回归测试钉死每个历史缺陷** — 17 个测试，0.02 秒
- **交互式面板** — 13 策略同屏净值/回撤对比，图例可开关，表格可排序，中英双语
- **CI 覆盖 Python 3.9–3.12** + GitHub Pages 静态站

---

## 快速开始 / Quick start

```bash
git clone https://github.com/aazh2026/vlab.git
cd vlab

# 跑测试（无需安装依赖，无需联网）
python3 -m unittest discover -s tests -v

# 抓取行情数据（约 7MB，缓存到 data/）
PYTHONPATH=src python3 -m vlab fetch

# 生成回测报告
PYTHONPATH=src python3 -m vlab report

# 启动本地面板 → http://127.0.0.1:8765
PYTHONPATH=src python3 -m vlab serve
```

**在线体验**：<https://aazh2026.github.io/vlab/>

---

## 作为库使用 / Use as a library

```python
from vlab import engine, strategies, windows

series = engine.load_series()
dates  = engine.trading_dates(series)
mat    = engine.align(series, dates)

# 切到"投资现实口径"
D, M = windows.slice_window(dates, mat, "A")

# 跑策略
res = engine.backtest(strategies.STRATEGIES["steve"].fn, M, D,
                       start_cash=1_000_000, fee_bps=5, slip_bps=3)
metrics = engine.metrics_of(res["curve"])
print(engine.fmt(metrics, "Steve"))
```

写自己的策略只需返回一个函数：

```python
def my_strategy(date, mat, dates, i):
    # 只能看到当日及之前的数据
    return {"sh512890": 0.5, "sh518880": 0.3, "sh511990": 0.2}
```

---

## 项目结构 / Layout

```
src/vlab/
  engine.py       回测引擎：权重归一化、成交、现金守恒
  metrics.py      指标计算：CAGR/Sharpe/Sortino/回撤区间/年度收益
  strategies.py   策略注册表
  windows.py      双窗口定义与切片
  datasource.py   多源行情抓取（腾讯 → 新浪 → Yahoo）
  report.py       报告构建（含免责声明、方法论、缺陷清单）
  web/            面板：server.py (标准库 HTTP) + index.html (自绘 SVG)
tests/
  test_regressions.py   三个历史缺陷 + 现金守恒 + 无未来信息
scripts/
  build_site.py   构建 GitHub Pages 静态站
```

---

## 已知局限 / Known limitations

诚实清单，面板里也有：

| 项 | 说明 |
|---|---|
| **美股为全收益近似** | 按固定年化分红率调整原始价格，非精确股息再投资，会略微高估美股长周期收益 |
| **成交价取调仓日收盘价** | 不含日内择时能力，未建模开盘/收盘价差之外的市场冲击 |
| **黄金分档择时收益有限** | 年化仅 +0.3pp，回撤改善不明显；复杂度可能不划算 |
| **MA200 趋势层已验证无效** | 保留在代码中仅作对照，建议实际使用中移除 |
| **网格搜索最优解过拟合** | 样本外衰减 -0.45，该结论已弃用 |
| **ETF 早期历史依赖指数代理** | 窗口 B 用指数代替尚未上市的 ETF，属代理而非真实可投 |
| **不含税费** | A 股红利税、基金赎回费、股息预扣税均未建模 |

---

## 贡献 / Contributing

见 [CONTRIBUTING.md](CONTRIBUTING.md)。核心要求只有一条：

> **宁可让一个结论被推翻，也不要让一个错误结论留在报告里。**

任何改动引擎行为的 PR，都必须同时更新回归测试，并说明这个改动影响了哪些已有结论。

---

## License

MIT © 2026 [aazh2026](https://github.com/aazh2026)

---

# English

## ⚠️ Disclaimer

> **For research and education only. All results are backtests on historical data. Past performance does not predict future returns, and nothing here constitutes investment advice, an offer, or a recommendation. Investing involves risk — you are solely responsible for your own decisions.**

## What this is

A zero-dependency backtesting lab for a multi-asset allocation, built around one idea: **honesty beats a pretty equity curve.**

Three engine bugs were found and fixed during development. Each one was severe enough to *invert* the conclusions:

| Bug | Impact | Fix |
|---|---|---|
| Cross-market holidays not aligned | -90% drawdown, 1618% volatility | forward-fill alignment |
| Money-market yield evaporated | "All cash" showed 0% CAGR | synthesize 1.8% APY |
| Weights over-normalised | fake -30% year in 2008 | leave excess weight in cash |

Every one of them now has a dedicated regression test. That test suite is the most valuable artifact in this repo.

The project also enforces **two separate evaluation windows** so that results are never mixed misleadingly:

- **Window A (2019-01-18 → 2026-11-25)** — "Investable Reality": starts when every tradable asset already exists. This is the primary, executable measure.
- **Window B (2008-07-01 → 2026-11-25)** — "Index-Proxy Long Window": uses indices to stand in for ETFs that did not exist yet, so the 2008 crisis is covered.

## Headline result

**This allocation's value is drawdown control, not return maximisation.**

Across an 18-year window containing the 2008 crisis, the tested allocation holds drawdown to **-9.96%**, versus **-52.89%** for the CSI 300 ETF and **-47.27%** for the S&P 500. The price is **5.7 percentage points of annual return** (4.77% vs 10.56%).

## Quick start

```bash
python3 -m unittest discover -s tests -v      # tests, no deps, no network
PYTHONPATH=src python3 -m vlab fetch          # download quotes (~7MB, cached)
PYTHONPATH=src python3 -m vlab report         # build the report
PYTHONPATH=src python3 -m vlab serve          # dashboard on :8765
```

Live demo: <https://aazh2026.github.io/vlab/>

## License

MIT © 2026 aazh2026
