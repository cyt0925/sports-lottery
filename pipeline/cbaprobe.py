# -*- coding: utf-8 -*-
"""暫時的探路程式（只寫 log，查完就拿掉）：CBA 在玩運彩的編號、球員數據從哪裡抓得到、中文新聞。"""
import re
import sys
import os
import html as htmlmod
from datetime import datetime, timedelta
from urllib.parse import quote

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taiwan_odds import fetch, parse_scale_page, fetch_livescore_ids, TW, BASE  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8", "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7"}


def strip(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def get(url, n=600):
    try:
        r = requests.get(url, headers=UA, timeout=25)
        print(f"URL {url} -> {r.status_code} len={len(r.text)} type={r.headers.get('content-type')}")
        return r.text if r.status_code == 200 else None
    except Exception as e:  # noqa: BLE001
        print("FAIL", url, repr(e)[:200])
        return None


def sec(t):
    print("=" * 80)
    print("##", t)


def main():
    now = datetime.now(TW)
    days = [(now + timedelta(days=k)).strftime("%Y%m%d") for k in (-1, 0, 1, 2)]
    sec("玩運彩聯盟列表")
    found = {}
    for url in (f"{BASE}/predict/scale", f"{BASE}/", f"{BASE}/gamesData/teams"):
        t = fetch(url)
        if not t:
            print("抓不到", url)
            continue
        for aid, txt in re.findall(r'allianceid=(\d+)[^"]*"[^>]*>(.*?)</a>', t, flags=re.S):
            name = strip(txt)[:30]
            if name and aid not in found:
                found[aid] = name
    print("聯盟：", sorted(found.items(), key=lambda x: int(x[0])))
    cand = [a for a, n in found.items() if re.search(r"CBA|中國|中职|中職|大陸", n)]
    print("CBA 候選：", cand)
    for aid in cand or ["94"]:
        sec(f"alliance {aid}")
        for d in days:
            t = fetch(f"{BASE}/predict/scale?allianceid={aid}&gametime={d}")
            rows = parse_scale_page(t) if t else []
            print(d, "盤口列", len(rows), [(r.get("time"), r.get("away"), r.get("home"), r.get("ml"), r.get("spread"), r.get("total")) for r in rows[:3]])
            ids = fetch_livescore_ids(aid, d)
            print(d, "即時比分", len(ids), list(ids.values())[:1])
        t = fetch(f"{BASE}/gamesData/teams?allianceid={aid}")
        if t:
            names = re.findall(r'teamid=(\d+)[^"]*"[^>]*>(.*?)</a>', t, flags=re.S)
            print("球隊：", sorted({(i, strip(n)) for i, n in names if strip(n)})[:40])

    sec("球員數據來源")
    for url in ("https://www.cbaleague.com/", "https://www.cbaleague.com/data/", "https://cba.sports.sina.com.cn/cba/stats/playerstats/",
                "http://cba.sports.sina.com.cn/cba/stats/playerstats/", "https://cba.hupu.com/stats/players", "https://nba.hupu.com/",
                "https://basketball.realgm.com/international/league/40/Chinese-CBA/stats",
                "https://www.proballers.com/basketball/league/52/china-cba", "https://www.asia-basket.com/China/basketball-League-CBA.aspx",
                "https://www.thesportsdb.com/api/v1/json/3/search_all_leagues.php?c=China&s=Basketball",
                "https://sports.qq.com/cba/", "https://www.basketball-reference.com/international/cba/"):
        t = get(url)
        if t:
            print("   字：", strip(t)[:500])
            apis = sorted(set(re.findall(r'https?://[a-zA-Z0-9.-]*(?:api|data)[a-zA-Z0-9.-]*\.[a-z]{2,}[^"\'\s<>]{0,80}', t)))[:15]
            if apis:
                print("   API 線索：", apis)
            scripts = re.findall(r'<script[^>]+src="([^"]+)"', t)[:8]
            if scripts:
                print("   script：", scripts)

    sec("中文新聞（Google 新聞）")
    for q, lang in (("广东宏远", "hl=zh-CN&gl=CN&ceid=CN:zh-Hans"), ("CBA 广东 伤", "hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
                    ("CBA 廣東", "hl=zh-TW&gl=TW&ceid=TW:zh-Hant"), ("辽宁本钢 外援", "hl=zh-CN&gl=CN&ceid=CN:zh-Hans")):
        t = get(f"https://news.google.com/rss/search?q={quote(q + ' when:14d')}&{lang}")
        if t:
            titles = re.findall(r"<item>.*?<title>(.*?)</title>", t, flags=re.S)
            print(f"   {q}：{len(titles)} 則", [htmlmod.unescape(x)[:60] for x in titles[:6]])


if __name__ == "__main__":
    main()
