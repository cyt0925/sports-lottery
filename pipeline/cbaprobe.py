# -*- coding: utf-8 -*-
"""暫時的探路程式（只寫 log，查完就拿掉）：新浪 CBA 球員數據（全聯盟、球隊頁、單場數據頁）。"""
import re
import html as htmlmod

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
BASE = "http://cba.sports.sina.com.cn"


def strip(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def get(url):
    try:
        r = requests.get(url, headers=UA, timeout=25)
        t = r.content.decode("gbk", errors="replace")
        print(f"URL {url} -> {r.status_code} len={len(t)}")
        return t if r.status_code == 200 else None
    except Exception as e:  # noqa: BLE001
        print("FAIL", url, repr(e)[:200])
        return None


def tables(t, n=3, rows_n=4):
    tbs = re.findall(r"<table.*?</table>", t, flags=re.S | re.I)
    print("TABLES", len(tbs))
    for tb in tbs[:n]:
        rows = re.findall(r"<tr.*?</tr>", tb, flags=re.S | re.I)
        print("  rows", len(rows))
        for tr in rows[:rows_n]:
            print("   ", strip(tr)[:300], "|RAW|", re.sub(r"\s+", " ", tr)[:500])


def main():
    for q in ("?qleagueid=216&qround=&qorder=pts", "?qleagueid=216&qround=%B3%A3%B9%E6%C8%FC", "?qleagueid=217&qround=&qorder=pts"):
        t = get(f"{BASE}/cba/stats/playerstats/{q}")
        if t:
            tables(t, 1, 5)
    t = get(f"{BASE}/cba/team/show/16/")
    if t:
        print("team links", sorted(set(re.findall(r'href="([^"]*(?:player|stats|schedule)[^"]*)"', t)))[:30])
        tables(t, 4, 5)
    t = get(f"{BASE}/cba/schedule/all/")
    if t:
        stat = re.findall(r'<a href="([^"]+)"[^>]*>\s*统计\s*</a>', t)
        print("統計連結", stat[:5])
        for u in stat[:1]:
            u = u if u.startswith("http") else BASE + u
            s = get(u)
            if s:
                tables(s, 4, 5)
    t = get(f"{BASE}/cba/player/show/4017/")
    if t:
        tables(t, 3, 4)


if __name__ == "__main__":
    main()
