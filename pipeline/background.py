# -*- coding: utf-8 -*-
"""比賽的背景（老球迷開口先講的那些）：兩隊上季在這個賽事打得怎樣、近兩季碰過幾次、誰剋誰。

都從逐場實力分（elo.py）用的那份比賽清單算：歐冠、歐盃（官方）、各國國內聯賽（TheSportsDB）、NBA（ESPN 比分板）。
交手每場都跟「賽前照實力該贏幾分」比：強隊本來就該贏，要比該贏的多贏很多，才算剋星。"""
from datetime import datetime, timedelta, timezone
from statistics import mean

TW = timezone(timedelta(hours=8))
JINX_TH, JINX_CAP = 5.0, 2.0
COMP_ZH = {"E": "歐冠", "U": "歐盃", "nba": "NBA"}


def comp_zh(c):
    if c in COMP_ZH:
        return COMP_ZH[c]
    try:
        import tsdb
        return next((m["zh"] for m in tsdb.LEAGUES if m["key"] == c), c)
    except Exception:  # noqa: BLE001
        return c


def tables(games):
    """{(第幾季, 賽事): {隊: [勝, 敗, 得分, 失分]}}；第幾季 0=上季、1=這季。季後賽（rs=False）不算進戰績。"""
    T = {}
    for x in games:
        if x["hs"] == x["as_"] or x.get("rs") is False:
            continue
        t = T.setdefault((x["season"], x["comp"]), {})
        for k, pf, pa in ((x["h"], x["hs"], x["as_"]), (x["a"], x["as_"], x["hs"])):
            r = t.setdefault(k, [0, 0, 0, 0])
            r[0 if pf > pa else 1] += 1
            r[2] += pf
            r[3] += pa
    return T


def _rank(tab, k):
    rows = sorted(tab, key=lambda t: (-tab[t][0] / max(1, tab[t][0] + tab[t][1]), -(tab[t][2] - tab[t][3])))
    return rows.index(k) + 1, len(rows)


def prev(T, k, comp, partial=None):
    """這隊上季在這個賽事：幾勝幾敗、排第幾。上季這個賽事沒有他 → absent（剛升上來或剛加入）。
    partial：上季還沒抓完（國內聯賽一輪一輪補），只抓到第幾輪。"""
    tab = T.get((0, comp))
    if not tab or len(tab) < 6:
        return None
    if k not in tab:
        return dict(comp=comp, comp_zh=comp_zh(comp), absent=True)
    w, l, pf, pa = tab[k]
    rk, n = _rank(tab, k)
    return dict(comp=comp, comp_zh=comp_zh(comp), w=w, l=l, rank=rk, of=n, diff=round((pf - pa) / max(1, w + l), 1), partial=partial)


def h2h(games, preds, kh, ka):
    """近兩季兩隊所有交手（不分賽事），主隊角度。preds 跟 games 一場對一場（elo.rate 的輸出）。"""
    rows = []
    for x, p in zip(games, preds):
        if x["h"] == kh and x["a"] == ka:
            home = True
        elif x["h"] == ka and x["a"] == kh:
            home = False
        else:
            continue
        pf, pa = (x["hs"], x["as_"]) if home else (x["as_"], x["hs"])
        exp = p[2] if home else -p[2]
        rows.append(dict(date=datetime.fromtimestamp(x["ts"], TW).strftime("%Y/%m/%d"), home=home, pf=int(pf), pa=int(pa),
                         margin=int(pf - pa), over=round(pf - pa - exp, 1), season="本季" if x["season"] == 1 else "上季",
                         comp=comp_zh(x["comp"])))
    if not rows:
        return None
    n = len(rows)
    w = sum(1 for r in rows if r["margin"] > 0)
    l = sum(1 for r in rows if r["margin"] < 0)
    avg_over = round(mean(r["over"] for r in rows), 1)
    out = dict(n=n, w=w, l=l, avg_margin=round(mean(r["margin"] for r in rows), 1), avg_over=avg_over,
               games=rows[-6:], source="近兩季交手（歐冠、歐盃、國內聯賽都算）")
    side, adj = None, 0.0
    if n >= 3:
        if w >= n - 1 and avg_over >= JINX_TH:
            side, adj = "home", min(JINX_CAP, 0.25 * avg_over)
        elif l >= n - 1 and avg_over <= -JINX_TH:
            side, adj = "away", max(-JINX_CAP, 0.25 * avg_over)
    out["jinx"] = side
    out["adj"] = round(adj * min(1.0, n / 4), 1)
    return out


def attach(g, T, games, preds, kh, ka, comp, partial=None):
    """g.analysis.bg = 上季戰績；國內聯賽、歐戰沒有交手紀錄的話也補上 h2h_long。回傳有沒有交手。"""
    a = g.setdefault("analysis", {})
    pv = dict(home=prev(T, kh, comp, partial), away=prev(T, ka, comp, partial))
    if pv["home"] or pv["away"]:
        a["bg"] = dict(prev=pv)
    if preds is None:
        return False
    h = h2h(games, preds, kh, ka)
    old = a.get("h2h_long") or {}
    if h and (not old or h["n"] >= (old.get("n") or 0)):
        a["h2h_long"] = h
    return bool(h)
