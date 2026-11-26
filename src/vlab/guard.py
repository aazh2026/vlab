# -*- coding: utf-8 -*-
"""防未来函数护栏 / Look-ahead guard.

为什么需要这个模块
------------------
本项目的全部价值是"诚实的回测"。但引擎原先把**完整的价格矩阵**直接
交给策略函数，策略只要写 ``mat[c][i + 1]`` 就能读到未来价格 —— 而且
引擎不会报错、回测照样跑完、结果照样漂亮。

这等于给一个专门消灭"回测欺骗"的项目留了后门。审稿人或用户无法察觉
自己的策略在偷看未来。

护栏的做法
----------
策略函数在第 ``i`` 天被调用时，拿到的是一个**只暴露 ``[0, i]``** 的视图：

* ``mat[c][j]``，其中 ``j > i`` → 抛出 :class:`LookAheadError`
* ``dates[j]``，其中 ``j > i`` → 同样抛出
* 负索引保持 Python 原生语义（相对**真实**序列末尾），因此
  ``mat[c][-1]`` 会正确地被判定为"未来"而不是被悄悄改写

这样"偷看未来"从一个静默的作弊变成一个**响亮的错误**。

需要注意
--------
护栏按"当前是第 i 天"截断，因此策略**无法读取窗口起点之前的数据**。
如果策略需要预热期（例如 60 日动量），请让引擎从更早的日期开始跑，
再对净值曲线取子集 —— ``vlab.validate`` 就是这么做的。
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Sequence


class LookAheadError(IndexError):
    """策略试图读取未来数据时被护栏拦截。

    继承 ``IndexError`` 是为了兼容"越界访问"这类直觉，
    但语义上它代表的是**诚实性违规**，不是普通的索引错误。
    """


class _PastOnly:
    """只暴露 ``[0, limit]`` 的序列视图。

    负索引按**底层真实长度**解析（与 Python 原生语义一致），
    因此 ``seq[-1]`` 指向真实末尾 —— 若那已经在 ``limit`` 之后，
    就会被判定为未来数据并抛错。
    """

    __slots__ = ("_src", "_limit")

    def __init__(self, src: Sequence, limit: int):
        self._src = src
        self._limit = max(-1, min(limit, len(src) - 1))

    def __len__(self) -> int:
        return self._limit + 1

    def _resolve(self, j):
        if isinstance(j, slice):
            return self._src[:self._limit + 1][j]
        n = len(self._src)
        k = j + n if j < 0 else j
        if k < 0 or k > self._limit:
            raise LookAheadError(
                "策略试图读取未来数据：索引 %r 超出当前可见范围 [0, %d]"
                % (j, self._limit)
            )
        return k

    def __getitem__(self, j):
        return self._src[self._resolve(j)]

    def __iter__(self):
        return iter(self._src[:self._limit + 1])

    def __contains__(self, v):
        return v in self._src[:self._limit + 1]

    def __repr__(self):  # pragma: no cover - 调试用
        return "<PastOnly len=%d limit=%d>" % (len(self._src), self._limit)


class PastOnlyMat:
    """只暴露 ``[0, limit]`` 的价格矩阵视图。

    键集合与原矩阵相同（策略仍需知道有哪些资产），
    但每个值列都被截断到 ``limit``。
    """

    __slots__ = ("_src", "_limit", "_keys")

    def __init__(self, src: Dict[str, Sequence], limit: int):
        self._src = src
        self._limit = limit
        self._keys = list(src.keys())

    def __contains__(self, k) -> bool:
        return k in self._src

    def __getitem__(self, k):
        if k not in self._src:
            raise KeyError(k)
        return _PastOnly(self._src[k], self._limit)

    def get(self, k, default=None):
        if k not in self._src:
            return default
        return self[k]

    def keys(self) -> List[str]:
        return list(self._keys)

    def items(self):
        return [(k, self[k]) for k in self._keys]

    def values(self):
        return [self[k] for k in self._keys]

    def __iter__(self):
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._keys)

    def __repr__(self):  # pragma: no cover - 调试用
        return "<PastOnlyMat cols=%d limit=%d>" % (len(self._keys), self._limit)


def guard_view(mat: Dict[str, Sequence], dates: Sequence, i: int):
    """返回给策略函数用的 ``(mat_view, dates_view)``。"""
    return PastOnlyMat(mat, i), _PastOnly(dates, i)
