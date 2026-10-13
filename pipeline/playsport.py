# -*- coding: utf-8 -*-
"""以玩運彩（playsport.cc）為主幹的聯盟：歐洲籃球（allianceid 8）、日本籃球（allianceid 97）。

這兩個聯盟 ESPN 沒有資料，但台灣運彩有開盤，玩運彩就有：賽程、台灣盤、國際盤、玩家預測比例、
每隊的歷史戰績（/gamesData/teams?allianceid=X&teamid=Y）。本模組把這些整理成跟 ESPN 一樣的賽事格式。
抓不到就少一點，不會整個壞掉。
"""
import re
import time
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from taiwan_odds import BASE, fetch, parse_scale_page, fetch_livescore_ids, TW, _num

UTC = timezone.utc
SOURCE_ZH = {
    "EuroLeague": "歐冠", "Euroleague": "歐冠", "EuroCup": "歐盃", "Eurocup": "歐盃",
    "BCL": "籃球冠軍聯賽", "ChampionsLeague": "籃球冠軍聯賽", "FibaEuropeCup": "FIBA 歐洲盃",
    "Bleague": "B.LEAGUE", "BLeague": "B.LEAGUE", "B1": "B.PREMIER", "B2": "B.ONE",
}
DEBUG = {}


def _blank_team(name, tid, aid):
    return dict(
        id=f"ps{aid}-{tid or name}", ps_teamid=tid, abbr="", name=name, short=name, name_zh=name,
        logo=None, color=None, record=None, record_home=None, record_away=None,
        score=None, winner=False, form_str=None, leaders=[], injuries=[], key_out=[], key_maybe=[],
        out_count=0, maybe_count=0, hot=[], form=[], form_note=None, streak=None, last10=None, last10_w=0,
        avg_for5=None, avg_against5=None, avg_total5=None, avg_margin5=None,
    )


def _spread_prob(spread_home):
    if spread_home is None:
        return None
    from math import erf, sqrt
    return 0.5 * (1 + erf((-spread_home) / (11.0 * sqrt(2))))


def build_odds(row):
    """用國際盤讓分估勝率；沒有就用台灣不讓分賠率去掉抽水。賠率欄位放台灣運彩的，前端才有東西可顯示。"""
    intl = row.get("intl") or {}
    ml = row.get("ml") or {}
    sp = row.get("spread") or {}
    tot = row.get("total") or {}
    ph = pa = None
    src = None
    if intl.get("spread_home") is not None:
        ph = _spread_prob(intl["spread_home"])
        pa = 1 - ph
        src = "spread"
    elif ml.get("home") and ml.get("away"):
        ih, ia = 1 / ml["home"], 1 / ml["away"]
        ph, pa = ih / (ih + ia), ia / (ih + ia)
        src = "tw_ml"
    elif sp.get("line_home") is not None:
        ph = _spread_prob(sp["line_home"])
        pa = 1 - ph
        src = "spread"
    if ph is None:
        return None
    spread_home = intl.get("spread_home") if intl.get("spread_home") is not None else sp.get("line_home")
    details = intl.get("spread_text") or sp.get("line")
    return dict(
        provider="台灣運彩" if ml else "國際盤",
        dec_home=ml.get("home"), dec_away=ml.get("away"), dec_draw=None,
        prob_home=round(ph, 3), prob_away=round(pa, 3), prob_draw=None, prob_source=src,
        spread=spread_home, details=details,
        total=intl.get("total") if intl.get("total") is not None else tot.get("line"),
    )


def _state_for(start_utc, now, ls):
    """玩運彩的即時 JSON 有比分與節次；沒有就用時間推。籃球抓 2 小時 40 分。"""
    if ls and ls.get("note") and any(k in str(ls["note"]) for k in ("延期", "取消", "延賽")):
        return "post", str(ls["note"]), False
    if now < start_utc:
        return "pre", "未開賽", False
    end = start_utc + timedelta(minutes=160)
    period = (ls or {}).get("period") or 0
    remaining = (ls or {}).get("remaining") or ""
    if now >= end:
        return "post", "已結束", True
    try:
        period = int(period)
    except (TypeError, ValueError):
        period = 0
    if period and period <= 4:
        label = f"第 {period} 節"
    elif period > 4:
        label = f"延長 {period - 4}"
    else:
        label = "進行中"
    return "in", f"{label} {remaining}".strip(), False


def fetch_games(lg, log, errors, now=None):
    """抓今天起三天的盤口表＋即時比分，組成賽事列表。"""
    aid = lg["alliance"]
    now = now or datetime.now(UTC)
    now_tw = now.astimezone(TW)
    days = [(now_tw + timedelta(days=i)).strftime("%Y%m%d") for i in range(-1, 3)]
    games = []
    seen = set()
    for d in days:
        url = f"{BASE}/predict/scale?allianceid={aid}&gametime={d}"
        text = fetch(url)
        if not text:
            errors.append(f"{lg['key']} 玩運彩 {d} 抓不到盤口頁")
            continue
        try:
            rows = parse_scale_page(text)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{lg['key']} 玩運彩 {d} 解析失敗: {e!r}")
            continue
        ids = fetch_livescore_ids(aid, d)
        if ids and f"ls_{aid}" not in DEBUG:
            DEBUG[f"ls_{aid}"] = next(iter(ids.values()))
        if rows and f"row_{aid}" not in DEBUG:
            DEBUG[f"row_{aid}"] = {k: v for k, v in rows[0].items() if k != "sides"}
        for r in rows:
            gid = str(r.get("gameid") or "")
            if not gid or gid in seen or not r.get("time"):
                continue
            seen.add(gid)
            try:
                start_tw = datetime.strptime(d + r["time"], "%Y%m%d%H:%M").replace(tzinfo=TW)
            except ValueError:
                continue
            # 玩運彩的「賽事日」是台灣日期；凌晨的歐洲比賽算在當天凌晨
            start_utc = start_tw.astimezone(UTC)
            ls = ids.get(gid) or {}
            state, detail, completed = _state_for(start_utc, now, ls)
            home = _blank_team(r["home"], r.get("home_teamid"), aid)
            away = _blank_team(r["away"], r.get("away_teamid"), aid)
            if state != "pre" and ls:
                if ls.get("hscore") not in (None, "", 0) or ls.get("ascore") not in (None, "", 0):
                    home["score"] = str(ls.get("hscore"))
                    away["score"] = str(ls.get("ascore"))
                    if state == "post":
                        try:
                            home["winner"] = float(ls["hscore"]) > float(ls["ascore"])
                            away["winner"] = float(ls["ascore"]) > float(ls["hscore"])
                        except (TypeError, ValueError):
                            pass
            src = (ls.get("source") or "").strip()
            comp = SOURCE_ZH.get(src) or (src if src and not src.lower().startswith(("fiba", "tw")) else None)
            tw = dict(source="玩運彩", url=url, updated=now_tw.isoformat(timespec="minutes"), no=r.get("no"),
                      matched_by="直接", spread=r.get("spread"), ml=r.get("ml"), total=r.get("total"),
                      intl=r.get("intl"), crowd=r.get("crowd"), tw_names=f"{r['away']} @ {r['home']}",
                      gameid=gid, battle_url=f"{BASE}/gamesData/battle?gameid={gid}&allianceid={aid}")
            g = dict(
                id=f"ps{gid}", league=lg["key"], league_zh=lg["label"], sport=lg["sport"], chip=lg["key"],
                tennis=False, tournament=None, round=comp, comp=comp, comp_source=src or None,
                name=f"{r['away']} @ {r['home']}",
                start=start_utc.isoformat(timespec="minutes"), start_tw=start_tw.isoformat(timespec="minutes"),
                day_tw=start_tw.strftime("%Y-%m-%d"), time_tw=start_tw.strftime("%H:%M"),
                status=dict(state=state, completed=completed, detail=detail, clock=ls.get("remaining"), period=ls.get("period")),
                venue=None, broadcast=None, home=home, away=away,
                odds=build_odds(r), headline=None, news=[], suggestion=None, tw=tw,
                analysis=dict(crowd=r.get("crowd")) if r.get("crowd") else {},
                official=ls.get("official"),
            )
            games.append(g)
        # 盤口頁沒列、但即時比分有的（通常是已開打或已結束的）：做成沒盤口的賽事，比分照顯示
        for gid, ls in ids.items():
            if gid in seen or not ls.get("dateon"):
                continue
            try:
                start_tw = datetime.strptime(ls["dateon"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TW)
            except ValueError:
                continue
            seen.add(gid)
            start_utc = start_tw.astimezone(UTC)
            state, detail, completed = _state_for(start_utc, now, ls)
            home = _blank_team(ls.get("hname") or ls.get("h") or "主隊", None, aid)
            away = _blank_team(ls.get("aname") or ls.get("a") or "客隊", None, aid)
            if ls.get("hscore") not in (None, "", 0) or ls.get("ascore") not in (None, "", 0):
                home["score"], away["score"] = str(ls.get("hscore")), str(ls.get("ascore"))
                if state == "post":
                    try:
                        home["winner"] = float(ls["hscore"]) > float(ls["ascore"])
                        away["winner"] = float(ls["ascore"]) > float(ls["hscore"])
                    except (TypeError, ValueError):
                        pass
            src = (ls.get("source") or "").strip()
            comp = SOURCE_ZH.get(src)
            games.append(dict(
                id=f"ps{gid}", league=lg["key"], league_zh=lg["label"], sport=lg["sport"], chip=lg["key"],
                tennis=False, tournament=None, round=comp, comp=comp, comp_source=src or None,
                name=f"{away['name']} @ {home['name']}",
                start=start_utc.isoformat(timespec="minutes"), start_tw=start_tw.isoformat(timespec="minutes"),
                day_tw=start_tw.strftime("%Y-%m-%d"), time_tw=start_tw.strftime("%H:%M"),
                status=dict(state=state, completed=completed, detail=detail, clock=ls.get("remaining"), period=ls.get("period")),
                venue=None, broadcast=None, home=home, away=away, odds=None, headline=None, news=[], suggestion=None,
                tw=None, analysis={}, official=ls.get("official"),
            ))
        time.sleep(0.3)
    log(f"[{lg['key']}] 玩運彩 {len(games)} 場（{'、'.join(days)}）")
    return games


# ---------- 球隊歷史戰績（近況） ----------
def _clean_name(td):
    if td is None:
        return ""
    p = td.find("p")
    alt = p.get_text(strip=True) if p else ""
    full = td.get_text(" ", strip=True)
    if alt and full.endswith(alt):
        full = full[: -len(alt)]
    return full.strip() or alt


def parse_team_history(text, team_name, now_tw):
    """解析 /gamesData/teams 的 historyGameTable。回傳由舊到新的近況列（跟 ESPN 的 parse_schedule 同格式）。"""
    soup = BeautifulSoup(text, "html.parser")
    table = soup.select_one("#historyGameTable") or soup.select_one("table.gamedata-history-tab1")
    if not table:
        return [], None
    rows = []
    raw_sample = None
    for tr in table.find_all("tr", recursive=False):
        info = tr.select_one("td.td-gameinfo")
        tinfo = tr.select_one("td.td-teaminfo")
        if info is None or tinfo is None:
            continue
        h3 = info.find("h3")
        h4 = info.find("h4")
        md = h3.get_text(strip=True) if h3 else ""
        m = re.match(r"(\d{1,2})/(\d{1,2})", md)
        if not m:
            continue
        mon, day = int(m.group(1)), int(m.group(2))
        year = now_tw.year
        if mon > now_tw.month + 1:
            year -= 1
        hhmm = "00:00"
        mt = re.match(r"(AM|PM)\s*(\d{1,2}):(\d{2})", h4.get_text(strip=True) if h4 else "")
        if mt:
            hh = int(mt.group(2)) % 12 + (12 if mt.group(1) == "PM" else 0)
            hhmm = f"{hh:02d}:{mt.group(3)}"
        try:
            dt = datetime(year, mon, day, int(hhmm[:2]), int(hhmm[3:]), tzinfo=TW)
        except ValueError:
            continue
        if dt > now_tw:
            continue
        scores = [li.get_text(strip=True) for li in tinfo.select("td.scores li") if "vsicon" not in (li.get("class") or [])]
        name_tds = [td for td in tinfo.find_all("td") if any(c in ("winnerteam", "secondteam", "loseteam") for c in (td.get("class") or []))]
        if len(scores) < 2 or len(name_tds) < 2:
            continue
        s1, s2 = _num(scores[0]), _num(scores[1])
        if s1 is None or s2 is None:
            continue
        n1, n2 = _clean_name(name_tds[0]), _clean_name(name_tds[1])
        alt1 = (name_tds[0].find("p").get_text(strip=True) if name_tds[0].find("p") else "")
        alt2 = (name_tds[1].find("p").get_text(strip=True) if name_tds[1].find("p") else "")
        me_first = team_name in (n1, alt1) or (team_name and (team_name in n1 or n1 in team_name))
        me_second = team_name in (n2, alt2) or (team_name and (team_name in n2 or n2 in team_name))
        if me_first and not me_second:
            pf, pa, opp, home = s1, s2, n2, False
        elif me_second:
            pf, pa, opp, home = s2, s1, n1, True
        else:
            # 認不出哪個是自己：以第一個當自己（玩運彩頁面通常把查詢的隊放前面）
            pf, pa, opp, home = s1, s2, n2, None
        bets = {}
        for td in tr.find_all("td", recursive=False):
            cls = " ".join(td.get("class") or [])
            if "bet" in cls or "scoresum" in cls:
                bets[cls.split()[-1]] = td.get_text(" ", strip=True)
        if raw_sample is None:
            bank = tr.find("td", class_=re.compile("td-bank-bet01"))
            raw_sample = dict(date=md, names=(n1, n2), scores=(s1, s2), bets=bets, bank_html=re.sub(r"\s+", " ", str(bank))[:500] if bank else None)
        rows.append(dict(
            date=f"{mon:02d}/{day:02d}", date_iso=dt.astimezone(UTC).isoformat(timespec="minutes"), ts=dt.timestamp(),
            opp=opp, opp_zh=opp, opp_logo=None, home=home, pf=int(pf), pa=int(pa),
            result="W" if pf > pa else ("L" if pf < pa else "D"), comp=None, bets=bets,
        ))
    rows.sort(key=lambda r: r["ts"])
    return rows, raw_sample


def summarize_form(team, rows, note=None):
    from statistics import mean
    for r in rows:
        r.pop("ts", None)
        r.pop("bets", None)
    if not rows:
        return
    last = rows[-10:]
    team["form"] = last
    team["form_note"] = note
    w = sum(1 for r in last if r["result"] == "W")
    l = sum(1 for r in last if r["result"] == "L")
    team["last10"] = f"{w}勝{l}敗"
    team["last10_w"] = w
    s, first = 0, last[-1]["result"]
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
    if not team.get("record"):
        aw = sum(1 for r in rows if r["result"] == "W")
        al = sum(1 for r in rows if r["result"] == "L")
        team["record"] = f"{aw}-{al}"
        team["record_note"] = "玩運彩有紀錄的比賽"


def attach_history(lg, games, log, errors):
    """每支球隊抓一次歷史戰績，算近況、連勝連敗、近 5 場平均。"""
    aid = lg["alliance"]
    cache = {}
    n_ok = 0
    now_tw = datetime.now(TW)
    for g in games:
        for side in ("home", "away"):
            t = g[side]
            tid = t.get("ps_teamid")
            if not tid:
                continue
            if tid in cache:
                src = cache[tid]
                for k in ("form", "form_note", "streak", "last10", "last10_w", "avg_for5", "avg_against5", "avg_total5", "avg_margin5", "record", "record_note"):
                    t[k] = src.get(k)
                continue
            text = fetch(f"{BASE}/gamesData/teams?allianceid={aid}&teamid={tid}")
            if not text:
                errors.append(f"{lg['key']} 球隊 {t['name']} 歷史頁抓不到")
                cache[tid] = t
                continue
            try:
                rows, raw = parse_team_history(text, t["name"], now_tw)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{lg['key']} 球隊 {t['name']} 歷史解析失敗: {e!r}")
                rows, raw = [], None
            if raw and f"hist_{aid}" not in DEBUG:
                DEBUG[f"hist_{aid}"] = raw
            if rows:
                summarize_form(t, rows, note="玩運彩歷史戰績")
                n_ok += 1
            cache[tid] = t
            time.sleep(0.25)
    log(f"[{lg['key']}] 球隊近況：{n_ok}/{len(cache)} 隊有資料")
    return n_ok
