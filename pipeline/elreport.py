# -*- coding: utf-8 -*-
"""歐籃傷兵報告：沒有官方傷兵 API，但 EuroLeague 每輪賽前都會發「injury report」，
Eurohoops / BasketNews / 官網都會整理成一篇「哪隊少了誰」。這裡用 Google 新聞找到那幾篇，
把 Google 的轉址解開、抓文章內文，交給 players.el_player_layer 用官方球員名單（全名）對出缺陣的人。
全部免費、不用金鑰；抓不到就回空清單，照舊只用標題。"""
import base64
import json
import re
import time
import html as htmlmod
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlparse

import requests

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
GN = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
QUERIES = [
    'euroleague "injury report" when:8d',
    '"injury report" site:euroleaguebasketball.net when:10d',
    'euroleague (absences OR "will miss" OR "ruled out") when:6d',
    'eurocup (injury OR "will miss" OR "ruled out") when:6d',
]
TITLE_OK = re.compile(r"injur|absen|will miss|miss |ruled out|sidelined|out for|key players", re.I)
TITLE_BAD = re.compile(r"soccer|football|NBA|NFL|Spurs|Wembanyama|UEFA|Champions League", re.I)
# 整輪的傷兵報告（team-by-team）最有用，優先抓；單一球員的新聞排後面
REPORT_TITLE = re.compile(r"injury report|absences|will miss|key players who will miss|team-by-team", re.I)
MAX_ARTICLES = 6


def _title_key(title):
    return re.sub(r"\s+", " ", (title or "").split(" - ")[0].strip().lower())


def _rss(q):
    try:
        r = requests.get(GN.format(q=quote(q)), headers=UA, timeout=20)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except Exception:  # noqa: BLE001
        return []
    items = []
    for it in root.iter("item"):
        title = htmlmod.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(pub).isoformat(timespec="minutes") if pub else None
        except (TypeError, ValueError):
            published = None
        src = it.find("source")
        items.append(dict(title=title, url=link, published=published, source=(src.text or "").strip() if src is not None else None))
    time.sleep(0.4)
    return items


def _old_format(b64):
    try:
        raw = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))
    except Exception:  # noqa: BLE001
        return None
    m = re.search(rb"https?://[\x21-\x7e]+", raw)
    if not m:
        return None
    url = m.group(0).decode("ascii", "ignore")
    return None if url.startswith("AU_yqL") else url


def decode_gnews(url, log=None):
    """news.google.com/rss/articles/<id> → 原始文章網址。
    舊格式的 id 直接 base64 解得出網址；2024 年後的新格式要先向 Google 拿簽章再用 batchexecute 換。"""
    p = urlparse(url)
    parts = [x for x in p.path.split("/") if x]
    if p.hostname != "news.google.com" or len(parts) < 2 or parts[-2] not in ("articles", "read"):
        return url
    b64 = parts[-1]
    direct = _old_format(b64)
    if direct:
        return direct
    try:
        r = requests.get(f"https://news.google.com/articles/{b64}", headers=UA, timeout=20)
        sg = re.search(r'data-n-a-sg="([^"]+)"', r.text)
        ts = re.search(r'data-n-a-ts="(\d+)"', r.text)
        if not sg or not ts:
            if log:
                log(f"[elreport] 解不開 Google 轉址（沒簽章）{url[:70]}")
            return None
        payload = ["Fbv4je", f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{b64}",{ts.group(1)},"{sg.group(1)}"]']
        body = "f.req=" + quote(json.dumps([[payload]]))
        r = requests.post("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                          headers={**UA, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}, data=body, timeout=20)
        text = r.text
        try:
            chunk = json.loads(text.split("\n\n", 1)[1])
            inner = json.loads(chunk[0][2])
            if isinstance(inner, list) and len(inner) > 1 and str(inner[1]).startswith("http"):
                return inner[1]
        except Exception:  # noqa: BLE001
            pass
        m = re.search(r'garturlres\\",\\"(https?://[^\\"]+)', text) or re.search(r'(https?://[^"\\\s]+)', text.split("garturlres", 1)[-1])
        return m.group(1) if m else None
    except Exception as e:  # noqa: BLE001
        if log:
            log(f"[elreport] 解 Google 轉址失敗 {e!r}")
        return None
    finally:
        time.sleep(0.5)


def _article_text(url):
    r = requests.get(url, headers=UA, timeout=25)
    if r.status_code != 200:
        return None, r.status_code
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript", "iframe", "form"]):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    lines = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "td"]):
        t = el.get_text(" ", strip=True)
        if t and len(t) > 2:
            lines.append(t)
    text = "\n".join(lines)
    text = re.sub(r"[ \t]+", " ", text)
    return text, 200


def fetch_reports(log, errors, limit=MAX_ARTICLES):
    """回傳 [{title, url, source, published, text}]，最新的在前。"""
    seen, cands = set(), []
    for q in QUERIES:
        for it in _rss(q):
            tk = _title_key(it["title"])
            if it["url"] in seen or tk in seen:
                continue
            seen.add(it["url"])
            seen.add(tk)
            if not TITLE_OK.search(it["title"]) or TITLE_BAD.search(it["title"]):
                continue
            cands.append(it)
    # 新的在前，但整輪傷兵報告永遠排最前面
    cands.sort(key=lambda x: x.get("published") or "", reverse=True)
    cands.sort(key=lambda x: 0 if REPORT_TITLE.search(x["title"]) else 1)
    log(f"[elreport] 候選 {len(cands)} 篇：" + "；".join(x["title"][:50] for x in cands[:8]))
    out = []
    seen_real = set()
    blocked = set()  # 回 403/429 的站，這一輪就不再試
    for it in cands[: limit * 2]:
        if len(out) >= limit:
            break
        real = decode_gnews(it["url"], log)
        if not real or "news.google.com" in real or real in seen_real:
            continue
        seen_real.add(real)
        host = urlparse(real).hostname or ""
        if host in blocked:
            continue
        time.sleep(1.2)
        try:
            text, code = _article_text(real)
        except Exception as e:  # noqa: BLE001
            log(f"[elreport] 抓文章失敗 {host} {e!r}")
            continue
        if code in (403, 429):
            blocked.add(host)
        if not text or len(text) < 300:
            log(f"[elreport] 文章太短或抓不到 {host} ({code}) {it['title'][:60]}")
            continue
        out.append(dict(title=it["title"], url=real, source=it.get("source") or host, published=it.get("published"), text=text))
        log(f"[elreport] 文章 {host} {len(text)} 字：{it['title'][:70]}")
    if not out:
        log(f"[elreport] 沒抓到傷兵報告文章（候選 {len(cands)} 篇）")
    else:
        log(f"[elreport] 傷兵報告 {len(out)} 篇；第一篇片段：{out[0]['text'][:300]!r}")
    return out
