# -*- coding: utf-8 -*-
"""球員看點：每隊 2～3 個主力，用一句白話講他這季打得怎樣、最近手感、上場時間、是不是新來的、有沒有傷。

  NBA：ESPN 逐場數據（這季得分、籃板、助攻、上場時間，近 5 場 vs 平均）；開季還沒打幾場就講上季的平均，
       上季只打幾場的多半是受傷或剛進聯盟，這季要看狀態
  歐冠、歐盃：官方球員數據（這季平均、效率值），官方逐場數據看近 5 場手感、上場時間；跟上季比、新來的上季在哪一隊
  日本籃球：B.LEAGUE 官網的球員平均
只是給爸爸看的說明，也交給 AI 寫進分析；不加分數（主力缺陣已經算在傷兵影響裡）。"""
import re
import unicodedata

from elbox import name_key as _latin_key

MAX = 3


def name_key(name):
    """比對名字用：英文名去重音、不管順序；日文名（沒有英文字母）用整串名字（去空白、中點）。"""
    k = _latin_key(name)
    if k:
        return k
    return re.sub(r"[\s・･·.]", "", unicodedata.normalize("NFKC", name or ""))


def _n(v):
    return f"{v:.0f}" if v is not None else None


def _stat_bits(pts, reb=None, ast=None, extra=None):
    bits = [f"{_n(pts)} 分"] if pts is not None else []
    if reb is not None and reb >= 4.5:
        bits.append(f"{_n(reb)} 籃板")
    if ast is not None and ast >= 3.5:
        bits.append(f"{_n(ast)} 助攻")
    if extra:
        bits.append(extra)
    return " ".join(bits)


def _minutes(p):
    a, b = p.get("min_last3"), p.get("min_base")
    if a is not None and b is not None and b >= 15 and a < 0.8 * b:
        return f"最近 3 場只打 {_n(a)} 分鐘（平常 {_n(b)}），可能在控制時間"
    if a is not None and b is not None and b >= 10 and a > 1.25 * b:
        return f"最近 3 場上場時間變多（{_n(a)} 分鐘，平常 {_n(b)}），教練越來越信任他"
    return None


def _trend(p):
    if p.get("label") == "火燙" and p.get("last5") is not None:
        return f"最近 5 場平均 {_n(p['last5'])} 分，手感正燙", "火燙"
    if p.get("label") == "冰冷" and p.get("last5") is not None:
        return f"最近 5 場只有 {_n(p['last5'])} 分，手感不太好", "冰冷"
    return None, None


def _item(p, text, tag, inj):
    x = inj.get(name_key(p.get("player")))
    return dict(player=p.get("player"), headshot=p.get("headshot"), tag=tag, text=text,
                status_zh=(x or {}).get("status_zh"), severity=(x or {}).get("severity"))


# ---------- NBA：名單＋全聯盟球員平均（開季還沒有球隊領袖名單，自己從名單挑主力） ----------
WEB = "https://site.web.api.espn.com/apis/common/v3/sports"
SITE = "https://site.api.espn.com/apis/site/v2/sports"


def _season_stats(get, season, log):
    """ESPN 全聯盟球員的平均（season：球季結束那年，2027 = 2026-27）。{球員 id: dict(team, gp, mpg, ppg, rpg, apg)}"""
    out, page, sample = {}, 1, None
    while page <= 12:
        js = get(f"{WEB}/basketball/nba/statistics/byathlete",
                 params=dict(region="us", lang="en", contentorigin="espn", isqualified="false", page=page, limit=100,
                             sort="offensive.avgPoints:desc", season=season, seasontype=2), quiet=True)
        if not isinstance(js, dict) or not js.get("athletes"):
            break
        cats = {c.get("name"): c.get("names") or [] for c in js.get("categories") or []}
        for a in js["athletes"]:
            ath = a.get("athlete") or {}
            vals = {}
            for c in a.get("categories") or []:
                for nm, v in zip(cats.get(c.get("name")) or [], c.get("values") or []):
                    vals[nm] = v
            pid = str(ath.get("id") or "")
            if not pid:
                continue
            team = str(ath.get("teamId") or (ath.get("team") or {}).get("id") or "")
            out[pid] = dict(team=team, team_abbr=ath.get("teamShortName"), gp=vals.get("gamesPlayed"), mpg=vals.get("avgMinutes"),
                            ppg=vals.get("avgPoints"), rpg=vals.get("avgRebounds"), apg=vals.get("avgAssists"))
            if sample is None:
                sample = dict(name=ath.get("displayName"), **out[pid])
        pg = js.get("pagination") or {}
        if page >= (pg.get("pages") or 1):
            break
        page += 1
    log(f"[nba] 球員平均（{season - 1}-{season % 100:02d}）：{len(out)} 人" + (f"，例：{sample}" if sample else ""))
    return out


def nba_prepare(games, get, season_year, log, errors):
    """每隊 t["nba_players"]：這季名單上的人，配上這季（打 3 場以上）或上季的平均、上季在哪一隊。"""
    teams = {}
    for g in games:
        if g["league"] == "nba" and g["status"]["state"] != "post" and not g.get("far"):
            for side in ("home", "away"):
                if g[side].get("id"):
                    teams.setdefault(str(g[side]["id"]), []).append(g[side])
    if not teams:
        return
    try:
        cur = _season_stats(get, season_year, log)
        prev = _season_stats(get, season_year - 1, log)
        prev2 = _season_stats(get, season_year - 2, log)     # 上季整季沒打的（受傷）看前一季
    except Exception as e:  # noqa: BLE001
        errors.append(f"nba 球員平均失敗: {e!r}")
        return
    from background import NBA_ID
    from names_zh import NBA as NBA_ZH
    n = 0
    for tid, ts in teams.items():
        js = get(f"{SITE}/basketball/nba/teams/{tid}/roster", quiet=True)
        roster = (js or {}).get("athletes") or []
        if roster and isinstance(roster[0], dict) and roster[0].get("items"):
            roster = [x for grp in roster for x in grp.get("items") or []]      # 有些回傳照位置分組
        players = []
        for a in roster:
            pid = str(a.get("id") or "")
            c, pv, p2 = cur.get(pid), prev.get(pid), prev2.get(pid)
            use = c if c and (c.get("gp") or 0) >= 3 else pv
            returning = False
            if (not use or (pv and (pv.get("gp") or 0) < 20)) and p2 and (p2.get("ppg") or 0) >= 12 and not (c and (c.get("gp") or 0) >= 3):
                use, returning = p2, True        # 上季沒打或只打幾場、前一季是主力：傷癒回來
            if not use or use.get("ppg") is None:
                continue
            prev_team = (pv or {}).get("team")
            moved = bool(pv and prev_team and prev_team != tid)
            players.append(dict(id=pid, player=a.get("displayName") or a.get("fullName"), headshot=(a.get("headshot") or {}).get("href"),
                                position=(a.get("position") or {}).get("abbreviation"), cur=bool(use is c), returning=returning, gp=use.get("gp"),
                                ppg=use.get("ppg"), rpg=use.get("rpg"), apg=use.get("apg"), mpg=use.get("mpg"),
                                prev_gp=(pv or {}).get("gp"), prev_ppg=(pv or {}).get("ppg"),
                                moved=moved, prev_team_zh=NBA_ZH.get(NBA_ID.get(prev_team, ""), (pv or {}).get("team_abbr")) if moved else None))
        players.sort(key=lambda p: -(p.get("ppg") or 0))
        for t in ts:
            t["nba_players"] = players[:6]
        n += bool(players)
    log(f"[nba] 球員看點用的名單：{n}/{len(teams)} 隊")


def _nba(t, inj, prev_rec=None):
    if t.get("nba_players"):
        return _nba_roster(t, inj, prev_rec)
    out = []
    for p in (t.get("hot") or []) + (t.get("prev_form") or []):
        if p.get("prev"):
            text = f"上季場均 {_stat_bits(p.get('season'), p.get('reb'), p.get('ast'))}（打了 {p.get('n_games')} 場）"
            tag = "上季"
            if (p.get("n_games") or 0) < 35:
                text += f"。上季只打 {p.get('n_games')} 場，可能是受傷，這季回來要看狀態"
                tag = "回歸"
        else:
            text = f"這季場均 {_stat_bits(p.get('season'), p.get('reb'), p.get('ast'))}"
            tr, tag = _trend(p)
            tag = tag or "主力"
            for extra in (tr, _minutes(p)):
                if extra:
                    text += "，" + extra
        out.append(_item(p, text + "。", tag, inj))
    return out


def _nba_roster(t, inj, prev_rec=None):
    hot = {name_key(h.get("player")): h for h in t.get("hot") or []}
    out = []
    for p in t["nba_players"][:MAX]:
        when = "這季" if p.get("cur") else "上季"
        text = f"{when}場均 {_stat_bits(p.get('ppg'), p.get('rpg'), p.get('apg'))}"
        tag = "主力"
        if p.get("returning"):
            tag = "回歸"
            pg = p.get("prev_gp")
            miss = "上季整季沒打" if not pg else f"上季只打了 {_n(pg)} 場"
            text = f"{miss}（多半是受傷），前一季場均 {_stat_bits(p.get('ppg'), p.get('rpg'), p.get('apg'))}，這季回來了"
            pr = prev_rec or {}
            if pr.get("w") is not None and pr["w"] / max(1, pr["w"] + pr.get("l", 0)) < 0.4:
                text += f"。上季球隊少了他只打出 {pr['w']} 勝 {pr['l']} 敗，這季的實力不能只看上季"
            else:
                text += "，要看他手感找不找得回來"
        elif p.get("moved"):
            tag = "新來的"
            text += f"，今年新來的（上季在{p['prev_team_zh']}）" if p.get("prev_team_zh") else "，今年新來的"
        elif not p.get("cur") and p.get("prev_gp") is not None and p["prev_gp"] < 35:
            tag = "回歸"
            text += f"，上季只打了 {_n(p['prev_gp'])} 場（可能是受傷），這季回來要看狀態"
        h = hot.get(name_key(p.get("player")))
        if h:
            tr, tg = _trend(h)
            if tr:
                text += "，" + tr
                tag = tg if tag == "主力" else tag
            mn = _minutes(h)
            if mn:
                text += "，" + mn
        out.append(_item(p, text + "。", tag, inj))
    return out


def _el(t, inj, el_state):
    code = t.get("el_code")
    stars = list(t.get("stars") or [])
    if not stars and code:
        roster = [p for p in (el_state.get("rosters") or {}).get(code) or [] if (p.get("gp") or 0) > 0]
        roster.sort(key=lambda p: -(p.get("ppg") or 0))
        stars = [dict(id=p["id"], player=p["name"], headshot=p.get("headshot"), ppg=p.get("ppg"), mpg=p.get("mpg"), pir=p.get("pir"),
                      rpg=p.get("rpg"), apg=p.get("apg"), gp=p.get("gp")) for p in roster[:4]]
    hot = {name_key(h.get("player")): h for h in t.get("hot") or []}
    arrived = {name_key(x["player"]): x for x in (t.get("moves") or {}).get("arrived") or []}
    prev = el_state.get("prev_players") or {}
    out = []
    for p in stars[:MAX]:
        k = name_key(p.get("player"))
        pir = f"效率值 {_n(p['pir'])}" if p.get("pir") is not None else None
        text = f"這季場均 {_stat_bits(p.get('ppg'), p.get('rpg'), p.get('apg'), pir)}"
        tag = "主力"
        a = arrived.get(k)
        pv = prev.get(p.get("id"))
        if a:
            tag = "新來的"
            if a.get("frm_zh") and a.get("ppg_prev") is not None:
                text += f"，新來的，上季在{a['frm_zh']}場均 {_n(a['ppg_prev'])} 分"
            else:
                text += "，今年新來的"
        elif pv and pv.get("team") == code and pv.get("ppg") is not None and p.get("ppg") is not None:
            d = p["ppg"] - pv["ppg"]
            if d >= 3:
                text += f"，比上季多 {_n(d)} 分，角色變重了"
            elif d <= -3:
                text += f"，比上季少 {_n(-d)} 分"
        h = hot.get(k)
        if h:
            tr, tg = _trend(h)
            if tr:
                text += "，" + tr
                tag = tg
            mn = _minutes(h)
            if mn:
                text += "，" + mn
        out.append(_item(p, text + "。", tag, inj))
    return out


def _jp(t, inj):
    out = []
    for p in (t.get("stars") or [])[:MAX]:
        if p.get("ppg") is None:
            continue
        mins = f"{_n(p['mpg'])} 分鐘" if p.get("mpg") is not None else None
        text = f"這季場均 {_stat_bits(p.get('ppg'), p.get('rpg'), p.get('apg'))}" + (f"、上場 {mins}" if mins else "")
        out.append(_item(p, text + "。", "主力", inj))
    return out


def build(g, el_state):
    """每隊的 t["spot"]。回傳有看點的隊數。"""
    n = 0
    for side in ("home", "away"):
        t = g[side]
        inj = {name_key(x.get("player")): x for x in t.get("injuries") or []}
        if g["league"] == "nba":
            spot = _nba(t, inj, (((g.get("analysis") or {}).get("bg") or {}).get("prev") or {}).get(side))
        elif g["league"] in ("eurobasket", "eurodom") and t.get("el_code"):
            spot = _el(t, inj, el_state)
        elif g["league"] == "jpbasket":
            spot = _jp(t, inj)
        else:
            spot = []
        if spot:
            t["spot"] = spot[:MAX]
            n += 1
    return n
