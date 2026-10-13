#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探路第二輪：玩運彩聯盟標籤與球隊近況頁、EuroLeague 排名/數據/傷兵報告、B.LEAGUE、SV.LEAGUE、ESPN NBA 模型勝率（只印 log）。"""
import re
import sys
import json
import time
import html as htmlmod
from datetime import datetime, timedelta, timezone

import requests

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
}
TW = timezone(timedelta(hours=8))
now = datetime.now(TW)
D = {k: (now + timedelta(days=k)).strftime("%Y%m%d") for k in (-3, -2, -1, 0, 1, 2)}


def strip_tags(s):
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", htmlmod.unescape(s)).strip()


def get(url, as_json=False, headers=None):
    try:
        r = requests.get(url, headers=headers or UA, timeout=25)
        print(f"URL {url} -> {r.status_code} len={len(r.text)} type={r.headers.get('content-type')}")
        if r.status_code != 200:
            return None
        return r.json() if as_json else r.text
    except Exception as e:  # noqa: BLE001
        print("FAIL", url, repr(e))
        return None


def sec(title):
    print("=" * 90)
    print("##", title)


def compact(s, n=2500):
    return re.sub(r"\s+", " ", s)[:n]


def main():
    # 1) 玩運彩盤口頁的聯盟標籤與第一場原始碼（歐籃 8、綜合籃賽 121、國際籃賽 110）
    sec("玩運彩 scale 聯盟標籤")
    for aid in (8, 121, 110):
        t = get(f"https://www.playsport.cc/predict/scale?allianceid={aid}&gametime={D[1]}")
        if not t:
            continue
        tags = re.findall(r'<[^>]+class="[^"]*tag-league[^"]*"[^>]*>.*?</[a-z]+>', t, flags=re.S | re.I)
        print(f"   alliance {aid} tag-league 片段 {len(tags)}：", [compact(x, 200) for x in tags[:4]])
        m = re.search(r"<table[^>]*predictgame-table.*?</table>", t, flags=re.S | re.I)
        if m:
            tb = m.group(0)
            # 印出表格裡 th/tr 之外的「分組列」：含 tag 或 colspan 的列
            rows = re.findall(r"<tr.*?</tr>", tb, flags=re.S | re.I)
            print("   rows:", len(rows))
            for tr in rows[:6]:
                print("   RAW ROW:", compact(tr, 1200))
        print("   text:", strip_tags(t)[600:1600])

    # 2) 玩運彩球隊頁（近況）：歐籃 8 的某一隊、日籃 97 的某一隊
    sec("玩運彩 teams 頁原始碼")
    for aid in (8, 97):
        t = get(f"https://www.playsport.cc/gamesData/teams?allianceid={aid}")
        if not t:
            continue
        links = sorted(set(re.findall(r'href="(/gamesData/teams\?allianceid=%d&teamid=\d+[^"]*)"' % aid, t)))
        names = re.findall(r'<a[^>]+href="/gamesData/teams\?allianceid=%d&teamid=(\d+)[^"]*"[^>]*>(.*?)</a>' % aid, t, flags=re.S)
        print(f"   alliance {aid} 球隊連結 {len(links)}：", [(i, strip_tags(n)) for i, n in names[:40]])
        tables = re.findall(r"<table.*?</table>", t, flags=re.S | re.I)
        print(f"   tables={len(tables)}")
        if tables:
            print("   RAW TABLE 0:", compact(tables[0], 3000))
        if len(tables) > 2:
            print("   RAW TABLE 2:", compact(tables[2], 1500))
        if links:
            u = "https://www.playsport.cc" + links[0].replace("&amp;", "&")
            t2 = get(u)
            if t2:
                tables2 = re.findall(r"<table.*?</table>", t2, flags=re.S | re.I)
                print(f"   單隊頁 tables={len(tables2)} title={strip_tags(re.search(r'<title>(.*?)</title>', t2, re.S).group(1)) if re.search(r'<title>(.*?)</title>', t2, re.S) else None}")
                for i, tb in enumerate(tables2[:3]):
                    print(f"   單隊 RAW TABLE {i}:", compact(tb, 2500))
        time.sleep(1)

    # 3) 玩運彩賽果頁：歐籃最近有比賽的一天（往前找）
    sec("玩運彩 result 歐籃/日籃 原始碼")
    for aid in (8, 97):
        for k in (-1, -2, -3):
            t = get(f"https://www.playsport.cc/gamesData/result?allianceid={aid}&gametime={D[k]}")
            if t and "此日無比賽" not in t:
                m = re.search(r"<table[^>]*gamedata-results.*?</table>", t, flags=re.S | re.I)
                if m:
                    print(f"   alliance {aid} {D[k]} RAW:", compact(m.group(0), 4000))
                break
            time.sleep(0.5)

    # 4) EuroLeague：排名、單場數據、傷兵報告
    sec("EuroLeague 排名/數據/傷兵")
    base = "https://api-live.euroleague.net"
    for url in (
        f"{base}/v2/competitions/E/seasons/E2026/standings?phaseTypeCode=RS",
        f"{base}/v1/standings?seasonCode=E2026",
        "https://feeds.incrowdsports.com/provider/euroleague-feeds/v2/competitions/E/seasons/E2026/standings",
        "https://feeds.incrowdsports.com/provider/euroleague-feeds/v2/competitions/E/seasons/E2026/standings?phaseTypeCode=RS",
        f"{base}/v2/competitions/U/seasons/U2026/games",
        f"{base}/v2/competitions/E/seasons/E2026/games/1/stats",
        f"{base}/v2/competitions/E/seasons/E2026/games/1/report",
        f"{base}/v3/competitions/E/statistics/players/traditional?seasonMode=Single&seasonCode=E2026&limit=5",
        f"{base}/v3/competitions/E/statistics/teams/traditional?seasonMode=Single&seasonCode=E2026",
    ):
        t = get(url)
        if t:
            print("   head:", compact(t, 900))
        time.sleep(0.5)
    g = get(f"{base}/v2/competitions/E/seasons/E2026/games", as_json=True)
    if isinstance(g, dict):
        data = g.get("data") or []
        played = [x for x in data if x.get("played")]
        upcoming = [x for x in data if not x.get("played")]
        print(f"   EuroLeague games total={len(data)} played={len(played)} upcoming={len(upcoming)}")
        if played:
            print("   played sample:", json.dumps(played[-1], ensure_ascii=False)[:1500])
        if upcoming:
            print("   upcoming sample keys:", list(upcoming[0].keys()))
    for url in (
        "https://www.euroleaguebasketball.net/euroleague/news/injury-report-round-3-el2627/",
        "https://www.euroleaguebasketball.net/euroleague/news/injury-report-round-2-el2627/",
        "https://www.euroleaguebasketball.net/en/euroleague/news/",
    ):
        time.sleep(2)
        t = get(url, headers={**UA, "Accept": "text/html"})
        if t:
            links = sorted(set(re.findall(r'href="([^"]*injury-report[^"]*)"', t)))
            print("   injury links:", links[:8])
            print("   text:", strip_tags(t)[:1500])

    # 5) B.LEAGUE：找賽程與排名的實際內容
    sec("B.LEAGUE 內容")
    for url in ("https://www.bleague.jp/schedule/?tab=1&year=2026&month=10&event=2&club=", "https://www.bleague.jp/standings/?tab=1"):
        t = get(url)
        if not t:
            continue
        for kw in ("schedule", "game-list", "match", "standings", "ranking", "table", "json", "ajax"):
            idx = [m.start() for m in re.finditer(kw, t)]
            print(f"   '{kw}' 出現 {len(idx)} 次")
        js = re.findall(r'<script[^>]+src="([^"]+)"', t)
        print("   scripts:", js[:15])
        xhr = re.findall(r'["\'](https?://[^"\']+|/[^"\']+)\?[^"\']*(?:year|month|date|club)[^"\']*["\']', t)
        print("   xhr-ish:", sorted(set(xhr))[:15])
        body = strip_tags(t)
        i = body.find("10/")
        print("   text around dates:", body[max(0, i - 200): i + 1500] if i >= 0 else body[1200:2700])

    # 6) SV.LEAGUE：連結與排名頁
    sec("SV.LEAGUE 連結")
    t = get("https://www.svleague.jp/")
    if t:
        hrefs = sorted(set(re.findall(r'href="([^"]+)"', t)))
        print("   links:", [h for h in hrefs if re.search(r"schedule|result|standing|rank|game|match|team|news", h, re.I)][:40])
        m = re.search(r'<a[^>]+href="([^"]*(?:standing|rank)[^"]*)"', t, re.I)
        if m:
            u = m.group(1) if m.group(1).startswith("http") else "https://www.svleague.jp" + m.group(1)
            t2 = get(u)
            if t2:
                print("   standings text:", strip_tags(t2)[:1500])
        # 首頁賽程區塊原始碼
        i = t.find("試合終了")
        print("   RAW around 試合終了:", compact(t[max(0, i - 1500): i + 2500], 4000))

    # 7) ESPN NBA：核心 predictor、againstTheSpread、pickcenter 原始樣本
    sec("ESPN NBA predictor / ATS / pickcenter")
    sb = get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={D[0]}", as_json=True) or {}
    evs = (sb.get("events") or [])
    if evs:
        eid = evs[0]["id"]
        p = get(f"https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events/{eid}/competitions/{eid}/predictor")
        if p:
            print("   predictor:", compact(p, 1200))
        s = get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={eid}", as_json=True) or {}
        print("   againstTheSpread:", json.dumps(s.get("againstTheSpread"), ensure_ascii=False)[:1200])
        pc = s.get("pickcenter") or []
        print("   pickcenter[0]:", json.dumps(pc[0] if pc else None, ensure_ascii=False)[:1800])
        print("   seasonseries:", json.dumps(s.get("seasonseries"), ensure_ascii=False)[:800])
    print("=" * 90)
    print("probe done")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print("probe crashed:", repr(e))
        sys.exit(0)
