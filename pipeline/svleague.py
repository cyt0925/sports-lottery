# -*- coding: utf-8 -*-
"""SV.LEAGUE（日本排球）官方網站：首頁與男女子賽程頁的伺服器端 HTML。
沒有盤口（台灣運彩與玩運彩都沒有日本排球），所以只有賽程、比分、近況、自己算的排名。"""
import re
import time
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from taiwan_odds import fetch, TW

SITE = "https://www.svleague.jp"
JST = timezone(timedelta(hours=9))
UTC = timezone.utc
PAGES = [("/", None), ("/match/sv/men/", "男"), ("/match/sv/women/", "女")]
DEBUG = {}

# 官網簡稱 -> 中文（看得懂的漢字就照用）
ZH = {
    "サントリー": "三得利太陽鳥大阪", "大阪B": "大阪布魯提翁", "WD名古屋": "名古屋狼犬", "愛知": "愛知捷太格特",
    "東レ静岡": "東麗箭靜岡", "東京GB": "東京大熊", "広島": "廣島雷霆", "堺": "堺火焰", "長野": "長野三叉戟",
    "北海道": "北海道沃雷亞斯", "日鉄堺": "堺火焰", "ジェイテクト": "愛知捷太格特", "大阪": "大阪",
    "NEC川崎": "NEC紅火箭川崎", "大阪MV": "大阪奇蹟", "東レ滋賀": "東麗箭滋賀", "埼玉上尾": "埼玉上尾", "デンソー": "電裝空中蜜蜂",
    "SAGA久光": "佐賀久光泉水", "姫路": "姬路勝利女神", "刈谷": "刈谷皇后", "PFU": "PFU藍貓石川", "岡山": "岡山海鷗",
    "KUROBE": "黑部水精靈", "日立": "日立Astemo茨城", "群馬": "群馬綠翼", "A山形": "山形阿蘭瑪蕾", "A愛知": "愛知",
}


def _season_year(now):
    return now.year if now.month >= 7 else now.year - 1


def _team(li, code_from_img):
    img = li.find("img")
    logo = None
    code = None
    if img and img.get("src"):
        logo = img["src"] if img["src"].startswith("http") else SITE + img["src"]
        m = re.search(r"/team/([^/]+)/", img["src"])
        code = m.group(1) if m else None
    span = li.find("span")
    score = span.get_text(strip=True) if span else None
    name = li.get_text(" ", strip=True)
    if score:
        name = name.replace(score, "").strip()
    name = re.sub(r"\s+", "", name)
    return dict(code=code or code_from_img or name, name=name, logo=logo, score=score)


def parse_page(text, gender_hint, now):
    """回傳 [(gender, date(JST), time_text, status_text, home, away)]。"""
    soup = BeautifulSoup(text, "html.parser")
    out = []
    year0 = _season_year(now)
    slides = [s for s in soup.find_all(class_=re.compile(r"\bswiper-slide\b")) if s.find(class_="match")]
    last_date = {}
    for s in slides:
        gender = gender_hint
        if not gender:
            em = s.find_previous(lambda tag: tag.name == "em" and tag.get_text(strip=True).upper() in ("MEN", "WOMEN"))
            gender = "男" if em is not None and em.get_text(strip=True).upper() == "MEN" else "女" if em is not None else None
        if not gender:
            continue
        strong = s.find("strong")
        em_d = strong.find("em") if strong else None
        if em_d:
            m = re.match(r"(\d{1,2})\.(\d{1,2})", em_d.get_text(strip=True))
            if m:
                mon, day = int(m.group(1)), int(m.group(2))
                last_date[gender] = (year0 if mon >= 7 else year0 + 1, mon, day)
        d = last_date.get(gender)
        if not d:
            continue
        field = s.find(class_="field")
        p = field.find("p") if field else s.find("p")
        status = p.get_text(" ", strip=True) if p else ""
        lis = s.find(class_="match").find_all("li")
        if len(lis) < 2:
            continue
        home, away = _team(lis[0], None), _team(lis[1], None)
        out.append(dict(gender=gender, date=d, status=status, home=home, away=away))
    return out


def _state(row, start_jst, now):
    st = row["status"]
    if "終了" in st:
        return "post", "已結束", True
    if "中止" in st or "延期" in st:
        return "post", st, False
    if now >= start_jst + timedelta(hours=3):
        return "post", "已結束（比分待更新）", True
    if now >= start_jst or "セット" in st or "試合中" in st:
        return "in", st if st and not re.match(r"^\d{1,2}:\d{2}$", st) else "進行中", False
    return "pre", "未開賽", False


def fetch_games(lg, log, errors, now=None):
    now = now or datetime.now(JST)
    now = now.astimezone(JST)
    rows_all = []
    for path, gender in PAGES:
        text = fetch(SITE + path)
        if not text:
            errors.append(f"日排 SV.LEAGUE {path} 抓不到")
            continue
        try:
            rows = parse_page(text, gender, now)
        except Exception as e:  # noqa: BLE001
            errors.append(f"日排 SV.LEAGUE {path} 解析失敗: {e!r}")
            rows = []
        log(f"[jpvolley] {path} 解析到 {len(rows)} 場")
        if path != "/" and f"raw{path}" not in DEBUG:
            i = text.find("試合終了")
            if i < 0:
                i = text.find('class="match"')
            if i < 0:
                m = re.search(r"<main.*?(\d{1,2}\.\d{1,2})", text, re.S)
                i = m.start(1) if m else -1
            if i < 0:
                m = re.search(r"(10|11|12|0?[1-9])月\s*\d{1,2}日|\d{1,2}/\d{1,2}", text)
                i = m.start() if m else -1
            classes = sorted(set(re.findall(r'class="([^"]+)"', text)))
            hot = [c for c in classes if re.search(r"match|game|result|schedule|table|score|list|item|card|day", c, re.I)]
            DEBUG[f"raw{path}"] = (re.sub(r"\s+", " ", text[max(0, i - 600): i + 1400]) if i >= 0 else f"len={len(text)} 找不到日期") + " ||| classes: " + ", ".join(hot[:60])
        rows_all.extend(rows)
        time.sleep(0.4)
    # 去重：同性別、同日、同兩隊
    seen = {}
    for r in rows_all:
        key = (r["gender"], r["date"], r["home"]["code"], r["away"]["code"])
        if key not in seen or ("終了" in r["status"] and "終了" not in seen[key]["status"]):
            seen[key] = r
    rows_all = list(seen.values())
    games, results = [], []
    for r in rows_all:
        y, mo, d = r["date"]
        mt = re.match(r"(\d{1,2}):(\d{2})", r["status"])
        hh, mm = (int(mt.group(1)), int(mt.group(2))) if mt else (13, 0)
        try:
            start_jst = datetime(y, mo, d, hh, mm, tzinfo=JST)
        except ValueError:
            continue
        state, detail, completed = _state(r, start_jst, now)
        if state == "post" and r["home"]["score"] and r["away"]["score"]:
            try:
                hs, as_ = int(r["home"]["score"]), int(r["away"]["score"])
                results.append(dict(gender=r["gender"], start=start_jst, home=r["home"], away=r["away"], hs=hs, as_=as_))
            except ValueError:
                pass
        start_utc = start_jst.astimezone(UTC)
        start_tw = start_jst.astimezone(TW)
        def team(t, score):
            name_zh = ZH.get(t["name"], t["name"])
            return dict(
                id=f"sv-{t['code']}", sv_code=t["code"], abbr=t["name"][:6], name=t["name"], short=t["name"], name_zh=name_zh,
                jp_name=t["name"], logo=t["logo"], color=None, record=None, record_home=None, record_away=None,
                score=score if state != "pre" else None, winner=False, form_str=None, leaders=[], injuries=[], key_out=[], key_maybe=[],
                out_count=0, maybe_count=0, hot=[], form=[], form_note=None, streak=None, last10=None, last10_w=0,
                avg_for5=None, avg_against5=None, avg_total5=None, avg_margin5=None,
            )
        home, away = team(r["home"], r["home"]["score"]), team(r["away"], r["away"]["score"])
        if state == "post" and home["score"] and away["score"]:
            try:
                home["winner"] = int(home["score"]) > int(away["score"])
                away["winner"] = int(away["score"]) > int(home["score"])
            except ValueError:
                pass
        games.append(dict(
            id=f"sv{r['gender']}{y}{mo:02d}{d:02d}-{r['home']['code']}-{r['away']['code']}",
            league=lg["key"], league_zh=lg["label"], sport=lg["sport"], chip=lg["key"], tennis=False, tournament=None,
            round=f"{r['gender']}子", comp=f"SV.LEAGUE {r['gender']}子", gender=r["gender"],
            name=f"{away['name']} @ {home['name']}",
            start=start_utc.isoformat(timespec="minutes"), start_tw=start_tw.isoformat(timespec="minutes"),
            day_tw=start_tw.strftime("%Y-%m-%d"), time_tw=start_tw.strftime("%H:%M"),
            status=dict(state=state, completed=completed, detail=detail, clock=None, period=None),
            venue=None, broadcast=None, home=home, away=away, odds=None, headline=None, news=[], suggestion=None,
            analysis={}, sets=True,
        ))
    # 近況與排名（從抓到的結果算）
    form = {}
    for x in sorted(results, key=lambda x: x["start"]):
        for me, opp, home_flag, pf, pa in ((x["home"], x["away"], True, x["hs"], x["as_"]), (x["away"], x["home"], False, x["as_"], x["hs"])):
            form.setdefault((x["gender"], me["code"]), []).append(dict(
                date=x["start"].astimezone(TW).strftime("%m/%d"), date_iso=x["start"].astimezone(UTC).isoformat(timespec="minutes"),
                ts=x["start"].timestamp(), opp=opp["name"], opp_zh=ZH.get(opp["name"], opp["name"]), opp_logo=opp["logo"],
                home=home_flag, pf=pf, pa=pa, result="W" if pf > pa else "L", comp=None,
            ))
    from playsport import summarize_form
    for g in games:
        for side in ("home", "away"):
            t = g[side]
            rows = [dict(r) for r in form.get((g["gender"], t["sv_code"])) or []]
            if rows:
                summarize_form(t, rows, note="SV.LEAGUE 官網賽果（局數）")
                t["record_note"] = "本站抓到的比賽"
                t["avg_for5"] = t["avg_against5"] = t["avg_total5"] = t["avg_margin5"] = None
    standings = {}
    for (gender, code), rows in form.items():
        w = sum(1 for r in rows if r["result"] == "W")
        l = len(rows) - w
        sw = sum(r["pf"] for r in rows)
        sl = sum(r["pa"] for r in rows)
        name = next((t["name"] for g in games for t in (g["home"], g["away"]) if t["sv_code"] == code), code)
        logo = next((t["logo"] for g in games for t in (g["home"], g["away"]) if t["sv_code"] == code), None)
        standings.setdefault(gender, []).append(dict(
            team_id=code, team=name, abbr=name, name_zh=ZH.get(name, name), logo=logo, w=w, l=l, d=None, otl=None,
            pct=f"{w / (w + l):.3f}".lstrip("0") if w + l else "", gb=None, streak=None, points=None, gp=w + l, rank=None,
            sets=f"{sw}-{sl}",
        ))
    groups = []
    for gender in ("男", "女"):
        rows = standings.get(gender) or []
        rows.sort(key=lambda r: (-(r["w"] / r["gp"] if r["gp"] else 0), -r["w"]))
        for i, r in enumerate(rows, 1):
            r["pos"] = r["rank"] = i
        if rows:
            groups.append(dict(name=f"{gender}子（依本站抓到的賽果計算，可能不完整）", rows=rows))
    log(f"[jpvolley] 賽事 {len(games)} 場、有比分 {len(results)} 場、排名 {sum(len(g['rows']) for g in groups)} 隊")
    for k, v in DEBUG.items():
        log(f"[jpvolley] 原始樣本 {k}: {v[:1500]}")
    return games, (dict(groups=groups) if groups else None)
