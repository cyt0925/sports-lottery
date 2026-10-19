# -*- coding: utf-8 -*-
"""NBA 兩季所有比賽的比分（ESPN 比分板，一次查半個月），給逐場實力分（elo.py）用。

打完的半個月存在 data/espn_games.json 不重抓；每次只重抓最近幾天。季前賽、明星賽不算。"""
import json
import os
from datetime import date, datetime, timedelta, timezone

UTC = timezone.utc
CHUNK_D = 15
SEASON_START = (10, 1)
SEASON_END = (6, 30)


def _season_ranges(end_year, today):
    """這一季（end_year = 2026 代表 2025-26）從 10/1 到 6/30，切成半個月一段。"""
    d = date(end_year - 1, *SEASON_START)
    last = min(date(end_year, *SEASON_END), today)
    out = []
    while d <= last:
        e = min(d + timedelta(days=CHUNK_D - 1), last)
        out.append((d, e))
        d = e + timedelta(days=1)
    return out


class Store:
    def __init__(self, path, log, errors):
        self.path, self.log, self.errors = path, log, errors
        self.data = {}
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                self.data = d
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, separators=(",", ":"))

    def sync(self, get, site, lg_key, path, season_year, max_calls=30):
        """season_year：這季的結束年（players._season_year()）。上季整季補齊，這季補到今天、最近 3 天每次重抓。"""
        today = datetime.now(UTC).date()
        L = self.data.setdefault(lg_key, {})
        calls = new = 0
        for yr in (season_year - 1, season_year):
            S = L.setdefault(str(yr), dict(games={}, done=[]))
            for d0, d1 in _season_ranges(yr, today):
                tag = f"{d0:%Y%m%d}-{d1:%Y%m%d}"
                if tag in S["done"]:
                    continue
                if calls >= max_calls:
                    break
                calls += 1
                js = get(f"{site}/{path}/scoreboard", params={"dates": tag, "limit": 1000}, quiet=True)
                if not isinstance(js, dict):
                    continue
                for ev in js.get("events") or []:
                    row = _row(ev)
                    if row:
                        if ev["id"] not in S["games"]:
                            new += 1
                        S["games"][str(ev["id"])] = row
                if d1 < today - timedelta(days=3):
                    S["done"].append(tag)
        n = sum(len(S["games"]) for S in L.values())
        self.log(f"[{lg_key}] 兩季比分：查了 {calls} 次、新增 {new} 場，共 {n} 場")
        return calls

    def games(self, lg_key, season_year):
        """[(ts, 主隊, 客隊, 主分, 客分, 中立, 第幾季 0=上季 1=這季)]，由舊到新。"""
        out = []
        L = self.data.get(lg_key) or {}
        for idx, yr in ((0, season_year - 1), (1, season_year)):
            for row in ((L.get(str(yr)) or {}).get("games") or {}).values():
                out.append(tuple(row) + (idx,))
        out.sort(key=lambda r: r[0])
        return out


def _row(ev):
    st = ((ev.get("status") or {}).get("type") or {})
    if not st.get("completed"):
        return None
    stype = (ev.get("season") or {}).get("type")
    if stype not in (2, 3, 5):      # 季前賽（1）、明星賽不算
        return None
    comp = (ev.get("competitions") or [{}])[0]
    cs = comp.get("competitors") or []
    h = next((c for c in cs if c.get("homeAway") == "home"), None)
    a = next((c for c in cs if c.get("homeAway") == "away"), None)
    if not h or not a:
        return None
    try:
        hs, as_ = int(float(h.get("score"))), int(float(a.get("score")))
        dt = datetime.fromisoformat((comp.get("date") or ev.get("date")).replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        return None
    return [int(dt.timestamp()), str((h.get("team") or {}).get("id")), str((a.get("team") or {}).get("id")), hs, as_, bool(comp.get("neutralSite"))]
