# -*- coding: utf-8 -*-
"""行情数据抓取 / Market data fetching.

数据源优先级
------------
============  ==========================  ==================================
优先级        源                          说明
============  ==========================  ==================================
1            腾讯 ``web.ifzq.gtimg.cn``   A 股 ETF / 指数 / 美股 / 港股，免费稳定
2            新浪 ``finance.sina.com.cn``  美股全历史、A 股备用
3            Yahoo Finance                兜底（实测常被限流）
============  ==========================  ==================================

所有数据落地为 JSON 缓存于 ``data/``，之后完全离线运行。

**数据质量说明**
----------------
* 美股标的返回的是**原始价格**，不含股息再投资。引擎按固定年化分红率
  做近似调整（见 ``engine.apply_dividend_approx``），这是**近似而非精确**，
  会略微高估美股长周期收益。
* 腾讯分页单次上限约 800 条，抓取函数会自动向前翻页拼接。
* 若上游限流（WAF），抓取会失败并回退到缓存，不会产生半截数据。
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from typing import List, Optional

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

DEFAULT_START = "2001-01-01"
DEFAULT_END = "2099-12-31"


def _curl(url: str, referer: Optional[str] = None) -> str:
    # -L 跟随重定向：frankfurter 等源会 301 到最终地址，
    # 不跟随就会拿到一段 HTML 而不是 JSON。
    cmd = ["curl", "-sL", "-m", "25", "-A", UA]
    if referer:
        cmd += ["-H", "Referer: " + referer]
    cmd.append(url)
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=40).stdout
    except Exception:
        return ""


def _rows_to_records(rows) -> List[dict]:
    out: List[dict] = []
    for r in rows or []:
        try:
            out.append({
                "d": r[0],
                "o": float(r[1]), "c": float(r[2]),
                "h": float(r[3]), "l": float(r[4]), "v": float(r[5]),
            })
        except Exception:
            continue
    return out


# --------------------------------------------------------------------------
# 各数据源
# --------------------------------------------------------------------------
def tencent_ashare(sym: str, start: str = DEFAULT_START,
                   end: str = DEFAULT_END) -> List[dict]:
    """A 股 ETF / 股票前复权日线，自动向前分页。"""
    out: List[dict] = []
    end_date = end
    for _ in range(14):
        url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=%s,day,,%s,800,qfq"
               % (sym, end_date))
        try:
            d = json.loads(_curl(url)).get("data", {})
        except Exception:
            break
        node = d.get(sym) or {}
        batch = _rows_to_records(node.get("qfqday") or node.get("day") or [])
        if not batch:
            break
        out.extend(batch)
        earliest = batch[0]["d"]
        if earliest <= start:
            break
        end_date = earliest
        time.sleep(0.4)
    return _dedupe(out, start)


def tencent_index(sym: str, start: str = DEFAULT_START,
                  end: str = DEFAULT_END) -> List[dict]:
    """指数日线（无复权），自动向前分页。"""
    out: List[dict] = []
    end_date = None
    for _ in range(14):
        url = ("https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param=%s,day,,%s,800"
               % (sym, end_date or ""))
        try:
            d = json.loads(_curl(url)).get("data", {})
        except Exception:
            break
        node = d.get(sym) or {}
        batch = _rows_to_records(node.get("day") or [])
        if not batch:
            break
        out.extend(batch)
        earliest = batch[0]["d"]
        if earliest <= start:
            break
        end_date = earliest
        time.sleep(0.4)
    return _dedupe(out, start)


def tencent_us(sym: str, start: str = DEFAULT_START,
               end: str = DEFAULT_END) -> List[dict]:
    """美股前复权日线。"""
    url = ("https://web.ifzq.gtimg.cn/appstock/app/usfqkline/get?param=%s,day,,,4000,qfq" % sym)
    try:
        d = json.loads(_curl(url)).get("data", {})
    except Exception:
        return []
    node = d.get(sym) or {}
    return _dedupe(_rows_to_records(node.get("qfqday") or node.get("day") or []), start)


def sina_us(sym: str, start: str = DEFAULT_START,
            end: str = DEFAULT_END) -> List[dict]:
    """新浪美股全历史日线（symbol 不带交易所后缀，如 ``GLD``）。"""
    url = ("https://stock.finance.sina.com.cn/usstock/api/jsonp.php/x/US_MinKService.getDailyK"
           "?symbol=%s&___qn=3" % sym)
    raw = _curl(url, "https://finance.sina.com.cn")
    i, j = raw.find("("), raw.rfind(")")
    if i < 0 or j < 0:
        return []
    try:
        d = json.loads(raw[i + 1:j])
    except Exception:
        return []
    out: List[dict] = []
    for x in d:
        try:
            out.append({
                "d": x["d"], "o": float(x["o"]), "c": float(x["c"]),
                "h": float(x["h"]), "l": float(x["l"]), "v": float(x["v"]),
            })
        except Exception:
            continue
    return _dedupe(out, start)


def sina_cn(sym: str, start: str = DEFAULT_START,
            end: str = DEFAULT_END) -> List[dict]:
    """新浪 A 股日线（备用源）。"""
    url = ("https://quotes.sina.cn/cn/api/openapi.php/CN_MarketDataService.getKLineData"
           "?symbol=%s&scale=240&ma=no&datalen=3000" % sym)
    raw = _curl(url, "https://finance.sina.com.cn")
    try:
        d = json.loads(raw)["result"]["data"]
    except Exception:
        return []
    out = []
    for x in d:
        try:
            out.append({
                "d": x["day"], "o": float(x["open"]), "c": float(x["close"]),
                "h": float(x["high"]), "l": float(x["low"]), "v": float(x["volume"]),
            })
        except Exception:
            continue
    return _dedupe(out, start)



# --------------------------------------------------------------------------
# 汇率（USD -> CNY）
# --------------------------------------------------------------------------

def frankfurter_fx(start: str = DEFAULT_START, end: str = DEFAULT_END) -> List[dict]:
    """抓取 ECB 参考汇率 USD/CNY（frankfurter.app）。

    为什么不只靠 Yahoo：Yahoo 的 chart 接口在 CI 机房 IP 上会返回
    429 "Too Many Requests"，导致每日刷新失败（实测 2026-11-26）。
    frankfurter 无需 API key、无明显限流，且历史可回溯到 1999 年。

    注意：ECB 参考汇率只在**工作日**更新，因此这个序列在周末与
    节假日是平的 —— 这与真实的离岸汇率（CNY=X）略有差异，
    但用于把美元资产折算成人民币口径是标准做法。
    """
    url = ("https://api.frankfurter.app/%s..%s?from=USD&to=CNY"
           % (start, end))
    try:
        d = json.loads(_curl(url))
        rates = d.get("rates") or {}
    except Exception:
        return []
    out: List[dict] = []
    for day in sorted(rates):
        try:
            c = float(rates[day]["CNY"])
        except Exception:
            continue
        out.append({"d": day, "o": c, "c": c, "h": c, "l": c, "v": 0.0})
    return out


def yahoo_fx(symbol: str = "CNY=X", start: str = DEFAULT_START,
             end: str = DEFAULT_END) -> List[dict]:
    """抓取汇率日线（Yahoo Finance chart API）。

    ``symbol`` 用 Yahoo 的写法：``CNY=X`` 表示 1 美元 = X 人民币。
    Yahoo 的 chart 接口需要 Unix 时间戳，这里做一次换算。
    """
    import calendar
    import datetime as _dt

    def _ts(d: str) -> int:
        y, m, dd = int(d[:4]), int(d[5:7]), int(d[8:10])
        return calendar.timegm(_dt.datetime(y, m, dd).timetuple())

    url = ("https://query1.finance.yahoo.com/v8/finance/chart/%s"
           "?period1=%d&period2=%d&interval=1d"
           % (symbol, _ts(start), _ts(end)))
    # Yahoo 会对短时间内的重复请求返回 429 / "Too Many Requests"。
    # 退避重试，而不是直接放弃 —— 汇率是 USD 资产能否正确换算的前提。
    node = None
    for attempt in range(4):
        raw = _curl(url)
        if "Too Many Requests" in raw[:64] or raw.strip() == "":
            time.sleep(2.0 * (attempt + 1))
            continue
        try:
            node = json.loads(raw)["chart"]["result"][0]
            break
        except Exception:
            time.sleep(1.0 * (attempt + 1))
    if node is None:
        return []
    out: List[dict] = []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        try:
            day = _dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d")
            out.append({"d": day, "o": float(c), "c": float(c),
                        "h": float(c), "l": float(c), "v": 0.0})
        except Exception:
            continue
    return _dedupe(out, start)


def fetch_fx(data_dir: str, start: str = DEFAULT_START,
             end: str = DEFAULT_END, force: bool = False) -> List[dict]:
    """抓取并缓存 USDCNY 汇率（``fx_usdcny.json``）。"""
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "fx_usdcny.json")
    if not force and os.path.exists(path):
        try:
            with open(path) as f:
                rows = json.load(f)
            if rows:
                return rows
        except Exception:
            pass
    # 主源：frankfurter（ECB 参考汇率，CI 机房 IP 不会 429）
    rows = frankfurter_fx(start, end)
    # 兜底：Yahoo
    if len(rows) < 200:
        rows = yahoo_fx("CNY=X", start, end)
    if rows:
        rows.sort(key=lambda x: x["d"])
        with open(path, "w") as f:
            json.dump(rows, f)
    return rows

def _dedupe(rows: List[dict], start: str) -> List[dict]:
    seen = {r["d"]: r for r in rows}
    res = [seen[k] for k in sorted(seen)]
    return [r for r in res if r["d"] >= start]


# --------------------------------------------------------------------------
# 统一入口
# --------------------------------------------------------------------------
def fetch(symbol: str, data_dir: str, start: str = DEFAULT_START,
          end: str = DEFAULT_END, use_cache: bool = True,
          force: bool = False) -> List[dict]:
    """抓取并缓存单个标的的日线。

    ``symbol`` 命名约定::

        sh510300   A 股 ETF / 股票
        ixsh000300 指数
        usSPY.OQ   美股（新浪优先，腾讯兜底）
        hkHSI      港股
    """
    os.makedirs(data_dir, exist_ok=True)
    key = symbol.replace(":", "_").replace(".", "_")
    path = os.path.join(data_dir, key + ".json")
    if use_cache and not force and os.path.exists(path):
        try:
            with open(path) as f:
                rows = json.load(f)
            if rows:
                return rows
        except Exception:
            pass

    rows: List[dict] = []
    try:
        if symbol in ("fx_usdcny", "USDCNY", "fxusdcny"):
            rows = frankfurter_fx(start, end)
            if len(rows) < 200:
                rows = yahoo_fx("CNY=X", start, end)
        elif symbol.startswith("ix"):
            rows = tencent_index(symbol[2:], start, end)
        elif symbol.startswith("us"):
            name = symbol[2:].split(".")[0]
            rows = sina_us(name, start, end)
            if len(rows) < 500:
                rows = tencent_us(symbol, start, end) or rows
        elif symbol.startswith("hk"):
            url = ("https://web.ifzq.gtimg.cn/appstock/app/hkfqkline/get?param=%s,day,,,4000,qfq"
                   % symbol)
            try:
                d = json.loads(_curl(url)).get("data", {})
                node = d.get(symbol) or {}
                rows = _dedupe(_rows_to_records(node.get("qfqday") or node.get("day") or []), start)
            except Exception:
                rows = []
        else:
            rows = tencent_ashare(symbol, start, end)
            if len(rows) < 200:
                rows = sina_cn(symbol, start, end) or rows
    except Exception:
        rows = []

    if rows:
        rows.sort(key=lambda x: x["d"])
        with open(path, "w") as f:
            json.dump(rows, f)
    return rows
