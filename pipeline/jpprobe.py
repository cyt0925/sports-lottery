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


def main():
    print("######## B.LEAGUE")
    _, st = describe("https://www.bleague.jp/standings/?tab=1", keys=("順位",), max_tables=1)
    team_links = []
    if st:
        for a in st.select("table a[href]"):
            if a["href"] not in team_links:
                team_links.append(a["href"])
        print(f"   standings team links: {team_links[:30]}")
    for u in ("https://www.bleague.jp/stats/", "https://www.bleague.jp/stats/?tab=1", "https://www.bleague.jp/stats/?tab=2",
              "https://www.bleague.jp/roster/", "https://www.bleague.jp/club/"):
        describe(u)
    for h in team_links[:2]:
        describe(h if h.startswith("http") else "https://www.bleague.jp" + h)
    print("######## SV.LEAGUE")
    _, home = describe("https://www.svleague.jp/", keys=("選手",), max_tables=1)
    links = []
    if home:
        for a in home.find_all("a", href=True):
            h = a["href"]
            if re.search(r"team|member|player|stats|ranking", h, re.I) and h not in links:
                links.append(h)
        print(f"   home links: {links[:40]}")
    for u in ("https://www.svleague.jp/team/", "https://www.svleague.jp/team/sv/men/", "https://www.svleague.jp/team/sv/men/tokyogb/",
              "https://www.svleague.jp/team/detail/tokyogb/", "https://www.svleague.jp/stats/", "https://www.svleague.jp/stats/sv/men/",
              "https://www.svleague.jp/ranking/", "https://www.svleague.jp/player/"):
        describe(u)
    for h in links[:3]:
        if h.startswith("/"):
            describe("https://www.svleague.jp" + h)


if __name__ == "__main__":
    main()
