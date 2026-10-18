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
# 大小分當主建議的門檻（算出來的總分跟盤口差這麼多才推），以及總分的標準差（換算「大概幾成」用）
TOTAL_MAIN = {"basketball": 7.0, "hockey": 0.8, "football": 6.0, "soccer": 99.0}  # 足球的得失分算法還不可靠，先不拿大小分當主建議
TOTAL_SIGMA = {"basketball": 17.0, "hockey": 1.9, "football": 13.0, "soccer": 1.4}
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


def _record_gp(rec):
    """「3-1」→ 4；「0-0」→ 0；看不懂就 None。"""
    try:
        parts = [int(x) for x in str(rec).split("-")[:3]]
        return sum(parts)
    except (TypeError, ValueError):
        return None


def rating(stat, sport):
    k = SHRINK_K.get(sport, 8)
    gp = stat["gp"]
    return stat["diff"] * gp / (gp + k)


REST_PTS = {"basketball": 1.5, "hockey": 0.2}     # 背靠背第二場、對手有休息：大概差多少
FORM_W = 0.3        # 近況（扣掉對手強弱）佔多少；整季 10 場以上才混
PREV_W = 0.7        # 上季實力打七折（換人、老化），開季從這裡出發，打越多場越看本季
PREV_K = {"basketball": 10, "hockey": 12}   # 本季打幾場之後，本季跟上季各佔一半
FACTORS = ("notes", "form", "h2h", "rest", "hot", "motive")
FACTOR_ZH = {"notes": "傷兵備註、上場時間、輪休習慣", "form": "近況（扣掉對手強弱）", "h2h": "交手剋星", "rest": "背靠背體力",
             "hot": "主力手感（火燙／冰冷）", "motive": "戰意（拚季後賽、已經沒希望、名次已定）"}
HOT_PTS = 0.12      # 主力近 5 場比季平均多（少）1 分，球隊大概多（少）0.12 分
HOT_CAP = 1.5
# 戰意：球季打到七成以後才看。每組前幾名進季後賽（含附加賽）
SEASON_GAMES = {"nba": 82, "eurobasket": 38}
PLAYOFF_CUT = {"nba": 10, "eurobasket": 10}
MOTIVE_PTS = {"race": 0.8, "out": -1.5, "locked": -1.0}


def hot_pts(team):
    """主力手感：火燙加分、冰冷扣分；冰冷又帶傷扣多一點。"""
    hurt = {x["player"] for x in team.get("injuries") or [] if x.get("severity") in ("maybe", "limited")}
    v = 0.0
    for p in team.get("hot") or []:
        if p.get("label") not in ("火燙", "冰冷") or p.get("last5") is None or p.get("season") is None:
            continue
        d = (p["last5"] - p["season"]) * HOT_PTS
        if p["label"] == "冰冷" and p.get("player") in hurt:
            d *= 1.5
        v += d
    return max(-HOT_CAP, min(HOT_CAP, v))


def motive(standings_entry, team_ids, lg_key):
    """回傳 (分數, 說明)。球季打到七成以後才判斷：拚季後賽、已經沒希望、名次已定。"""
    total = SEASON_GAMES.get(lg_key)
    cut = PLAYOFF_CUT.get(lg_key)
    ids = {str(x) for x in team_ids if x}
    if not total or not cut or not ids:
        return 0.0, None
    for grp in (standings_entry or {}).get("groups") or []:
        rows = []
        for r in grp.get("rows") or []:
            w, l = _num(r.get("w")), _num(r.get("l"))
            if w is None or l is None:
                continue
            rows.append(dict(id=str(r.get("team_id") or ""), w=w, l=l))
        me = next((r for r in rows if r["id"] in ids), None)
        if not me:
            continue
        gp = me["w"] + me["l"]
        if gp < 0.7 * total or len(rows) <= cut:
            return 0.0, None
        rows.sort(key=lambda r: (-(r["w"] / max(1, r["w"] + r["l"])), -r["w"]))
        rank = rows.index(me) + 1
        left = total - gp
        line_in, line_out = rows[cut - 1], rows[cut]
        if rank > cut and me["w"] + left < line_in["w"]:
            return MOTIVE_PTS["out"], "已經確定進不了季後賽，常讓年輕人打"
        if rank == 1 and len(rows) > 1 and me["w"] - rows[1]["w"] > left:
            return MOTIVE_PTS["locked"], "第一名已經確定，主力可能輪休"
        if abs(me["w"] - (line_out["w"] if rank <= cut else line_in["w"])) <= 2 and left <= 0.3 * total:
            return MOTIVE_PTS["race"], "正在拚季後賽門檻，每場都很拚"
        return 0.0, None
    return 0.0, None


def _prob(edge, sigma):
    return 0.5 * (1 + erf(edge / (sigma * sqrt(2))))


def rate_game(g, lg, standings):
    from matchup import form_view
    sport = lg["sport"]
    table = team_table(standings.get(lg["key"]))
    ratings = {k: rating(v, sport) for k, v in table.items()}
    a = g.get("analysis") or {}
    prev = a.get("prev_rating") or {}
    sides = {}
    for side in ("home", "away"):
        t = g[side]
        stat = None
        for tid in _ids(t):
            if tid in table:
                stat = dict(table[tid], src="standings")
                break
        # 例行賽剛開打：比分板上的戰績（例行賽）跟排名表／近況（還是季前賽）對不起來，就不用季前賽的數字，從上季出發
        rec_gp = _record_gp(t.get("record")) if g.get("season_type") == 2 else None
        if rec_gp is not None and prev.get(side) is not None and (stat is None or abs(stat["gp"] - rec_gp) >= 1):
            stat = dict(gp=0, pf=None, pa=None, diff=0.0, src="prev")
        elif rec_gp == 0:
            return None      # 例行賽還沒打、上季資料也沒抓到：寧可不估，也不要拿季前賽來估
        if stat is None:
            stat = from_form(t)
        if stat is None and prev.get(side) is not None:
            stat = dict(gp=0, pf=None, pa=None, diff=0.0, src="prev")   # 本季還沒打：只有上季
        if stat is None:
            return None
        sides[side] = stat
    hca = HCA.get(lg["key"], HCA_SPORT.get(sport, 2.5))

    def eff(stat, side):
        # 有上季實力就從上季出發（打七折），本季打越多場越看本季；沒有就往 0 拉
        pv = prev.get(side)
        if pv is None:
            return rating(stat, sport)
        k = PREV_K.get(sport, 10)
        return (stat["diff"] * stat["gp"] + PREV_W * pv * k) / (stat["gp"] + k)
    rh, ra = eff(sides["home"], "home"), eff(sides["away"], "away")
    # 傷兵：新算法（讀備註、限時、輪休習慣）vs 舊算法（只看名單狀態）
    ih = (g["home"].get("injury_impact") or {}) if sport == "basketball" else {}
    ia = (g["away"].get("injury_impact") or {}) if sport == "basketball" else {}
    imp_h, imp_a = ih.get("pts") or 0, ia.get("pts") or 0
    imp_h0 = ih.get("pts_basic", imp_h) or 0
    imp_a0 = ia.get("pts_basic", imp_a) or 0
    # 近況
    fh, fa = form_view(g["home"], ratings, hca), form_view(g["away"], ratings, hca)
    def blend(stat, r, fv):
        if fv and stat.get("gp", 0) >= 10 and fv["n"] >= 4:
            return (1 - FORM_W) * r + FORM_W * fv["recent"]
        return r
    bh, ba = blend(sides["home"], rh, fh), blend(sides["away"], ra, fa)
    # 背靠背
    rest = a.get("rest") or {}
    rest_pts = REST_PTS.get(sport, 0)
    rest_d = 0.0
    if isinstance(rest, dict):
        rh_b = bool((rest.get("home") or {}).get("b2b"))
        ra_b = bool((rest.get("away") or {}).get("b2b"))
        if rh_b and not ra_b:
            rest_d = -rest_pts
        elif ra_b and not rh_b:
            rest_d = rest_pts
    # 交手剋星
    h2h_d = float((a.get("h2h_long") or {}).get("adj") or 0)
    # 主力手感、戰意
    hot_d = hot_pts(g["home"]) - hot_pts(g["away"]) if sport == "basketball" else 0.0
    st_entry = standings.get(lg["key"])
    mh, mh_why = motive(st_entry, _ids(g["home"]), lg["key"])
    ma, ma_why = motive(st_entry, _ids(g["away"]), lg["key"])
    comp = dict(
        base=rh + hca - ra - imp_h0 + imp_a0,
        notes=-(imp_h - imp_h0) + (imp_a - imp_a0),
        form=(bh - rh) - (ba - ra),
        h2h=h2h_d,
        rest=rest_d,
        hot=hot_d,
        motive=mh - ma,
    )
    edge = sum(comp.values())        # 正數 = 主隊比較強
    sigma = SIGMA.get(sport, 11.0)
    prob_home = _prob(edge, sigma)
    variants = dict(base=round(_prob(comp["base"], sigma), 3), full=round(prob_home, 3))
    for f in FACTORS:
        variants["no_" + f] = round(_prob(edge - comp[f], sigma), 3)
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
        parts={k: round(v, 1) for k, v in comp.items()}, variants=variants,
        form_home=fh, form_away=fa, season_diff_home=round(sides["home"]["diff"], 1), season_diff_away=round(sides["away"]["diff"], 1),
        prev_home=prev.get("home"), prev_away=prev.get("away"),
        motive_home=mh_why, motive_away=ma_why,
    )
    if market is not None:
        out["diff"] = round(market - out["our_spread"], 1)   # 負數 = 盤口比我們更看好主隊
    # 大小分：得分力 × 對手失分力
    pf_h, pa_h = sides["home"]["pf"], sides["home"]["pa"]
    pf_a, pa_a = sides["away"]["pf"], sides["away"]["pa"]
    if pa_h and pa_a and pf_h and pf_a and min(sides["home"]["gp"], sides["away"]["gp"]) >= 1:
        avg = (pf_h + pf_a + pa_h + pa_a) / 4
        if avg > 0:
            exp_h = pf_h * pa_a / avg
            exp_a = pf_a * pa_h / avg
            total = exp_h + exp_a
            if sport == "basketball":
                # 季初往聯盟平均拉；限時、缺陣的主力會讓總分少一點
                total = total * (0.5 + 0.5 * min(1, (sides["home"]["gp"] + sides["away"]["gp"]) / 16)) + (2 * avg) * (0.5 - 0.5 * min(1, (sides["home"]["gp"] + sides["away"]["gp"]) / 16))
                total -= 0.5 * (imp_h + imp_a)
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
