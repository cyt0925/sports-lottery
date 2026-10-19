# -*- coding: utf-8 -*-
"""暫時的探路程式（只寫 log，查完就拿掉）：新浪 CBA 球員數據頁的查詢參數、表格、球隊名單頁。"""
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


def show(t, label):
    print("##", label)
    for f in re.findall(r"<form.*?</form>", t, flags=re.S | re.I)[:3]:
        print("FORM", re.sub(r"\s+", " ", f)[:1500])
    for sel in re.findall(r"<select[^>]*>.*?</select>", t, flags=re.S | re.I)[:6]:
        name = re.search(r'name="([^"]+)"', sel)
        opts = re.findall(r'<option[^>]*value="([^"]*)"[^>]*>(.*?)</option>', sel, flags=re.S)
        print("SELECT", name.group(1) if name else None, [(v, strip(x)) for v, x in opts][:30])
    links = sorted(set(re.findall(r'href="([^"]*(?:stats|team|player|schedule|rank)[^"]*)"', t)))
    print("LINKS", links[:60])
    tables = re.findall(r"<table.*?</table>", t, flags=re.S | re.I)
    print("TABLES", len(tables))
    for tb in tables[:3]:
        rows = re.findall(r"<tr.*?</tr>", tb, flags=re.S | re.I)
        print("  rows", len(rows))
        for tr in rows[:4]:
            print("   ", strip(tr)[:300], "|RAW|", re.sub(r"\s+", " ", tr)[:400])


def main():
    t = get(f"{BASE}/cba/stats/playerstats/")
    if t:
        show(t, "playerstats")
    for q in ("?qtype=avg&y=2026", "?dpc=1&qtype=avg&y=2025", "?y=2025", "?season=2025"):
        t2 = get(f"{BASE}/cba/stats/playerstats/{q}")
        if t2:
            tb = re.findall(r"<tr.*?</tr>", t2, flags=re.S | re.I)
            print("  ", q, "rows", len(tb), [strip(x)[:120] for x in tb[1:3]])
    for path in ("/cba/team/", "/cba/stats/teamrank/", "/cba/schedule/all/", "/cba/"):
        t3 = get(BASE + path)
        if t3:
            show(t3, path)


if __name__ == "__main__":
    main()
