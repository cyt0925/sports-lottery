# -*- coding: utf-8 -*-
"""日籃、日排的球員層級：官網名單（日籃有場均得分）＋日文新聞標題對球員全名。

日文新聞標題幾乎都直接寫全名（「富樫勇樹が欠場」），所以對名字比歐籃準；
外籍球員用片假名，有時只寫姓（「ホーキンソン」），全聯盟只有一個人這樣叫才算。
日排沒有讓分盤、也沒有「少他差幾分」的算法，只標「誰缺陣」。"""
import re
import time
import unicodedata

from bs4 import BeautifulSoup

from taiwan_odds import fetch

# 日文傷兵用語
STRONG_OUT = re.compile(r"欠場|離脱|手術|全治|戦線離脱|登録抹消|帯同せず|長期|今季絶望|シーズン絶望|欠く")
OUT_JA = re.compile(r"負傷|怪我|ケガ|故障|骨折|捻挫|肉離れ|痛め|違和感|脳震盪|不在")
MAYBE_JA = re.compile(r"出場未定|状態次第|不透明|様子見|調整中|微妙|見合わせ|慎重|注目")
BACK_JA = re.compile(r"復帰|戻る|合流|出場可能|復活|再開|練習参加|帯同")
BACK_NOT = re.compile(r"未定|時期|へ|目指|目標|見込|めど|メド|予定|まで|には|か\?|いつ")
JP_CHAR = r"一-龥ぁ-んァ-ヶー々"


LIMIT_JA = re.compile(r"出場時間制限|プレータイム制限|強行出場|痛みを抱え|痛みに耐え|万全ではない|万全でない|テーピング|コンディション不良|調整しながら")


def severity_ja(title):
    """標題看狀態：先看最強的字（欠場／離脱／手術），再看帶傷上場，最後看「復帰」是真的回來還是「復帰へ」還沒。"""
    t = title or ""
    if STRONG_OUT.search(t):
        return "out"
    if LIMIT_JA.search(t):
        return "limited"
    if BACK_JA.search(t):
        return "ok" if not BACK_NOT.search(t) else "maybe"
    if MAYBE_JA.search(t):
        return "maybe"
    if OUT_JA.search(t):
        return "out"
    return None


def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"[\s　・･\-–—]", "", s)


def split_name(raw):
    """'富樫 勇樹' -> ('富樫勇樹', '富樫')；'キヨンテ・ジョンソン' -> ('キヨンテジョンソン', 'ジョンソン')。"""
    raw = unicodedata.normalize("NFKC", (raw or "").strip())
    full = norm(raw)
    if re.search(r"[ァ-ヶー]", raw) and not re.search(r"[一-龥]", raw):
        parts = [p for p in re.split(r"[・･\s]+", raw) if p]
        sur = parts[-1] if parts else raw
    else:
        parts = [p for p in re.split(r"\s+", raw) if p]
        sur = parts[0] if parts else raw
    return full, norm(sur)


def _boundary(text, m):
    pre = text[m.start() - 1] if m.start() > 0 else ""
    post = text[m.end()] if m.end() < len(text) else ""
    return not re.match(f"[{JP_CHAR}]", pre or " ") and not re.match(f"[{JP_CHAR}]", post or " ")


def match_players(roster, titles, sur_count):
    """roster: [{name, full, surname, ...}]；titles: [{title, url, source, published}] → {id: injury dict}"""
    found = {}
    for a in titles:
        t_raw = a.get("title") or ""
        t = norm(t_raw)
        sev = severity_ja(t_raw)
        if not sev:
            continue
        for p in roster:
            hit = None
            if p["full"] and p["full"] in t:
                hit = True
            elif len(p["surname"]) >= 2 and sur_count.get(p["surname"], 0) == 1:
                m = re.search(re.escape(p["surname"]), t)
                if m and _boundary(t, m) and (len(p["surname"]) >= 3 or re.search(r"[一-龥]", p["surname"])):
                    hit = True
            if not hit:
                continue
            key = (a.get("published") or "", {"out": 3, "maybe": 2, "limited": 1, "ok": 0}[sev])
            cur = found.get(p["id"])
            if cur is None or key > cur["_key"]:
                found[p["id"]] = dict(
                    id=p["id"], player=p["name"], headshot=p.get("headshot"), position=p.get("position"), position_zh=None,
                    status={"out": "Out", "maybe": "Doubtful", "limited": "Limited", "ok": "Available"}[sev],
                    status_zh={"out": "缺陣", "maybe": "存疑", "limited": "帶傷上、可能限時", "ok": "回歸"}[sev], severity=sev,
                    detail=t_raw[:80], url=a.get("url"), source=a.get("source"), official=False,
                    ppg=p.get("ppg"), mpg=p.get("mpg"), return_date=None, comment=None, _key=key,
                )
    for x in found.values():
        x.pop("_key", None)
    return list(found.values())


# ---------- B.LEAGUE ----------
BL = "https://www.bleague.jp"
POS_ZH_BL = {"PG": "控球", "SG": "得分後衛", "SF": "小前鋒", "PF": "大前鋒", "C": "中鋒", "G": "後衛", "F": "前鋒"}


def _num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _mmss(s):
    m = re.match(r"^(\d+):(\d{2})$", str(s or "").strip())
    return round(int(m.group(1)) + int(m.group(2)) / 60, 1) if m else _num(s)


def parse_bleague_club(html, team_id=None):
    """球隊頁的 table.table-player（平均）：第二列表頭是英文代碼（PLAYER / PO / G / MINPG / PPG…），用它找欄位。
    回傳 [{id, name, position, number, gp, mpg, ppg, headshot}]。"""
    soup = BeautifulSoup(html, "html.parser")
    shots = {}
    for m in re.finditer(r"(https://[^\"'\s]*?/roster/\d+/[^\"'\s]*?/(\d+)_\d+\.png)", html):
        shots.setdefault(m.group(2), m.group(1))
    players = []
    for tb in soup.find_all("table", class_=re.compile(r"table-player")):
        code_row = None
        for tr in tb.find_all("tr"):
            ths = [th.get_text(" ", strip=True) for th in tr.find_all("th")]
            if "PPG" in ths and ("G" in ths or "GP" in ths):
                code_row = ths
                break
        if not code_row:
            continue
        code_idx = {c: i for i, c in enumerate(code_row)}
        # 背號那欄在第一層表頭（rowspan），英文代碼那列從 PLAYER 開始；所以用「相對於名字那格」的位移找欄位
        rel = {c: i - code_idx.get("PLAYER", 0) for c, i in code_idx.items()}
        for tr in tb.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 6:
                continue
            texts = [td.get_text(" ", strip=True) for td in tds]
            a = tr.find("a", href=re.compile(r"PlayerID=(\d+)"))
            pid = re.search(r"PlayerID=(\d+)", a["href"]).group(1) if a else None
            i_name = next((i for i, td in enumerate(tds) if td.find("a", href=re.compile("PlayerID"))), None)
            if not pid or i_name is None:
                continue
            name = texts[i_name]

            def col(code):
                j = i_name + rel[code] if code in rel else None
                return texts[j] if j is not None and 0 <= j < len(texts) else None
            season = col("SEASON") or ""
            rec = dict(
                id=pid, name=name, number=texts[0] if texts[0].isdigit() else None,
                position=col("PO"), gp=_num(col("G") if "G" in rel else col("GP")),
                mpg=_mmss(col("MINPG")), ppg=_num(col("PPG")), season=season, headshot=shots.get(pid),
                rpg=_num(col("RPG") or col("TRPG")), apg=_num(col("APG")),
            )
            if rec["position"]:
                rec["position_zh"] = "/".join(POS_ZH_BL.get(x, x) for x in rec["position"].split("/"))
            # 同一個人可能有多列（不同大會／賽季）：留本季聯賽那列，否則留第一列
            cur = next((p for p in players if p["id"] == pid), None)
            if cur is None:
                players.append(rec)
            elif (col("TYPE") or "") in ("BP", "B1") and (rec["gp"] or 0) >= (cur["gp"] or 0):
                players[players.index(cur)] = rec
        if players:
            break
    return players


def bleague_rosters(team_ids, log, errors):
    """{bl_id: [player...]}，從各球隊頁抓。"""
    out = {}
    for tid in team_ids:
        if not tid:
            continue
        html = fetch(f"{BL}/club_detail/?TeamID={tid}", tries=1)
        if not html:
            errors.append(f"日籃 球隊頁 {tid} 抓不到")
            continue
        try:
            out[tid] = parse_bleague_club(html, tid)
            if not out[tid]:
                i = html.find("table-player")
                log(f"[jpbasket] 球隊頁 {tid} 沒解析到球員；片段：" + re.sub(r"\s+", " ", html[max(0, i - 200): i + 1200]))
        except Exception as e:  # noqa: BLE001
            errors.append(f"日籃 球隊頁 {tid} 解析失敗: {e!r}")
        time.sleep(0.4)
    log(f"[jpbasket] 球員名單：{sum(1 for v in out.values() if v)}/{len([t for t in team_ids if t])} 隊，共 {sum(len(v) for v in out.values())} 人")
    return out


# ---------- SV.LEAGUE ----------
SV = "https://www.svleague.jp"
POS_ZH_SV = {"Outside Hitter": "主攻", "Opposite Hitter": "接應", "Middle Blocker": "攔中", "Setter": "舉球", "Libero": "自由球員"}


def parse_sv_roster(html):
    """球隊選手頁：div.player ul.list li > a[href=/player/detail/?id=N]（b 背號、strong 日文名、em 羅馬拼音、p 位置）。"""
    soup = BeautifulSoup(html, "html.parser")
    players = []
    for a in soup.select("a[href*='/player/detail/']"):
        strong = a.find("strong")
        name = strong.get_text(" ", strip=True) if strong else a.get_text(" ", strip=True)
        if not name or len(name) > 24:
            continue
        m = re.search(r"id=(\d+)", a["href"])
        pos_el = a.find("p")
        pos = pos_el.get_text(" ", strip=True) if pos_el else None
        num_el = a.find("b")
        em = a.find("em")
        li = a.find_parent("li")
        players.append(dict(
            id=m.group(1) if m else a["href"], name=name, romaji=em.get_text(" ", strip=True) if em else None,
            number=num_el.get_text(strip=True) if num_el else None, position=pos, position_zh=POS_ZH_SV.get(pos or "", pos),
            captain=bool(li is not None and "cap" in (li.get("class") or [])), headshot=None, ppg=None, mpg=None, gp=None,
        ))
    return players


def sv_rosters(codes, log, errors):
    out = {}
    miss = 0
    for code in codes:
        if not code or code in out:
            continue
        if miss >= 4:           # 連續 4 隊抓不到：網站在擋或掛了，這次先不抓
            out[code] = []
            continue
        html = fetch(f"{SV}/team/{code}/player/", tries=1)
        if not html:
            miss += 1
            errors.append(f"日排 選手頁 {code} 抓不到")
            continue
        miss = 0
        try:
            out[code] = parse_sv_roster(html)
        except Exception as e:  # noqa: BLE001
            errors.append(f"日排 選手頁 {code} 解析失敗: {e!r}")
        time.sleep(0.4)
    log(f"[jpvolley] 球員名單：{sum(1 for v in out.values() if v)}/{len([c for c in codes if c])} 隊，共 {sum(len(v) for v in out.values())} 人")
    return out


# ---------- 共用：掛到比賽上 ----------
def _prep(roster):
    out = []
    for p in roster:
        full, sur = split_name(p["name"])
        out.append(dict(p, full=full, surname=sur))
    return out


def player_layer(games, rosters, key_attr, log, errors, label, impact_scale=None):
    """rosters: {team_key: roster}；key_attr: 球隊 dict 上的鍵（bl_id / sv_code）。
    掛上 t["stars"]（日籃：場均前 4）、t["injuries"]、t["injury_impact"]（日籃）。"""
    from players import impact_points
    prepped = {k: _prep(v) for k, v in rosters.items() if v}
    sur_count = {}
    for roster in prepped.values():
        for p in roster:
            sur_count[p["surname"]] = sur_count.get(p["surname"], 0) + 1
    n_star = n_inj = 0
    for g in games:
        for side in ("home", "away"):
            t = g[side]
            roster = prepped.get(t.get(key_attr))
            if not roster:
                continue
            if any(p.get("ppg") is not None for p in roster):
                top = sorted([p for p in roster if (p.get("gp") or 0) > 0], key=lambda p: -(p.get("ppg") or 0))[:4]
                t["stars"] = [dict(id=p["id"], player=p["name"], headshot=p.get("headshot"), ppg=p.get("ppg"), mpg=p.get("mpg"), position=p.get("position"),
                                   rpg=p.get("rpg"), apg=p.get("apg"), gp=p.get("gp")) for p in top]
                t["leaders"] = [dict(id=p["id"], player=p["name"], headshot=p.get("headshot"), position=p.get("position"), stat="PTS", value=str(p.get("ppg"))) for p in top[:3]]
                n_star += 1
            inj = match_players(roster, t.get("injury_news") or [], sur_count)
            if not inj:
                continue
            for x in inj:
                p = next((q for q in roster if q["id"] == x["id"]), {})
                x["position_zh"] = p.get("position_zh")
                x["key"] = bool(p.get("captain")) or (p.get("position") in ("Outside Hitter", "Opposite Hitter", "Setter"))
            for x in inj:
                x["sev0"] = x["severity"] if x["severity"] != "limited" else "ok"
                if x["severity"] == "limited":
                    x.update(limit=0.3, why="新聞說他帶傷上或會限時")
            t["injuries"] = inj
            if impact_scale:
                from players import team_impact
                imp = team_impact(t, impact_scale)
                if imp and imp["players"]:
                    imp["note"] = "從日文新聞對到球員，依場均得分估算；帶傷上場只算少打的那幾成"
                    t["injury_impact"] = imp
            if not impact_scale:
                t["key_out"] = [x["player"] for x in inj if x["severity"] == "out" and x.get("key")]
                t["key_maybe"] = [x["player"] for x in inj if x["severity"] in ("maybe", "limited") and x.get("key")]
            t["injury_note"] = "沒有官方傷兵名單，這是從日文新聞標題對出來的，賽前再確認一次"
            n_inj += 1
            log(f"[{label}] 傷兵 {t.get('jp_name') or t.get('name')}：" + "、".join(f"{x['player']}({x['status_zh']}｜{x['detail'][:40]})" for x in inj))
    log(f"[{label}] 球員層級：{n_star} 隊有主力名單，{n_inj} 隊從新聞對到傷兵")
    return n_inj


def validate(label, teams, log, errors, days=14):
    """窗口內沒比賽時也跑一次：拿幾隊的名單去對最近兩週的日文新聞，看對不對得到（只寫 log）。"""
    import newsinj
    prepped = {k: _prep(v) for k, v in teams.items() if v}
    sur_count = {}
    for roster in prepped.values():
        for p in roster:
            sur_count[p["surname"]] = sur_count.get(p["surname"], 0) + 1
    for name, roster in prepped.items():
        try:
            items = newsinj.injury_news(name, "ja", days=days, limit=5, hint="")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{label} 驗證新聞 {name} 失敗: {e!r}")
            continue
        inj = match_players(roster, items, sur_count)
        log(f"[{label}] 驗證 {name}：名單 {len(roster)} 人（例：{'、'.join(p['name'] for p in roster[:3])}）；傷兵新聞 {len(items)} 則（{'；'.join((x.get('title') or '')[:30] for x in items[:3])}）；對到 "
            + ("、".join(f"{x['player']}({x['status_zh']})" for x in inj) if inj else "0 人"))
