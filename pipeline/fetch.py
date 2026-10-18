#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓今日賽事、盤口、傷兵、球員近況、球隊近況與新聞，輸出 data/today.json。
只用 ESPN 的公開接口，不需要任何 key，也不用錢。

用法：python pipeline/fetch.py            # 正式輸出
      python pipeline/fetch.py --out x.json
"""
import json
import os
import re
import sys
import time
import argparse
from datetime import datetime, timedelta, timezone
from statistics import mean
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from names_zh import LEAGUE_ZH, STATUS_ZH, OUT_LIKE, MAYBE_LIKE, POS_ZH, zh_name  # noqa: E402

TW = ZoneInfo("Asia/Taipei")
SITE = "https://site.api.espn.com/apis/site/v2/sports"
SITE_V2 = "https://site.api.espn.com/apis/v2/sports"
WEB = "https://site.web.api.espn.com/apis/common/v3/sports"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}
WINDOW_BACK_H = 10     # 保留幾小時前開打的比賽（含剛結束的）
WINDOW_AHEAD_H = 40    # 往後看幾小時
# 爸爸要看的球種多抓幾天：昨天（對答案）到 3 天後，網頁有日期列表可以切
MAIN_DAYS_AHEAD = 3
NEAR_H = 48            # 48 小時內的比賽才做完整分析（單場 summary、新聞、球員名單）；更後面的先放基本資料
NEAR_HI = None         # main() 裡設定

# total_th：兩隊近五場平均總分 與 盤口大小分 差多少才建議大/小
LEAGUES = [
    dict(key="nba", sport="basketball", path="basketball/nba", injuries=True, gamelog=True,
         stat="PTS", hot_min=10, total_th=6, headshot="nba"),
    # 以玩運彩為主幹的聯盟（ESPN 沒有）：賽程、台灣盤、國際盤、玩家預測、球隊歷史戰績都從玩運彩來
    dict(key="eurobasket", label="歐洲籃球", sport="basketball", source="playsport", alliance=8,
         injuries=False, gamelog=False, total_th=6, headshot=None),
    dict(key="jpbasket", label="日本籃球", sport="basketball", source="playsport", alliance=97,
         injuries=False, gamelog=False, total_th=6, headshot=None),
    # 日本排球：SV.LEAGUE 官網，沒有盤口
    dict(key="jpvolley", label="日本排球", sport="volleyball", source="svleague",
         injuries=False, gamelog=False, total_th=99, headshot=None),
    dict(key="nhl", sport="hockey", path="hockey/nhl", injuries=True, gamelog=True,
         stat="PTS", hot_min=0.5, total_th=0.6, headshot="nhl"),
    dict(key="nfl", sport="football", path="football/nfl", injuries=True, gamelog=False,
         total_th=4, headshot="nfl"),
    dict(key="eng.1", sport="soccer", path="soccer/eng.1", injuries=True, gamelog=False, total_th=0.5, headshot="soccer"),
    dict(key="esp.1", sport="soccer", path="soccer/esp.1", injuries=True, gamelog=False, total_th=0.5, headshot="soccer"),
    dict(key="ita.1", sport="soccer", path="soccer/ita.1", injuries=True, gamelog=False, total_th=0.5, headshot="soccer"),
    dict(key="ger.1", sport="soccer", path="soccer/ger.1", injuries=True, gamelog=False, total_th=0.5, headshot="soccer"),
    dict(key="fra.1", sport="soccer", path="soccer/fra.1", injuries=True, gamelog=False, total_th=0.5, headshot="soccer"),
    dict(key="uefa.champions", sport="soccer", path="soccer/uefa.champions", injuries=False, gamelog=False, total_th=0.5, headshot="soccer"),
    dict(key="uefa.europa", sport="soccer", path="soccer/uefa.europa", injuries=False, gamelog=False, total_th=0.5, headshot="soccer"),
]
LEAGUES_BY_KEY = {lg["key"]: lg for lg in LEAGUES}
# 首頁的球種按鈕：爸爸要看的放前面，其他收在「更多球種」
SPORTS = [
    dict(key="all", label="全部"),
    dict(key="nba", label="NBA", icon="basketball"),
    dict(key="eurobasket", label="歐洲籃球", icon="basketball"),
    dict(key="jpbasket", label="日本籃球", icon="basketball"),
    dict(key="jpvolley", label="日本排球", icon="volleyball"),
    dict(key="soccer", label="足球", hidden=True),
    dict(key="hockey", label="冰球", hidden=True),
    dict(key="football", label="美足", hidden=True),
]


MAIN_CHIPS = {x["key"] for x in SPORTS if x["key"] != "all" and not x.get("hidden")}


def is_near(g):
    """這場要不要做完整分析：已開打／打完的、或 48 小時內開打的。"""
    if g["status"]["state"] != "pre" or NEAR_HI is None:
        return True
    st = parse_dt(g["start"])
    return st is None or st <= NEAR_HI


def chip_of(lg):
    return "nba" if lg["key"] == "nba" else (lg["key"] if lg.get("source") else lg["sport"])

SESSION = requests.Session()
SESSION.headers.update(HEADERS)
ERRORS = []
CALLS = {"n": 0}


def log(msg):
    print(msg, flush=True)


def get(url, params=None, tries=3, quiet=False):
    last = None
    for i in range(tries):
        try:
            CALLS["n"] += 1
            r = SESSION.get(url, params=params, timeout=25)
            if r.status_code == 200:
                time.sleep(0.12)
                return r.json()
            if r.status_code in (400, 404):
                if not quiet:
                    ERRORS.append(f"{r.status_code} {url}")
                return None
            last = f"http {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = repr(e)
        time.sleep(1.5 * (i + 1))
    if not quiet:
        ERRORS.append(f"fail {url} {last}")
    return None


# ---------- 小工具 ----------
def parse_dt(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def iso(dt):
    return dt.isoformat(timespec="minutes") if dt else None


def to_american(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().upper().replace("+", "")
    if s in ("EVEN", "EV", "PK", "PICK"):
        return 100.0
    try:
        return float(s)
    except ValueError:
        return None


def dec(a):
    if a is None:
        return None
    return round(1 + (a / 100 if a > 0 else 100 / abs(a)), 2)


def implied(a):
    if a is None:
        return None
    return (100 / (a + 100)) if a > 0 else (abs(a) / (abs(a) + 100))


def num(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def headshot_url(athlete, lg):
    h = athlete.get("headshot")
    if isinstance(h, dict):
        h = h.get("href")
    if h:
        return h
    aid = athlete.get("id")
    if aid and lg.get("headshot") in ("nba", "nhl", "nfl", "soccer"):
        return f"https://a.espncdn.com/i/headshots/{lg['headshot']}/players/full/{aid}.png"
    return None


def team_label(t):
    return t.get("name_zh") or t.get("short") or t.get("name") or ""


# ---------- 盤口 ----------
RAW = {}


def keep_raw(name, obj):
    """保留第一筆原始資料，--debug-dir 時寫出來，方便看 ESPN 的欄位長什麼樣。"""
    if name not in RAW and obj is not None:
        RAW[name] = obj


def dec_to_american(d):
    d = num(d)
    if not d or d <= 1:
        return None
    return float(round((d - 1) * 100)) if d >= 2 else float(round(-100 / (d - 1)))


def _ml_from_dict(ml):
    """moneyLine 可能是數字、字串，或 {american, decimal, displayValue, ...} 的物件。"""
    if isinstance(ml, dict):
        v = to_american(ml.get("american") or ml.get("alternateDisplayValue") or ml.get("displayValue"))
        if v is None and ml.get("decimal") is not None:
            v = dec_to_american(ml.get("decimal"))
        return v
    return to_american(ml)


def _ml_from_block(block):
    """homeTeamOdds / awayTeamOdds / drawOdds：舊版直接有 moneyLine，新版藏在 current/close/open 裡。"""
    if not isinstance(block, dict):
        return None
    v = _ml_from_dict(block.get("moneyLine"))
    if v is not None:
        return v
    for k in ("current", "close", "open"):
        sub = block.get(k)
        if isinstance(sub, dict):
            v = _ml_from_dict(sub.get("moneyLine"))
            if v is not None:
                return v
    return None


def _ml_from_market(o, side):
    """另一種版本：o["moneyline"] = {home:{close:{odds}}, away:{...}, draw:{...}}"""
    ml = o.get("moneyline")
    if not isinstance(ml, dict):
        return None
    s = ml.get(side)
    if not isinstance(s, dict):
        return None
    for k in ("close", "current", "open"):
        sub = s.get(k)
        if isinstance(sub, dict):
            v = _ml_from_dict(sub.get("odds") if sub.get("odds") is not None else sub.get("american"))
            if v is not None:
                return v
    return None


def _line_from_market(o, market, side, key="line"):
    m = o.get(market)
    if not isinstance(m, dict):
        return None
    s = m.get(side)
    if not isinstance(s, dict):
        return None
    for k in ("close", "current", "open"):
        sub = s.get(k)
        if isinstance(sub, dict) and sub.get(key) is not None:
            return num(str(sub.get(key)).replace("+", ""))
    return None


SPREAD_SIGMA = {"basketball": 11.5, "football": 13.5, "hockey": 2.0}
ML_MIN_DEC = 1.20      # 台灣不讓分賠率低於這個，贏了也幾乎沒賺頭，改看讓分


def spread_prob(spread, sport):
    """沒有獨贏賠率時，用讓分盤估主隊勝率（常態分布近似）。spread 為主隊讓分，負數代表主隊讓。"""
    sigma = SPREAD_SIGMA.get(sport)
    if spread is None or not sigma:
        return None
    from math import erf, sqrt
    return 0.5 * (1 + erf((-spread) / (sigma * sqrt(2))))


def parse_odds(comp, sport=None):
    arr = comp.get("odds") or []
    o = next((x for x in arr if isinstance(x, dict)), None)
    if not o:
        return None
    keep_raw(f"odds_{sport}", o)
    ml_h = _ml_from_block(o.get("homeTeamOdds"))
    if ml_h is None:
        ml_h = _ml_from_market(o, "home")
    ml_a = _ml_from_block(o.get("awayTeamOdds"))
    if ml_a is None:
        ml_a = _ml_from_market(o, "away")
    ml_d = _ml_from_block(o.get("drawOdds"))
    if ml_d is None:
        ml_d = _ml_from_market(o, "draw")
    spread = num(o.get("spread"))
    if spread is None:
        spread = _line_from_market(o, "pointSpread", "home")
    total = num(o.get("overUnder"))
    if total is None:
        total = _line_from_market(o, "total", "over")
    probs = {k: implied(v) for k, v in (("home", ml_h), ("away", ml_a), ("draw", ml_d)) if v is not None}
    source = "moneyline"
    if "home" not in probs or "away" not in probs:
        p = spread_prob(spread, sport)
        if p is not None:
            probs = {"home": p, "away": 1 - p}
            source = "spread"
    s = sum(probs.values())
    fair = {k: round(v / s, 3) for k, v in probs.items()} if s else {}
    fav = None
    if fair.get("home") is not None and fair.get("away") is not None:
        fav = "home" if fair["home"] >= fair["away"] else "away"
    elif (o.get("homeTeamOdds") or {}).get("favorite"):
        fav = "home"
    elif (o.get("awayTeamOdds") or {}).get("favorite"):
        fav = "away"
    return dict(
        provider=(o.get("provider") or {}).get("name"),
        details=o.get("details"),
        spread=spread,
        total=total,
        ml_home=ml_h, ml_away=ml_a, ml_draw=ml_d,
        dec_home=dec(ml_h), dec_away=dec(ml_a), dec_draw=dec(ml_d),
        prob_home=fair.get("home"), prob_away=fair.get("away"), prob_draw=fair.get("draw"),
        prob_source=source if fair else None,
        fav=fav,
    )


# ---------- 賽事解析 ----------
def status_text(lg, st, typ):
    state = typ.get("state")
    if state == "pre":
        return "未開賽"
    if state == "post":
        return "已結束" if typ.get("completed") else (typ.get("description") or "已結束")
    clock = st.get("displayClock") or ""
    p = st.get("period") or 0
    sp = lg["sport"]
    if typ.get("name") == "STATUS_HALFTIME":
        return "中場休息"
    if sp == "soccer":
        return f"進行中 {clock}".strip()
    if sp == "tennis":
        return f"第 {p} 盤" if p else "進行中"
    if p and p <= 4:
        label = f"第 {p} 節"
    elif p and p > 4:
        label = f"延長 {p - 4}"
    else:
        label = "進行中"
    if sp == "hockey" and p and p <= 3:
        label = f"第 {p} 節"
    elif sp == "hockey" and p and p > 3:
        label = "延長賽"
    return f"{label} {clock}".strip()


def parse_team(c, lg):
    t = c.get("team") or {}
    abbr = t.get("abbreviation") or ""
    name = t.get("displayName") or t.get("name") or ""
    short = t.get("shortDisplayName") or t.get("name") or name
    logo = t.get("logo")
    if not logo:
        logos = t.get("logos") or []
        logo = logos[0].get("href") if logos else None
    recs = {}
    for r in c.get("records") or []:
        recs[(r.get("name") or r.get("type") or "").lower()] = r.get("summary")
    score = c.get("score")
    if isinstance(score, dict):
        score = score.get("displayValue")
    leaders = []
    seen = set()
    for cat in c.get("leaders") or []:
        for l in (cat.get("leaders") or [])[:1]:
            a = l.get("athlete") or {}
            if not a.get("id") or a["id"] in seen:
                continue
            seen.add(a["id"])
            leaders.append(dict(
                id=str(a.get("id")),
                player=a.get("displayName") or a.get("fullName") or a.get("shortName"),
                headshot=headshot_url(a, lg),
                position=(a.get("position") or {}).get("abbreviation"),
                stat=cat.get("shortDisplayName") or cat.get("abbreviation") or cat.get("name"),
                value=l.get("displayValue"),
            ))
    return dict(
        id=str(t.get("id") or ""),
        abbr=abbr,
        name=name,
        short=short,
        name_zh=zh_name(lg["key"], abbr, name, short),
        logo=logo,
        color=t.get("color"),
        record=recs.get("overall") or recs.get("total") or (next(iter(recs.values()), None) if recs else None),
        record_home=recs.get("home"),
        record_away=recs.get("road") or recs.get("away"),
        score=score,
        winner=bool(c.get("winner")),
        form_str=c.get("form"),
        leaders=leaders,
        injuries=[],
        key_out=[],
        out_count=0,
        maybe_count=0,
        hot=[],
        form=[],
        form_note=None,
        streak=None,
        last10=None,
        avg_for5=None,
        avg_against5=None,
        avg_total5=None,
        avg_margin5=None,
    )


def parse_player(c, lg):
    a = c.get("athlete") or {}
    flag = a.get("flag") or {}
    sets = []
    for ls in c.get("linescores") or []:
        v = ls.get("value")
        if v is not None:
            sets.append(str(int(v)) if float(v).is_integer() else str(v))
    return dict(
        id=str(a.get("id") or c.get("id") or ""),
        abbr=(a.get("shortName") or "")[:3].upper(),
        name=a.get("displayName") or a.get("fullName") or "",
        short=a.get("shortName") or a.get("displayName") or "",
        name_zh=None,
        logo=flag.get("href") if isinstance(flag, dict) else None,
        headshot=headshot_url(a, lg) if a.get("headshot") else None,
        color=None,
        record=None, record_home=None, record_away=None,
        score=" ".join(sets) if sets else (c.get("score") if isinstance(c.get("score"), str) else None),
        winner=bool(c.get("winner")),
        form_str=None, leaders=[], injuries=[], key_out=[], out_count=0, maybe_count=0,
        hot=[], form=[], form_note=None, streak=None, last10=None,
        avg_for5=None, avg_against5=None, avg_total5=None, avg_margin5=None,
        rank=a.get("rank") or (a.get("ranks") or [{}])[0].get("rank") if isinstance(a.get("ranks"), list) else a.get("rank"),
    )


def make_game(lg, ev, comp, is_tennis=False, group_name=None):
    comps = comp.get("competitors") or []
    if len(comps) < 2:
        return None
    if is_tennis:
        if group_name and "Doubles" in group_name:
            return None
        home_c, away_c = comps[0], comps[1]
        home, away = parse_player(home_c, lg), parse_player(away_c, lg)
        if not home["name"] or not away["name"]:
            return None
    else:
        home_c = next((c for c in comps if c.get("homeAway") == "home"), comps[0])
        away_c = next((c for c in comps if c.get("homeAway") == "away"), comps[1])
        home, away = parse_team(home_c, lg), parse_team(away_c, lg)
    start = parse_dt(comp.get("date") or ev.get("date"))
    if not start:
        return None
    st = comp.get("status") or ev.get("status") or {}
    typ = st.get("type") or {}
    state = typ.get("state") or "pre"
    start_tw = start.astimezone(TW)
    headline = None
    for h in comp.get("headlines") or []:
        if h.get("description"):
            headline = h.get("description")
            break
    bc = []
    for b in comp.get("broadcasts") or []:
        bc.extend(b.get("names") or [])
    venue = (comp.get("venue") or {}).get("fullName")
    name = ev.get("shortName") or ev.get("name")
    if is_tennis:
        name = f"{home['name']} vs {away['name']}"
    return dict(
        id=str(comp.get("id") or ev.get("id")),
        league=lg["key"],
        league_zh=LEAGUE_ZH.get(lg["key"], lg["key"]),
        sport=lg["sport"],
        chip=chip_of(lg),
        tennis=is_tennis,
        tournament=(ev.get("name") if is_tennis else None),
        round=group_name,
        name=name,
        start=iso(start.astimezone(timezone.utc)),
        start_tw=iso(start_tw),
        day_tw=start_tw.strftime("%Y-%m-%d"),
        time_tw=start_tw.strftime("%H:%M"),
        status=dict(state=state, completed=bool(typ.get("completed")), detail=status_text(lg, st, typ),
                    clock=st.get("displayClock"), period=st.get("period")),
        venue=venue,
        broadcast=", ".join(dict.fromkeys(bc)) or None,
        home=home,
        away=away,
        odds=parse_odds(comp, lg["sport"]),
        headline=headline,
        news=[],
        suggestion=None,
        season_type=(ev.get("season") or {}).get("type"),
    )


def fetch_games(lg, dates):
    games = {}
    for d in dates:
        params = {"dates": d.strftime("%Y%m%d"), "limit": 300}
        data = get(f"{SITE}/{lg['path']}/scoreboard", params=params)
        if not data:
            continue
        if data.get("events"):
            keep_raw(f"scoreboard_event_{lg['key']}", data["events"][0])
        for ev in data.get("events") or []:
            try:
                if lg.get("tennis"):
                    groupings = ev.get("groupings") or []
                    if groupings:
                        for gp in groupings:
                            gname = (gp.get("grouping") or {}).get("displayName")
                            for comp in gp.get("competitions") or []:
                                g = make_game(lg, ev, comp, is_tennis=True, group_name=gname)
                                if g:
                                    games[g["id"]] = g
                    else:
                        for comp in ev.get("competitions") or []:
                            g = make_game(lg, ev, comp, is_tennis=True)
                            if g:
                                games[g["id"]] = g
                else:
                    for comp in (ev.get("competitions") or [])[:1]:
                        g = make_game(lg, ev, comp)
                        if g:
                            games[g["id"]] = g
            except Exception as e:  # noqa: BLE001
                ERRORS.append(f"{lg['key']} 解析賽事 {ev.get('id')} 失敗: {e!r}")
    return list(games.values())


# ---------- 傷兵 ----------
def parse_injury_entries(entries, lg):
    """ESPN 傷兵列表（聯盟傷兵頁或單場 summary 都是同一種格式）。"""
    lst = []
    for inj in entries or []:
        if True:
            a = inj.get("athlete") or {}
            status = inj.get("status") or (inj.get("type") or {}).get("description") or ""
            det = inj.get("details") or {}
            if status in ("Available", "Active"):
                sev = "ok"
            elif status in MAYBE_LIKE:
                sev = "maybe"
            elif status.startswith("Injured Reserve") or status == "Out For Season":
                sev = "ir"
            elif status in OUT_LIKE:
                sev = "out"
            else:
                sev = "other"
            aid = str(a.get("id") or "")
            shot = headshot_url(a, lg)
            if not aid:
                # ESPN 聯盟傷兵頁的球員沒有 id，只有大頭照網址和連結裡帶 id
                m = re.search(r"/players/full/(\d+)\.png", shot or "") or re.search(r"/id/(\d+)", json.dumps(a.get("links") or []))
                aid = m.group(1) if m else ""
            lst.append(dict(
                id=aid,
                player=a.get("displayName") or a.get("fullName") or a.get("shortName"),
                headshot=shot,
                position=(a.get("position") or {}).get("abbreviation"),
                position_zh=POS_ZH.get((a.get("position") or {}).get("abbreviation") or ""),
                status=status,
                status_zh=STATUS_ZH.get(status, status),
                severity=sev,
                detail=det.get("type") or det.get("detail"),
                side=det.get("side"),
                return_date=det.get("returnDate"),
                comment=inj.get("shortComment") or inj.get("longComment"),
                date=inj.get("date"),
                official=False,
            ))
    return lst


def fetch_injuries(lg):
    data = get(f"{SITE}/{lg['path']}/injuries")
    out = {}
    if not data:
        return out
    if data.get("injuries"):
        keep_raw(f"injuries_{lg['key']}", data["injuries"][0])
    for team in data.get("injuries") or []:
        tid = str(team.get("id") or (team.get("team") or {}).get("id") or "")
        if tid:
            out[tid] = parse_injury_entries(team.get("injuries"), lg)
    return out


def merge_injuries(team, extra):
    """把另一來源的傷兵併進球隊，同名不重複。"""
    have = {(x.get("player") or "").lower() for x in team.get("injuries") or []}
    n = 0
    for x in extra or []:
        if (x.get("player") or "").lower() in have:
            continue
        team.setdefault("injuries", []).append(x)
        have.add((x.get("player") or "").lower())
        n += 1
    return n


# ---------- 球隊近況 ----------
def _score_val(c):
    s = c.get("score")
    if isinstance(s, dict):
        return num(s.get("value") if s.get("value") is not None else s.get("displayValue"))
    return num(s)


def parse_schedule(data, team_id, lg, comp_key=None):
    """把球隊賽程裡已完成的比賽整理成近況列。comp_key 是賽事代號（足球跨賽事合併時用）。"""
    rows = []
    for ev in (data or {}).get("events") or []:
        comp = (ev.get("competitions") or [{}])[0]
        typ = ((comp.get("status") or ev.get("status") or {}).get("type") or {})
        if not typ.get("completed"):
            continue
        comps = comp.get("competitors") or []
        me = next((c for c in comps if str((c.get("team") or {}).get("id") or c.get("id")) == str(team_id)), None)
        opp = next((c for c in comps if c is not me), None)
        if not me or not opp:
            continue
        dt = parse_dt(comp.get("date") or ev.get("date"))
        if not dt:
            continue
        pf, pa = _score_val(me), _score_val(opp)
        if pf is None or pa is None:
            continue
        if me.get("winner") is True:
            res = "W"
        elif opp.get("winner") is True:
            res = "L"
        else:
            res = "W" if pf > pa else ("L" if pf < pa else "D")
        ot = (opp.get("team") or {})
        rows.append(dict(
            date=dt.astimezone(TW).strftime("%m/%d"),
            date_iso=dt.astimezone(timezone.utc).isoformat(timespec="minutes"),
            ts=dt.timestamp(),
            opp=ot.get("abbreviation") or ot.get("shortDisplayName") or ot.get("displayName"),
            opp_id=str(ot.get("id") or opp.get("id") or ""),
            opp_zh=zh_name(lg["key"], ot.get("abbreviation"), ot.get("displayName"), ot.get("shortDisplayName")),
            opp_logo=ot.get("logo") or ((ot.get("logos") or [{}])[0].get("href") if ot.get("logos") else None),
            home=(me.get("homeAway") == "home"),
            pf=pf, pa=pa, result=res,
            comp=(LEAGUE_ZH.get(comp_key, comp_key) if comp_key and lg["sport"] == "soccer" else None),
        ))
    rows.sort(key=lambda r: r["ts"])
    return rows


# 足球：一支球隊同時踢國內聯賽和歐戰，近況要跨賽事合併才有意義
SOCCER_FORM_LEAGUES = ["eng.1", "esp.1", "ita.1", "ger.1", "fra.1", "ned.1", "por.1", "tur.1", "bel.1", "sco.1",
                       "nor.1", "aut.1", "sui.1", "gre.1", "den.1", "cze.1", "ukr.1", "swe.1", "pol.1", "cro.1",
                       "srb.1", "hun.1", "aze.1", "svk.1", "cyp.1", "kaz.1", "isr.1"]
SOCCER_CUPS = ["uefa.champions", "uefa.europa", "uefa.europa.conf"]
_SOCCER_TEAM_LEAGUE = None   # team_id -> 國內聯賽
_SOCCER_TEAM_CUPS = None     # team_id -> {盃賽}


def _standings_team_ids(data):
    children = (data or {}).get("children") or []
    if not children and (data or {}).get("standings"):
        children = [dict(standings=data["standings"])]
    for ch in children:
        for e in ((ch.get("standings") or {}).get("entries")) or []:
            tid = str((e.get("team") or {}).get("id") or "")
            if tid:
                yield tid


def soccer_team_index():
    global _SOCCER_TEAM_LEAGUE, _SOCCER_TEAM_CUPS
    if _SOCCER_TEAM_LEAGUE is not None:
        return
    _SOCCER_TEAM_LEAGUE, _SOCCER_TEAM_CUPS = {}, {}
    for lgk in SOCCER_FORM_LEAGUES:
        for tid in _standings_team_ids(get(f"{SITE_V2}/soccer/{lgk}/standings", quiet=True)):
            _SOCCER_TEAM_LEAGUE.setdefault(tid, lgk)
    for cup in SOCCER_CUPS:
        for tid in _standings_team_ids(get(f"{SITE_V2}/soccer/{cup}/standings", quiet=True)):
            _SOCCER_TEAM_CUPS.setdefault(tid, set()).add(cup)
    log(f"足球球隊索引：國內聯賽 {len(_SOCCER_TEAM_LEAGUE)} 隊、歐戰 {len(_SOCCER_TEAM_CUPS)} 隊")


def fetch_form(lg, team):
    if not team.get("id"):
        return
    data = get(f"{SITE}/{lg['path']}/teams/{team['id']}/schedule")
    if data and data.get("events"):
        keep_raw(f"schedule_event_{lg['key']}", data["events"][0])
    rows = parse_schedule(data, team["id"], lg, comp_key=lg["key"])
    note = None
    if lg["sport"] == "soccer":
        soccer_team_index()
        others = set()
        dom = _SOCCER_TEAM_LEAGUE.get(team["id"])
        if dom and dom != lg["key"]:
            others.add(dom)
        for cup in _SOCCER_TEAM_CUPS.get(team["id"], ()):
            if cup != lg["key"]:
                others.add(cup)
        for other in sorted(others):
            d2 = get(f"{SITE}/soccer/{other}/teams/{team['id']}/schedule", quiet=True)
            rows += parse_schedule(d2, team["id"], lg, comp_key=other)
        seen, merged = set(), []
        for r in sorted(rows, key=lambda r: r["ts"]):
            k = (round(r["ts"] / 3600), r["opp"])
            if k in seen:
                continue
            seen.add(k)
            merged.append(r)
        rows = merged
        if others:
            note = "含國內聯賽與歐戰"
    if not rows and lg["sport"] in ("basketball", "hockey", "football"):
        data = get(f"{SITE}/{lg['path']}/teams/{team['id']}/schedule", params={"seasontype": 1})
        rows = parse_schedule(data, team["id"], lg)
        if rows:
            note = "季前賽"
    if not rows:
        return
    for r in rows:
        r.pop("ts", None)
    last = rows[-10:]
    team["form"] = last
    team["form_note"] = note
    w = sum(1 for r in last if r["result"] == "W")
    l = sum(1 for r in last if r["result"] == "L")
    d = sum(1 for r in last if r["result"] == "D")
    team["last10"] = f"{w}勝{l}敗" + (f"{d}和" if d else "")
    team["last10_w"] = w
    # 連勝連敗
    s = 0
    first = last[-1]["result"]
    for r in reversed(last):
        if r["result"] == first:
            s += 1
        else:
            break
    team["streak"] = {"W": "連勝", "L": "連敗", "D": "連和"}[first] + str(s) if s >= 2 else None
    last5 = last[-5:]
    team["avg_for5"] = round(mean(r["pf"] for r in last5), 1)
    team["avg_against5"] = round(mean(r["pa"] for r in last5), 1)
    team["avg_total5"] = round(team["avg_for5"] + team["avg_against5"], 1)
    team["avg_margin5"] = round(team["avg_for5"] - team["avg_against5"], 1)


# ---------- 球員近況（火燙/冰冷）＋上場時間 ----------
def current_season_label(now=None):
    now = now or datetime.now(TW)
    y = now.year if now.month >= 7 else now.year - 1
    return f"{y}-{(y + 1) % 100:02d}"


def _mmss(v):
    s = str(v or "").strip()
    m = re.match(r"^(\d+):(\d{2})$", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60
    return num(s)


def fetch_player_form(lg, athlete):
    """本季正式比賽（例行賽、季後賽）的近 5 場 vs 本季平均。季前賽和上一季不算，免得拿去年季後賽說現在手感燙。
    另外算最近 3 場的上場時間（差 20 分以上的大比分不算，那是垃圾時間）。"""
    data = get(f"{WEB}/{lg['path']}/athletes/{athlete['id']}/gamelog")
    if not data:
        return None
    keep_raw(f"gamelog_{lg['key']}", dict(labels=data.get("labels"), seasonTypes=[dict(displayName=st.get("displayName")) for st in (data.get("seasonTypes") or [])],
                                         events=dict(list((data.get("events") or {}).items())[:2])))
    labels = data.get("labels") or []
    stat = lg["stat"]
    if stat not in labels:
        return None
    idx = labels.index(stat)
    i_min = labels.index("MIN") if "MIN" in labels else None
    meta = data.get("events") or {}
    cur = current_season_label()
    rows = []
    season_name = None
    for st in data.get("seasonTypes") or []:
        name = st.get("displayName") or ""
        if cur not in name or "Preseason" in name:
            continue
        season_name = season_name or name
        for cat in st.get("categories") or []:
            for e in cat.get("events") or []:
                stats = e.get("stats") or []
                if idx >= len(stats):
                    continue
                v = num(stats[idx])
                if v is None:
                    continue
                m = meta.get(str(e.get("eventId"))) or {}
                dt = parse_dt(m.get("gameDate"))
                opp = (m.get("opponent") or {})
                margin = None
                sc = re.match(r"^\s*(\d+)\s*-\s*(\d+)", str(m.get("score") or ""))
                if sc:
                    margin = abs(int(sc.group(1)) - int(sc.group(2)))
                rows.append(dict(ts=dt.timestamp() if dt else 0,
                                 date=dt.astimezone(TW).strftime("%m/%d") if dt else "",
                                 opp=opp.get("abbreviation") or opp.get("displayName"),
                                 result=m.get("gameResult"), v=v,
                                 mins=_mmss(stats[i_min]) if i_min is not None and i_min < len(stats) else None,
                                 blowout=bool(margin is not None and margin >= 20)))
    if len(rows) < 3:
        return None
    rows.sort(key=lambda r: r["ts"], reverse=True)
    last5 = rows[:5]
    l5 = mean(r["v"] for r in last5)
    season = mean(r["v"] for r in rows)
    delta = ((l5 - season) / season * 100) if season > 0 else 0
    label = "平穩"
    if delta >= 15 and l5 >= lg["hot_min"]:
        label = "火燙"
    elif delta <= -15 and season >= lg["hot_min"]:
        label = "冰冷"
    # 上場時間：最近 3 場（不含大比分）vs 之前的平均
    clean = [r for r in rows if r.get("mins") is not None and not r["blowout"]]
    min_last3 = round(mean(r["mins"] for r in clean[:3]), 1) if len(clean) >= 3 else None
    earlier = clean[3:]
    min_base = round(mean(r["mins"] for r in earlier), 1) if len(earlier) >= 4 else None
    return dict(
        id=athlete["id"], player=athlete["player"], headshot=athlete.get("headshot"),
        position=athlete.get("position"), stat=stat, season_name=season_name,
        last5=round(l5, 1), season=round(season, 1), delta_pct=round(delta),
        label=label, games=[dict(date=r["date"], opp=r["opp"], v=r["v"], mins=r.get("mins")) for r in reversed(last5)],
        n_games=len(rows), min_last3=min_last3, min_base=min_base,
    )


# ---------- 新聞 ----------
def fetch_news(lg):
    data = get(f"{SITE}/{lg['path']}/news", params={"limit": 60})
    arts = []
    for a in (data or {}).get("articles") or []:
        teams = set()
        for c in a.get("categories") or []:
            if c.get("type") == "team":
                tid = c.get("teamId") or (c.get("team") or {}).get("id")
                if tid:
                    teams.add(str(tid))
        imgs = a.get("images") or []
        link = ((a.get("links") or {}).get("web") or {}).get("href")
        arts.append(dict(
            title=a.get("headline"), desc=a.get("description"), url=link,
            image=imgs[0].get("url") if imgs else None,
            published=a.get("published"), teams=teams,
        ))
    arts.sort(key=lambda x: x.get("published") or "", reverse=True)
    return arts


# ---------- 排名 ----------
def fetch_standings(lg):
    data = get(f"{SITE_V2}/{lg['path']}/standings")
    if not data:
        return None
    keep_raw(f"standings_{lg['key']}", dict(children=[dict(name=c.get("name"), standings=dict(entries=((c.get("standings") or {}).get("entries") or [])[:1])) for c in (data.get("children") or [])[:1]]))
    groups = []
    children = data.get("children") or []
    if not children and data.get("standings"):
        children = [dict(name=data.get("name") or LEAGUE_ZH.get(lg["key"]), standings=data["standings"])]
    conf_zh = {"Eastern Conference": "東區", "Western Conference": "西區",
               "American Football Conference": "美聯", "National Football Conference": "國聯"}
    for ch in children:
        entries = ((ch.get("standings") or {}).get("entries")) or []
        rows = []
        for e in entries:
            t = e.get("team") or {}
            st = {}
            for s in e.get("stats") or []:
                st[s.get("name")] = s
            def val(n):
                s = st.get(n) or {}
                return s.get("value")
            def disp(n):
                s = st.get(n) or {}
                return s.get("displayValue")
            logos = t.get("logos") or []
            rows.append(dict(
                team_id=str(t.get("id") or ""),
                team=t.get("displayName"),
                abbr=t.get("abbreviation"),
                name_zh=zh_name(lg["key"], t.get("abbreviation"), t.get("displayName"), t.get("shortDisplayName")),
                logo=logos[0].get("href") if logos else None,
                w=val("wins"), l=val("losses"), d=val("ties") if val("ties") is not None else val("draws"),
                otl=val("otLosses"),
                pct=disp("winPercent"), gb=disp("gamesBehind"), streak=disp("streak"),
                points=val("points"), gp=val("gamesPlayed"),
                rank=val("rank") or val("playoffSeed"),
                pf=(val("avgPointsFor") if val("avgPointsFor") is not None else (val("pointsFor") / val("gamesPlayed") if val("pointsFor") is not None and val("gamesPlayed") else None)),
                pa=(val("avgPointsAgainst") if val("avgPointsAgainst") is not None else (val("pointsAgainst") / val("gamesPlayed") if val("pointsAgainst") is not None and val("gamesPlayed") else None)),
            ))
        if lg["sport"] == "soccer":
            rows.sort(key=lambda r: (-(r["points"] or 0), (r["rank"] or 99)))
        elif lg["sport"] == "hockey":
            rows.sort(key=lambda r: (-(r["points"] or 0)))
        else:
            rows.sort(key=lambda r: ((r["rank"] or 99), -(num(r["pct"]) or 0)))
        for i, r in enumerate(rows, 1):
            r["pos"] = i
        groups.append(dict(name=conf_zh.get(ch.get("name"), ch.get("name") or ""), rows=rows))
    return dict(groups=groups) if groups else None


# ---------- 建議 ----------
def build_suggestion(g, lg):
    o = g.get("odds") or {}
    sp = lg["sport"]
    res = dict(pick=None, pick_label=None, play="觀望", confidence="低", summary="", reasons=[], cautions=[], totals=None)
    if g["status"]["state"] == "post":
        res["summary"] = "這場打完了"
        return res
    if g.get("tennis"):
        if o.get("prob_home") is not None and o.get("prob_away") is not None:
            fav = "home" if o["prob_home"] >= o["prob_away"] else "away"
            pf = max(o["prob_home"], o["prob_away"])
            res["reasons"].append(f"國際盤 {g[fav]['name']} 勝率約 {round(pf * 100)}%")
            if pf >= 0.68:
                res.update(pick=fav, pick_label=g[fav]["name"], play="不讓分", confidence="中",
                           summary=f"押 {g[fav]['name']}，盤口明顯看好，信心中")
            else:
                res["summary"] = "兩人差不多，先不下"
        else:
            res["summary"] = "還沒開盤，等盤出來再說"
        return res
    if o.get("prob_home") is None or o.get("prob_away") is None:
        res["summary"] = "還沒開盤，等盤出來再說"
        return res
    ph, pa = o["prob_home"], o["prob_away"]
    fav, dog = ("home", "away") if ph >= pa else ("away", "home")
    pf = max(ph, pa)
    ft, dt = g[fav], g[dog]
    fn, dn = team_label(ft), team_label(dt)
    score = 0.0
    reasons, cautions = [], []
    signals = []

    def sig(label, side_, impact, text):
        signals.append(dict(label=label, side=side_, impact=impact, text=text))
    side = "主" if fav == "home" else "客"
    psrc = o.get("prob_source")
    if psrc == "spread":
        reasons.append(f"依讓分盤推估{side}隊 {fn} 勝率約 {round(pf * 100)}%（無獨贏賠率）")
    elif psrc == "tw_ml":
        reasons.append(f"依台灣運彩賠率換算，{side}隊 {fn} 勝率約 {round(pf * 100)}%")
    elif psrc == "form":
        reasons.append(f"沒有盤口，依兩隊近況估{side}隊 {fn} 勝率約 {round(pf * 100)}%，只能當參考")
    else:
        reasons.append(f"國際盤看好{side}隊 {fn}，勝率約 {round(pf * 100)}%")
    if o.get("prob_draw"):
        reasons.append(f"和局機率約 {round(o['prob_draw'] * 100)}%")
    if ft["key_out"]:
        cautions.append(f"{fn} 主力缺陣：{'、'.join(ft['key_out'][:3])}")
        sig("傷兵", dog, -1, f"{fn} 主力缺陣：{'、'.join(ft['key_out'][:3])}")
        score -= 1.0
    elif ft["out_count"] >= 3:
        cautions.append(f"{fn} 有 {ft['out_count']} 名球員缺陣")
        score -= 0.3
    if dt["key_out"]:
        reasons.append(f"{dn} 主力缺陣：{'、'.join(dt['key_out'][:3])}")
        sig("傷兵", fav, 1, f"{dn} 主力缺陣：{'、'.join(dt['key_out'][:3])}")
        score += 0.7
    elif dt["out_count"] >= 3:
        reasons.append(f"{dn} 有 {dt['out_count']} 名球員缺陣")
        score += 0.2
    if ft.get("form"):
        n = len(ft["form"])
        fw = ft.get("last10_w", 0)
        if n >= 5 and fw / n >= 0.7:
            reasons.append(f"{fn} 近 {n} 場 {fw} 勝，狀態好")
            sig("近況", fav, 1, f"{fn} 近 {n} 場 {fw} 勝")
            score += 0.5
        elif n >= 5 and fw / n <= 0.3:
            cautions.append(f"{fn} 近 {n} 場只有 {fw} 勝")
            sig("近況", dog, -1, f"{fn} 近 {n} 場只有 {fw} 勝")
            score -= 0.5
        if ft.get("streak", "") and ft["streak"].startswith("連敗"):
            cautions.append(f"{fn} {ft['streak']}")
            score -= 0.2
    if dt.get("form"):
        n = len(dt["form"])
        dw = dt.get("last10_w", 0)
        if dt.get("streak", "") and dt["streak"].startswith("連勝") and int(dt["streak"][2:]) >= 3:
            cautions.append(f"{dn} {dt['streak']}，手感正熱")
            sig("近況", dog, -1, f"{dn} {dt['streak']}")
            score -= 0.3
        elif n >= 5 and dw / n >= 0.7:
            cautions.append(f"{dn} 近 {n} 場 {dw} 勝，不弱")
            score -= 0.2
    for p in ft.get("hot") or []:
        if p["label"] == "火燙":
            reasons.append(f"{p['player']} 近 5 場場均 {p['last5']} {p['stat']}，比季平均高 {p['delta_pct']}%")
            sig("手感", fav, 1, f"{p['player']} 火燙，近 5 場場均 {p['last5']} {p['stat']}")
            score += 0.2
        elif p["label"] == "冰冷":
            cautions.append(f"{p['player']} 近 5 場場均 {p['last5']} {p['stat']}，比季平均低 {abs(p['delta_pct'])}%")
            sig("手感", dog, -1, f"{p['player']} 冰冷，近 5 場場均 {p['last5']} {p['stat']}")
            score -= 0.2
    for p in dt.get("hot") or []:
        if p["label"] == "火燙":
            cautions.append(f"對手 {p['player']} 手感火燙，近 5 場場均 {p['last5']} {p['stat']}")
            sig("手感", dog, -1, f"{p['player']} 火燙，近 5 場場均 {p['last5']} {p['stat']}")
            score -= 0.15
    # 進階訊號：ESPN 模型、休息、盤口變動、讓分盤戰績、對戰、先發
    try:
        from analysis import extra_signals
        for x in extra_signals(g, lg):
            if x["side"] == fav:
                score += x["weight"]
                reasons.append(f"{x['label']}：{x['text']}")
                sig(x["label"], fav, 1, x["text"])
            elif x["side"] == dog:
                score -= x["weight"]
                cautions.append(f"{x['label']}：{x['text']}")
                sig(x["label"], dog, -1, x["text"])
            else:
                sig(x["label"], None, 0, x["text"])
    except Exception as e:  # noqa: BLE001
        ERRORS.append(f"進階訊號失敗 {g['id']}: {e!r}")
    try:
        from model import rating_signals
        for x in rating_signals(g, lg):
            if x["side"] == fav:
                score += x["weight"]
                reasons.append(f"{x['label']}：{x['text']}")
                sig(x["label"], fav, 1, x["text"])
            elif x["side"] == dog:
                score -= x["weight"]
                cautions.append(f"{x['label']}：{x['text']}")
                sig(x["label"], dog, -1, x["text"])
            else:
                sig(x["label"], None, 0, x["text"])
    except Exception as e:  # noqa: BLE001
        ERRORS.append(f"評分訊號失敗 {g['id']}: {e!r}")
    if sp == "soccer":
        hi, mid = 0.60, 0.50
    else:
        hi, mid = 0.66, 0.56
    adj = pf + score * 0.05
    # 網站估的勝率，串關算機率用：以盤口為主，網站的調整（傷兵、近況…）還沒證明準不準，只算一半、最多加減 5%
    res["fav"], res["p_est"] = fav, round(min(0.97, max(0.03, pf + max(-0.05, min(0.05, score * 0.025)))), 3)
    if adj >= hi and score >= 0:
        conf = "高"
    elif adj >= mid:
        conf = "中"
    else:
        conf = "低"
    if psrc == "form" and conf == "高":
        conf = "中"   # 沒盤口、只靠近況估的，不給高信心
    if conf == "低":
        res.update(pick=None, pick_label=None, play="觀望", confidence="低",
                   summary="看不出誰比較穩，先不下")
    else:
        play = "不讓分"
        spread = o.get("spread")
        if sp == "soccer":
            if pf >= 0.70 and spread is not None and abs(spread) >= 1:
                play = "讓分"
        elif pf >= 0.72 and spread is not None:
            m = ft.get("avg_margin5")
            if m is not None and m >= abs(spread):
                play = "讓分"
                reasons.append(f"{fn} 近 5 場平均贏 {m} 分，高於讓分 {abs(spread)}")
            else:
                cautions.append("賠率偏低，不讓分獲利有限")
        res.update(pick=fav, pick_label=fn, play=play, confidence=conf,
                   summary=f"押 {fn}，玩{play}，信心{conf}")
    th = lg.get("total_th", 99)
    h, a = g["home"], g["away"]
    rt = ((g.get("analysis") or {}).get("rating") or {}) if isinstance(g.get("analysis"), dict) else {}
    if o.get("total") and rt.get("total") is not None and not rt.get("weak"):
        from model import TOTAL_TH
        exp = rt["total"]
        diff = exp - o["total"]
        th2 = TOTAL_TH.get(sp, th)
        lean = "無明顯方向"
        if diff >= th2:
            lean = "大"
            reasons.append(f"照兩隊得分和失分算，這場大概 {exp:.0f} 分，盤口 {o['total']}，偏大分")
        elif diff <= -th2:
            lean = "小"
            reasons.append(f"照兩隊得分和失分算，這場大概 {exp:.0f} 分，盤口 {o['total']}，偏小分")
        res["totals"] = dict(lean=lean, line=o["total"], expected=round(exp, 1), method="評分")
    elif o.get("total") and h.get("avg_total5") and a.get("avg_total5"):
        exp = (h["avg_total5"] + a["avg_total5"]) / 2
        diff = exp - o["total"]
        lean = "無明顯方向"
        if diff >= th:
            lean = "大"
            reasons.append(f"兩隊近 5 場平均總分 {exp:.1f}，高於盤口 {o['total']}，可考慮大分")
        elif diff <= -th:
            lean = "小"
            reasons.append(f"兩隊近 5 場平均總分 {exp:.1f}，低於盤口 {o['total']}，可考慮小分")
        res["totals"] = dict(lean=lean, line=o["total"], expected=round(exp, 1), method="近5場")
    # ---- 大小分差距夠大、輸贏那邊又沒明顯優勢時，主建議改玩大小分 ----
    tot = res.get("totals")
    if tot and tot.get("lean") in ("大", "小") and tot.get("method") == "評分" and g["status"]["state"] == "pre":
        from math import erf, sqrt
        from model import TOTAL_SIGMA, TOTAL_MAIN
        tt_tw = (g.get("tw") or {}).get("total") or {}
        line_use = tt_tw["line"] if tt_tw.get("line") is not None else tot["line"]
        diff_t = tot["expected"] - line_use
        if (diff_t > 0) == (tot["lean"] == "大"):
            p_t = 0.5 * (1 + erf(abs(diff_t) / (TOTAL_SIGMA.get(sp, 17.0) * sqrt(2))))
            tot["prob"] = round(p_t, 3)
            tot["line_tw"] = tt_tw.get("line")
            if abs(diff_t) >= TOTAL_MAIN.get(sp, 99) and res["confidence"] != "高":
                conf_t = "高" if p_t >= 0.70 else "中"
                lean = tot["lean"]
                res["side"] = dict(pick=res["pick"], pick_label=res["pick_label"], play=res["play"], confidence=res["confidence"])
                res.update(pick="over" if lean == "大" else "under", pick_label=f"{lean}分", play="大小分", confidence=conf_t,
                           summary=f"玩{lean}分 {line_use:g}，信心{conf_t}")
                tot["main"] = True
                reasons.append(f"算出來的總分跟盤口差 {abs(diff_t):.0f} 分，比輸贏那邊有把握，改玩大小分")
                if tt_tw.get("over") and tt_tw.get("under"):
                    dec_t = tt_tw["over"] if lean == "大" else tt_tw["under"]
                    ev_t = p_t * dec_t - 1
                    res["tw_ev"], res["tw_dec"] = round(ev_t * 100), dec_t
                    res["tw_value"] = "划算" if ev_t >= -0.04 else "偏差" if ev_t <= -0.15 else "正常"
    # 台灣運彩盤口：用國際盤的公平勝率去算台灣賠率的期望值
    tw = g.get("tw") or {}
    ml = tw.get("ml") or {}
    ev = None
    if res["pick"] and ml.get(res["pick"]) and o.get(f"prob_{res['pick']}") and psrc != "tw_ml":
        dec_tw = ml[res["pick"]]
        p = o[f"prob_{res['pick']}"]
        ev = p * dec_tw - 1
        if dec_tw < ML_MIN_DEC:
            cautions.append(f"台灣運彩不讓分賠率只有 {dec_tw}，贏了也幾乎沒賺頭，想下的話看讓分盤")
            ev = None
            if (o.get("spread") is not None or (tw.get("spread") or {}).get("line_home") is not None) and res["play"] == "不讓分":
                res["play"] = "讓分"
                if res["confidence"] == "高":
                    res["confidence"] = "中"
                res["summary"] = f"押 {res['pick_label']}，不讓分賠率太低，改玩讓分，信心{res['confidence']}"
    if res["pick"] and ml.get(res["pick"]) and o.get(f"prob_{res['pick']}") and psrc != "tw_ml" and ev is not None:
        # 台灣運彩抽水約一成多，期望值 -8% 到 -14% 是「正常」；比這好算划算，比這差才提醒
        res["tw_ev"] = round(ev * 100)
        res["tw_dec"] = dec_tw
        if ev >= -0.04:
            res["tw_value"] = "划算"
            reasons.append(f"台灣運彩不讓分賠率 {dec_tw}，以國際盤勝率算期望值 {ev * 100:+.0f}%，比平常划算")
        elif ev <= -0.15:
            res["tw_value"] = "偏差"
            cautions.append(f"台灣運彩不讓分賠率 {dec_tw} 偏低，期望值 {ev * 100:.0f}%，比平常差，考慮改玩讓分或縮小注碼")
        else:
            res["tw_value"] = "正常"
    res["reasons"] = reasons
    res["cautions"] = cautions
    g.setdefault("analysis", {})
    if isinstance(g["analysis"], dict):
        g["analysis"]["signals"] = signals
    return res


# ---------- 整合 ----------
def finalize_team(team, lg, injuries_map=None):
    if injuries_map is None:
        inj = team.get("injuries") or []
    else:
        inj = injuries_map.get(team["id"], []) if team.get("id") else []
    order = {"limited": 0, "maybe": 1, "out": 2, "ir": 3, "ok": 4, "other": 5}
    inj = sorted(inj, key=lambda x: order.get(x["severity"], 3))
    team["injuries"] = inj
    team["out_count"] = sum(1 for x in inj if x["severity"] in ("out", "ir"))
    team["maybe_count"] = sum(1 for x in inj if x["severity"] == "maybe")
    leader_ids = {l["id"] for l in team.get("leaders") or []}
    leader_names = {l["player"] for l in team.get("leaders") or []}
    key = [x["player"] for x in inj if x["severity"] in ("out", "ir") and ((x.get("id") and x["id"] in leader_ids) or x["player"] in leader_names)]
    team["key_out"] = key
    team["key_maybe"] = [x["player"] for x in inj if x["severity"] in ("maybe", "limited") and ((x.get("id") and x["id"] in leader_ids) or x["player"] in leader_names)]
    team["limited_count"] = sum(1 for x in inj if x["severity"] == "limited")


def aggregate(games):
    """傷兵快報與火燙榜。同一隊在窗口內打兩場（背靠背）只列一次，掛在較早的那場。"""
    feed, hot = [], []
    seen_inj, seen_hot = set(), set()
    for g in sorted(games, key=lambda x: x["start"]):
        if g["status"]["state"] == "post":
            continue
        for side in ("home", "away"):
            t = g[side]
            for x in t.get("injuries") or []:
                key = (t.get("id"), x.get("id") or x.get("player"))
                if x["severity"] in ("out", "maybe", "ir", "limited") and key not in seen_inj:
                    seen_inj.add(key)
                    feed.append(dict(
                        game_id=g["id"], league=g["league"], league_zh=g["league_zh"], sport=g["sport"], chip=g.get("chip") or g["sport"],
                        team_id=t["id"], team=team_label(t), team_logo=t.get("logo"),
                        player=x["player"], headshot=x.get("headshot"), position=x.get("position"),
                        status=x["status"], status_zh=x["status_zh"], severity=x["severity"],
                        # 從新聞對出來的（有連結、沒有官方狀態）快報只寫來源，英文原句留在詳細頁
                        detail=(x.get("why") or (f"{x.get('source') or '新聞'}" if x.get("url") and not x.get("official") else (x.get("detail_zh") or x.get("detail")))),
                        return_date=x.get("return_date"),
                        key=(x["player"] in t.get("key_out", []) or x["player"] in t.get("key_maybe", [])),
                        official=bool(x.get("official")), url=x.get("url"), ppg=x.get("ppg"), impact=x.get("impact"),
                        time_tw=g["time_tw"], day_tw=g["day_tw"],
                    ))
            # 沒有官方傷兵名單的聯盟：新聞裡的傷兵消息也放進快報，讓爸爸不用自己翻
            # （已經從那則新聞對出球員的，就不再重複放一次標題）
            used_urls = {x.get("url") for x in t.get("injuries") or [] if x.get("url")}
            for a in (t.get("injury_news") or [])[:2]:
                key = (t.get("id"), a.get("url") or a.get("title"))
                if key in seen_inj or (a.get("url") and a.get("url") in used_urls):
                    continue
                seen_inj.add(key)
                feed.append(dict(
                    game_id=g["id"], league=g["league"], league_zh=g["league_zh"], sport=g["sport"], chip=g.get("chip") or g["sport"],
                    team_id=t["id"], team=team_label(t), team_logo=t.get("logo"),
                    player=(a.get("title") or "")[:60], headshot=None, position=None,
                    status="news", status_zh="新聞", severity="news",
                    detail=f"{a.get('source') or '新聞'} · {str(a.get('published') or '')[:10]}", return_date=None,
                    url=a.get("url"), key=False, official=False, time_tw=g["time_tw"], day_tw=g["day_tw"],
                ))
            for p in t.get("hot") or []:
                key = (t.get("id"), p.get("id") or p.get("player"))
                if p["label"] != "平穩" and key not in seen_hot:
                    seen_hot.add(key)
                    hot.append(dict(game_id=g["id"], league=g["league"], league_zh=g["league_zh"], sport=g["sport"],
                                    chip=g.get("chip") or g["sport"], team=team_label(t), team_logo=t.get("logo"), **p))
    # 排序：主力優先；再來是「今天到底上不上」最有用的存疑/逐日觀察，然後缺陣，長期傷兵名單放最後
    sev_order = {"limited": 0, "maybe": 1, "out": 2, "ir": 3, "news": 4}
    feed.sort(key=lambda x: (0 if x["key"] else 1, sev_order.get(x["severity"], 3), x["day_tw"], x["time_tw"]))
    # 每個聯盟最多 30 筆，避免 NFL 那種一隊二十幾個傷兵把版面塞滿
    per = {}
    trimmed = []
    for x in feed:
        per[x["league"]] = per.get(x["league"], 0) + 1
        if per[x["league"]] <= 30:
            trimmed.append(x)
    hot.sort(key=lambda x: -abs(x["delta_pct"]))
    return trimmed, hot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "today.json"))
    ap.add_argument("--leagues", default="", help="逗號分隔，只抓這些聯盟（測試用）")
    ap.add_argument("--debug-dir", default="", help="把每種 ESPN 回應的第一筆原始資料寫到這個資料夾")
    args = ap.parse_args()

    global NEAR_HI
    now = datetime.now(timezone.utc)
    now_tw = now.astimezone(TW)
    dates = [now.date() - timedelta(days=1), now.date(), now.date() + timedelta(days=1)]
    lo = now - timedelta(hours=WINDOW_BACK_H)
    hi = now + timedelta(hours=WINDOW_AHEAD_H)
    # 主要球種：台灣時間昨天 0 點到 3 天後 24 點。ESPN 的日期是美東，前後各多抓一天
    d_tw = now_tw.date()
    lo_main = datetime(d_tw.year, d_tw.month, d_tw.day, tzinfo=TW) - timedelta(days=1)
    hi_main = datetime(d_tw.year, d_tw.month, d_tw.day, tzinfo=TW) + timedelta(days=MAIN_DAYS_AHEAD + 1) - timedelta(seconds=1)
    dates_main = [d_tw + timedelta(days=i) for i in range(-2, MAIN_DAYS_AHEAD + 1)]
    NEAR_HI = now + timedelta(hours=NEAR_H)
    only = {s.strip() for s in args.leagues.split(",") if s.strip()}

    all_games = []
    standings = {}
    for lg in LEAGUES:
        if only and lg["key"] not in only:
            continue
        try:
            if chip_of(lg) in MAIN_CHIPS:
                process_league(lg, dates_main, lo_main.astimezone(timezone.utc), hi_main.astimezone(timezone.utc), all_games, standings)
            else:
                process_league(lg, dates, lo, hi, all_games, standings)
        except Exception as e:  # noqa: BLE001
            import traceback
            ERRORS.append(f"{lg['key']} 整個聯盟失敗: {e!r}")
            log(f"[{lg['key']}] 失敗：{e!r}")
            traceback.print_exc()

    all_games.sort(key=lambda g: (g["start"], g["league"]))
    for g in all_games:
        g["far"] = not is_near(g)
    log(f"日期列表：{', '.join(f'{k} {v} 場' for k, v in sorted(__import__('collections').Counter(g['day_tw'] for g in all_games).items()))}；48 小時後的 {sum(1 for g in all_games if g['far'])} 場只放基本資料")
    # 台灣運彩盤口（抓不到就全部沒有，不影響其他）
    tw_count = 0
    try:
        from taiwan_odds import attach_taiwan_odds
        tw_count = attach_taiwan_odds(all_games, ERRORS, log)
    except Exception as e:  # noqa: BLE001
        ERRORS.append(f"台灣盤口失敗: {e!r}")
        log(f"台灣盤口失敗：{e!r}")
    log(f"台灣盤口：配對到 {tw_count} 場")
    enrich_games(all_games)
    espn_matchups(all_games, standings)
    try:
        from model import rate_games
        rate_games(all_games, LEAGUES_BY_KEY, standings, log, ERRORS)
    except Exception as e:  # noqa: BLE001
        ERRORS.append(f"實力評分失敗: {e!r}")
    for g in all_games:
        lg = LEAGUES_BY_KEY[g["league"]]
        if not g.get("odds") or g["odds"].get("prob_home") is None:
            est = estimate_from_form(g)
            if est:
                g["odds"] = est
        try:
            fill_notes(g, lg)
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"{lg['key']} notes {g['id']} 失敗: {e!r}")
        try:
            if chip_of(lg) in MAIN_CHIPS:
                # 爸爸要看的球種：自己判斷，不看賭盤和賠率（算完才拿去對台灣運彩的線和賠率）
                import own
                g["suggestion"] = own.build(g, lg)
                g["suggestion"]["outside"] = own.outside(g)
            else:
                g["suggestion"] = build_suggestion(g, lg)
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"{lg['key']} 建議 {g['id']} 失敗: {e!r}")
            g["suggestion"] = dict(pick=None, pick_label=None, play="觀望", confidence="低",
                                   summary="資料不夠，先不下", reasons=[], cautions=[], totals=None)
        # 純模型預測（只看實力評分、主場、傷兵，不看賠率）：另外記一條線跟盤口比
        try:
            rt = ((g.get("analysis") or {}).get("rating") or {}) if isinstance(g.get("analysis"), dict) else {}
            if rt.get("our_prob_home") is not None:
                ph = rt["our_prob_home"]
                g["suggestion"]["model"] = dict(pick="home" if ph >= 0.5 else "away", prob_home=round(ph, 3),
                                                spread=rt.get("our_spread"), weak=bool(rt.get("weak")), variants=rt.get("variants"))
            # 季前賽：主力常常輪休、打不久；48 小時後的比賽傷兵和盤口都還沒出來：信心最多給「中」
            if (g.get("season_type") == 1 or g.get("far")) and g["suggestion"].get("confidence") == "高":
                g["suggestion"]["confidence"] = "中"
                g["suggestion"]["summary"] = (g["suggestion"].get("summary") or "").replace("信心高", "信心中")
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"{lg['key']} 純模型 {g['id']} 失敗: {e!r}")
        # 每個選項（不讓分、讓分、大小分兩邊）會中的機率，給串關用
        try:
            if g["status"]["state"] == "pre" and not g["suggestion"].get("probs"):
                import parlay
                from model import TOTAL_SIGMA
                g["suggestion"]["probs"] = parlay.side_probs(g, lg["sport"], SPREAD_SIGMA, TOTAL_SIGMA)
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"{lg['key']} 串關機率 {g['id']} 失敗: {e!r}")
        try:
            from story import build_story
            talk = build_story(g, lg["sport"])
            g["suggestion"]["talk"] = talk
            g["suggestion"]["story"] = [talk["verdict"]] + ([talk["fan"]] if talk.get("fan") else []) + talk["why"] + talk["care"] + [talk["odds"]]
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"{lg['key']} 白話 {g['id']} 失敗: {e!r}")
            g["suggestion"]["story"] = [g["suggestion"].get("summary") or "資料整理中。"]
    # 網頁抓即時比分用：ESPN 的聯盟網頁直接抓；玩運彩、SV.LEAGUE 走 live 分支
    for g in all_games:
        lg = LEAGUES_BY_KEY.get(g["league"]) or {}
        g["live_src"] = lg.get("source") or (f"espn:{lg['path']}" if lg.get("path") else None)
    # AI 寫分析（GitHub 免費 AI 模型；沒有權杖或額度用完就跳過）
    try:
        import ai_note
        ai_path = os.path.join(os.path.dirname(os.path.abspath(args.out)), "ai_notes.json")
        ai_note.run(all_games, ai_path, now_tw, MAIN_CHIPS, log, ERRORS)
    except Exception as e:  # noqa: BLE001
        import traceback
        ERRORS.append(f"AI 分析整個失敗: {e!r}")
        traceback.print_exc()
    feed, hot = aggregate(all_games)
    # 成績單：記下建議、賽後對答案
    record = None
    parlay_out = None
    try:
        import history
        hpath = os.path.join(os.path.dirname(os.path.abspath(args.out)), "history.json")
        hist = history.load(hpath)
        n_new, n_upd, n_set = history.update(hist, all_games, now_tw)
        try:
            import ai_note
            ai_note.track(hist, all_games, now_tw)
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"AI 對答案失敗: {e!r}")
        for g in all_games:
            if g["status"]["state"] == "post":
                gr = history.graded(hist, g)
                if gr:
                    g["graded"] = gr
        try:
            import parlay
            parlay_out = parlay.track(hist, all_games, now_tw, hidden={x["key"] for x in SPORTS if x.get("hidden")})
            cur = parlay_out.get("current")
            log("串關：" + (f"{'已鎖定' if cur.get('locked') else '推薦'} " + "＋".join(x["label"] for x in cur["legs"]) + f"，總賠率 {cur['dec']}、全中約 {round(cur['p'] * 100)}%" if cur else parlay_out.get("note", "")))
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"串關失敗: {e!r}")
        history.save(hpath, hist)
        record = history.summarize(hist, now_tw)
        record["model"] = history.model_summary(hist, now_tw)
        try:
            record["parlay"] = parlay.summary(hist, now_tw)
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"串關成績失敗: {e!r}")
        try:
            import ai_note
            record["ai"] = ai_note.summary(hist, now_tw)
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"AI 成績失敗: {e!r}")
        rpath = os.path.join(os.path.dirname(os.path.abspath(args.out)), "results.json")
        with open(rpath, "w", encoding="utf-8") as f:
            json.dump(history.results_payload(hist, now_tw), f, ensure_ascii=False, separators=(",", ":"))
        log(f"成績單：新記 {n_new} 場、更新 {n_upd} 場、結算 {n_set} 場；近 30 天已結算 {record['settled']} 場、待結算 {record['pending']} 場；"
            f"賽果庫 {len(hist.get('results') or {})} 場、純模型 {len(hist.get('model') or {})} 場（已結算 {record['model']['overall'].get('n', 0)}）")
    except Exception as e:  # noqa: BLE001
        import traceback
        ERRORS.append(f"成績單失敗: {e!r}")
        traceback.print_exc()
    out = dict(
        generated_at=now_tw.isoformat(timespec="minutes"),
        generated_ts=int(now.timestamp()),
        today_tw=now_tw.strftime("%Y-%m-%d"),
        sports=SPORTS,
        leagues={k: LEAGUE_ZH.get(k, k) for k in LEAGUES_BY_KEY},
        games=all_games,
        injury_feed=feed[:80],
        hot_players=hot[:40],
        standings=standings,
        record=record,
        parlay=parlay_out,
        source="NBA 來自 ESPN；歐洲籃球、日本籃球的賽程與盤口來自玩運彩，隊徽與排名來自 EuroLeague 官方與 B.LEAGUE 官網；日本排球來自 SV.LEAGUE 官網；沒有官方傷兵名單的聯盟用 Google 新聞",
        errors=ERRORS[:50],
        calls=CALLS["n"],
    )
    for g in all_games:
        for side in ("home", "away"):
            t = g[side]
            if not t.get("stars") and t.get("leaders"):
                t["stars"] = [dict(id=l.get("id"), player=l.get("player"), headshot=l.get("headshot"), position=l.get("position"),
                                   stat=l.get("stat"), value=l.get("value")) for l in t["leaders"][:3]]
            t.pop("leaders", None)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    log(f"寫入 {args.out}：{len(all_games)} 場、傷兵 {len(feed)} 筆、火燙/冰冷 {len(hot)} 人、錯誤 {len(ERRORS)}")
    for e in ERRORS[:20]:
        log("  ! " + e)
    if args.debug_dir:
        try:
            import probe   # 暫時：台灣運彩官網資料主機讀不讀得到（只寫 log）
            probe.run(log)
        except Exception as e:  # noqa: BLE001
            log(f"[查詢4] 失敗：{e!r}")
        os.makedirs(args.debug_dir, exist_ok=True)
        for name, obj in RAW.items():
            with open(os.path.join(args.debug_dir, f"{name}.json"), "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=1)
        log(f"原始資料樣本 {len(RAW)} 份寫到 {args.debug_dir}")


def enrich_games(all_games):
    """進階分析：ESPN 單場 summary、休息天數、NBA 官方傷報。每一步都各自容錯。"""
    try:
        from analysis import fetch_summary, compute_rest, nba_official_report, merge_official
    except Exception as e:  # noqa: BLE001
        ERRORS.append(f"analysis 模組載入失敗: {e!r}")
        return
    targets = [g for g in all_games if not g.get("tennis") and g["status"]["state"] != "post" and not g.get("far")]
    official = None
    if any(g["league"] == "nba" for g in targets):
        try:
            official = nba_official_report(log)
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"NBA 官方傷報失敗: {e!r}")
    n_sum = n_off = n_notes = n_min = n_b2b = 0
    logged = set()
    for g in targets:
        lg = LEAGUES_BY_KEY[g["league"]]
        a = None
        if not lg.get("source"):
            try:
                a = fetch_summary(lg, g, get, keep_raw, SITE, _ml_from_block)
            except Exception as e:  # noqa: BLE001
                ERRORS.append(f"{lg['key']} summary {g['id']} 失敗: {e!r}")
        a = {**(g.get("analysis") or {}), **(a or {})}
        raw_inj = a.pop("raw_injuries", None)
        for err in a.pop("errors", None) or []:
            ERRORS.append(f"{lg['key']} summary {g['id']} {err}")
        if a and not lg.get("source"):
            n_sum += 1
            if lg["key"] not in logged:
                logged.add(lg["key"])
                log(f"[{lg['key']}] summary 樣本：predictor={bool(a.get('predictor'))} ats={bool(a.get('ats'))} h2h={bool(a.get('h2h'))} "
                    f"books={len(a.get('books') or [])} line_move={bool(a.get('line_move'))} lineup={bool(a.get('lineup'))} live={bool(a.get('live_prob'))} "
                    f"raw_keys={list((RAW.get('summary_' + lg['key']) or {}).get('keys') or [])[:30]}")
        start = parse_dt(g["start"])
        try:
            # 歐籃只有歐戰賽程、沒有各國聯賽，休息天數算不準，不算
            a["rest"] = None if lg["key"] == "eurobasket" else {"home": compute_rest(g["home"], start), "away": compute_rest(g["away"], start)}
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"休息天數 {g['id']} 失敗: {e!r}")
        g["analysis"] = a
        # 單場 summary 的傷兵併進來（有時比聯盟傷兵頁完整）
        if raw_inj:
            try:
                for t in raw_inj:
                    tid = str((t.get("team") or {}).get("id") or t.get("id") or "")
                    for side in ("home", "away"):
                        if g[side]["id"] == tid:
                            merge_injuries(g[side], parse_injury_entries(t.get("injuries"), lg))
            except Exception as e:  # noqa: BLE001
                ERRORS.append(f"summary 傷兵 {g['id']} 失敗: {e!r}")
        if official and g["league"] == "nba":
            try:
                n_off += merge_official(g, official)
            except Exception as e:  # noqa: BLE001
                ERRORS.append(f"官方傷報併入 {g['id']} 失敗: {e!r}")
        # 老球迷看傷兵：讀備註（這場打不打、會不會限時）、看最近上場時間、看背靠背輪休習慣
        if lg["sport"] in ("basketball", "hockey", "football") and not lg.get("source"):
            try:
                import availability
                n_notes += availability.apply_notes(g)
                if lg["key"] == "nba":
                    for side in ("home", "away"):
                        n_min += availability.merge_minutes(g[side])
                    from players import _season_year
                    n_b2b += availability.apply_b2b(g, lg, get, _season_year() - 1, log)
            except Exception as e:  # noqa: BLE001
                import traceback
                tb = traceback.extract_tb(e.__traceback__)[-1]
                ERRORS.append(f"{lg['key']} 上場判斷 {g['id']} 失敗: {e!r} @ {tb.name}:{tb.lineno}")
        for side in ("home", "away"):
            finalize_team(g[side], lg)
    log(f"進階分析：summary {n_sum}/{len(targets)} 場，官方傷報 {n_off} 筆，累計呼叫 {CALLS['n']}")
    log(f"上場判斷：讀了 {n_notes} 則傷兵備註、{n_min} 人上場時間被控制、{n_b2b} 人背靠背常輪休")
    if any(g["league"] == "nba" for g in targets):
        try:
            from players import nba_injury_impact
            nba_injury_impact(targets, get, log, ERRORS, keep_raw)
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"nba 傷兵影響失敗: {e!r}")


def espn_matchups(all_games, standings):
    """ESPN 聯盟（NBA、NHL）：近兩季交手跟預期比；NBA 另外看打法對位（籃板、三分、失誤、節奏）。"""
    try:
        import matchup
        import availability
        from model import team_table, rating, HCA, HCA_SPORT
        from players import _season_year
    except Exception as e:  # noqa: BLE001
        ERRORS.append(f"對戰模組載入失敗: {e!r}")
        return
    prev = _season_year() - 1
    by_lg = {}
    for g in all_games:
        if g["status"]["state"] == "post" or g.get("tennis"):
            continue
        lg = LEAGUES_BY_KEY.get(g["league"])
        if lg and not lg.get("source") and lg["key"] in ("nba", "nhl"):
            by_lg.setdefault(lg["key"], []).append(g)
    for key, games in by_lg.items():
        lg = LEAGUES_BY_KEY[key]
        hca = HCA.get(key, HCA_SPORT.get(lg["sport"], 2.5))
        try:
            prev_r = matchup.prev_ratings(get, lg, prev, rating, team_table, hca)
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"{key} 上季排名失敗: {e!r}")
            prev_r = {}
        # 上季實力：開季前幾場場數太少，實力評分從上季出發（model.rate_game 會用）
        for g in games:
            hid, aid = str(g["home"].get("id") or ""), str(g["away"].get("id") or "")
            if hid in prev_r or aid in prev_r:
                g.setdefault("analysis", {})["prev_rating"] = dict(home=prev_r.get(hid), away=prev_r.get(aid))
        cur_tab = team_table(standings.get(key))
        cur_r = {k: rating(v, lg["sport"]) for k, v in cur_tab.items() if v["gp"] >= 5}
        n_h = n_j = n_s = 0
        styles = {}
        for g in games:
            try:
                h = matchup.espn_h2h(g, lg, get, prev, prev_r, cur_r, hca, availability._team_schedule)
                if h:
                    g.setdefault("analysis", {})["h2h_long"] = h
                    n_h += 1
                    n_j += bool(h.get("jinx"))
            except Exception as e:  # noqa: BLE001
                ERRORS.append(f"{key} 交手 {g['id']} 失敗: {e!r}")
            if key == "nba":
                for side in ("home", "away"):
                    tid = g[side].get("id")
                    if tid and tid not in styles:
                        try:
                            styles[tid] = matchup.team_style(get, lg, tid, prev)
                        except Exception as e:  # noqa: BLE001
                            ERRORS.append(f"nba 球隊數據 {tid} 失敗: {e!r}")
                            styles[tid] = None
        if key == "nba" and styles:
            paces = [st["pace"] for st in styles.values() if st and st.get("pace")]
            lp = mean(paces) if len(paces) >= 6 else None
            for g in games:
                hs, as_ = styles.get(g["home"].get("id")), styles.get(g["away"].get("id"))
                lines = matchup.style_lines(hs, as_, team_label(g["home"]), team_label(g["away"]), lp)
                if lines:
                    note = "（用上季數據，陣容有變的話參考就好）" if (hs or {}).get("note") or (as_ or {}).get("note") else ""
                    g.setdefault("analysis", {})["style"] = dict(lines=lines, note=note)
                    n_s += 1
        log(f"[{key}] 對戰：交手紀錄 {n_h} 場（算得上剋星 {n_j} 場）、打法對位 {n_s} 場；上季評分 {len(prev_r)} 隊")


def args_debug():
    return "--debug-dir" in sys.argv


def _window(games, lo, hi):
    keep = []
    for g in games:
        st = parse_dt(g["start"])
        if g["status"]["state"] == "in" or (st and lo <= st <= hi):
            keep.append(g)
    keep.sort(key=lambda g: g["start"])
    return keep


def process_playsport(lg, lo, hi, all_games, standings):
    """歐籃、日籃：玩運彩為主幹，再用官方來源補隊徽、排名、英日文隊名，最後用新聞補傷兵。"""
    import playsport
    import newsinj
    t0 = time.time()
    games = playsport.fetch_games(lg, log, ERRORS)
    keep = _window(games, lo, hi)
    log(f"[{lg['key']}] 賽事 {len(games)} 場，窗口內 {len(keep)} 場")
    if keep:
        playsport.attach_history(lg, keep, log, ERRORS)
    st = None
    bl = None
    try:
        if lg["key"] == "eurobasket":
            from euroleague import EuroLeague
            el = EuroLeague(log, ERRORS)
            el.load()
            if keep:
                el.enrich(keep)
            st = el.standings_payload()
            name_fn = lambda t: (t["en_key"], "en") if t.get("en_key") else None  # noqa: E731
        else:
            from bleague import BLeague
            bl = BLeague(log, ERRORS)
            bl.load()
            if keep:
                bl.enrich(keep)
            st = bl.standings_payload()
            name_fn = lambda t: (t["jp_name"], "ja") if t.get("jp_name") else None  # noqa: E731
    except Exception as e:  # noqa: BLE001
        import traceback
        ERRORS.append(f"{lg['key']} 官方資料失敗: {e!r}")
        traceback.print_exc()
        name_fn = lambda t: None  # noqa: E731
    for g in keep:
        for side in ("home", "away"):
            finalize_team(g[side], lg)
    near = [g for g in keep if is_near(g)]
    if near:
        try:
            newsinj.attach(near, name_fn, log, ERRORS, lg["key"], hint=(" basketball" if lg["key"] == "eurobasket" else ""))
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"{lg['key']} 新聞失敗: {e!r}")
        if lg["key"] == "eurobasket":
            try:
                from players import fetch_el_players, el_player_layer
                from euroleague import season_code
                from taiwan_odds import fetch as _fetch
                rosters = {}
                for comp in ("E", "U"):
                    rosters.update(fetch_el_players(comp, season_code(comp), _fetch, log, ERRORS))
                try:
                    from elreport import fetch_reports
                    articles = fetch_reports(log, ERRORS)
                except Exception as e:  # noqa: BLE001
                    ERRORS.append(f"eurobasket 傷兵報告失敗: {e!r}")
                    articles = []
                el_player_layer(near, rosters, log, ERRORS, articles)
                for g in near:
                    for side in ("home", "away"):
                        finalize_team(g[side], lg)
            except Exception as e:  # noqa: BLE001
                import traceback
                ERRORS.append(f"eurobasket 球員層級失敗: {e!r}")
                traceback.print_exc()
        elif lg["key"] == "jpbasket":
            try:
                from jpplayers import bleague_rosters, player_layer
                ids = sorted({g[s_]["bl_id"] for g in near for s_ in ("home", "away") if g[s_].get("bl_id")})
                rosters = bleague_rosters(ids, log, ERRORS)
                player_layer(near, rosters, "bl_id", log, ERRORS, "jpbasket", impact_scale="el")
                for g in near:
                    for side in ("home", "away"):
                        finalize_team(g[side], lg)
            except Exception as e:  # noqa: BLE001
                ERRORS.append(f"jpbasket 球員層級失敗: {e!r}")
    elif lg["key"] == "jpbasket" and st and args_debug():
        # 沒比賽的時候也驗證一下名單與新聞對得起來（只寫 log）
        try:
            from jpplayers import bleague_rosters, validate
            rows = [r for r in (bl.rows if bl else []) if r.get("bl_id")][:3]
            rosters = bleague_rosters([r["bl_id"] for r in rows], log, ERRORS)
            validate("jpbasket", {r["team"]: rosters.get(r["bl_id"]) for r in rows}, log, ERRORS)
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"jpbasket 球員驗證失敗: {e!r}")
    all_games.extend(keep)
    if st:
        standings[lg["key"]] = dict(label=lg["label"], sport=lg["sport"], chip=lg["key"], **st)
    for k, v in list(playsport.DEBUG.items()):
        log(f"[{lg['key']}] 玩運彩樣本 {k}: {json.dumps(v, ensure_ascii=False)[:700]}")
    playsport.DEBUG.clear()
    log(f"[{lg['key']}] 完成，{time.time() - t0:.1f}s，累計呼叫 {CALLS['n']}")


def process_svleague(lg, lo, hi, all_games, standings):
    import svleague
    import newsinj
    t0 = time.time()
    games, st = svleague.fetch_games(lg, log, ERRORS)
    keep = _window(games, lo, hi)
    log(f"[{lg['key']}] 賽事 {len(games)} 場，窗口內 {len(keep)} 場")
    for g in keep:
        for side in ("home", "away"):
            finalize_team(g[side], lg)
    if keep:
        near = [g for g in keep if is_near(g)]
        try:
            newsinj.attach(near, lambda t: (t["jp_name"] + " バレー", "ja") if t.get("jp_name") else None, log, ERRORS, lg["key"])
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"{lg['key']} 新聞失敗: {e!r}")
        try:
            from jpplayers import sv_rosters, player_layer
            codes = sorted({g[s_]["sv_code"] for g in near for s_ in ("home", "away") if g[s_].get("sv_code")})
            rosters = sv_rosters(codes, log, ERRORS)
            player_layer(near, rosters, "sv_code", log, ERRORS, "jpvolley")
            for g in near:
                for side in ("home", "away"):
                    finalize_team(g[side], lg)
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"{lg['key']} 球員層級失敗: {e!r}")
    elif games and args_debug():
        try:
            from jpplayers import sv_rosters, validate
            seen = {}
            for g in games:
                for s_ in ("home", "away"):
                    if g[s_].get("sv_code") and g[s_]["sv_code"] not in seen:
                        seen[g[s_]["sv_code"]] = g[s_]["jp_name"]
            codes = list(seen)[:3]
            rosters = sv_rosters(codes, log, ERRORS)
            validate("jpvolley", {seen[c] + " バレー": rosters.get(c) for c in codes}, log, ERRORS)
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"{lg['key']} 球員驗證失敗: {e!r}")
    all_games.extend(keep)
    if st:
        standings[lg["key"]] = dict(label=lg["label"], sport=lg["sport"], chip=lg["key"], **st)
    log(f"[{lg['key']}] 完成，{time.time() - t0:.1f}s")


def estimate_from_form(g):
    """沒有任何盤口時，用兩隊近況粗估勝率（主場 +4 個百分點），只當參考。"""
    H, A = g["home"], g["away"]
    fh, fa = H.get("form") or [], A.get("form") or []
    if len(fh) < 3 or len(fa) < 3:
        return None
    wh = sum(1 for r in fh if r["result"] == "W") / len(fh)
    wa = sum(1 for r in fa if r["result"] == "W") / len(fa)
    ph = min(0.85, max(0.15, 0.5 + (wh - wa) * 0.45 + 0.04))
    return dict(provider=None, dec_home=None, dec_away=None, dec_draw=None,
                prob_home=round(ph, 3), prob_away=round(1 - ph, 3), prob_draw=None, prob_source="form",
                spread=None, details=None, total=None)


def fill_notes(g, lg):
    """每場都補一句「為什麼這裡沒資料」，前端就不會出現空白。"""
    n = {}
    src = lg.get("source")
    o = g.get("odds") or {}
    if o.get("prob_home") is None:
        n["odds"] = {
            "svleague": "台灣運彩和玩運彩都沒有日本排球的盤口，這場只看近況和新聞",
            "playsport": "台灣運彩還沒開這場的盤，通常比賽前一天才會出現",
        }.get(src, "台灣運彩還沒開這場的盤，通常比賽前一天才會出現")
    elif o.get("prob_source") == "form" and chip_of(lg) not in MAIN_CHIPS:
        n["odds"] = "沒有盤口，勝率是用兩隊近況估的，只能當參考"
    if lg.get("injuries"):
        n["injuries"] = "ESPN 傷兵名單裡沒有這隊的人，表示目前沒有傷兵回報"
    else:
        n["injuries"] = "這個聯盟沒有官方傷兵名單，改看新聞；賽前再確認一次"
    n["hot"] = "這個聯盟沒有球員逐場數據，手感看球隊近況為主" if not lg.get("gamelog") else "主力球員本季場次還不夠，暫時看不出手感冷熱"
    n["news"] = "近 4 天沒有找到這兩隊的新聞" if src else "24 小時內沒有相關新聞"
    if not g.get("tw"):
        n["tw"] = "台灣運彩沒有開日本排球" if src == "svleague" else "台灣運彩還沒開這場，通常比賽前一天才會出現"
    if not (g["home"].get("form") or g["away"].get("form")):
        n["form"] = "兩隊本季都還沒有打完的比賽紀錄，近況暫時看不出來"
    g["notes"] = n


def process_league(lg, dates, lo, hi, all_games, standings):
    if lg.get("source") == "playsport":
        return process_playsport(lg, lo, hi, all_games, standings)
    if lg.get("source") == "svleague":
        return process_svleague(lg, lo, hi, all_games, standings)
    if True:
        t0 = time.time()
        games = fetch_games(lg, dates)
        keep = []
        for g in games:
            st = parse_dt(g["start"])
            if g["status"]["state"] == "in" or (lo <= st <= hi):
                keep.append(g)
        keep.sort(key=lambda g: g["start"])
        log(f"[{lg['key']}] 賽事 {len(games)} 場，窗口內 {len(keep)} 場")
        if not keep:
            return
        injuries_map = fetch_injuries(lg) if lg.get("injuries") else {}
        news = fetch_news(lg) if not lg.get("tennis") else []
        seen_teams = {}
        for g in keep:
            for side in ("home", "away"):
                t = g[side]
                finalize_team(t, lg, injuries_map)
                if g.get("tennis"):
                    continue
                want_hot = lg.get("gamelog") and g["status"]["state"] != "post" and is_near(g)
                if t["id"] in seen_teams:
                    cached = seen_teams[t["id"]]
                    for k in ("form", "form_note", "streak", "last10", "last10_w", "avg_for5", "avg_against5", "avg_total5", "avg_margin5", "hot"):
                        t[k] = cached.get(k)
                    if not want_hot or cached.get("hot") is not None:
                        continue
                else:
                    try:
                        fetch_form(lg, t)
                    except Exception as e:  # noqa: BLE001
                        import traceback
                        tb = traceback.extract_tb(e.__traceback__)[-1]
                        ERRORS.append(f"{lg['key']} 球隊 {t.get('abbr')} 近況失敗: {e!r} @ {tb.name}:{tb.lineno} {tb.line}")
                if want_hot:
                    hot = []
                    for ath in (t.get("leaders") or [])[:3]:
                        try:
                            pf = fetch_player_form(lg, ath)
                        except Exception as e:  # noqa: BLE001
                            ERRORS.append(f"{lg['key']} 球員 {ath.get('player')} 近況失敗: {e!r}")
                            pf = None
                        if pf:
                            hot.append(pf)
                    t["hot"] = hot
                    if t["id"] in seen_teams:
                        seen_teams[t["id"]]["hot"] = hot
                seen_teams.setdefault(t["id"], t)
            ids = {g["home"]["id"], g["away"]["id"]}
            picked = []
            for a in news:
                if a["teams"] & ids:
                    picked.append(dict(title=a["title"], desc=a["desc"], url=a["url"], image=a["image"],
                                       published=a["published"],
                                       team="home" if g["home"]["id"] in a["teams"] else "away"))
                if len(picked) >= 4:
                    break
            g["news"] = picked
        all_games.extend(keep)
        if not lg.get("tennis"):
            try:
                s = fetch_standings(lg)
            except Exception as e:  # noqa: BLE001
                ERRORS.append(f"{lg['key']} 排名失敗: {e!r}")
                s = None
            if s:
                standings[lg["key"]] = dict(label=LEAGUE_ZH.get(lg["key"]), sport=lg["sport"], chip=chip_of(lg), **s)
        log(f"[{lg['key']}] 完成，{time.time() - t0:.1f}s，累計呼叫 {CALLS['n']}")


if __name__ == "__main__":
    main()
