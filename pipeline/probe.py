# -*- coding: utf-8 -*-
"""暫時的查詢：台灣運彩官網用哪些資料網址（從網路存檔 Wayback Machine 看）、403 是不是擋國外。只寫 log，查完會拿掉。"""
import re
import time

import requests

HEAD = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
        "Accept": "application/json, text/plain, */*", "Referer": "https://www.sportslottery.com.tw/", "Origin": "https://www.sportslottery.com.tw",
        "Accept-Language": "zh-TW,zh;q=0.9"}
WB = "https://web.archive.org"
CDX = WB + "/cdx/search/cdx"
URL_RE = re.compile(r"""https?://[a-z0-9.-]*sportslottery\.com\.tw[^"'\s)<>\\]*|apidata/[A-Za-z0-9_./{}$+-]+|/api/[A-Za-z0-9_./{}$+-]+""")


def _get(url, **kw):
    try:
        return requests.get(url, headers=kw.pop("headers", {"User-Agent": HEAD["User-Agent"]}), timeout=30, **kw)
    except Exception as e:  # noqa: BLE001
        return type(e).__name__


def _cdx(log, url, extra=None, limit=300):
    q = {"url": url, "matchType": "prefix", "output": "json", "limit": limit, "collapse": "urlkey",
         "fl": "timestamp,original,mimetype,statuscode"}
    q.update(extra or {})
    r = _get(CDX, params=q)
    if isinstance(r, str):
        log(f"[查詢5] 存檔清單 {url}：{r}")
        return []
    try:
        rows = r.json()[1:]
    except ValueError:
        log(f"[查詢5] 存檔清單 {url}：HTTP {r.status_code} {r.text[:200]!r}")
        return []
    log(f"[查詢5] 存檔清單 {url}：{len(rows)} 筆")
    return rows


def run(log):
    r = _get("https://blob3rd.sportslottery.com.tw/apidata/Pre/34731.1-Games.zh.json", headers=HEAD)
    if not isinstance(r, str):
        body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))
        log(f"[查詢5] blob3rd 403 內容：{body[:500]!r}；標頭 {dict((k, v) for k, v in r.headers.items() if k.lower() in ('server', 'x-cache', 'x-azure-ref', 'via', 'cf-ray', 'x-msedge-ref'))}")

    rows = _cdx(log, "blob3rd.sportslottery.com.tw/")
    for t, u, m, s in rows[:300]:
        log(f"[查詢5]   blob3rd {t} {s} {m} {u}")
    rows = _cdx(log, "blob.sportslottery.com.tw/apidata/")
    for t, u, m, s in rows[:120]:
        log(f"[查詢5]   blob {t} {s} {m} {u}")

    rows = _cdx(log, "www.sportslottery.com.tw/", {"filter": "mimetype:.*javascript.*", "from": "2024"}, 400)
    js = [u for t, u, m, s in rows if s == "200"]
    log(f"[查詢5] 官網 js 檔 {len(js)} 個，例 {js[:15]}")
    seen = {}
    home = _get(WB + "/web/2026id_/https://www.sportslottery.com.tw/")
    pages = []
    if not isinstance(home, str):
        log(f"[查詢5] 官網首頁存檔：HTTP {home.status_code}，{len(home.text)} 字，網址 {home.url}")
        for u in URL_RE.findall(home.text):
            seen[u] = seen.get(u, 0) + 1
        pages = re.findall(r"""<script[^>]+src=["']([^"']+)["']""", home.text)
        log(f"[查詢5] 首頁 script：{pages[:20]}")
    cand = []
    for s in pages:
        m = re.search(r"https?://.*", s.split("/web/", 1)[-1]) if "/web/" in s else None
        full = m.group(0) if m else (s if s.startswith("http") else "https://www.sportslottery.com.tw/" + s.lstrip("/"))
        cand.append(full)
    cand += [u for u in js if re.search(r"(main|app|index|chunk|vendor|runtime|sport|bet|config)", u, re.I)]
    done, t0 = 0, time.time()
    for u in dict.fromkeys(cand):
        if done >= 25 or time.time() - t0 > 300:
            break
        r = _get(f"{WB}/web/2026id_/{u}")
        if isinstance(r, str) or r.status_code != 200:
            continue
        done += 1
        hits = URL_RE.findall(r.text)
        for h in hits:
            seen[h] = seen.get(h, 0) + 1
        log(f"[查詢5] 讀 {u}：{len(r.text)} 字，網址 {len(hits)} 個")
    for u, n in sorted(seen.items(), key=lambda x: -x[1])[:150]:
        log(f"[查詢5]   網址 {n}× {u}")
