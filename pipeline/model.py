# -*- coding: utf-8 -*-
"""自己的實力評分與大小分估計，拿來跟盤口比。

評分 = 每場淨勝分（得分 - 失分），用場數做收縮（季初場數少就往 0 拉），再加主場優勢。
  我們的讓分 = -(主隊評分 + 主場優勢 - 客隊評分)   （負數代表主隊讓分）
  我們的勝率 = 常態分布換算（籃球標準差約 11 分）
大小分 = 主隊得分力 × 客隊失分力 / 聯盟平均 + 反過來，再跟盤口比。
資料來源：各聯盟排名表（有得失分與場數）；沒有的球隊退而用玩運彩歷史戰績的近況列。"""
from math import erf, sqrt

HCA = {"nba": 2.8, "eurobasket": 3.5, "jpbasket": 2.5, "nhl": 0.25, "nfl": 2.0}
HCA_SPORT = {"basketball": 3.0, "hockey": 0.25, "football": 2.0, "soccer": 0.3, "volleyball": 0.15}
SIGMA = {"basketball": 11.0, "hockey": 2.2, "football": 13.5, "soccer": 1.3, "volleyball": 1.0}
SHRINK_K = {"basketball": 8, "hockey": 10, "football": 4, "soccer": 8, "volleyball": 6}
EDGE_TH = {"basketball": 3.0, "hockey": 0.45, "football": 3.0, "soccer": 0.35}       # 我們的讓分跟盤口差多少才算有話講
TOTAL_TH = {"basketball": 5.0, "hockey": 0.5, "football": 4.0, "soccer": 0.4}
MIN_GP = 4


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def team_table(standings_entry):
    """排名表 -> {team_id: {gp, pf, pa, diff}}（都是每場平均）。"""
    table = {}
    for grp in (standings_entry or {}).get("groups") or []:
        for r in grp.get("rows") or []:
            gp = _num(r.get("gp")) or ((_num(r.get("w")) or 0) + (_num(r.get("l")) or 0) + (_num(r.get("d")) or 0) + (_num(r.get("otl")) or 0))
            if not gp:
                continue
            pf, pa = _num(r.get("pf")), _num(r.get("pa"))
            if pf is None or pa is None:
                if _num(r.get("diff")) is not None:
                    pf, pa = _num(r["diff"]), 0.0
                else:
                    continue
            # 排名表給的是總分還是每場平均？籃球單場不可能超過 200，超過就當總分
            if pf > 200 or pa > 200:
                pf, pa = pf / gp, pa / gp
            table[str(r.get("team_id") or r.get("abbr") or "")] = dict(gp=gp, pf=pf, pa=pa, diff=pf - pa, name=r.get("name_zh") or r.get("team"))
    return table


def from_form(team):
    rows = [r for r in (team.get("form") or []) if r.get("pf") is not None and r.get("pa") is not None]
    if not rows:
        return None
    gp = len(rows)
    pf = sum(r["pf"] for r in rows) / gp
    pa = sum(r["pa"] for r in rows) / gp
    return dict(gp=gp, pf=pf, pa=pa, diff=pf - pa, name=team.get("name_zh") or team.get("name"), src="form")


def _ids(team):
    out = []
    for k in ("el_code", "jp_abbr", "id"):
        v = team.get(k)
        if v:
            out.append(str(v))
    return out


def rating(stat, sport):
    k = SHRINK_K.get(sport, 8)
    gp = stat["gp"]
    return stat["diff"] * gp / (gp + k)


def rate_game(g, lg, standings):
    sport = lg["sport"]
    table = team_table(standings.get(lg["key"]))
    sides = {}
    for side in ("home", "away"):
        t = g[side]
        stat = None
        for tid in _ids(t):
            if tid in table:
                stat = dict(table[tid], src="standings")
                break
        if stat is None:
            stat = from_form(t)
        if stat is None:
            return None
        sides[side] = stat
    hca = HCA.get(lg["key"], HCA_SPORT.get(sport, 2.5))
    rh, ra = rating(sides["home"], sport), rating(sides["away"], sport)
    imp_h = ((g["home"].get("injury_impact") or {}).get("pts") or 0) if sport == "basketball" else 0
    imp_a = ((g["away"].get("injury_impact") or {}).get("pts") or 0) if sport == "basketball" else 0
    edge = rh + hca - ra - imp_h + imp_a      # 正數 = 主隊比較強；缺陣的影響也扣進去
    sigma = SIGMA.get(sport, 11.0)
    prob_home = 0.5 * (1 + erf(edge / (sigma * sqrt(2))))
    o = g.get("odds") or {}
    tw = g.get("tw") or {}
    market = o.get("spread")
    if market is None and (tw.get("spread") or {}).get("line_home") is not None:
        market = tw["spread"]["line_home"]
    out = dict(
        home=round(rh, 1), away=round(ra, 1), hca=hca,
        gp_home=int(sides["home"]["gp"]), gp_away=int(sides["away"]["gp"]),
        src_home=sides["home"].get("src", "standings"), src_away=sides["away"].get("src", "standings"),
        our_spread=round(-edge * 2) / 2, our_prob_home=round(prob_home, 3),
        market_spread=market, weak=min(sides["home"]["gp"], sides["away"]["gp"]) < MIN_GP,
        impact_home=imp_h, impact_away=imp_a,
    )
    if market is not None:
        out["diff"] = round(market - out["our_spread"], 1)   # 負數 = 盤口比我們更看好主隊
    # 大小分：得分力 × 對手失分力
    pf_h, pa_h = sides["home"]["pf"], sides["home"]["pa"]
    pf_a, pa_a = sides["away"]["pf"], sides["away"]["pa"]
    if pa_h and pa_a and pf_h and pf_a:
        avg = (pf_h + pf_a + pa_h + pa_a) / 4
        if avg > 0:
            exp_h = pf_h * pa_a / avg
            exp_a = pf_a * pa_h / avg
            total = exp_h + exp_a
            if sport == "basketball":
                # 主場效應一點點、季初往聯盟平均拉
                total = total * (0.5 + 0.5 * min(1, (sides["home"]["gp"] + sides["away"]["gp"]) / 16)) + (2 * avg) * (0.5 - 0.5 * min(1, (sides["home"]["gp"] + sides["away"]["gp"]) / 16))
            out["total"] = round(total, 1)
            out["exp_home"], out["exp_away"] = round(exp_h, 1), round(exp_a, 1)
            mt = o.get("total")
            if mt is None and (tw.get("total") or {}).get("line") is not None:
                mt = tw["total"]["line"]
            if mt is not None:
                out["market_total"] = mt
                out["total_diff"] = round(total - mt, 1)
    return out


def rate_games(games, leagues_by_key, standings, log, errors):
    n = 0
    for g in games:
        lg = leagues_by_key.get(g["league"])
        if not lg or g.get("tennis") or g.get("sets"):
            continue
        try:
            r = rate_game(g, lg, standings)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{lg['key']} 評分 {g['id']} 失敗: {e!r}")
            r = None
        if r:
            g.setdefault("analysis", {})
            if isinstance(g["analysis"], dict):
                g["analysis"]["rating"] = r
                n += 1
    log(f"實力評分：{n}/{len(games)} 場有評分")
    return n


def rating_signals(g, lg):
    """給 build_suggestion 用：讓分盤差距、勝率差距。"""
    a = g.get("analysis") or {}
    r = a.get("rating")
    if not r:
        return []
    sport = lg["sport"]
    H, A = g["home"], g["away"]
    hn = H.get("name_zh") or H.get("name")
    an = A.get("name_zh") or A.get("name")
    sigs = []
    if r.get("weak"):
        sigs.append(dict(label="實力評分", side=None, weight=0,
                         text=f"兩隊才打 {min(r['gp_home'], r['gp_away'])} 場，評分還不準，先參考就好（我們算主隊讓 {-r['our_spread']:+g} 分）"))
        return sigs
    for side, t in (("home", H), ("away", A)):
        imp = t.get("injury_impact") or {}
        if imp.get("pts", 0) >= 1:
            names = "、".join(p["player"].split(" ")[-1] for p in imp["players"][:2])
            tn = hn if side == "home" else an
            other = "away" if side == "home" else "home"
            lm = a.get("line_move") or {}
            moved = ""
            if lm.get("spread_open") is not None and lm.get("spread_now") is not None and abs(lm["spread_now"] - lm["spread_open"]) >= 1:
                moved = "，盤口已經有動"
            sigs.append(dict(label="傷兵影響", side=other, weight=min(0.6, imp["pts"] * 0.12),
                             text=f"{tn}少了 {names}，大概差 {imp['pts']:g} 分{moved}"))
    th = EDGE_TH.get(sport, 3.0)
    if r.get("diff") is not None:
        d = r["diff"]
        ours = -r["our_spread"]   # 正數 = 主隊該讓幾分
        mk = -r["market_spread"]
        if d <= -th:
            sigs.append(dict(label="實力評分", side="away", weight=0.45,
                             text=f"照兩隊實力算主隊大概只該讓 {ours:g} 分，盤口開到 {mk:g}，讓分盤偏向{an}"))
        elif d >= th:
            sigs.append(dict(label="實力評分", side="home", weight=0.45,
                             text=f"照兩隊實力算主隊該讓 {ours:g} 分，盤口只開 {mk:g}，讓分盤偏向{hn}"))
        else:
            sigs.append(dict(label="實力評分", side=None, weight=0,
                             text=f"我們算主隊該讓 {ours:g} 分，跟盤口（{mk:g}）差不多"))
    return sigs
