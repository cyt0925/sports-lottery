# -*- coding: utf-8 -*-
"""暫時的查詢：玩運彩上有哪些籃球分類（allianceid），每個分類今天到 3 天後有哪些比賽、屬於哪個聯賽。
只寫 log，不影響網站資料。查完會拿掉。"""
import re
from collections import Counter
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from taiwan_odds import fetch, TW, BASE, LS
from playsport import parse_scale_page


def run(log):
    now = datetime.now(TW)
    day = now.strftime("%Y%m%d")
    text = fetch(f"{BASE}/predict/scale?allianceid=8&gametime={day}")
    if not text:
        log("[查詢] 玩運彩抓不到")
        return
    soup = BeautifulSoup(text, "html.parser")
    alliances = {}
    for a in soup.find_all("a", href=True):
        m = re.search(r"allianceid=(\d+)", a["href"])
        name = a.get_text(" ", strip=True)
        if m and name and len(name) <= 12:
            alliances.setdefault(int(m.group(1)), name)
    log("[查詢] 玩運彩所有分類：" + "、".join(f"{k}={v}" for k, v in sorted(alliances.items())))
    basket = {k: v for k, v in alliances.items() if "籃" in v or k in (8, 3, 97, 92, 94, 110)}
    for aid, name in sorted(basket.items()):
        games, comps = [], Counter()
        for i in range(0, 4):
            d = (now + timedelta(days=i)).strftime("%Y%m%d")
            t = fetch(f"{BASE}/predict/scale?allianceid={aid}&gametime={d}")
            rows = parse_scale_page(t) if t else []
            ls = fetch(f"{LS}?alliance={aid}&gamedate={d}", as_json=True)
            src = {}
            if isinstance(ls, dict):
                for v in ls.values():
                    if isinstance(v, dict) and v.get("gameid"):
                        src[str(v["gameid"])] = (v.get("source") or "", v.get("official_id") or "", v.get("league") or v.get("leaguename") or "")
            for r in rows:
                s = src.get(str(r.get("gameid")), ("", "", ""))
                comps[s[0] or "?"] += 1
                games.append(f"{d[4:]} {r.get('time')} {r.get('away')}@{r.get('home')} [{s[0]}|{s[1][:24]}|{s[2]}] 有盤:{bool(r.get('ml') or r.get('spread'))}")
        log(f"[查詢] 分類 {aid}={name}：{len(games)} 場；來源欄 {dict(comps)}")
        for g in games[:40]:
            log(f"[查詢]   {g}")


def run_sources(log):
    """暫時：測試幾個免費的國內聯賽資料來源（只寫 log）。"""
    import requests
    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
    tsdb = "https://www.thesportsdb.com/api/v1/json/123"
    for c in ("Spain", "Turkey", "Greece", "Italy", "Israel", "France", "Germany", "Lithuania", "Serbia"):
        try:
            r = requests.get(f"{tsdb}/search_all_leagues.php", params={"c": c, "s": "Basketball"}, headers=ua, timeout=20)
            ls = (r.json() or {}).get("countries") or []
            log(f"[查詢] TheSportsDB {c}：HTTP {r.status_code}，" + "、".join(f"{x.get('idLeague')}={x.get('strLeague')}" for x in ls[:6]))
        except Exception as e:  # noqa: BLE001
            log(f"[查詢] TheSportsDB {c} 失敗：{type(e).__name__} {str(e)[:120]}")
    for lid in ("4408", "4433"):
        try:
            r = requests.get(f"{tsdb}/eventspastleague.php", params={"id": lid}, headers=ua, timeout=20)
            ev = (r.json() or {}).get("events") or []
            log(f"[查詢] TheSportsDB 聯賽 {lid} 最近比賽 {len(ev)} 場：" + "；".join(f"{e.get('dateEvent')} {e.get('strEvent')} {e.get('intHomeScore')}-{e.get('intAwayScore')}" for e in ev[:5]))
        except Exception as e:  # noqa: BLE001
            log(f"[查詢] TheSportsDB 聯賽 {lid} 失敗：{type(e).__name__}")
    day = datetime.now(TW).strftime("%Y-%m-%d")
    for url in (f"https://api.sofascore.com/api/v1/sport/basketball/scheduled-events/{day}",
                f"https://www.sofascore.com/api/v1/sport/basketball/scheduled-events/{day}"):
        try:
            r = requests.get(url, headers={**ua, "Accept": "application/json"}, timeout=20)
            n = len((r.json() or {}).get("events") or []) if r.status_code == 200 else 0
            tours = Counter(((e.get("tournament") or {}).get("name") or "?") for e in ((r.json() or {}).get("events") or [])) if r.status_code == 200 else {}
            log(f"[查詢] Sofascore {url.split('/')[2]}：HTTP {r.status_code}，{n} 場；聯賽 {dict(list(dict(tours).items())[:25])}")
        except Exception as e:  # noqa: BLE001
            log(f"[查詢] Sofascore 失敗：{type(e).__name__} {str(e)[:120]}")
