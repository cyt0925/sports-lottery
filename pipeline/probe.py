# -*- coding: utf-8 -*-
"""暫時的查詢：TheSportsDB 免費版能不能拿到歐洲國內籃球聯賽的整季賽程、比分、排名。只寫 log，查完會拿掉。"""
import time
from collections import Counter

import requests

B = "https://www.thesportsdb.com/api/v1/json/123"
LEAGUES = {4408: "ACB", 4433: "LBA", 4475: "BSL", 4452: "希臘", 4423: "LNB", 4441: "BBL", 4478: "LKL", 4474: "以色列"}


def _j(path, **params):
    time.sleep(2.2)   # 免費版每分鐘 30 次
    try:
        r = requests.get(f"{B}/{path}", params=params, timeout=30)
        return r.json() if r.text.strip() else {}
    except Exception as e:  # noqa: BLE001
        return {"_err": f"{type(e).__name__}"}


def _ev(e):
    return f"{e.get('dateEvent')} {e.get('strTime')} r{e.get('intRound')} {e.get('strHomeTeam')} {e.get('intHomeScore')}-{e.get('intAwayScore')} {e.get('strAwayTeam')}"


def run(log):
    d = _j("search_all_leagues.php", s="Basketball")
    names = [(x.get("idLeague"), x.get("strLeague")) for x in (d.get("countries") or d.get("leagues") or [])]
    log(f"[查詢6] 籃球聯賽 {len(names)} 個，有 Adriatic/ABA/Euro：{[n for n in names if any(k in (n[1] or '') for k in ('Adriatic', 'ABA', 'Euro', 'Champions', 'VTB', 'Romania', 'Pol', 'Belg', 'Dutch'))]}")
    day = _j("eventsday.php", d="2026-10-19", s="Basketball")
    evs = day.get("events") or []
    log(f"[查詢6] 10/19 籃球 {len(evs)} 場：{Counter(e.get('strLeague') for e in evs).most_common(20)}")
    for lid, nm in LEAGUES.items():
        lg = (_j("lookupleague.php", id=lid).get("leagues") or [{}])[0]
        season = lg.get("strCurrentSeason") or "2026-2027"
        se = _j("eventsseason.php", id=lid, s=season)
        sev = se.get("events") or []
        played = [e for e in sev if e.get("intHomeScore") not in (None, "")]
        rounds = sorted({int(e["intRound"]) for e in sev if (e.get("intRound") or "").isdigit()})
        log(f"[查詢6] {nm} {lid} 季 {season}：整季 {len(sev)} 場（有比分 {len(played)}），輪次 {rounds[:3]}…{rounds[-3:]}，"
            f"第一場 {sev[0].get('dateEvent') if sev else ''}，最後 {sev[-1].get('dateEvent') if sev else ''} {se.get('_err', '')}")
        cur = max([int(e["intRound"]) for e in played if (e.get("intRound") or "").isdigit()] or [3])
        for r in (cur, cur + 1):
            ro = _j("eventsround.php", id=lid, r=r, s=season).get("events") or []
            log(f"[查詢6]   第 {r} 輪 {len(ro)} 場：{[_ev(e) for e in ro[:10]]}")
        tb = _j("lookuptable.php", l=lid, s=season).get("table") or []
        log(f"[查詢6]   排名 {len(tb)} 隊：{[(t.get('strTeam'), t.get('intWin'), t.get('intLoss'), t.get('intGoalsFor'), t.get('intGoalsAgainst')) for t in tb[:5]]}")
        nx = _j("eventsnextleague.php", id=lid).get("events") or []
        log(f"[查詢6]   接下來 {len(nx)} 場：{[_ev(e) for e in nx[:5]]}")
