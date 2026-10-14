#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生本機測試用的範例資料 data/sample.json（不連網）。
網頁加上 ?data=sample 就會讀這份。"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch as F  # noqa: E402

TW = F.TW
now = datetime.now(timezone.utc)


def team(lg, abbr, name, short, tid, record, form, hot=None, injuries=None, color=None):
    logo_lg = {"nba": "nba", "nhl": "nhl", "eng.1": "soccer", "nfl": "nfl"}[lg]
    t = dict(id=tid, abbr=abbr, name=name, short=short, name_zh=F.zh_name(lg, abbr, name, short),
             logo=f"https://a.espncdn.com/i/teamlogos/{logo_lg}/500/{abbr.lower()}.png" if logo_lg != "soccer" else f"https://a.espncdn.com/i/teamlogos/soccer/500/{tid}.png",
             color=color, record=record, record_home=None, record_away=None, score=None, winner=False,
             form_str=None, leaders=[], injuries=injuries or [], key_out=[], key_maybe=[], out_count=0, maybe_count=0,
             hot=hot or [], form=[], form_note=None, streak=None, last10=None, last10_w=0,
             avg_for5=None, avg_against5=None, avg_total5=None, avg_margin5=None)
    rows = []
    base = now - timedelta(days=len(form) * 2)
    for i, (res, pf, pa, opp) in enumerate(form):
        d = base + timedelta(days=i * 2)
        rows.append(dict(date=d.astimezone(TW).strftime("%m/%d"), opp=opp, opp_zh=F.zh_name(lg, opp, opp, opp), opp_logo=None,
                         home=(i % 2 == 0), pf=pf, pa=pa, result=res))
    t["form"] = rows
    w = sum(1 for r in rows if r["result"] == "W"); l = sum(1 for r in rows if r["result"] == "L"); dr = sum(1 for r in rows if r["result"] == "D")
    t["last10"] = f"{w}勝{l}敗" + (f"{dr}和" if dr else "")
    t["last10_w"] = w
    s = 0; first = rows[-1]["result"]
    for r in reversed(rows):
        if r["result"] == first: s += 1
        else: break
    t["streak"] = {"W": "連勝", "L": "連敗", "D": "連和"}[first] + str(s) if s >= 2 else None
    last5 = rows[-5:]
    t["avg_for5"] = round(sum(r["pf"] for r in last5) / 5, 1)
    t["avg_against5"] = round(sum(r["pa"] for r in last5) / 5, 1)
    t["avg_total5"] = round(t["avg_for5"] + t["avg_against5"], 1)
    t["avg_margin5"] = round(t["avg_for5"] - t["avg_against5"], 1)
    t["out_count"] = sum(1 for x in t["injuries"] if x["severity"] == "out")
    t["maybe_count"] = sum(1 for x in t["injuries"] if x["severity"] == "maybe")
    return t


def inj(pid, player, pos, status, detail, lg="nba", ret=None):
    return dict(id=pid, player=player, headshot=f"https://a.espncdn.com/i/headshots/{lg}/players/full/{pid}.png",
                position=pos, position_zh=F.POS_ZH.get(pos), status=status, status_zh=F.STATUS_ZH.get(status, status),
                severity="out" if status in F.OUT_LIKE else ("maybe" if status in F.MAYBE_LIKE else "other"),
                detail=detail, side=None, return_date=ret, comment=None, date=None)


def hot(pid, player, pos, stat, last5, season, games, lg="nba"):
    delta = round((last5 - season) / season * 100)
    label = "火燙" if delta >= 15 else ("冰冷" if delta <= -15 else "平穩")
    return dict(id=pid, player=player, headshot=f"https://a.espncdn.com/i/headshots/{lg}/players/full/{pid}.png", position=pos,
                stat=stat, season_name="2026-27 例行賽", last5=last5, season=season, delta_pct=delta, label=label,
                games=[dict(date=f"10/{d}", opp=o, v=v) for d, o, v in games], n_games=12)


def odds(ml_h, ml_a, ml_d=None, spread=None, total=None, details=None):
    probs = {k: F.implied(v) for k, v in (("home", ml_h), ("away", ml_a), ("draw", ml_d)) if v is not None}
    s = sum(probs.values())
    fair = {k: round(v / s, 3) for k, v in probs.items()}
    return dict(provider="ESPN BET", details=details, spread=spread, total=total, ml_home=ml_h, ml_away=ml_a, ml_draw=ml_d,
                dec_home=F.dec(ml_h), dec_away=F.dec(ml_a), dec_draw=F.dec(ml_d),
                prob_home=fair.get("home"), prob_away=fair.get("away"), prob_draw=fair.get("draw"),
                fav="home" if ml_h is not None and ml_a is not None and ml_h < ml_a else "away")


def game(gid, lg, sport, hours_from_now, home, away, o, state="pre", scores=None, detail=None, news=None, venue=None, bc=None, headline=None):
    start = now + timedelta(hours=hours_from_now)
    stw = start.astimezone(TW)
    st = dict(state=state, completed=(state == "post"), detail=detail or ("未開賽" if state == "pre" else "已結束"), clock=None, period=None)
    if scores:
        home["score"], away["score"] = scores
    g = dict(id=gid, league=lg, league_zh=F.LEAGUE_ZH[lg], sport=sport, chip=F.chip_of(F.LEAGUES_BY_KEY[lg]), tennis=False, tournament=None, round=None,
             name=f"{away['abbr']} @ {home['abbr']}", start=F.iso(start), start_tw=F.iso(stw), day_tw=stw.strftime("%Y-%m-%d"),
             time_tw=stw.strftime("%H:%M"), status=st, venue=venue, broadcast=bc, home=home, away=away, odds=o,
             headline=headline, news=news or [], suggestion=None)
    for side in ("home", "away"):
        t = g[side]
        leaders = {p["player"] for p in t["hot"]}
        t["key_out"] = [x["player"] for x in t["injuries"] if x["severity"] == "out" and x["player"] in leaders]
        t["key_maybe"] = [x["player"] for x in t["injuries"] if x["severity"] == "maybe" and x["player"] in leaders]
    g["suggestion"] = F.build_suggestion(g, F.LEAGUES_BY_KEY[lg])
    return g


def plain_team(lg, name, name_zh, tid, form, logo=None, rank_note=None, record=None, injury_news=None, injury_note=None, en_key=None, jp_name=None):
    """沒有 ESPN 的聯盟：隊名、隊徽、近況、排名說明、傷兵新聞。"""
    t = dict(id=tid, abbr=name[:3].upper(), name=name, short=name, name_zh=name_zh, logo=logo, color=None, record=record,
             record_home=None, record_away=None, score=None, winner=False, form_str=None, leaders=[], injuries=[], key_out=[], key_maybe=[],
             out_count=0, maybe_count=0, hot=[], form=[], form_note=None, streak=None, last10=None, last10_w=0,
             avg_for5=None, avg_against5=None, avg_total5=None, avg_margin5=None, rank_note=rank_note,
             injury_news=injury_news or [], injury_note=injury_note, en_key=en_key, jp_name=jp_name)
    rows = []
    base = now - timedelta(days=len(form) * 3)
    for i, (res, pf, pa, opp, home) in enumerate(form):
        d = base + timedelta(days=i * 3)
        rows.append(dict(date=d.astimezone(TW).strftime("%m/%d"), date_iso=d.isoformat(timespec="minutes"), opp=opp, opp_zh=opp, opp_logo=None, home=home, pf=pf, pa=pa, result=res, comp=None))
    from playsport import summarize_form
    summarize_form(t, rows, note="官方賽程")
    if record:
        t["record"] = record
    return t


def new_league_games():
    el = "https://media-cdn.incrowdsports.com/"
    fen = plain_team("eurobasket", "Fenerbahce Beko Istanbul", "費內巴切", "ps8-1", [("W", 88, 80, "皇家馬德里", True), ("W", 95, 83, "摩納哥", False), ("L", 77, 84, "奧林匹亞科斯", False), ("W", 90, 86, "巴塞隆納", True)],
                     logo=el + "371b0d9b-9250-4c09-bda7-0686cf024657.png", rank_note="歐冠第 4 名", record="3-1", en_key="Fenerbahce",
                     injury_news=[dict(title="Fenerbahce star Wade Baldwin ruled out two weeks with ankle sprain", url="https://news.google.com/", published="2026-10-11T08:00", source="Eurohoops")],
                     injury_note="沒有官方傷兵名單，近 10 天新聞有提到傷兵相關消息（1 則，點進去看）")
    zal = plain_team("eurobasket", "Zalgiris Kaunas", "考納斯綠林", "ps8-2", [("W", 92, 85, "巴黎", True), ("W", 81, 79, "米蘭", True), ("W", 99, 90, "拜仁", False), ("L", 70, 88, "帕納辛奈科斯", False)],
                     logo=el + "1efae090-16e2-4963-ae47-4b94f249c244.png", rank_note="歐冠第 6 名", record="3-1", en_key="Zalgiris",
                     injury_note="沒有官方傷兵名單；近 10 天新聞沒有提到這隊的傷兵消息，通常代表陣容完整，但賽前仍可能臨時缺陣")
    g_el = game("e1", "eurobasket", "basketball", 5.5, fen, zal, None, venue=None)
    g_el["round"] = g_el["comp"] = "歐冠 Round 5"
    g_el["odds"] = dict(provider="台灣運彩", dec_home=1.23, dec_away=2.8, dec_draw=None, prob_home=0.67, prob_away=0.33, prob_draw=None, prob_source="spread", spread=-6.5, details="費內巴切 6分贏", total=164.0)
    g_el["tw"] = dict(source="玩運彩", url="https://www.playsport.cc/predict/scale?allianceid=8", updated=now.astimezone(TW).isoformat(timespec="minutes"), no="306",
                      spread=dict(line="費內巴切 -6.5", line_home=-6.5, home=1.68, away=1.75), ml=dict(home=1.23, away=2.8, draw=None), total=dict(line=163.5, over=1.73, under=1.7),
                      intl=dict(spread_home=-6.0, total=164.0, spread_text="費內巴切 6分贏"), crowd=dict(ml_home=82, ml_away=18, spread_home=48, spread_away=52, over=53, under=47, n=57))
    g_el["analysis"] = dict(crowd=g_el["tw"]["crowd"])
    g_el["news"] = [dict(title="Fenerbahce edge Barcelona in EuroLeague thriller", desc=None, url="https://news.google.com/", image=None, published="2026-10-12T21:00", source="Eurohoops", team="home")]

    toy = plain_team("jpbasket", "富山グラウジーズ", "富山松雞", "ps97-1", [("W", 94, 74, "千葉阿爾提里", False), ("L", 77, 81, "京都創榮", True), ("W", 88, 80, "信州勇士", True), ("W", 90, 85, "茨城機器人", False)],
                     rank_note="B.LEAGUE 東區第 4 名", record="4-3", jp_name="富山グラウジーズ", injury_note="沒有官方傷兵名單；近 10 天新聞沒有提到這隊的傷兵消息，通常代表陣容完整，但賽前仍可能臨時缺陣")
    chb = plain_team("jpbasket", "千葉ジェッツ", "千葉噴射機", "ps97-2", [("L", 70, 88, "廣島飛龍", False), ("W", 95, 90, "仙台89ers", True), ("L", 80, 92, "群馬雷霆", True), ("L", 78, 85, "琉球黃金國王", False)],
                     rank_note="B.LEAGUE 東區第 11 名", record="2-5", jp_name="千葉ジェッツ",
                     injury_news=[dict(title="千葉ジェッツ 富樫勇樹が左足首の負傷で欠場へ", url="https://news.google.com/", published="2026-10-12T03:00", source="バスケットボールキング")],
                     injury_note="沒有官方傷兵名單，近 10 天新聞有提到傷兵相關消息（1 則，點進去看）")
    g_jp = game("j1", "jpbasket", "basketball", 16, toy, chb, None)
    g_jp["round"] = g_jp["comp"] = "B.LEAGUE"
    g_jp["odds"] = dict(provider="台灣運彩", dec_home=1.45, dec_away=2.1, dec_draw=None, prob_home=0.6, prob_away=0.4, prob_source="tw_ml", prob_draw=None, spread=-3.5, details="富山松雞 -3.5", total=168.5)
    g_jp["tw"] = dict(source="玩運彩", url="https://www.playsport.cc/predict/scale?allianceid=97", updated=now.astimezone(TW).isoformat(timespec="minutes"), no="401",
                      spread=dict(line="富山松雞 -3.5", line_home=-3.5, home=1.72, away=1.72), ml=dict(home=1.45, away=2.1, draw=None), total=dict(line=168.5, over=1.7, under=1.73), intl=None,
                      crowd=dict(ml_home=64, ml_away=36, spread_home=55, spread_away=45, over=40, under=60, n=31))
    g_jp["analysis"] = dict(crowd=g_jp["tw"]["crowd"])

    sv = "https://www.svleague.jp/files/2026-27/team/"
    saga = plain_team("jpvolley", "SAGA久光", "佐賀久光泉水", "sv-sagahm", [("W", 3, 1, "A愛知", True), ("W", 3, 2, "A愛知", True), ("W", 3, 0, "岡山", False), ("L", 1, 3, "NEC川崎", False)], logo=sv + "sagahm/emblem.png", jp_name="SAGA久光")
    nec = plain_team("jpvolley", "NEC川崎", "NEC紅火箭川崎", "sv-nec", [("W", 3, 1, "佐賀久光", True), ("W", 3, 0, "デンソー", True), ("L", 2, 3, "大阪MV", False), ("W", 3, 1, "PFU", False)], logo=sv + "nec/emblem.png", jp_name="NEC川崎",
                     injury_note="沒有官方傷兵名單；近 10 天新聞沒有提到這隊的傷兵消息，通常代表陣容完整，但賽前仍可能臨時缺陣")
    for t in (saga, nec):
        t["avg_for5"] = t["avg_against5"] = t["avg_total5"] = t["avg_margin5"] = None
        t["form_note"] = "SV.LEAGUE 官網賽果（局數）"
    g_sv = game("v1", "jpvolley", "volleyball", 14, saga, nec, None)
    g_sv["round"] = "女子"; g_sv["comp"] = "SV.LEAGUE 女子"; g_sv["sets"] = True; g_sv["gender"] = "女"
    for g in (g_el, g_jp, g_sv):
        if not g.get("odds") or g["odds"].get("prob_home") is None:
            est = F.estimate_from_form(g)
            if est:
                g["odds"] = est
        F.fill_notes(g, F.LEAGUES_BY_KEY[g["league"]])
        g["suggestion"] = F.build_suggestion(g, F.LEAGUES_BY_KEY[g["league"]])
    return [g_el, g_jp, g_sv]


def sv_logo(code):
    return f"https://www.svleague.jp/files/2026-27/team/{code}/emblem.png"


def main():
    lal = team("nba", "LAL", "Los Angeles Lakers", "Lakers", "13", "4-1",
               [("W", 118, 109, "PHX"), ("W", 112, 104, "SAC"), ("L", 101, 115, "DEN"), ("W", 124, 117, "MIN"), ("W", 110, 102, "POR"), ("W", 121, 113, "GS")],
               hot=[hot("1966", "LeBron James", "SF", "PTS", 28.6, 24.1, [(3, "PHX", 27), (5, "SAC", 31), (7, "DEN", 24), (9, "MIN", 33), (11, "POR", 28)]),
                    hot("3136195", "Austin Reaves", "SG", "PTS", 15.2, 19.8, [(3, "PHX", 14), (5, "SAC", 18), (7, "DEN", 12), (9, "MIN", 16), (11, "POR", 16)])],
               injuries=[inj("6583", "Anthony Davis", "PF", "Out", "膝蓋", ret="2026-10-20"), inj("4066648", "Jarred Vanderbilt", "PF", "Questionable", "腳踝")])
    bos = team("nba", "BOS", "Boston Celtics", "Celtics", "2", "3-2",
               [("W", 115, 108, "NY"), ("L", 99, 105, "MIA"), ("W", 120, 110, "TOR"), ("L", 104, 112, "PHI"), ("W", 118, 101, "CHA"), ("L", 108, 116, "CLE")],
               hot=[hot("4065648", "Jayson Tatum", "SF", "PTS", 33.4, 27.2, [(2, "NY", 35), (4, "MIA", 29), (6, "TOR", 38), (8, "PHI", 31), (10, "CHA", 34)])],
               injuries=[inj("3917376", "Jaylen Brown", "SG", "Day-To-Day", "腿後肌")])
    gsw = team("nba", "GS", "Golden State Warriors", "Warriors", "9", "2-3",
               [("L", 104, 118, "LAL"), ("W", 122, 108, "UTAH"), ("L", 100, 109, "OKC"), ("L", 111, 120, "DEN"), ("W", 115, 110, "SAC"), ("L", 98, 112, "HOU")],
               hot=[hot("3975", "Stephen Curry", "PG", "PTS", 21.0, 26.5, [(2, "LAL", 18), (4, "UTAH", 25), (6, "OKC", 19), (8, "DEN", 22), (10, "SAC", 21)])],
               injuries=[inj("3975", "Stephen Curry", "PG", "Out", "腳踝"), inj("6589", "Draymond Green", "PF", "Out", "禁賽")])
    okc = team("nba", "OKC", "Oklahoma City Thunder", "Thunder", "25", "5-0",
               [("W", 120, 100, "DAL"), ("W", 115, 103, "GS"), ("W", 128, 110, "HOU"), ("W", 112, 106, "MEM"), ("W", 119, 104, "SA"), ("W", 123, 109, "POR")],
               hot=[hot("4278073", "Shai Gilgeous-Alexander", "PG", "PTS", 34.8, 30.1, [(1, "DAL", 36), (3, "GS", 31), (5, "HOU", 40), (7, "MEM", 33), (9, "SA", 34)])],
               injuries=[])

    mci = team("eng.1", "MCI", "Manchester City", "Man City", "382", "5-2-1",
               [("W", 3, 0, "BUR"), ("W", 2, 1, "ARS"), ("D", 1, 1, "LIV"), ("W", 4, 0, "FUL"), ("W", 2, 0, "EVE"), ("W", 3, 1, "BHA")],
               injuries=[inj("166676", "Rodri", "M", "Out", "膝蓋", lg="soccer")])
    ars = team("eng.1", "ARS", "Arsenal", "Arsenal", "359", "6-1-1",
               [("W", 2, 0, "TOT"), ("W", 1, 0, "NEW"), ("W", 3, 1, "CHE"), ("W", 2, 1, "AVL"), ("L", 1, 2, "MCI"), ("W", 2, 0, "WHU")],
               injuries=[inj("250586", "Bukayo Saka", "FW", "Doubtful", "腿後肌", lg="soccer")])
    liv = team("eng.1", "LIV", "Liverpool", "Liverpool", "364", "5-1-2",
               [("W", 2, 1, "BOU"), ("D", 1, 1, "MCI"), ("L", 0, 2, "CHE"), ("W", 3, 0, "EVE"), ("W", 2, 0, "CRY"), ("L", 1, 2, "MUN")])
    tot = team("eng.1", "TOT", "Tottenham Hotspur", "Tottenham", "367", "3-2-3",
               [("L", 0, 2, "ARS"), ("W", 2, 1, "BRE"), ("D", 2, 2, "WOL"), ("L", 1, 3, "AVL"), ("W", 3, 0, "LEE"), ("D", 1, 1, "NFO")])

    edm = team("nhl", "EDM", "Edmonton Oilers", "Oilers", "6", "3-1-1",
               [("W", 4, 2, "CGY"), ("W", 5, 3, "VAN"), ("L", 2, 4, "COL"), ("W", 3, 1, "SEA"), ("W", 6, 2, "SJ")],
               hot=[hot("3114778", "Connor McDavid", "C", "PTS", 2.4, 1.6, [(5, "CGY", 3), (7, "VAN", 2), (9, "COL", 1), (11, "SEA", 3), (13, "SJ", 3)], lg="nhl")])
    tor = team("nhl", "TOR", "Toronto Maple Leafs", "Maple Leafs", "21", "2-3-0",
               [("L", 1, 3, "MTL"), ("W", 4, 1, "OTT"), ("L", 2, 5, "DET"), ("L", 2, 3, "BUF"), ("W", 3, 2, "BOS")],
               injuries=[inj("4024123", "Auston Matthews", "C", "Day-To-Day", "上半身", lg="nhl")])

    news_lal = [dict(title="Anthony Davis 膝傷持續缺席，湖人禁區輪替吃緊", desc="", url="https://www.espn.com/", image="https://a.espncdn.com/photo/2024/0109/r1274140_1296x729_16-9.jpg", published="2026-10-13T02:10:00Z", team="home"),
                dict(title="LeBron 近五場場均 28.6 分，湖人四連勝", desc="", url="https://www.espn.com/", image=None, published="2026-10-12T20:00:00Z", team="home"),
                dict(title="Jaylen Brown 腿後肌不適，賽前決定是否出賽", desc="", url="https://www.espn.com/", image=None, published="2026-10-12T18:30:00Z", team="away")]

    games = [
        game("g1", "nba", "basketball", 6.5, lal, bos, odds(-165, 140, spread=-3.5, total=224.5, details="LAL -3.5"), news=news_lal, venue="Crypto.com Arena", bc="ESPN"),
        game("g2", "nba", "basketball", 9, okc, gsw, odds(-420, 330, spread=-9.5, total=226.0, details="OKC -9.5"), venue="Paycom Center", bc="TNT"),
        game("g3", "nba", "basketball", -1.2, bos, okc, odds(120, -140, spread=2.5, total=228.5, details="OKC -2.5"), state="in", scores=("78", "81"), detail="第 3 節 05:12"),
        game("g4", "eng.1", "soccer", 27, mci, ars, odds(105, 240, ml_d=250, spread=-0.5, total=2.5, details="MCI -0.5"), venue="Etihad Stadium"),
        game("g5", "eng.1", "soccer", 29.5, liv, tot, odds(-160, 400, ml_d=300, total=3.0, details="LIV -1"), venue="Anfield"),
        game("g6", "nhl", "hockey", 11, edm, tor, odds(-150, 125, spread=-1.5, total=6.5, details="EDM -1.5"), venue="Rogers Place"),
        game("g7", "nba", "basketball", -7, gsw, lal, odds(150, -180), state="post", scores=("104", "118"), detail="已結束"),
    ]
    games += new_league_games()
    games.sort(key=lambda g: g["start"])
    # 範例：第一場掛上台灣運彩盤口，看介面
    g1 = next(g for g in games if g["id"] == "g1")
    g1["tw"] = dict(source="玩運彩", url="https://www.playsport.cc/predict/scale?allianceid=3", updated=now.astimezone(TW).isoformat(timespec="minutes"), no="327",
                    spread=dict(line="湖人 -3.5", line_home=-3.5, home=1.75, away=1.68), ml=dict(home=1.5, away=1.96, draw=None),
                    total=dict(line=228.5, over=1.7, under=1.73), intl=None)
    g1["analysis"] = dict(
        predictor=dict(home=0.66, away=0.34, source="ESPN"), live_prob=None,
        ats=dict(home="3-2-0", away="2-3-0"),
        h2h=dict(summary="本季系列 1-1", games=[dict(date="10/06", home="LAL", away="BOS", hs=112, **{"as": 104}, winner="home"), dict(date="03/11", home="BOS", away="LAL", hs=120, **{"as": 110}, winner="away")]),
        line_move=dict(provider="ESPN BET", spread_open=-2.5, spread_now=-3.5, total_open=226.5, total_now=224.5),
        rest=dict(home=dict(days=2, b2b=False, last7=3), away=dict(days=0, b2b=True, last7=4)),
        lineup=None,
        books=[dict(provider="ESPN BET", spread=-3.5, total=224.5, dec_home=1.61, dec_away=2.4), dict(provider="DraftKings", spread=-3.0, total=225.0, dec_home=1.59, dec_away=2.45), dict(provider="FanDuel", spread=-3.5, total=224.5, dec_home=1.62, dec_away=2.38)],
    )
    for r in bos["form"]:
        r["date_iso"] = (now - timedelta(hours=20)).isoformat(timespec="minutes")
    g1["suggestion"] = F.build_suggestion(g1, F.LEAGUES_BY_KEY["nba"])
    from story import build_story
    for g in games:
        if "notes" not in g:
            F.fill_notes(g, F.LEAGUES_BY_KEY[g["league"]])
        talk = build_story(g, g["sport"])
        g["suggestion"]["talk"] = talk
        g["suggestion"]["story"] = [talk["verdict"]] + talk["why"] + talk["care"] + [talk["odds"]]
    feed, hotp = F.aggregate(games)
    standings = {
        "eurobasket": dict(label="歐洲籃球", sport="basketball", chip="eurobasket", groups=[dict(name="歐冠 Regular Season", rows=[
            dict(pos=1, team_id="PAN", team="Panathinaikos AKTOR Athens", abbr="PAN", name_zh="Panathinaikos", logo=None, w=4, l=0, pct=".1000", streak=None, diff=83),
            dict(pos=2, team_id="PAM", team="Valencia Basket", abbr="PAM", name_zh="Valencia", logo=None, w=4, l=0, pct=".1000", streak=None, diff=49),
            dict(pos=3, team_id="OLY", team="Olympiacos Piraeus", abbr="OLY", name_zh="Olympiacos", logo=None, w=3, l=1, pct=".750", streak=None, diff=40),
        ])]),
        "jpbasket": dict(label="日本籃球", sport="basketball", chip="jpbasket", groups=[dict(name="東地区", rows=[
            dict(pos=1, team_id="群馬", team="群馬クレインサンダーズ", abbr="群馬", name_zh="群馬雷霆", logo=None, w=6, l=1, pct=".857", streak="W1", last5="4-1"),
            dict(pos=2, team_id="仙台", team="仙台89ERS", abbr="仙台", name_zh="仙台89ers", logo=None, w=4, l=3, pct=".571", streak="W3", last5="3-2"),
            dict(pos=3, team_id="富山", team="富山グラウジーズ", abbr="富山", name_zh="富山松雞", logo=None, w=4, l=3, pct=".571", streak="W2", last5="3-2"),
        ])]),
        "jpvolley": dict(label="日本排球", sport="volleyball", chip="jpvolley", groups=[dict(name="女子（依本站抓到的賽果計算，可能不完整）", rows=[
            dict(pos=1, team_id="sagahm", team="SAGA久光", abbr="SAGA久光", name_zh="佐賀久光泉水", logo=sv_logo("sagahm"), w=3, l=1, pct=".750", streak=None, sets="10-6"),
            dict(pos=2, team_id="nec", team="NEC川崎", abbr="NEC川崎", name_zh="NEC紅火箭川崎", logo=sv_logo("nec"), w=3, l=1, pct=".750", streak=None, sets="11-5"),
        ])]),
        "nba": dict(label="NBA", sport="basketball", chip="nba", groups=[dict(name="西區", rows=[
            dict(pos=1, team_id="25", team="Oklahoma City Thunder", abbr="OKC", name_zh="雷霆", logo="https://a.espncdn.com/i/teamlogos/nba/500/okc.png", w=5, l=0, pct=".1000", streak="W5"),
            dict(pos=2, team_id="13", team="Los Angeles Lakers", abbr="LAL", name_zh="湖人", logo="https://a.espncdn.com/i/teamlogos/nba/500/lal.png", w=4, l=1, pct=".800", streak="W4"),
            dict(pos=3, team_id="9", team="Golden State Warriors", abbr="GS", name_zh="勇士", logo="https://a.espncdn.com/i/teamlogos/nba/500/gs.png", w=2, l=3, pct=".400", streak="L1"),
        ]), dict(name="東區", rows=[
            dict(pos=1, team_id="2", team="Boston Celtics", abbr="BOS", name_zh="塞爾提克", logo="https://a.espncdn.com/i/teamlogos/nba/500/bos.png", w=3, l=2, pct=".600", streak="L1"),
        ])]),
        "eng.1": dict(label="英超", sport="soccer", chip="soccer", groups=[dict(name="", rows=[
            dict(pos=1, team_id="359", team="Arsenal", abbr="ARS", name_zh="兵工廠", logo="https://a.espncdn.com/i/teamlogos/soccer/500/359.png", gp=8, w=6, d=1, l=1, points=19),
            dict(pos=2, team_id="382", team="Manchester City", abbr="MCI", name_zh="曼城", logo="https://a.espncdn.com/i/teamlogos/soccer/500/382.png", gp=8, w=5, d=2, l=1, points=17),
            dict(pos=3, team_id="364", team="Liverpool", abbr="LIV", name_zh="利物浦", logo="https://a.espncdn.com/i/teamlogos/soccer/500/364.png", gp=8, w=5, d=1, l=2, points=16),
        ])]),
    }
    # 實力評分與成績單的範例
    from model import rate_games
    rate_games(games, F.LEAGUES_BY_KEY, standings, lambda m: None, [])
    for g in games:
        g["suggestion"] = F.build_suggestion(g, F.LEAGUES_BY_KEY[g["league"]])
        talk = build_story(g, g["sport"])
        g["suggestion"]["talk"] = talk
        g["suggestion"]["story"] = [talk["verdict"]] + talk["why"] + talk["care"] + [talk["odds"]]
    record = dict(days=30, since="2026-10-01", settled=12, pending=5,
                  overall=dict(n=12, ml_w=8, ml_l=4, ml_p=0, ats_w=6, ats_l=5, ats_p=1, ou_w=3, ou_l=2, clv_avg=0.4, clv_n=11, clv_dec_avg=0.02, ml_rate=67, ats_rate=55),
                  by_league={"nba": dict(n=7, ml_w=5, ml_l=2, ml_p=0, ats_w=4, ats_l=3, ats_p=0, ou_w=2, ou_l=1, clv_avg=0.3, clv_n=7, clv_dec_avg=0.01, ml_rate=71, ats_rate=57),
                             "eurobasket": dict(n=5, ml_w=3, ml_l=2, ml_p=0, ats_w=2, ats_l=2, ats_p=1, ou_w=1, ou_l=1, clv_avg=0.6, clv_n=4, clv_dec_avg=0.04, ml_rate=60, ats_rate=50)},
                  by_conf={"高": dict(n=6, ml_w=5, ml_l=1, ml_p=0, ats_w=4, ats_l=2, ats_p=0, ou_w=1, ou_l=1, clv_avg=0.5, clv_n=6, clv_dec_avg=0.02, ml_rate=83, ats_rate=67),
                           "中": dict(n=6, ml_w=3, ml_l=3, ml_p=0, ats_w=2, ats_l=3, ats_p=1, ou_w=2, ou_l=1, clv_avg=0.3, clv_n=5, clv_dec_avg=0.01, ml_rate=50, ats_rate=40)},
                  by_play={},
                  recent=[dict(id="g7", league_zh="NBA", chip="nba", day_tw="2026-10-13", time_tw="07:00", home="湖人", away="勇士", pick="home", pick_label="湖人", play="不讓分", confidence="高", dec=1.5, line=-3.5, hs=118, as_=104, ml="win", ats="win", ou="win", clv=1.0, total_lean="大"),
                          dict(id="e1", league_zh="歐洲籃球", chip="eurobasket", day_tw="2026-10-12", time_tw="02:30", home="費內巴切", away="考納斯綠林", pick="home", pick_label="費內巴切", play="讓分", confidence="中", dec=1.23, line=-6.5, hs=80, as_=78, ml="win", ats="loss", ou=None, clv=-0.5, total_lean=None),
                          dict(id="g2", league_zh="NBA", chip="nba", day_tw="2026-10-12", time_tw="10:00", home="雷霆", away="勇士", pick="home", pick_label="雷霆", play="不讓分", confidence="高", dec=1.2, line=-9.5, hs=101, as_=109, ml="loss", ats="loss", ou=None, clv=0.0, total_lean=None)])
    out = dict(generated_at=now.astimezone(TW).isoformat(timespec="minutes"), generated_ts=int(now.timestamp()), record=record,
               today_tw=now.astimezone(TW).strftime("%Y-%m-%d"), sports=F.SPORTS,
               leagues={k: F.LEAGUE_ZH.get(k, k) for k in F.LEAGUES_BY_KEY}, games=games, injury_feed=feed, hot_players=hotp,
               standings=standings, source="範例資料（非即時）", errors=[], calls=0)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "sample.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("寫入", path, len(games), "場")


if __name__ == "__main__":
    main()
