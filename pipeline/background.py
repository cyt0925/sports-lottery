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


# ---------- NBA：上季東西區排名、季後賽打到哪 ----------
# ESPN 的球隊代碼 -> 縮寫；東區 15 隊
NBA_ID = {"1": "ATL", "2": "BOS", "3": "NO", "4": "CHI", "5": "CLE", "6": "DAL", "7": "DEN", "8": "DET", "9": "GS", "10": "HOU",
          "11": "IND", "12": "LAC", "13": "LAL", "14": "MIA", "15": "MIL", "16": "MIN", "17": "BKN", "18": "NY", "19": "ORL", "20": "PHI",
          "21": "PHX", "22": "POR", "23": "SAC", "24": "SA", "25": "OKC", "26": "UTAH", "27": "WSH", "28": "TOR", "29": "MEM", "30": "CHA"}
EAST = {"ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DET", "IND", "MIA", "MIL", "NY", "ORL", "PHI", "TOR", "WSH"}
PLAYOFF_ZH = {0: "沒打進季後賽", 1: "季後賽第一輪就出局", 2: "季後賽打到第二輪", 3: "打到分區決賽", 4: "打進總冠軍賽但輸了", 5: "拿下總冠軍"}


def nba_split(games):
    """上季的比賽分成例行賽（每隊前 82 場）和之後的附加賽、季後賽；季中盃冠軍賽（12 月中立場地的最後一場）不算戰績。
    會在每場加上 rs（是不是例行賽）。"""
    prev = sorted([x for x in games if x["season"] == 0], key=lambda x: x["ts"])
    from datetime import datetime, timezone
    dec = [x for x in prev if x.get("neutral") and datetime.fromtimestamp(x["ts"], timezone.utc).month == 12]
    cup_final = dec[-1] if dec else None
    cnt = {}
    for x in prev:
        if x is cup_final:
            x["rs"] = False
            x["cup_final"] = True
            continue
        h, a = x["h"], x["a"]
        if cnt.get(h, 0) < 82 and cnt.get(a, 0) < 82:
            x["rs"] = True
            cnt[h] = cnt.get(h, 0) + 1
            cnt[a] = cnt.get(a, 0) + 1
        else:
            x["rs"] = False
    return prev


def nba_prev(games):
    """{球隊代碼: dict(w, l, conf, conf_rank, rank, of, playoff, playoff_zh)}：上季例行賽戰績、東西區排名、季後賽打到哪。"""
    prev = nba_split(games)
    rec = {}
    for x in prev:
        if not x.get("rs"):
            continue
        for k, win in ((x["h"], x["hs"] > x["as_"]), (x["a"], x["as_"] > x["hs"])):
            r = rec.setdefault(k, [0, 0, 0])
            r[0 if win else 1] += 1
            r[2] += (x["hs"] - x["as_"]) * (1 if k == x["h"] else -1)
    # 季後賽：同一組對手打 4 場以上才是系列賽（附加賽只打一場）
    post = [x for x in prev if not x.get("rs") and not x.get("cup_final")]
    pairs = {}
    for x in post:
        key = frozenset((x["h"], x["a"]))
        w = pairs.setdefault(key, {})
        win = x["h"] if x["hs"] > x["as_"] else x["a"]
        w[win] = w.get(win, 0) + 1
    rounds, alive = {}, {}
    for key, w in pairs.items():
        if sum(w.values()) < 4:
            continue
        a, b = list(key)
        for t in (a, b):
            rounds[t] = rounds.get(t, 0) + 1
        winner = a if w.get(a, 0) > w.get(b, 0) else b
        loser = b if winner == a else a
        alive[loser] = False
        alive.setdefault(winner, True)
    out = {}
    for conf_set, conf in ((EAST, "東區"), (None, "西區")):
        teams = [k for k in rec if (NBA_ID.get(k) in EAST) == (conf_set is not None)]
        teams.sort(key=lambda k: (-rec[k][0] / max(1, rec[k][0] + rec[k][1]), -rec[k][2]))
        for i, k in enumerate(teams, 1):
            out[k] = dict(conf=conf, conf_rank=i)
    allt = sorted(rec, key=lambda k: (-rec[k][0] / max(1, rec[k][0] + rec[k][1]), -rec[k][2]))
    for i, k in enumerate(allt, 1):
        n_r = rounds.get(k, 0)
        lvl = 5 if (n_r == 4 and alive.get(k)) else n_r
        out.setdefault(k, {}).update(w=rec[k][0], l=rec[k][1], rank=i, of=len(allt), playoff=lvl, playoff_zh=PLAYOFF_ZH.get(lvl, ""),
                                     comp="nba", comp_zh="NBA")
    return out
