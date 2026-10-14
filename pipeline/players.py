# -*- coding: utf-8 -*-
"""球員層級：缺陣的人平常扛多少，換算成讓分影響；主力球員名單。

NBA：ESPN 傷兵名單有球員 id → 查本季（沒有就上季）場均得分、上場時間。
歐籃：官方 v3 球員數據（場均得分、分鐘、PIR）當名單；傷兵從新聞標題對姓氏（out / doubtful / return）。
影響分數用簡單的級距（透明、好解釋），不假裝很精準。"""
import re
import time
from datetime import datetime, timezone, timedelta

TW = timezone(timedelta(hours=8))
CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"


def impact_points(ppg, mpg, scale="nba"):
    """缺一個場均 X 分的人大概差幾分讓分。NBA 級距：22+ → 4、15–22 → 2.5、10–15 → 1.5、其餘 0.5；先發（28 分鐘以上）再加 0.5。"""
    if ppg is None:
        return 0.5
    if scale == "el":
        tiers = ((16, 4.0), (11, 2.5), (7, 1.5))
    else:
        tiers = ((22, 4.0), (15, 2.5), (10, 1.5))
    pts = 0.5
    for th, v in tiers:
        if ppg >= th:
            pts = v
            break
    if mpg and mpg >= (26 if scale == "el" else 28):
        pts += 0.5
    return pts


def _season_year(now=None):
    now = now or datetime.now(TW)
    return now.year + 1 if now.month >= 7 else now.year


# ---------- NBA ----------
def _espn_stats(get, athlete_id, season):
    d = get(f"{CORE}/seasons/{season}/types/2/athletes/{athlete_id}/statistics", params={"lang": "en", "region": "us"}, tries=1, quiet=True)
    if not isinstance(d, dict):
        return None
    out = {}
    for cat in ((d.get("splits") or {}).get("categories") or []):
        for st in cat.get("stats") or []:
            n = st.get("name")
            if n in ("avgPoints", "avgMinutes", "avgRebounds", "avgAssists", "gamesPlayed"):
                out[n] = st.get("value")
    if not out.get("gamesPlayed"):
        return None
    return out


def nba_injury_impact(games, get, log, errors, keep_raw=None):
    season = _season_year()
    cache = {}
    n_q = n_hit = 0
    for g in games:
        if g["league"] != "nba" or g["status"]["state"] == "post":
            continue
        for side in ("home", "away"):
            t = g[side]
            players = []
            for inj in t.get("injuries") or []:
                if inj.get("severity") not in ("out", "ir", "maybe") or not inj.get("id"):
                    continue
                pid = str(inj["id"])
                if pid not in cache:
                    n_q += 1
                    st = None
                    for yr in (season, season - 1):
                        try:
                            st = _espn_stats(get, pid, yr)
                        except Exception as e:  # noqa: BLE001
                            errors.append(f"nba 球員數據 {pid} 失敗: {e!r}")
                            st = None
                        if st:
                            st["season"] = yr
                            break
                        time.sleep(0.15)
                    cache[pid] = st
                    if st and keep_raw and n_hit == 0:
                        keep_raw("athlete_stats_nba", st)
                st = cache[pid]
                if not st:
                    continue
                n_hit += 1
                ppg, mpg = st.get("avgPoints"), st.get("avgMinutes")
                pts = impact_points(ppg, mpg)
                if inj["severity"] == "maybe":
                    pts = round(pts * 0.5, 1)
                inj["ppg"], inj["mpg"] = ppg, mpg
                inj["impact"] = pts
                inj["stats_season"] = st.get("season")
                players.append(dict(player=inj["player"], ppg=ppg, mpg=mpg, status=inj["severity"], impact=pts, status_zh=inj.get("status_zh")))
            if players:
                players.sort(key=lambda x: -x["impact"])
                total = round(min(8.0, sum(p["impact"] for p in players)), 1)
                t["injury_impact"] = dict(pts=total, players=players[:4], note="依場均得分與上場時間的級距估算")
    log(f"[nba] 傷兵影響：查了 {n_q} 人、有數據 {n_hit} 人")


# ---------- EuroLeague ----------
OUT_WORDS = re.compile(r"\b(out|miss|misses|missing|sidelined|surgery|injur|ruled out|absent|absence|will not|won't|without)\b", re.I)
MAYBE_WORDS = re.compile(r"\b(doubtful|questionable|game-time|uncertain|50-50|could miss|may miss|might miss)\b", re.I)
BACK_WORDS = re.compile(r"\b(returns?|is back|comeback|cleared|available|rejoins?|recovered)\b", re.I)


def _display(name):
    """'MOTLEY, JOHNATHAN' -> 'Johnathan Motley'"""
    if "," in name:
        sur, first = [x.strip() for x in name.split(",", 1)]
        return f"{first.title()} {sur.title()}".strip()
    return name.title()


def _surname(name):
    sur = name.split(",", 1)[0].strip() if "," in name else name.split(" ")[-1]
    return sur.title()


def fetch_el_players(comp, season_code, fetch, log, errors):
    """回傳 {team_code: [player dict...]}（場均）。"""
    base = f"https://api-live.euroleague.net/v3/competitions/{comp}/statistics/players/traditional"
    out = {}
    offset, total, got = 0, None, 0
    while True:
        d = fetch(f"{base}?seasonMode=Single&seasonCode={season_code}&limit=200&offset={offset}", as_json=True)
        if not isinstance(d, dict) or not d.get("players"):
            if offset == 0:
                errors.append(f"歐籃 {comp} 球員數據抓不到")
            break
        total = d.get("total") or 0
        for p in d["players"]:
            pl = p.get("player") or {}
            team = (pl.get("team") or {}).get("code")
            if not team:
                continue
            out.setdefault(team, []).append(dict(
                id=pl.get("code"), name=_display(pl.get("name") or ""), surname=_surname(pl.get("name") or ""),
                headshot=pl.get("imageUrl"), gp=p.get("gamesPlayed"), ppg=p.get("pointsScored"), mpg=p.get("minutesPlayed"),
                pir=p.get("pir"), rpg=p.get("totalRebounds"), apg=p.get("assists"),
            ))
        got += len(d["players"])
        offset += len(d["players"])
        if got >= total or len(d["players"]) == 0:
            break
        time.sleep(0.3)
    log(f"[eurobasket] {comp} 球員數據 {got} 人、{len(out)} 隊")
    return out


def el_player_layer(games, rosters, log, errors):
    """主力名單（stars）＋從新聞標題對出來的傷兵＋影響分數。"""
    n_star = n_inj = 0
    for g in games:
        for side in ("home", "away"):
            t = g[side]
            code = t.get("el_code")
            roster = rosters.get(code) if code else None
            if not roster:
                continue
            roster = [p for p in roster if (p.get("gp") or 0) > 0]
            roster.sort(key=lambda p: -(p.get("ppg") or 0))
            t["stars"] = [dict(id=p["id"], player=p["name"], headshot=p.get("headshot"), ppg=p.get("ppg"), mpg=p.get("mpg"), pir=p.get("pir"), position=None) for p in roster[:4]]
            t["leaders"] = [dict(id=p["id"], player=p["name"], headshot=p.get("headshot"), position=None, stat="PTS", value=str(p.get("ppg"))) for p in roster[:3]]
            n_star += 1
            found = {}
            for a in t.get("injury_news") or []:
                title = a.get("title") or ""
                for p in roster:
                    sur = p["surname"]
                    if len(sur) < 4:
                        continue
                    if not re.search(r"(?<![A-Za-z])" + re.escape(sur) + r"(?![a-z])", title):
                        continue
                    if BACK_WORDS.search(title) and not OUT_WORDS.search(title):
                        sev = "ok"
                    elif MAYBE_WORDS.search(title):
                        sev = "maybe"
                    elif OUT_WORDS.search(title):
                        sev = "out"
                    else:
                        continue
                    cur = found.get(p["id"])
                    rank = {"out": 2, "maybe": 1, "ok": 0}
                    if cur is None or rank[sev] > rank[cur["severity"]]:
                        found[p["id"]] = dict(
                            id=p["id"], player=p["name"], headshot=p.get("headshot"), position=None,
                            status={"out": "Out", "maybe": "Doubtful", "ok": "Available"}[sev],
                            status_zh={"out": "缺陣", "maybe": "存疑", "ok": "回歸"}[sev], severity=sev,
                            detail=title[:80], url=a.get("url"), source=a.get("source"), official=False,
                            ppg=p.get("ppg"), mpg=p.get("mpg"), return_date=None, comment=None,
                        )
            if found:
                inj = list(found.values())
                for x in inj:
                    if x["severity"] in ("out", "maybe"):
                        x["impact"] = round(impact_points(x["ppg"], x["mpg"], "el") * (0.5 if x["severity"] == "maybe" else 1), 1)
                t["injuries"] = inj
                players = [dict(player=x["player"], ppg=x["ppg"], mpg=x["mpg"], status=x["severity"], impact=x["impact"], status_zh=x["status_zh"]) for x in inj if x["severity"] in ("out", "maybe")]
                if players:
                    players.sort(key=lambda x: -x["impact"])
                    t["injury_impact"] = dict(pts=round(min(8.0, sum(p["impact"] for p in players)), 1), players=players[:4], note="從新聞標題對到球員，依場均得分估算")
                t["injury_note"] = "沒有官方傷兵名單，這是從新聞標題對出來的，賽前再確認一次"
                n_inj += 1
    log(f"[eurobasket] 球員層級：{n_star} 隊有主力名單，{n_inj} 隊從新聞對到傷兵")
