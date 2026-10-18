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
