# -*- coding: utf-8 -*-
"""vlab — 零依赖的资产配置回测实验室 / Zero-dependency portfolio backtesting lab.

设计原则
--------
1. 诚实优先于好看：任何未上市资产不得"提前入场"，任何口径偏差都必须在
   输出中显式声明。
2. 零第三方依赖：仅使用 Python 标准库，``git clone`` 即可运行。
3. 缺陷即资产：本项目在开发过程中修正了三个会造成结论反转的引擎缺陷，
   每一个都有对应的回归测试钉死（见 ``tests/test_regressions.py``）。

快速开始
--------
::

    from vlab import engine, strategies, windows

    series = engine.load_series()
    dates  = engine.trading_dates(series)
    mat    = engine.align(series, dates)
    D, M   = windows.slice_window(dates, mat, "A")

    res = engine.run(strategies.STEVE_STATIC, M, D)
    print(engine.fmt(res))

免责声明：本项目仅为量化研究与教学用途。所有回测结果均基于历史数据，
**不预示未来收益，不构成任何投资建议**。
"""
from . import engine, guard, metrics, strategies, validate, windows  # noqa: F401
from .engine import (  # noqa: F401
    GOLD_BANDS,
    STRATEGY_CURRENT,
    UNIVERSE,
    align,
    backtest,
    bench_from_mat,
    const_weights,
    load_series,
    month_ends,
    normalize_weights,
    run,
    trading_dates,
)
from .metrics import (  # noqa: F401
    cagr,
    calmar,
    drawdown_periods,
    drawdown_series,
    max_drawdown,
    sharpe,
    sortino,
    summarize,
    volatility,
    yearly_returns,
)
from .strategies import STRATEGIES  # noqa: F401
from .windows import WINDOWS  # noqa: F401
from .guard import LookAheadError  # noqa: F401
from .validate import (  # noqa: F401
    evaluate,
    holdout,
    parameter_sweep,
    walk_forward,
)

__version__ = "1.0.0"

__all__ = [
    "engine", "guard", "metrics", "strategies", "validate", "windows",
    "LookAheadError", "evaluate", "holdout", "parameter_sweep", "walk_forward",
    "UNIVERSE", "STRATEGY_CURRENT", "GOLD_BANDS", "STRATEGIES", "WINDOWS",
    "load_series", "trading_dates", "align", "month_ends", "backtest", "run",
    "normalize_weights", "const_weights", "bench_from_mat",
    "cagr", "volatility", "sharpe", "sortino", "max_drawdown", "calmar",
    "drawdown_series", "drawdown_periods", "yearly_returns", "summarize",
]
