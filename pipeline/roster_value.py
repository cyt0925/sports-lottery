# -*- coding: utf-8 -*-
"""今年陣容跟上季比，實力差多少（NBA）：老球迷講的「這隊今年補了誰、少了誰」換成分數。

  逐場實力分（elo.py）開季時是從上季戰績帶過來的，看不到休賽季的補強（七六人補了 LeBron、Jaylen Brown，
  上季才 45 勝也不代表今年弱）。所以另外算「陣容變化」：
  1. 每個球員的貢獻 =（得分 + 0.8×籃板 + 1.2×助攻）× 出賽比例，一隊算前 10 個人。
  2. 上季的陣容：上季在這隊打的人、照真的出賽場數（主力整季受傷就少算，像溜馬少了 Haliburton）。
  3. 這季的名單：每個人最近一個健康球季的數字（上季整季受傷的看前一季）。
  4. 貢獻 1 單位值幾分：拿上季 30 隊的「陣容貢獻」對「場均淨勝分」算斜率，網站自己從資料學。
  5. 開季越久越不用：實力分會跟著真的比賽結果走，這季打 20 場以後就不加了。
"""

TOP = 10            # 一隊算前幾個人
FADE_GAMES = 20     # 這季打幾場之後就不再加陣容變化
SHRINK = 0.8        # 只信八成（新隊友要磨合、數字也有雜訊）
CAP = 9.0           # 最多加減幾分
K_DEFAULT = 0.25    # 學不到斜率的時候用的
MIN_GP = 20         # 上季打不到 20 場的，看前一季


def pra(s):
    return (s.get("ppg") or 0) + 0.8 * (s.get("rpg") or 0) + 1.2 * (s.get("apg") or 0)


def _actual(s):
    """那一季真的貢獻了多少（照出賽場數）。"""
    return pra(s) * min(1.0, (s.get("gp") or 0) / 82)


def _expected(pid, prev, prev2):
    """這季預期的貢獻：最近一個健康球季的數字（上季打不到 20 場、前一季有打的，看前一季）。回傳 (貢獻, 用的數字, 是不是傷癒回來)。"""
    pv, p2 = prev.get(pid), prev2.get(pid)
    use, back = pv, False
    if (not pv or (pv.get("gp") or 0) < MIN_GP) and p2 and (p2.get("gp") or 0) >= MIN_GP:
        use, back = p2, True
    if not use:
        return 0.0, None, False
    return pra(use) * min(1.0, (use.get("gp") or 0) / 75), use, back


def _top(vals):
    return sum(sorted(vals, reverse=True)[:TOP])


def team_values(stats):
    """{球隊: 那一季的陣容貢獻}（照真的出賽，前 10 個人）。"""
    by = {}
    for s in stats.values():
        if s.get("team"):
            by.setdefault(s["team"], []).append(_actual(s))
    return {t: _top(v) for t, v in by.items()}


def fit_k(values, margins):
    """陣容貢獻 1 單位值幾分：30 隊的「陣容貢獻」對「場均淨勝分」的斜率。回傳 (斜率, 相關係數, 隊數)。"""
    xs = [(values[t], margins[t]) for t in values if t in margins]
    if len(xs) < 20:
        return K_DEFAULT, None, len(xs)
    mx = sum(x for x, _ in xs) / len(xs)
    my = sum(y for _, y in xs) / len(xs)
    sxy = sum((x - mx) * (y - my) for x, y in xs)
    sxx = sum((x - mx) ** 2 for x, _ in xs)
    syy = sum((y - my) ** 2 for _, y in xs)
    if sxx <= 0 or syy <= 0:
        return K_DEFAULT, None, len(xs)
    k = sxy / sxx
    r = sxy / (sxx * syy) ** 0.5
    if r < 0.4:                 # 對不太起來（資料怪怪的）：用預設值
        return K_DEFAULT, round(r, 2), len(xs)
    return round(max(0.05, min(0.6, k)), 3), round(r, 2), len(xs)


def margins(games):
    """上季例行賽每隊場均淨勝分。games：nba_elo 用的比賽列表（background.nba_split 標好 rs）。"""
    tot, n = {}, {}
    for x in games:
        if x.get("season") != 0 or not x.get("rs"):
            continue
        d = x["hs"] - x["as_"]
        for t, v in ((x["h"], d), (x["a"], -d)):
            tot[t] = tot.get(t, 0) + v
            n[t] = n.get(t, 0) + 1
    return {t: tot[t] / n[t] for t in tot if n[t] >= 40}


def attach(games, data, season_games, log):
    """每隊 t["roster_change"]，每場 g.analysis.roster（主客隊各加幾分）。
    data：spotlight.nba_prepare 存的 dict(rosters={隊: [(球員 id, 名字)]}, prev=上季平均, prev2=前一季平均)。"""
    from background import NBA_ID
    from names_zh import NBA as NBA_ZH
    prev, prev2, rosters = data.get("prev") or {}, data.get("prev2") or {}, data.get("rosters") or {}
    if not prev or not rosters:
        return
    k, r, n_fit = fit_k(team_values(prev), margins(season_games))
    names = {pid: nm for ro in rosters.values() for pid, nm in ro}
    zh = lambda tid: NBA_ZH.get(NBA_ID.get(tid, ""), "")  # noqa: E731
    out = {}
    for tid, ro in rosters.items():
        ids = {pid for pid, _ in ro}
        now = []
        gained, back = [], []
        for pid, nm in ro:
            v, use, is_back = _expected(pid, prev, prev2)
            now.append(v)
            pv = prev.get(pid)
            if pv and pv.get("team") and pv["team"] != tid and v >= 12:
                gained.append(dict(player=nm, v=round(v, 1), frm=zh(pv["team"]), ppg=pv.get("ppg")))
            if is_back and v >= 12:
                back.append(dict(player=nm, v=round(v, 1), ppg=(use or {}).get("ppg")))
        lost = [dict(player=s.get("name") or names.get(pid) or "", v=round(_actual(s), 1), ppg=s.get("ppg"))
                for pid, s in prev.items() if s.get("team") == tid and pid not in ids and _actual(s) >= 8]
        v_now = _top(now)
        v_prev = _top([_actual(s) for s in prev.values() if s.get("team") == tid])
        raw = SHRINK * k * (v_now - v_prev)
        out[tid] = dict(raw=round(max(-CAP, min(CAP, raw)), 1), v_now=round(v_now, 1), v_prev=round(v_prev, 1),
                        gained=sorted(gained, key=lambda x: -x["v"])[:3], back=sorted(back, key=lambda x: -x["v"])[:2],
                        lost=sorted(lost, key=lambda x: -x["v"])[:3])
    n = 0
    for g in games:
        if g["league"] != "nba" or g["status"]["state"] == "post":
            continue
        el = (g.get("analysis") or {}).get("elo") or {}
        adj = {}
        for side in ("home", "away"):
            t = g[side]
            rc = out.get(str(t.get("id") or ""))
            if not rc:
                continue
            gp = el.get("n_" + side) or 0                # 這季已經打幾場
            fade = max(0.0, 1 - gp / FADE_GAMES)
            t["roster_change"] = dict(rc, pts=round(rc["raw"] * fade, 1), fade=round(fade, 2))
            adj[side] = t["roster_change"]["pts"]
        if adj:
            g.setdefault("analysis", {})["roster"] = dict(home=adj.get("home", 0.0), away=adj.get("away", 0.0), k=k)
            n += 1
    top = sorted(out.items(), key=lambda kv: -kv[1]["raw"])
    log(f"[nba] 陣容變化：貢獻 1 單位值 {k} 分（上季 {n_fit} 隊算的，相關 {r}）；用在 {n} 場；"
        f"變強最多 {[(zh(t), v['raw']) for t, v in top[:4]]}；變弱最多 {[(zh(t), v['raw']) for t, v in top[-3:]]}")


def line(t, name):
    """白話：「七六人今年補了 LeBron James（上季在湖人場均 21 分）、Jaylen Brown，少了…，網站估計陣容比上季強 5 分。」"""
    rc = t.get("roster_change") or {}
    if not rc or (abs(rc.get("raw") or 0) < 1.5 and not rc.get("gained") and not rc.get("back")):
        return None
    bits = []
    if rc.get("gained"):
        bits.append("今年補了 " + "、".join(f"{x['player']}" + (f"（上季在{x['frm']}場均 {x['ppg']:.0f} 分）" if x.get("frm") and x.get("ppg") else "")
                                         for x in rc["gained"][:2]))
    if rc.get("back"):
        bits.append("、".join(x["player"] for x in rc["back"]) + " 傷癒回來")
    if rc.get("lost"):
        bits.append("少了 " + "、".join(x["player"] for x in rc["lost"][:2]))
    raw = rc.get("raw") or 0
    how = f"網站估計陣容比上季強 {raw:.0f} 分" if raw >= 1 else f"網站估計陣容比上季弱 {-raw:.0f} 分" if raw <= -1 else "陣容強弱跟上季差不多"
    return f"{name}" + "，".join(bits) + f"，{how}。"
