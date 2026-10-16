# -*- coding: utf-8 -*-
"""老球迷看對戰：近況要扣掉對手強弱、交手紀錄要看「有沒有贏得比預期多」、打法對不對位。

近況：最近 5 場每場的「表現分」= 淨勝分 + 對手實力 − 主場優勢。贏弱隊 10 分跟贏強隊 10 分不一樣。
交手（剋星）：只交手一兩場多半是運氣。至少 3 場、幾乎都贏，而且平均比預期多贏 5 分以上（或台灣讓分盤幾乎都過），才算「剋」。
打法對位（NBA）：籃板、三分、失誤、節奏。只當參考說明，不加進分數（還沒有證據證明有用）。
"""
from statistics import mean

SITE = "https://site.api.espn.com/apis/site/v2/sports"
SITE_V2 = "https://site.api.espn.com/apis/v2/sports"


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ---------- 近況（扣掉對手強弱）----------
def form_view(team, ratings, hca, n=5):
    rows = [r for r in (team.get("form") or []) if r.get("pf") is not None and r.get("pa") is not None]
    perfs, opps, used = [], [], []
    for r in reversed(rows):
        key = str(r.get("opp_id") or r.get("opp_code") or "")
        ro = ratings.get(key)
        if ro is None:
            continue
        loc = hca if r.get("home") is True else (-hca if r.get("home") is False else 0.0)
        perfs.append((r["pf"] - r["pa"]) + ro - loc)
        opps.append(ro)
        used.append(dict(r, opp_rating=round(ro, 1), perf=round(perfs[-1], 1)))
        if len(perfs) >= n:
            break
    if len(perfs) < 3:
        return None
    used.reverse()
    # 最近連勝／連敗都是打什麼樣的對手
    streak = []
    for r in reversed(rows):
        if not streak or r["result"] == streak[0]["result"]:
            streak.append(r)
        else:
            break
    s_opp = [ratings.get(str(r.get("opp_id") or r.get("opp_code") or "")) for r in streak]
    s_opp = [x for x in s_opp if x is not None]
    return dict(n=len(perfs), recent=round(mean(perfs), 1), opp_avg=round(mean(opps), 1), games=used,
                streak_kind=streak[0]["result"] if streak else None, streak_n=len(streak),
                streak_opp_avg=round(mean(s_opp), 1) if len(s_opp) >= 2 else None)


# ---------- 交手：玩運彩聯盟（有台灣讓分盤過盤紀錄）----------
def _same(a, b):
    a, b = (a or "").strip(), (b or "").strip()
    return bool(a and b and (a == b or (len(a) >= 2 and len(b) >= 2 and (a in b or b in a))))


def playsport_h2h(home_rows, away_names):
    """home_rows：主隊完整歷史（玩運彩），找出對上今天客隊的那幾場。從主隊角度。"""
    games = [r for r in home_rows if any(_same(r.get("opp"), nm) for nm in away_names)]
    if len(games) < 2:
        return None
    w = sum(1 for r in games if r["result"] == "W")
    l = sum(1 for r in games if r["result"] == "L")
    aw = sum(1 for r in games if r.get("ats") is True)
    al = sum(1 for r in games if r.get("ats") is False)
    margins = [r["pf"] - r["pa"] for r in games]
    out = dict(n=len(games), w=w, l=l, ats_w=aw, ats_l=al, avg_margin=round(mean(margins), 1),
               games=[dict(date=r.get("date"), home=r.get("home"), pf=r["pf"], pa=r["pa"], ats=r.get("ats")) for r in games[-6:]],
               source="玩運彩交手紀錄（含台灣讓分盤）")
    n = len(games)
    side, adj = None, 0.0
    if n >= 3:
        if (aw + al >= 3 and aw >= aw + al - 1 and w >= n - 1) or (w >= n - 1 and out["avg_margin"] >= 8):
            side, adj = "home", 1.5
        elif (aw + al >= 3 and al >= aw + al - 1 and l >= n - 1) or (l >= n - 1 and out["avg_margin"] <= -8):
            side, adj = "away", -1.5
    out["jinx"] = side
    out["adj"] = round(adj * min(1.0, n / 4), 1)
    return out


# ---------- 交手：ESPN 聯盟（上一季＋這一季，跟預期比）----------
def prev_ratings(get, lg, season_prev, rating_fn, team_table_fn, hca):
    d = get(f"{SITE_V2}/{lg['path']}/standings", params={"season": season_prev}, quiet=True)
    if not d:
        return {}
    rows = []
    children = d.get("children") or []
    if not children and d.get("standings"):
        children = [dict(standings=d["standings"])]
    for ch in children:
        for e in ((ch.get("standings") or {}).get("entries")) or []:
            t = e.get("team") or {}
            st = {s.get("name"): s.get("value") for s in e.get("stats") or []}
            gp = st.get("gamesPlayed") or ((st.get("wins") or 0) + (st.get("losses") or 0))
            pf = st.get("avgPointsFor") if st.get("avgPointsFor") is not None else ((st.get("pointsFor") or 0) / gp if gp else None)
            pa = st.get("avgPointsAgainst") if st.get("avgPointsAgainst") is not None else ((st.get("pointsAgainst") or 0) / gp if gp else None)
            rows.append(dict(team_id=str(t.get("id") or ""), gp=gp, pf=pf, pa=pa))
    table = team_table_fn(dict(groups=[dict(rows=rows)]))
    return {k: rating_fn(v, lg["sport"]) for k, v in table.items()}


def espn_h2h(g, lg, get, season_prev, prev_r, cur_r, hca, schedule_fn):
    """主隊角度：近兩季交手，每場跟「照當時實力該贏幾分」比。"""
    hid, aid = str(g["home"].get("id") or ""), str(g["away"].get("id") or "")
    if not hid or not aid:
        return None
    games = []
    for ev in schedule_fn(get, lg["path"], hid, season_prev):
        comps = (ev.get("comp") or {}).get("competitors") or []
        me = next((c for c in comps if str((c.get("team") or {}).get("id") or c.get("id")) == hid), None)
        op = next((c for c in comps if str((c.get("team") or {}).get("id") or c.get("id")) == aid), None)
        if not me or not op:
            continue
        try:
            pf = float((me.get("score") or {}).get("value") if isinstance(me.get("score"), dict) else me.get("score"))
            pa = float((op.get("score") or {}).get("value") if isinstance(op.get("score"), dict) else op.get("score"))
        except (TypeError, ValueError):
            continue
        home = me.get("homeAway") == "home"
        exp = None
        if hid in prev_r and aid in prev_r:
            exp = prev_r[hid] - prev_r[aid] + (hca if home else -hca)
        games.append(dict(date=ev["dt"].strftime("%Y/%m/%d"), home=home, pf=int(pf), pa=int(pa), margin=pf - pa,
                          over=None if exp is None else round(pf - pa - exp, 1), season="上季"))
    # 這一季（ESPN summary 的 seasonseries）
    h2h = (g.get("analysis") or {}).get("h2h") or {}
    for x in h2h.get("games") or []:
        home_abbr = g["home"].get("abbr")
        if x.get("home") == home_abbr:
            pf, pa, home = x["hs"], x["as"], True
        elif x.get("away") == home_abbr:
            pf, pa, home = x["as"], x["hs"], False
        else:
            continue
        exp = None
        if hid in cur_r and aid in cur_r:
            exp = cur_r[hid] - cur_r[aid] + (hca if home else -hca)
        games.append(dict(date=x.get("date"), home=home, pf=pf, pa=pa, margin=pf - pa,
                          over=None if exp is None else round(pf - pa - exp, 1), season="本季"))
    if len(games) < 2:
        return None
    n = len(games)
    w = sum(1 for x in games if x["margin"] > 0)
    l = sum(1 for x in games if x["margin"] < 0)
    overs = [x["over"] for x in games if x["over"] is not None]
    avg_over = round(mean(overs), 1) if overs else None
    out = dict(n=n, w=w, l=l, avg_margin=round(mean(x["margin"] for x in games), 1), avg_over=avg_over,
               games=games[-6:], source="近兩季交手")
    side, adj = None, 0.0
    if n >= 3 and avg_over is not None:
        if w >= n - 1 and avg_over >= 5:
            side, adj = "home", clamp(0.25 * avg_over, 0, 2)
        elif l >= n - 1 and avg_over <= -5:
            side, adj = "away", clamp(0.25 * avg_over, -2, 0)
    out["jinx"] = side
    out["adj"] = round(adj * min(1.0, n / 4), 1)
    return out


# ---------- 打法對位（NBA）----------
STAT_KEYS = ("avgRebounds", "avgOffensiveRebounds", "avgThreePointFieldGoalsAttempted", "threePointPct", "avgTurnovers",
             "avgSteals", "avgPoints", "gamesPlayed", "avgFieldGoalsAttempted", "avgFreeThrowsAttempted")
_STYLE = {}


def team_style(get, lg, tid, season_prev):
    if tid in _STYLE:
        return _STYLE[tid]

    def pull(params):
        d = get(f"{SITE}/{lg['path']}/teams/{tid}/statistics", params=params, quiet=True)
        res = (d or {}).get("results") or {}
        out = {}
        for c in ((res.get("stats") or {}).get("categories")) or []:
            for s in c.get("stats") or []:
                if s.get("name") in STAT_KEYS:
                    try:
                        out[s["name"]] = float(s.get("value") if s.get("value") is not None else s.get("displayValue"))
                    except (TypeError, ValueError):
                        pass
        return out
    st = pull(None)
    note = None
    if (st.get("gamesPlayed") or 0) < 10:
        prev = pull({"season": season_prev})
        if (prev.get("gamesPlayed") or 0) >= 30:
            st, note = prev, "上季數據"
    if st.get("avgFieldGoalsAttempted"):
        st["pace"] = st["avgFieldGoalsAttempted"] + 0.44 * st.get("avgFreeThrowsAttempted", 0) - st.get("avgOffensiveRebounds", 0) + st.get("avgTurnovers", 0)
    st["note"] = note
    _STYLE[tid] = st if st.get("gamesPlayed") else None
    return _STYLE[tid]


def style_lines(hs, as_, hn, an, league_pace=None):
    if not hs or not as_:
        return []
    lines = []
    for a, b, na, nb in ((hs, as_, hn, an), (as_, hs, an, hn)):
        d = (a.get("avgRebounds") or 0) - (b.get("avgRebounds") or 0)
        if d >= 5:
            lines.append(f"{na}籃板每場比{nb}多 {d:.0f} 個，禁區跟二次進攻會占便宜。")
        d3 = (a.get("avgThreePointFieldGoalsAttempted") or 0) - (b.get("avgThreePointFieldGoalsAttempted") or 0)
        if d3 >= 8 and (a.get("threePointPct") or 0) >= 36:
            lines.append(f"{na}很愛投三分（每場 {a['avgThreePointFieldGoalsAttempted']:.0f} 次、命中 {a['threePointPct']:.0f}%），手感來了很難擋，冷掉也輸得快。")
        dt = (b.get("avgTurnovers") or 0) - (a.get("avgTurnovers") or 0)
        if dt >= 3 and (a.get("avgSteals") or 0) >= 8.5:
            lines.append(f"{nb}每場失誤比{na}多 {dt:.0f} 次，{na}又很會抄球，這點{nb}會吃虧。")
    if league_pace and hs.get("pace") and as_.get("pace"):
        if hs["pace"] >= league_pace + 2 and as_["pace"] >= league_pace + 2:
            lines.append("兩隊節奏都快，比分容易衝高。")
        elif hs["pace"] <= league_pace - 2 and as_["pace"] <= league_pace - 2:
            lines.append("兩隊都打得慢，比分容易偏低。")
    return lines[:3]
