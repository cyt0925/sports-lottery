# -*- coding: utf-8 -*-
"""網站自己學：每個因素（傷兵、近況、剋星、體力、手感、戰意）該給多少分量。

做法：拿最近 90 天打完的籃球比賽，每場記著「每個因素原本算幾分」（parts_raw）。
一個因素一個因素試：乘 0 倍、0.25 倍 … 2 倍，看哪個倍數讓賽前預測最準（Brier 分數最低）。
場數少的因素不太動（往 1 倍拉）：真正的倍數 = 1 + (試出來的 − 1) × 場數 ÷ (場數 + 60)。
學到的倍數存在 history.json 的 learn，下一次更新就用（model.WEIGHTS）。"""
from datetime import timedelta
from math import erf, sqrt

from model import FACTORS, FACTOR_ZH

SIGMA = 11.0
CHIPS = ("nba", "eurobasket", "jpbasket")
STEPS = [x / 4 for x in range(0, 9)]     # 0、0.25 … 2 倍
PRIOR_N = 60
MIN_ROWS = 40
DAYS = 90


def _phi(x):
    return 0.5 * (1 + erf(x / sqrt(2)))


def _brier(rows, w):
    s = 0.0
    for parts, y in rows:
        z = parts.get("base", 0.0) + sum(w[f] * parts.get(f, 0.0) for f in FACTORS)
        p = _phi(z / SIGMA)
        s += (p - y) ** 2
    return s / len(rows)


def fit(hist, now):
    cutoff = (now - timedelta(days=DAYS)).strftime("%Y-%m-%d")
    rows = []
    for e in (hist.get("model") or {}).values():
        r = e.get("res") or {}
        if "home_won" not in r or not e.get("parts") or e.get("chip") not in CHIPS or e.get("day", "") < cutoff:
            continue
        rows.append(({k: float(v or 0) for k, v in e["parts"].items()}, 1.0 if r["home_won"] else 0.0))
    out = dict(n=len(rows), updated=now.isoformat(timespec="minutes"))
    if len(rows) < MIN_ROWS:
        out.update(weights={}, note=f"打完的比賽才 {len(rows)} 場，還不夠學（要 {MIN_ROWS} 場）")
        return out
    w = {f: 1.0 for f in FACTORS}
    before = _brier(rows, w)
    for _pass in range(3):
        for f in FACTORS:
            best, best_b = w[f], None
            for x in STEPS:
                w2 = dict(w, **{f: x})
                b = _brier(rows, w2)
                if best_b is None or b < best_b - 1e-9:
                    best, best_b = x, b
            w[f] = best
    n_f = {f: sum(1 for parts, _y in rows if abs(parts.get(f, 0.0)) >= 0.3) for f in FACTORS}
    final = {f: round(1 + (w[f] - 1) * n_f[f] / (n_f[f] + PRIOR_N), 2) for f in FACTORS}
    after = _brier(rows, final)
    out.update(weights=final, raw=w, n_f=n_f, brier_before=round(before, 4), brier_after=round(after, 4),
               lines=[dict(key=f, label=FACTOR_ZH.get(f, f), w=final[f], n=n_f[f]) for f in FACTORS])
    return out
