# -*- coding: utf-8 -*-
"""球員層級：缺陣的人平常扛多少，換算成讓分影響；主力球員名單。

NBA：ESPN 傷兵名單有球員 id → 查本季（沒有就上季）場均得分、上場時間。
歐籃：官方 v3 球員數據（場均得分、分鐘、PIR）當名單；傷兵從新聞標題對姓氏（out / doubtful / return）。
影響分數用簡單的級距（透明、好解釋），不假裝很精準。"""
import re
import time
import unicodedata
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
OUT_WORDS = re.compile(r"\b(out|miss|misses|missing|sidelined|surgery|injur\w*|ruled out|absent|absence|absences|will not|won't|without|unavailable|not travel\w*|not play\w*|remain out|still out|inactive)\b", re.I)
MAYBE_WORDS = re.compile(r"\b(doubtful|questionable|game-time|game time decision|uncertain|50-50|could miss|may miss|might miss|probable|expected to)\b", re.I)
BACK_WORDS = re.compile(r"\b(returns?|returned|returning|is back|back in|comeback|cleared|available|rejoins?|recovered|will play|ready to play|makes his debut|set to play)\b"
                        r"|(?<!lower )(?<!his )(?<!the )\bback\b(?!\s+(?:injur|problem|issue|pain|spasm|strain|surgery|tightness|trouble))", re.I)
REPORT_TITLE = re.compile(r"injury report|absences|will miss|key players who will miss|sidelined", re.I)
SEV_RANK = {"out": 2, "maybe": 1, "ok": 0}
STATUS = {"out": ("Out", "缺陣"), "maybe": ("Doubtful", "存疑"), "ok": ("Available", "回歸")}


def _ascii(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(ch for ch in s if not unicodedata.combining(ch))


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


def _sentences(text):
    out = []
    for line in (text or "").split("\n"):
        for s in re.split(r"(?<=[.!?;])\s+", line):
            s = s.strip()
            if len(s) > 3:
                out.append(s)
    return out


def _clauses(sentence):
    """一句裡講到兩隊的話拆開看：「Besiktas will be without X, and Paris has Y back」。"""
    return [c.strip() for c in re.split(r",\s+(?:and|but|while|whereas)\s+|;\s+|\s+(?:while|whereas|but)\s+", sentence) if c.strip()]


IMPLIED_HINT = re.compile(r"\(|knee|ankle|calf|hamstring|shoulder|foot|hand|wrist|thigh|groin|hip|muscle|illness|surgery|fracture|strain|sprain|tear|rehab|recover|achilles|concussion|back\b", re.I)


def _severity(sentence, implied_out=False):
    """同一句裡誰先出現就聽誰的：「returns after missing two games」是回來，「will not return」是缺陣。
    傷兵報告類文章裡只點名、沒講狀態的句子（通常是「名字（膝蓋）」這種），當缺陣。"""
    hits = []
    for sev, rx in (("ok", BACK_WORDS), ("out", OUT_WORDS), ("maybe", MAYBE_WORDS)):
        m = rx.search(sentence)
        if m:
            hits.append((m.start(), sev))
    if hits:
        return min(hits)[1]
    if implied_out and (IMPLIED_HINT.search(sentence) or len(sentence) < 90):
        return "out"
    return None


def _name_regex(name):
    return re.compile(r"(?<![A-Za-z])" + re.escape(_ascii(name)) + r"(?![a-z])", re.I)


STATUS_TOKEN = re.compile(r"^(out|remains?|returns?|returned|doubtful|questionable|sidelined|misses|missed|missing|will|set|ruled|back|injured|injury|available|expected|cleared|to|is|not|could|may|might|won't|has|had|was|were|still|also|likely|unlikely|suffered|underwent|undergoes|faces|and|who)$", re.I)


def _surname_alone(text, m, first):
    """只對到姓氏時再保險一點：前面接著別的名字（TyTy Washington）或後面接著別的姓（Gabriel Deck）就不算。"""
    pre, post = text[:m.start()], text[m.end():]
    mp = re.search(r"([A-Z][A-Za-z'\-]+)\s*$", pre)
    if mp and mp.group(1).lower() != first.lower() and not mp.group(1).endswith("'s"):
        return False
    mf = re.match(r"\s+([A-Z][A-Za-z'\-]+)", post)
    if mf and not STATUS_TOKEN.match(mf.group(1)):
        return False
    return True


def el_player_layer(games, rosters, log, errors, articles=None):
    """主力名單（stars）＋傷兵（從傷兵報告文章內文與新聞標題對球員全名）＋影響分數。

    對名字的規則：全名一定對；只有姓氏的話，要姓氏夠長、全聯盟只有他一個人姓這個、而且是在傷兵報告文章或這隊自己的新聞標題裡，才算。
    傷兵報告類的文章（標題有 injury report / absences / will miss），句子裡點到名又沒說「回來了」就當缺陣。"""
    articles = articles or []
    # 全聯盟姓氏出現幾次，只出現一次的才准用姓氏對
    sur_count = {}
    for roster in rosters.values():
        for p in roster:
            k = _ascii(p["surname"]).lower()
            sur_count[k] = sur_count.get(k, 0) + 1
    art_sents = []
    for a in articles:
        implied = bool(REPORT_TITLE.search(a.get("title") or ""))
        for s in _sentences(a.get("text")):
            art_sents.append((s, implied, a, True))
    n_star = n_inj = 0
    seen_codes = set()
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
            # 要比對的句子：傷兵報告文章的每一句 + 這隊新聞標題
            sents = list(art_sents)
            for a in t.get("injury_news") or []:
                sents.append((a.get("title") or "", False, a, True))
            found = {}
            for p in roster:
                full_re = _name_regex(p["name"])
                sur = _ascii(p["surname"])
                first = _ascii(p["name"])[: -len(sur)].strip() if _ascii(p["name"]).lower().endswith(sur.lower()) else ""
                sur_ok = len(sur) >= 5 and sur_count.get(sur.lower(), 0) == 1
                sur_re = _name_regex(sur) if sur_ok else None
                for s, implied, a, sur_allowed in sents:
                    s_a = _ascii(s)
                    m = full_re.search(s_a)
                    if not m and sur_re and sur_allowed and (implied or not a.get("text")):
                        m = sur_re.search(s_a)
                        if m and not _surname_alone(s_a, m, first):
                            m = None
                    if not m:
                        continue
                    clause = next((c for c in _clauses(s_a) if m.group(0).lower() in c.lower()), s_a)
                    sev = _severity(clause, implied_out=implied)
                    if not sev:
                        continue
                    # 新的消息優先，同一天才比嚴重程度
                    key = (a.get("published") or "", SEV_RANK[sev])
                    cur = found.get(p["id"])
                    if cur is None or key > cur["_key"]:
                        status, status_zh = STATUS[sev]
                        found[p["id"]] = dict(
                            id=p["id"], player=p["name"], headshot=p.get("headshot"), position=None,
                            status=status, status_zh=status_zh, severity=sev,
                            detail=clause[:90], url=a.get("url"), source=a.get("source"), official=False,
                            ppg=p.get("ppg"), mpg=p.get("mpg"), return_date=None, comment=None, _key=key,
                        )
            if found:
                inj = list(found.values())
                for x in inj:
                    x.pop("_key", None)
                    if x["severity"] in ("out", "maybe"):
                        x["impact"] = round(impact_points(x["ppg"], x["mpg"], "el") * (0.5 if x["severity"] == "maybe" else 1), 1)
                t["injuries"] = inj
                players = [dict(player=x["player"], ppg=x["ppg"], mpg=x["mpg"], status=x["severity"], impact=x["impact"], status_zh=x["status_zh"]) for x in inj if x["severity"] in ("out", "maybe")]
                if players:
                    players.sort(key=lambda x: -x["impact"])
                    t["injury_impact"] = dict(pts=round(min(8.0, sum(p["impact"] for p in players)), 1), players=players[:4], note="從傷兵報告與新聞對到球員，依場均得分估算")
                t["injury_note"] = "沒有官方傷兵名單，這是從傷兵報告文章和新聞對出來的，賽前再確認一次"
                n_inj += 1
                if code not in seen_codes:
                    seen_codes.add(code)
                    log(f"[eurobasket] 傷兵 {t.get('name')}：" + "、".join(f"{x['player']}({x['status_zh']}｜{x['detail'][:50]})" for x in inj))
    log(f"[eurobasket] 球員層級：{n_star} 隊有主力名單，{n_inj} 隊對到傷兵（傷兵報告 {len(articles)} 篇、{len(art_sents)} 句）")
