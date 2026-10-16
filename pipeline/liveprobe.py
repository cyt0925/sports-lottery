# -*- coding: utf-8 -*-
"""探路：哪些即時比分來源允許網頁直接抓（CORS），以及 ESPN 球員出賽紀錄（上場時間）的格式。只印，不改資料。"""
import json
import re
from datetime import datetime, timedelta, timezone

import requests

ORIGIN = "https://cyt0925.github.io"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Origin": ORIGIN, "Referer": ORIGIN + "/sports-lottery/"}
TW = timezone(timedelta(hours=8))
today = datetime.now(TW).strftime("%Y%m%d")


def cors(url, label):
    try:
        r = requests.get(url, headers=UA, timeout=20)
        h = {k.lower(): v for k, v in r.headers.items()}
        print(f"[CORS] {label}: {r.status_code} allow-origin={h.get('access-control-allow-origin')!r} cache={h.get('cache-control')!r} type={h.get('content-type')!r} len={len(r.content)}")
        return r
    except Exception as e:  # noqa: BLE001
        print(f"[CORS] {label}: 失敗 {e!r}")
        return None


def main():
    cors("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard", "ESPN NBA scoreboard")
    cors("https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard", "ESPN NHL scoreboard")
    cors("https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/scoreboard", "ESPN soccer scoreboard")
    r = cors(f"https://ls.playsport.cc/ls_json.php?alliance=8&gamedate={today}", "玩運彩 即時比分 歐籃")
    if r is not None and r.ok:
        try:
            d = r.json()
            k = next(iter(d))
            print("   樣本:", json.dumps(d[k], ensure_ascii=False)[:400])
        except Exception as e:  # noqa: BLE001
            print("   不是 JSON", e, r.text[:200])
    cors(f"https://ls.playsport.cc/ls_json.php?alliance=97&gamedate={today}", "玩運彩 即時比分 日籃")
    cors("https://api-live.euroleague.net/v2/competitions/E/seasons/E2026/games?teamCode=", "EuroLeague 官方賽程")
    cors("https://live.euroleague.net/api/Header?gamecode=1&seasoncode=E2026", "EuroLeague live Header")
    cors("https://www.svleague.jp/", "SV.LEAGUE 首頁")
    cors("https://raw.githubusercontent.com/cyt0925/sports-lottery/main/data/today.json", "GitHub raw")

    # ESPN 出賽紀錄：上場時間欄位、季別、事件日期
    for season in (None, 2026):
        url = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/6450/gamelog"
        r = requests.get(url, params={"season": season} if season else None, headers=UA, timeout=20)
        if not r.ok:
            print(f"[gamelog] season={season} -> {r.status_code}")
            continue
        d = r.json()
        labels = d.get("labels")
        print(f"[gamelog] Kawhi season={season} labels={labels}")
        ev = d.get("events") or {}
        for st in d.get("seasonTypes") or []:
            cats = st.get("categories") or []
            n = sum(len(c.get("events") or []) for c in cats)
            print(f"   seasonType {st.get('displayName')!r} events={n} cats={[c.get('displayName') or c.get('type') for c in cats][:6]}")
            for c in cats[:1]:
                for e in (c.get("events") or [])[:2]:
                    m = ev.get(str(e.get("eventId"))) or {}
                    print("     ", e.get("stats"), "|", {k: m.get(k) for k in ("gameDate", "atVs", "homeTeamId", "awayTeamId", "gameResult", "score")}, (m.get("opponent") or {}).get("abbreviation"))
    # Kawhi 現在在哪一隊
    r = requests.get("https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/6450", headers=UA, timeout=20)
    if r.ok:
        a = (r.json().get("athlete") or {})
        print("[athlete] Kawhi team:", (a.get("team") or {}).get("displayName"), "| status:", (a.get("status") or {}).get("name"), "| injuries:", json.dumps(a.get("injuries") or [], ensure_ascii=False)[:300])
    # 球隊上季賽程（背靠背輪休要用）
    r = requests.get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/28/schedule", params={"season": 2026, "seasontype": 2}, headers=UA, timeout=20)
    if r.ok:
        evs = r.json().get("events") or []
        print(f"[schedule] 暴龍 2025-26 例行賽 {len(evs)} 場；第一場 {evs[0].get('date') if evs else None}")
    # 球隊數據（打法對位用）
    r = requests.get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/28/statistics", headers=UA, timeout=20)
    if r.ok:
        d = r.json()
        res = d.get("results") or d
        cats = ((res.get("stats") or {}).get("categories")) or []
        for c in cats[:4]:
            print("[teamstats]", c.get("name"), [(s.get("name"), s.get("displayValue")) for s in (c.get("stats") or [])][:14])
        print("[teamstats] keys:", list(d.keys())[:10], "season:", (res.get("season") or {}) if isinstance(res, dict) else None)


if __name__ == "__main__":
    main()
