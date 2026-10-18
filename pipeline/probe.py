# -*- coding: utf-8 -*-
"""暫時的查詢：歐洲國內聯賽（義甲、西甲、立陶宛、法甲、土超…）在玩運彩哪個分類、台灣運彩官網的資料抓不抓得到。
只寫 log，不影響網站資料。查完會拿掉。"""
import re
from datetime import datetime, timedelta

import requests

from taiwan_odds import fetch, TW, BASE, HEADERS
from playsport import parse_scale_page

KNOWN = {1, 2, 3, 4, 6, 7, 8, 9, 12, 87, 90, 91, 92, 93, 94, 97}
LOOK = ("尤文圖特", "托爾托納", "考納斯綠林", "加拉塔薩雷", "勒芒", "的里雅斯特", "波隆那", "加那利")


def run(log):
    now = datetime.now(TW)
    days = [(now + timedelta(days=i)).strftime("%Y%m%d") for i in (0, 1)]
    found = 0
    for aid in [x for x in range(1, 131) if x not in KNOWN]:
        for d in days:
            t = fetch(f"{BASE}/predict/scale?allianceid={aid}&gametime={d}", tries=1)
            if not t:
                continue
            rows = parse_scale_page(t)
            hits = [w for w in LOOK if w in t]
            title = re.search(r"<title>(.*?)</title>", t, re.S)
            if rows or hits:
                found += 1
                log(f"[查詢2] 玩運彩 allianceid={aid} {d}：{len(rows)} 場，看到 {hits}，標題 {title.group(1).strip()[:40] if title else ''}")
                for r in rows[:12]:
                    log(f"[查詢2]   {r.get('time')} {r.get('away')}@{r.get('home')} 不讓分 {r.get('ml')} 讓分 {(r.get('spread') or {}).get('line')} 大小 {(r.get('total') or {}).get('line')}")
                break
    log(f"[查詢2] 玩運彩其他分類掃完，有比賽的 {found} 個")
    # 台灣運彩官網
    for url in ("https://www.sportslottery.com.tw/", "https://www.sportslottery.com.tw/sportsbook/basketball",
                "https://blob.sportslottery.com.tw/", "https://member.sportslottery.com.tw/"):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25, allow_redirects=True)
            log(f"[查詢2] 官網 {url}：HTTP {r.status_code}，{len(r.text)} 字，最後網址 {r.url}，類型 {r.headers.get('content-type')}")
            if r.status_code == 200 and "html" in (r.headers.get("content-type") or ""):
                srcs = re.findall(r'<script[^>]+src="([^"]+)"', r.text)
                log(f"[查詢2]   script：{srcs[:12]}")
                apis = set(re.findall(r'https?://[a-zA-Z0-9.-]*sportslottery[a-zA-Z0-9./_?=&-]*', r.text))
                log(f"[查詢2]   網址：{sorted(apis)[:30]}")
                for s in srcs[:8]:
                    su = s if s.startswith("http") else requests.compat.urljoin(r.url, s)
                    try:
                        js = requests.get(su, headers=HEADERS, timeout=25).text
                    except Exception as e:  # noqa: BLE001
                        log(f"[查詢2]   抓不到 {su}：{type(e).__name__}")
                        continue
                    hosts = sorted(set(re.findall(r'https?://[a-zA-Z0-9.-]+(?:sportslottery|azure|cloudfront|amazonaws)[a-zA-Z0-9.-]*[a-zA-Z0-9./_-]{0,60}', js)))[:25]
                    paths = sorted(set(re.findall(r'["\'`](/(?:api|apidata|services|web/services|sportsbook|odds|event|market|league)[a-zA-Z0-9/_.{}$-]{2,80})["\'`]', js)))[:40]
                    log(f"[查詢2]   {su[-60:]}（{len(js)} 字）主機 {hosts}")
                    log(f"[查詢2]     路徑 {paths}")
        except Exception as e:  # noqa: BLE001
            log(f"[查詢2] 官網 {url} 失敗：{type(e).__name__} {str(e)[:150]}")
