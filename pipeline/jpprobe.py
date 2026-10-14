# -*- coding: utf-8 -*-
"""探路：B.LEAGUE 與 SV.LEAGUE 官網哪一頁有球員名單／個人數據，長什麼樣。只印結構，不改資料。"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bs4 import BeautifulSoup  # noqa: E402
from taiwan_odds import fetch  # noqa: E402


def describe(url, keys=("得点", "PTS", "選手", "身長"), max_tables=3):
    text = fetch(url, tries=1)
    if not text:
        print(f"== {url}: 抓不到")
        return None, None
    soup = BeautifulSoup(text, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    tables = soup.find_all("table")
    print(f"== {url}: len={len(text)} title={title!r} tables={len(tables)} next={'__NEXT_DATA__' in text} nuxt={'__NUXT__' in text} selects={len(soup.find_all('select'))}")
    for i, tb in enumerate(tables[:max_tables]):
        trs = tb.find_all("tr")
        head = [th.get_text(" ", strip=True) for th in trs[0].find_all(["th", "td"])][:18] if trs else []
        row = next(([td.get_text(" ", strip=True) for td in tr.find_all("td")][:18] for tr in trs[1:] if tr.find_all("td")), [])
        print(f"   table{i}: rows={len(trs)} class={tb.get('class')} head={head} row={row}")
    for sel in soup.find_all("select")[:6]:
        opts = [(o.get("value"), o.get_text(strip=True)) for o in sel.find_all("option")][:8]
        print(f"   select name={sel.get('name')} id={sel.get('id')} opts={opts}")
    hrefs = []
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if re.search(r"roster|player|stats|club|team|member|ranking", h, re.I) and h not in hrefs:
            hrefs.append(h)
    print(f"   links({len(hrefs)}): {hrefs[:30]}")
    apis = sorted(set(re.findall(r"https?://[^\"'\s<>]*(?:api|json|ajax)[^\"'\s<>]*", text)))[:10]
    print(f"   api-ish: {apis}")
    forms = [(f.get("action"), f.get("method"), [i.get("name") for i in f.find_all(["input", "select"])][:10]) for f in soup.find_all("form")][:4]
    if forms:
        print(f"   forms: {forms}")
    for k in keys:
        i = text.find(k)
        if i >= 0:
            snippet = re.sub(r"\s+", " ", text[max(0, i - 400): i + 900])
            print(f"   around {k!r}: {snippet}")
            break
    return text, soup


def snippet(text, key, before=200, after=1500, nth=0):
    idx = -1
    for _ in range(nth + 1):
        idx = text.find(key, idx + 1)
        if idx < 0:
            return None
    return re.sub(r"\s+", " ", text[max(0, idx - before): idx + after])


def main():
    print("######## B.LEAGUE club_detail")
    text, soup = describe("https://www.bleague.jp/club_detail/?TeamID=706", keys=("選手",), max_tables=6)
    if text:
        for i, tb in enumerate(soup.find_all("table")):
            head = [th.get_text(" ", strip=True) for th in tb.find_all("th")][:20]
            if any("選手" in h for h in head):
                trs = tb.find_all("tr")
                print(f"   player-table{i}: rows={len(trs)} head={head}")
                for tr in trs[1:4]:
                    print("      row:", [td.get_text(" ", strip=True) for td in tr.find_all("td")][:20])
                    a = tr.find("a", href=True)
                    print("      link:", a["href"] if a else None, "| html:", re.sub(r"\s+", " ", str(tr))[:600])
        print("   around roster_detail (2nd):", snippet(text, "roster_detail", 600, 1400, nth=1))
        print("   around clubDetail-leader:", snippet(text, "clubDetail-leader", 100, 1200))
    print("######## B.LEAGUE roster list")
    text, soup = describe("https://www.bleague.jp/roster/?year=2026&club=706&e=%E5%9C%A8%E7%B1%8D%E4%B8%AD", keys=("選手",), max_tables=2)
    if text:
        n = len(re.findall(r"roster_detail/\?PlayerID=", text))
        print(f"   roster_detail links: {n}")
        print("   around roster_detail (1st):", snippet(text, "roster_detail", 800, 1600))
    print("######## B.LEAGUE stats with params")
    text, soup = describe("https://www.bleague.jp/stats/?year=2026&data=avg&club=706&event=2&tab=1", keys=("得点",), max_tables=2)
    if text:
        print("   around player_b1_more:", snippet(text, "player_b1_more", 1500, 1500))
        print("   around 'ajax' :", snippet(text, "ajax(", 800, 1200))
        print("   around '.php':", snippet(text, ".php", 400, 600))
    print("######## SV.LEAGUE team/player")
    for u in ("https://www.svleague.jp/team/tokyogb/player/", "https://www.svleague.jp/team/tokyogb/", "https://www.svleague.jp/record/",
              "https://www.svleague.jp/match/detail/37992/"):
        text, soup = describe(u, keys=("選手", "得点"), max_tables=4)
        if not text:
            continue
        main = soup.find("main") or soup.find(class_="content-main") or soup
        body_text = re.sub(r"\s+", " ", main.get_text(" ", strip=True))
        print("   text:", body_text[:1200])
        for cls in ("player", "member", "roster", "card", "list"):
            el = main.find(class_=re.compile(cls))
            if el is not None:
                print(f"   first .{cls}:", re.sub(r"\s+", " ", str(el))[:1500])
                break
        if "record" in u:
            print("   record links:", [a["href"] for a in main.find_all("a", href=True)][:40])


if __name__ == "__main__":
    main()
