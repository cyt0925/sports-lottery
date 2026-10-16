# -*- coding: utf-8 -*-
"""誰會上、會打多久。老球迷看傷兵不只看名單上寫什麼，還會看：

1. 備註寫什麼：ESPN 每個傷兵都有一段說明。「(rest) won't play Wednesday」是這場確定不打，
   名單上卻只標「逐日觀察」；「will play but on a minutes restriction」是會上但打不久。
   備註講的如果是別天、別的對手，那是上一場的事，這場要重新看。
2. 最近上場時間：名單寫可以打，但最近 3 場都只打平常的七成以下，等於被控制上場時間。
   差 20 分以上的大比分不算，那是垃圾時間主力本來就提早下來。
3. 背靠背輪休習慣：有些球星（像 Kawhi）背靠背第二場常常不打。看他上一季背靠背第二場缺席的比例，
   跟其他比賽比，明顯比較高的才算；連續缺好幾場的是受傷，不算輪休。

結果寫回 team["injuries"]：severity 用 out / maybe / limited / ok，另外記 p_out（不打的機率）和 limit（少打幾成）。
"""
import re
from datetime import datetime, timedelta, timezone
from statistics import mean
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = timezone.utc
SITE = "https://site.api.espn.com/apis/site/v2/sports"
WEB = "https://site.web.api.espn.com/apis/common/v3/sports"

WD = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
WD_RE = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:'s)?\b", re.I)
WD_ZH = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
REASON_RE = re.compile(r"\(([^)]{2,40})\)")
OUT_RE = re.compile(
    r"\b(won't play|will not play|won't suit up|will not suit up|won't be available|will not be available|isn't expected to play|"
    r"is not expected to play|not expected to play|has been ruled out|ruled out|is out\b|will be out|will sit|sit out|sitting out|"
    r"will miss|is set to miss|won't dress|won't travel|didn't travel|did not travel|will rest|is resting|out for|"
    r"didn't play|did not play|sat out|missed)\b", re.I)
IN_RE = re.compile(
    r"\b(will play|is available|will be available|expected to play|is expected to play|cleared to play|has been cleared|will return|"
    r"set to return|will make his (?:season )?debut|will be in the lineup|will start|is starting|plans to play|intends to play|"
    r"upgraded to available|is good to go|will suit up|is active)\b", re.I)
LIMIT_RE = re.compile(
    r"(minutes? restriction|minutes? limit|limited minutes|restricted minutes|on a restriction|minutes cap|monitor(?:ed)? (?:his )?minutes|"
    r"ramp(?:ing)? up|ramp-up|conditioning|not 100 percent|playing through|managed workload|workload)", re.I)
NO_LIMIT_RE = re.compile(r"(no|without|won't have an?|will not have an?|isn't on an?|not be on an?|free of)\s+(?:any\s+)?(?:minutes? )?(restriction|limit)", re.I)
DOUBT_RE = re.compile(r"\bdoubtful\b", re.I)
QUES_RE = re.compile(r"\b(questionable|game-time decision|uncertain|50-50|touch-and-go)\b", re.I)
PROB_RE = re.compile(r"\bprobable\b", re.I)
REST_RE = re.compile(r"\((?:rest|load management|injury management|injury maintenance)\)|\bload management\b|\bresting\b|\bwill rest\b", re.I)
OPP_RE = re.compile(r"\b(?:against|vs\.?|versus|facing|hosting|host)\s+(?:the\s+)?([A-Z][A-Za-z0-9.'-]+(?:\s+[A-Z][A-Za-z0-9.'-]+)?)")

REASON_ZH = {"rest": "輪休", "knee": "膝蓋", "ankle": "腳踝", "back": "背", "hamstring": "大腿後側", "calf": "小腿", "foot": "腳",
             "illness": "生病", "personal": "私人因素", "shoulder": "肩膀", "hip": "髖部", "groin": "鼠蹊", "wrist": "手腕",
             "hand": "手", "thumb": "拇指", "finger": "手指", "concussion": "腦震盪", "achilles": "阿基里斯腱", "toe": "腳趾",
             "quad": "大腿前側", "elbow": "手肘", "neck": "脖子", "load management": "控制負荷", "injury management": "傷勢控管"}
LIMIT_DEFAULT = 0.35     # 「限時」平常大概少打三到四成


def _reason_zh(text):
    m = REASON_RE.search(text or "")
    if not m:
        return None
    raw = m.group(1).strip().lower()
    for k, v in REASON_ZH.items():
        if k in raw:
            return v
    return None


def _dt(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except ValueError:
        return None


PAST_RE = re.compile(r"\b(didn't play|did not play|sat out|missed|was held out|didn't suit up|did not suit up|was out)\b", re.I)


def _applies(text, note_dt, game_start, opp_names):
    """備註講的是不是「這一場」。回傳 (是不是, 講的是哪場, 那場在這場之前還是之後)。"""
    ge = game_start.astimezone(ET)
    if note_dt and game_start - note_dt > timedelta(days=6):
        return False, "很多天前的消息", "past"
    days = [WD[x.lower()] for x in WD_RE.findall(text or "")]
    if days and days[0] != ge.weekday():
        label = f"{WD_ZH[days[0]]}那場"
        if PAST_RE.search(text or ""):
            return False, label, "past"
        # 「won't play Saturday」：從發消息那天往後找最近的星期六，再跟這場比
        base = (note_dt or game_start).astimezone(ET).date()
        delta = (days[0] - base.weekday()) % 7
        when = base + timedelta(days=delta)
        return False, label, ("future" if when > ge.date() else "past")
    mo = OPP_RE.search(text or "")
    if mo and opp_names:
        nm = mo.group(1).lower()
        if not any(o and (o in nm or nm in o) for o in opp_names):
            return False, f"對{mo.group(1)}那場", ("past" if PAST_RE.search(text or "") else "other")
    if not days and note_dt and game_start - note_dt > timedelta(hours=48):
        return False, "兩天前的消息", "past"
    return True, None, None


def read_note(inj, game_start, opp_names):
    """把一則傷兵備註讀成：這場打不打、會不會限時。"""
    text = inj.get("comment") or ""
    if not text:
        return None
    rest = bool(REST_RE.search(text))
    if OUT_RE.search(text):
        kind = "out"
    elif LIMIT_RE.search(text) and not NO_LIMIT_RE.search(text):
        kind = "limited"
    elif IN_RE.search(text):
        kind = "in"
    elif DOUBT_RE.search(text):
        kind = "doubtful"
    elif QUES_RE.search(text):
        kind = "questionable"
    elif PROB_RE.search(text):
        kind = "probable"
    else:
        return None
    applies, other, when = _applies(text, _dt(inj.get("date")), game_start, opp_names)
    return dict(kind=kind, applies=applies, other=other, when=when, rest=rest, reason=_reason_zh(text))


def apply_notes(g, log=None):
    """讀這場兩隊每個傷兵的備註，改寫 severity / 狀態 / 不打的機率。"""
    start = _dt(g.get("start"))
    if not start:
        return 0
    n = 0
    for side, other in (("home", "away"), ("away", "home")):
        t, o = g[side], g[other]
        opp_names = [x.lower() for x in (o.get("short"), o.get("name"), o.get("abbr"), (o.get("name") or "").split(" ")[-1]) if x]
        for x in t.get("injuries") or []:
            x.setdefault("sev0", x.get("severity"))
            r = read_note(x, start, opp_names)
            if not r:
                continue
            x["note"] = r
            why_rest = "球隊讓他休息" if r["rest"] else (f"{r['reason']}有傷" if r["reason"] else None)
            if r["kind"] == "out" and r["applies"]:
                x.update(severity="out", p_out=1.0, status_zh="這場輪休" if r["rest"] else "這場不打",
                         why=(why_rest + "，這場確定不打") if why_rest else "備註寫這場不打")
            elif r["kind"] == "out":
                # 講的是別場：輪休不會延續，這場大概會打；受傷的就還要看
                hurt = r["reason"] or "傷"
                if r["rest"] and r["when"] == "future":
                    x.update(severity="maybe", p_out=0.15, status_zh="下一場輪休", why=f"球隊排他{r['other']}休息，這場應該會打")
                elif r["rest"]:
                    x.update(severity="maybe", p_out=0.15, status_zh="上一場輪休", why=f"{r['other']}輪休，這場應該會回來")
                elif r["when"] == "future":
                    x.update(severity="maybe", p_out=0.7, status_zh="很可能不打", why=f"{hurt}的關係，連{r['other']}都說不會打，這場也很可能不打")
                else:
                    x.update(severity="maybe", p_out=0.5, status_zh="上一場沒打", why=f"{r['other']}因為{hurt}沒打，這場還要看")
            elif r["kind"] == "limited":
                x.update(severity="limited", p_out=0.0, limit=LIMIT_DEFAULT, status_zh="會上但限時",
                         why="球隊在控制他的上場時間" + (f"（{r['reason']}）" if r["reason"] else ""))
            elif r["kind"] == "in" and r["applies"]:
                x.update(severity="ok", p_out=0.0, status_zh="會上場", why="備註寫這場會打")
            elif r["kind"] == "doubtful":
                x.update(severity="maybe", p_out=0.75, status_zh="很可能不打", why="備註寫很可能缺陣")
            elif r["kind"] == "questionable":
                x.update(severity="maybe", p_out=0.5, status_zh="不確定", why="要等賽前才知道")
            elif r["kind"] == "probable":
                x.update(severity="maybe", p_out=0.15, status_zh="應該會打", why="備註寫應該會打")
            n += 1
    return n


def merge_minutes(t, log=None):
    """主力最近 3 場上場時間掉到平常七成五以下：名單寫可以打也當成限時。"""
    n = 0
    have = {str(x.get("id")): x for x in t.get("injuries") or [] if x.get("id")}
    for p in t.get("hot") or []:
        last3, base = p.get("min_last3"), p.get("min_base")
        if not last3 or not base or base < 24 or last3 > base * 0.75:
            continue
        lim = round(min(0.6, max(0.15, 1 - last3 / base)), 2)
        why = f"最近 3 場平均只打 {last3:.0f} 分鐘，之前平均 {base:.0f} 分鐘"
        x = have.get(str(p["id"]))
        if x:
            if x.get("severity") in ("out", "ir"):
                continue
            x.update(severity="limited", limit=max(lim, x.get("limit") or 0), status_zh="上場時間被控制", why=why, min_last3=last3, min_base=base)
        else:
            t.setdefault("injuries", []).append(dict(
                id=str(p["id"]), player=p["player"], headshot=p.get("headshot"), position=p.get("position"), position_zh=None,
                status="Minutes", status_zh="上場時間被控制", severity="limited", sev0="ok", p_out=0.0, limit=lim,
                detail=None, side=None, return_date=None, comment=None, date=None, official=False, why=why,
                min_last3=last3, min_base=base,
            ))
        n += 1
    return n


# ---------- 背靠背輪休習慣 ----------
_CACHE = {}


def _team_schedule(get, path, tid, season):
    key = ("sched", path, tid, season)
    if key not in _CACHE:
        d = get(f"{SITE}/{path}/teams/{tid}/schedule", params={"season": season, "seasontype": 2}, quiet=True)
        evs = []
        for ev in (d or {}).get("events") or []:
            comp = (ev.get("competitions") or [{}])[0]
            st = ((comp.get("status") or ev.get("status") or {}).get("type") or {})
            if not st.get("completed"):
                continue
            dt = _dt(comp.get("date") or ev.get("date"))
            if dt:
                evs.append(dict(id=str(ev.get("id")), dt=dt, comp=comp))
        evs.sort(key=lambda e: e["dt"])
        _CACHE[key] = evs
    return _CACHE[key]


def _player_games(get, path, pid, season):
    """上一季例行賽他打了哪些比賽（ESPN 的 event id）、幫哪一隊打。"""
    key = ("log", path, pid, season)
    if key not in _CACHE:
        d = get(f"{WEB}/{path}/athletes/{pid}/gamelog", params={"season": season}, quiet=True)
        played, teams = set(), {}
        meta = (d or {}).get("events") or {}
        for st in (d or {}).get("seasonTypes") or []:
            name = st.get("displayName") or ""
            if "Regular Season" not in name or "Play In" in name:
                continue
            for cat in st.get("categories") or []:
                for e in cat.get("events") or []:
                    eid = str(e.get("eventId"))
                    played.add(eid)
                    m = meta.get(eid) or {}
                    tid = m.get("homeTeamId") if m.get("atVs") == "vs" else m.get("awayTeamId")
                    if tid:
                        teams[str(tid)] = teams.get(str(tid), 0) + 1
        _CACHE[key] = (played, teams)
    return _CACHE[key]


def b2b_habit(get, path, pid, season):
    """上一季：背靠背第二場缺席率 vs 其他比賽缺席率。連續缺 5 場以上的段落當受傷，不算。"""
    played, teams = _player_games(get, path, pid, season)
    if len(played) < 15 or not teams:
        return None
    tid = max(teams, key=teams.get)
    evs = _team_schedule(get, path, tid, season)
    if len(evs) < 30:
        return None
    # 只看他在這隊的那段時間
    idx = [i for i, e in enumerate(evs) if e["id"] in played]
    if not idx:
        return None
    evs = evs[idx[0]: idx[-1] + 1]
    miss = [e["id"] not in played for e in evs]
    # 連續缺 5 場以上 = 受傷，整段拿掉
    keep = [True] * len(evs)
    i = 0
    while i < len(evs):
        if miss[i]:
            j = i
            while j < len(evs) and miss[j]:
                j += 1
            if j - i >= 5:
                for k in range(i, j):
                    keep[k] = False
            i = j
        else:
            i += 1
    b2b_n = b2b_m = other_n = other_m = 0
    for k in range(1, len(evs)):
        if not keep[k]:
            continue
        second = (evs[k]["dt"] - evs[k - 1]["dt"]) < timedelta(hours=30)
        if second:
            b2b_n += 1
            b2b_m += miss[k]
        else:
            other_n += 1
            other_m += miss[k]
    if b2b_n < 5 or other_n < 10:
        return None
    return dict(b2b_n=b2b_n, b2b_miss=b2b_m, other_n=other_n, other_miss=other_m,
                rate_b2b=round(b2b_m / b2b_n, 2), rate_other=round(other_m / other_n, 2), season=season)


def apply_b2b(g, lg, get, season_prev, log=None):
    """今天是背靠背第二場的隊伍：看主力上季背靠背的缺席習慣。"""
    rest = (g.get("analysis") or {}).get("rest") or {}
    n = 0
    for side in ("home", "away"):
        r = rest.get(side) if isinstance(rest, dict) else None
        if not r or not r.get("b2b"):
            continue
        t = g[side]
        have = {str(x.get("id")): x for x in t.get("injuries") or [] if x.get("id")}
        for p in (t.get("leaders") or [])[:3]:
            pid = str(p.get("id") or "")
            if not pid or (have.get(pid) and have[pid].get("severity") in ("out", "ir")):
                continue
            h = b2b_habit(get, lg["path"], pid, season_prev)
            if not h or h["rate_b2b"] < 0.4 or h["rate_b2b"] - h["rate_other"] < 0.25:
                continue
            why = f"上季背靠背第二場 {h['b2b_n']} 場缺了 {h['b2b_miss']} 場，其他比賽只缺 {round(h['rate_other'] * 100)}%"
            p_out = round(min(0.8, h["rate_b2b"]), 2)
            x = have.get(pid)
            if x:
                x.update(severity="maybe", p_out=max(p_out, x.get("p_out") or 0), status_zh="背靠背常輪休", why=why, b2b=h)
            else:
                t.setdefault("injuries", []).append(dict(
                    id=pid, player=p.get("player"), headshot=p.get("headshot"), position=p.get("position"), position_zh=None,
                    status="Rest risk", status_zh="背靠背常輪休", severity="maybe", sev0="ok", p_out=p_out,
                    detail=None, side=None, return_date=None, comment=None, date=None, official=False, why=why, b2b=h,
                ))
            n += 1
            if log:
                log(f"[{lg['key']}] 背靠背輪休習慣 {p.get('player')}：{why}")
    return n
