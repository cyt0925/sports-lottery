# -*- coding: utf-8 -*-
"""CBA（中國男籃職業聯賽）：玩運彩（allianceid 94）給賽程、台灣盤、球隊戰績；這裡補每隊的新聞查詢名、主場城市。

  玩運彩的隊名是繁體、常常帶贊助商（廣東宏遠、遼寧本鋼），贊助商每年換，所以用城市或隊名裡不會變的字來認隊。
  新聞用大陸媒體常用的叫法查（「广东男篮」），簡體中文；AI 讀完寫成繁體。
  城市座標給「客隊要跑多遠」用：新疆飛廣東 3000 多公里，比歐洲跨國還遠。"""
from datetime import datetime, timezone

# (認隊的字（玩運彩的繁體隊名、即時比分的簡稱）, 新聞查詢名（簡體）, 標題裡算講到這隊的字（簡體）, 主場城市, 緯度, 經度)
# 同一個城市或省有兩隊的（北京首鋼、北京北控；浙江廣廈、浙江稠州），要先比對特別的字
TEAMS = [
    (("首鋼",), "北京首钢", ("首钢", "北京男篮"), "北京", 39.90, 116.40),
    (("紫禁", "勇士", "北控", "北汽", "北京勇"), "北控男篮", ("北控", "北汽", "紫禁勇士"), "北京", 39.90, 116.40),
    (("廣廈", "廣夏"), "浙江广厦", ("广厦",), "杭州", 30.27, 120.15),
    (("稠州", "金租", "金牛"), "浙江稠州", ("稠州", "浙江男篮"), "義烏", 29.31, 120.08),
    (("同曦", "頭排", "南京"), "南京同曦", ("同曦", "南京男篮", "南京头排"), "南京", 32.06, 118.80),
    (("廣東", "宏遠", "東陽光"), "广东宏远", ("广东", "宏远", "东阳光"), "東莞", 23.02, 113.75),
    (("遼寧", "本鋼"), "辽宁男篮", ("辽宁", "本钢"), "瀋陽", 41.80, 123.43),
    (("上海", "鯊魚", "久事"), "上海男篮", ("上海", "久事"), "上海", 31.23, 121.47),
    (("新疆", "伊力特", "廣匯"), "新疆男篮", ("新疆", "伊力特"), "烏魯木齊", 43.83, 87.62),
    (("山東", "高速"), "山东男篮", ("山东", "高速男篮"), "濟南", 36.65, 117.12),
    (("山西", "汾酒"), "山西男篮", ("山西", "汾酒"), "太原", 37.87, 112.55),
    (("深圳", "馬可波羅"), "深圳男篮", ("深圳", "马可波罗"), "深圳", 22.54, 114.06),
    (("廣州", "龍獅"), "广州男篮", ("广州", "龙狮"), "廣州", 23.13, 113.26),
    (("青島", "國信"), "青岛男篮", ("青岛", "国信"), "青島", 36.07, 120.38),
    (("江蘇", "肯帝亞"), "江苏男篮", ("江苏", "肯帝亚"), "蘇州", 31.30, 120.62),
    (("福建", "潯興", "鱘"), "福建男篮", ("福建", "浔兴", "鲟浔兴"), "晉江", 24.78, 118.55),
    (("天津", "先行者", "榮鋼"), "天津男篮", ("天津", "先行者", "荣钢"), "天津", 39.13, 117.20),
    (("四川", "錦城", "金強", "豐谷"), "四川男篮", ("四川", "金强", "丰谷", "锦城"), "成都", 30.66, 104.07),
    (("吉林", "農商", "九台"), "吉林男篮", ("吉林", "九台"), "長春", 43.88, 125.32),
    (("寧波", "富邦", "町渥"), "宁波男篮", ("宁波", "富邦", "町渥"), "寧波", 29.87, 121.55),
    # 只寫城市的（玩運彩偶爾只給簡稱），最後才比
    (("北京",), "北京首钢", ("首钢", "北京男篮"), "北京", 39.90, 116.40),
    (("浙江",), "浙江稠州", ("稠州", "浙江男篮"), "義烏", 29.31, 120.08),
]
# 玩運彩隊名的錯字、看起來怪的（只改顯示）
DISPLAY = {"浙江廣夏": "浙江廣廈"}
# 新浪的簡體簡稱轉繁體（排名表上今天沒比賽的隊）
T2S_SHORT = str.maketrans("广东辽宁苏岛厦锦农汇", "廣東遼寧蘇島廈錦農匯")


def lookup(name):
    """玩運彩隊名 -> dict(q, words, city, lat, lon)；認不出來就 None。"""
    name = name or ""
    for keys, q, words, city, lat, lon in TEAMS:
        if any(k in name for k in keys):
            return dict(q=q, words=list(words), city=city, lat=lat, lon=lon)
    return None


def place(name):
    hit = lookup(name)
    return (hit["city"], hit["lat"], hit["lon"]) if hit else None


def enrich(games, log):
    """每隊掛上 cn_name（新聞查詢名）、cn_words（標題要有的字）、顯示用的中文名。"""
    n, miss = 0, set()
    for g in games:
        for side in ("home", "away"):
            t = g[side]
            hit = lookup(t.get("name"))
            if t.get("name") in DISPLAY:
                t["name_zh"] = t["short"] = DISPLAY[t["name"]]
            if not hit:
                miss.add(t.get("name"))
                continue
            t["cn_name"], t["cn_words"], t["city"] = hit["q"], hit["words"], hit["city"]
            n += 1
    log(f"[cba] 對到新聞查詢名 {n} 隊次" + (f"；沒對到：{'、'.join(sorted(x for x in miss if x))}" if miss else ""))


STATE = {}       # 新浪的賽季代碼（attach_sina 填）


def key_of(name):
    """玩運彩（繁體）或新浪（簡體簡稱）的隊名 -> 這隊的代表名（新聞查詢名）；認不出來就 None。"""
    name = (name or "").strip()
    if not name:
        return None
    for keys, q, words, *_ in TEAMS:
        if any(k in name for k in keys) or any(w in name for w in words):
            return q
    return None


def _h2h(sched, kh, ka, now):
    """新浪賽程（上季＋這季）裡兩隊打完的交手，主隊角度，格式跟玩運彩的交手一樣。"""
    rows = []
    for x in sched:
        if x["hs"] is None or x["start"] > now:
            continue
        h, a = key_of(x["home"]), key_of(x["away"])
        if {h, a} != {kh, ka}:
            continue
        home = h == kh
        pf, pa = (x["hs"], x["as_"]) if home else (x["as_"], x["hs"])
        rows.append(dict(date=x["start"].strftime("%Y/%m/%d"), home=home, pf=pf, pa=pa, opp=ka, result="W" if pf > pa else "L"))
    if len(rows) < 2:
        return None
    from matchup import playsport_h2h
    out = playsport_h2h(rows, [ka])
    if out:
        out["source"] = "新浪 CBA 賽程（上季＋這季）"
    return out


def attach_sina(games, log, errors, now=None):
    """新浪的排名表：這季戰績、主客場、排名（玩運彩的歷史含季前熱身賽，不準）；上季戰績和排名；交手；季前賽標出來。
    回傳排名頁要用的 dict(groups=[...])，抓不到就 None。"""
    import sina_cba as S
    from playsport import summarize_form
    now = now or datetime.now(timezone.utc)
    cur, opts = S.standings()
    if not cur:
        errors.append("cba 新浪排名表抓不到")
        return None
    prev_id = opts[1][0] if len(opts) > 1 else None
    STATE.update(cur_id=opts[0][0] if opts else None, prev_id=prev_id)
    prev, _ = S.standings(prev_id) if prev_id else ([], [])
    sched = S.schedule()
    sched_prev = S.schedule(prev_id) if prev_id else []
    regular = [x["start"] for x in sched if x["round"].startswith("第1")]
    season_start = min(regular) if regular else None
    by_cur = {key_of(r["team"]): r for r in cur}
    by_prev = {key_of(r["team"]): r for r in prev}
    played = any(r["w"] + r["l"] for r in cur)
    n_rec = n_prev = n_pre = n_h2h = 0
    for g in games:
        keys = {}
        for side in ("home", "away"):
            t = g[side]
            k = keys[side] = key_of(t.get("name"))
            # 開季前的比賽是季前熱身賽：近況只算開季後的；還沒打正式比賽就標「季前賽」
            if season_start and t.get("form"):
                reg = [r for r in t["form"] if (r.get("date_iso") or "") >= season_start.astimezone(timezone.utc).isoformat(timespec="minutes")]
                if len(reg) < len(t["form"]):
                    n_pre += 1
                    if reg:
                        summarize_form(t, reg, note="玩運彩歷史戰績（季前熱身賽不算）")
                    else:
                        t["form_note"] = "季前賽"
                        t["streak"] = None
            r = by_cur.get(k)
            if r:
                t["sina_id"], t["sina_team"] = r["sina_id"], r["team"]
            if r and played:
                t["record"] = f"{r['w']}-{r['l']}"
                t["record_note"] = "新浪 CBA 排名表"
                t["record_home"], t["record_away"] = r["home"], r["away"]
                if r["w"] + r["l"] >= 3:
                    t["rank"], t["rank_note"] = r["pos"], f"CBA 第 {r['pos']} 名"
                n_rec += 1
            p = by_prev.get(k)
            if len(prev) >= 10:
                pv = (dict(comp="cba", comp_zh="CBA", w=p["w"], l=p["l"], rank=p["pos"], of=len(prev), diff=round(p["pf"] - p["pa"], 1))
                      if p else dict(comp="cba", comp_zh="CBA", absent=True))
                g.setdefault("analysis", {}).setdefault("bg", {}).setdefault("prev", {})[side] = pv
                n_prev += bool(p)
        if keys.get("home") and keys.get("away") and not (g.get("analysis") or {}).get("h2h_long"):
            h = _h2h(sched_prev + sched, keys["home"], keys["away"], now)
            if h:
                g.setdefault("analysis", {})["h2h_long"] = h
                n_h2h += 1
    log(f"[cba] 新浪：排名表 {len(cur)} 隊（上季 {len(prev)} 隊）、賽程 {len(sched)} 場（上季 {len(sched_prev)} 場），"
        f"開季 {season_start.strftime('%m/%d') if season_start else '?'}；戰績 {n_rec} 隊次、上季 {n_prev} 隊次、"
        f"季前熱身賽拿掉 {n_pre} 隊次、交手 {n_h2h} 場")
    if not played:
        return None
    # 隊名用玩運彩的繁體，對不到就用新浪的簡稱
    names = {}
    for g in games:
        for side in ("home", "away"):
            k = key_of(g[side].get("name"))
            if k:
                names[k] = g[side].get("name_zh") or g[side].get("name")
    rows = [dict(team_id=key_of(r["team"]) or r["team"], team=r["team"], sina_id=r["sina_id"], name_zh=names.get(key_of(r["team"])) or r["team"].translate(T2S_SHORT), logo=None,
                 w=r["w"], l=r["l"], streak=r["streak"], pos=r["pos"], rank=r["pos"], home=r["home"], away=r["away"],
                 pf=r["pf"], pa=r["pa"], diff=round(r["pf"] - r["pa"], 1)) for r in cur]
    return dict(groups=[dict(name="CBA", rows=rows)])


def _zh(name):
    """簡體名字轉繁體（給爸爸看）；轉換套件沒裝就照原樣。"""
    try:
        from opencc import OpenCC
        if "cc" not in _CC:
            _CC["cc"] = OpenCC("s2tw")      # 台灣的寫法（杰倫 → 傑倫）
        return _CC["cc"].convert(name or "")
    except Exception:  # noqa: BLE001
        return name


_CC = {}


def attach_players(games, log, errors):
    """新浪的球員數據：這季名單（球隊頁）配上這季（打 3 場以上）或上季的例行賽場均，看得出新來的（上季在哪隊）。
    t["stars"]（前 4，傷兵新聞用簡體名字對）、t["leaders"]、t["cba_players"]（球員看點）。"""
    import sina_cba as S
    cur_id, prev_id = STATE.get("cur_id"), STATE.get("prev_id")
    if not cur_id:
        return 0
    cur = S.players(cur_id)
    prev = S.players(prev_id) if prev_id else {}
    if not cur and not prev:
        errors.append("cba 新浪球員數據抓不到")
        return 0
    rosters, n = {}, 0
    for g in games:
        for side in ("home", "away"):
            t = g[side]
            sid = t.get("sina_id")
            if not sid:
                continue
            if sid not in rosters:
                ro = S.roster(sid)
                if not ro:         # 球隊頁沒名單：用數據表上這隊的人
                    ro = [(pid, p["name"]) for pid, p in cur.items() if p["team"] == t.get("sina_team")]
                rosters[sid] = ro
            out = []
            for pid, name in rosters[sid]:
                c, pv = cur.get(pid), prev.get(pid)
                use = c if c and (c.get("gp") or 0) >= 3 else pv if pv and (pv.get("gp") or 0) >= 5 else c
                if not use or use.get("ppg") is None:
                    continue
                moved = bool(pv and pv.get("team") and t.get("sina_team") and key_of(pv["team"]) != key_of(t["sina_team"]))
                out.append(dict(id=pid, player=_zh(name), player_cn=name, cur=use is c, gp=use.get("gp"), ppg=use.get("ppg"),
                                rpg=use.get("rpg"), apg=use.get("apg"), eff=use.get("eff"), mpg=None,
                                prev_ppg=(pv or {}).get("ppg"), prev_gp=(pv or {}).get("gp"),
                                moved=moved, prev_team_zh=_zh(pv["team"]) if moved else None))
            out.sort(key=lambda p: -(p.get("ppg") or 0))
            if not out:
                continue
            t["cba_players"] = out[:6]
            t["stars"] = [dict(p, season=p["ppg"]) for p in out[:4]]
            t["leaders"] = [dict(id=p["id"], player=p["player"], headshot=None, position=None, stat="PTS", value=str(p["ppg"])) for p in out[:3]]
            n += 1
    log(f"[cba] 新浪球員數據：這季 {len(cur)} 人、上季 {len(prev)} 人；{len(rosters)} 隊有名單，{n} 隊次挑出主力"
        + (f"，例：{games[0]['home'].get('cba_players', [{}])[0]}" if games and games[0]["home"].get("cba_players") else ""))
    return n


# 維基百科（英文）的條目名稱：隊徽從條目的代表圖抓（新浪的球隊頁沒有隊徽）。改名的隊維基會自動轉到新條目
WIKI = {
    "北京首钢": "Beijing Ducks", "北控男篮": "Beijing Royal Fighters", "浙江广厦": "Zhejiang Lions", "浙江稠州": "Zhejiang Golden Bulls",
    "南京同曦": "Nanjing Monkey Kings", "广东宏远": "Guangdong Southern Tigers", "辽宁男篮": "Liaoning Flying Leopards",
    "上海男篮": "Shanghai Sharks", "新疆男篮": "Xinjiang Flying Tigers", "山东男篮": "Shandong Heroes", "山西男篮": "Shanxi Loongs",
    "深圳男篮": "Shenzhen Leopards", "广州男篮": "Guangzhou Loong Lions", "青岛男篮": "Qingdao Eagles", "江苏男篮": "Jiangsu Dragons",
    "福建男篮": "Fujian Sturgeons", "天津男篮": "Tianjin Pioneers", "四川男篮": "Sichuan Blue Whales", "吉林男篮": "Jilin Northeast Tigers",
    "宁波男篮": "Ningbo Rockets",
}
WIKI_UA = {"User-Agent": "sports-lottery-family-site/1.0 (https://github.com/cyt0925/sports-lottery)"}


def _wiki_thumbs(titles):
    """維基百科條目的代表圖（多半是隊徽）縮圖網址：{條目名稱: 網址}。"""
    import requests
    out = {}
    try:
        r = requests.get("https://en.wikipedia.org/w/api.php", headers=WIKI_UA, timeout=20, params=dict(
            action="query", format="json", prop="pageimages", piprop="thumbnail", pithumbsize=160, pilicense="any",
            redirects=1, titles="|".join(titles)))
        q = r.json().get("query") or {}
    except Exception:  # noqa: BLE001
        return out
    back = {t: t for t in titles}
    for m in (q.get("normalized") or []) + (q.get("redirects") or []):
        back[m["to"]] = back.get(m["from"], m["from"])
    for p in (q.get("pages") or {}).values():
        th = (p.get("thumbnail") or {}).get("source")
        if th:
            out[back.get(p.get("title"), p.get("title"))] = th
    return out


def attach_logos(games, standing, out_dir, log, errors):
    """隊徽：玩運彩沒有、新浪的球隊頁也沒有，從維基百科條目的代表圖抓下來存在網站自己的資料夾
    （data/logos/cba/新浪代碼.png），抓過就不重抓。"""
    import os
    import time
    folder = os.path.join(out_dir, "logos", "cba")
    os.makedirs(folder, exist_ok=True)
    have = {os.path.splitext(f)[0]: f for f in os.listdir(folder)}
    new, fail = 0, []
    todo = {}
    for g in games:
        for side in ("home", "away"):
            t = g[side]
            sid, k = t.get("sina_id"), key_of(t.get("name"))
            if sid and sid not in have and k in WIKI:
                todo[sid] = WIKI[k]
    for grp in (standing or {}).get("groups") or []:
        for r in grp["rows"]:
            k = key_of(r.get("team"))
            if r.get("sina_id") and r["sina_id"] not in have and k in WIKI:
                todo[r["sina_id"]] = WIKI[k]
    thumbs = _wiki_thumbs(sorted(set(todo.values()))) if todo else {}
    import requests
    for sid, title in sorted(todo.items()):
        url = thumbs.get(title)
        try:
            r = requests.get(url, headers=WIKI_UA, timeout=20) if url else None
        except Exception:  # noqa: BLE001
            r = None
        ct = ((r.headers.get("content-type") if r is not None else "") or "").lower()
        if r is None or r.status_code != 200 or not ct.startswith("image/"):
            fail.append(title)
            continue
        ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp", "image/svg+xml": ".svg"}.get(ct.split(";")[0], ".png")
        with open(os.path.join(folder, sid + ext), "wb") as fh:
            fh.write(r.content)
        have[sid] = sid + ext
        new += 1
        time.sleep(0.3)
    path = lambda sid: f"data/logos/cba/{have[sid]}" if sid in have else None  # noqa: E731
    for g in games:
        for s in ("home", "away"):
            if g[s].get("sina_id") and path(g[s]["sina_id"]):
                g[s]["logo"] = path(g[s]["sina_id"])
    for grp in (standing or {}).get("groups") or []:
        for r in grp["rows"]:
            if r.get("sina_id") and path(r["sina_id"]):
                r["logo"] = path(r["sina_id"])
    log(f"[cba] 隊徽（維基百科）：{len(have)} 隊有（這次新抓 {new} 隊）" + (f"；抓不到：{'、'.join(fail)}" if fail else ""))
    if fail and not have:
        errors.append("cba 隊徽一張都抓不到")
