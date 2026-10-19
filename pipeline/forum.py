# -*- coding: utf-8 -*-
"""論壇：PTT NBA 板（www.ptt.cc/bbs/NBA）最近兩天的 [情報]、[新聞] 文章。

台灣球迷常常比外電還快貼出「今天誰不打」「誰回來了」「換教練」。每場挑跟兩隊有關的文章（標題有隊名或主力名字），
放進「外界怎麼看」，標題裡的場外消息（換帥、禁賽…）也交給 context.team_signals。抓不到就算了，不影響其他。"""
import re
import time
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from taiwan_odds import fetch

BASE = "https://www.ptt.cc"
PAGES = 8
TW = timezone(timedelta(hours=8))
KEEP = re.compile(r"^\s*\[(情報|新聞|專欄)\]")
# PTT 習慣的叫法（跟網站上的中文隊名不一樣的）
ALIAS = {"PHI": ["76人", "七六人"], "POR": ["拓荒者", "拓荒"], "BOS": ["塞爾提克", "綠衫軍"], "GS": ["勇士"], "GSW": ["勇士"],
         "LAL": ["湖人"], "LAC": ["快艇"], "NY": ["尼克"], "NYK": ["尼克"], "BKN": ["籃網"], "DAL": ["獨行俠", "小牛"],
         "OKC": ["雷霆"], "SA": ["馬刺"], "SAS": ["馬刺"], "MIN": ["灰狼"], "NO": ["鵜鶘"], "NOP": ["鵜鶘"], "WSH": ["巫師"], "WAS": ["巫師"]}


def fetch_posts(log, now=None):
    now = now or datetime.now(TW)
    url = f"{BASE}/bbs/NBA/index.html"
    posts = []
    for _ in range(PAGES):
        html = fetch(url)
        if not html:
            break
        soup = BeautifulSoup(html, "html.parser")
        for ent in soup.select("div.r-ent"):
            a = ent.select_one("div.title a")
            if not a:
                continue
            title = a.get_text(strip=True)
            if not KEEP.search(title):
                continue
            nrec_el, date_el = ent.select_one("div.nrec"), ent.select_one("div.date")
            nrec = nrec_el.get_text(strip=True) if nrec_el else ""
            date = date_el.get_text(strip=True) if date_el else ""
            posts.append(dict(title=title, url=BASE + a.get("href", ""), push=nrec, date=date))
        prev = next((x.get("href") for x in soup.select("div.btn-group-paging a") if "上頁" in x.get_text()), None)
        if not prev:
            break
        url = BASE + prev
        time.sleep(0.4)
    # 只留兩天內（PTT 列表只有月/日）
    keep_days = {(now - timedelta(days=i)).strftime("%-m/%d") for i in range(3)}
    posts = [p for p in posts if p["date"].strip() in keep_days]
    log(f"論壇：PTT NBA 板最近的情報、新聞 {len(posts)} 篇")
    return posts


def _names(t):
    from names_zh import NBA
    out = set()
    ab = str(t.get("abbr") or "")
    if NBA.get(ab):
        out.add(NBA[ab])
    out.update(ALIAS.get(ab, []))
    if t.get("name_zh"):
        out.add(t["name_zh"])
    stars = [x.get("player") for x in (t.get("stars") or t.get("leaders") or [])[:3] if x.get("player")]
    for p in stars:
        last = p.split(" ")[-1]
        if len(last) >= 4:
            out.add(last)
    return {x for x in out if x}


def attach(games, log, errors):
    nba = [g for g in games if g.get("league") == "nba" and g["status"]["state"] != "post" and not g.get("far")]
    if not nba:
        return 0
    try:
        posts = fetch_posts(log)
    except Exception as e:  # noqa: BLE001
        errors.append(f"論壇失敗: {e!r}")
        return 0
    if not posts:
        return 0
    import context
    n = 0
    for g in nba:
        picked = []
        for side in ("home", "away"):
            names = _names(g[side])
            mine = [dict(p, team=side) for p in posts if any(nm in p["title"] for nm in names)]
            picked += mine[:3]
            sig = context.team_signals([dict(title=p["title"]) for p in mine])
            if sig:
                have = {s["kind"] for s in g[side].get("signals") or []}
                g[side]["signals"] = (g[side].get("signals") or []) + [s for s in sig if s["kind"] not in have]
        if picked:
            g["forum"] = picked[:5]
            n += 1
    log(f"論壇：{n} 場 NBA 有 PTT 球迷在聊的文章")
    return n
