# -*- coding: utf-8 -*-
"""歐冠、歐盃每場的球員數據（官方 live.euroleague.net 的 Boxscore）。

拿來看三件事（老球迷看球員近況的方式）：
  1. 主力手感：近 5 場得分 vs 本季平均（跟 NBA 一樣的火燙／冰冷）
  2. 上場時間：最近 3 場是不是比平常少很多（教練在控制、或帶傷）
  3. 上一場有沒有上：平常打 18 分鐘以上的人，上一場名單上沒有或 0 分鐘，多半是受傷或輪休
打完的比賽存在 data/el_box.json 不重抓；每次最多抓 MAX_CALLS 場，慢慢補齊。"""
import json
import os
import re
import time
import unicodedata
from statistics import mean

import requests

URL = "https://live.euroleague.net/api/Boxscore"
MAX_CALLS = 60
HOT_MIN = 8.0
STAR_MIN = 18.0


def _mins(v):
    if v is None:
        return 0.0
    s = str(v).strip()
    if not s or s.upper().startswith("DNP"):
        return 0.0
    m = re.match(r"^(\d+):(\d+)$", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60
    try:
        return float(s)
    except ValueError:
        return 0.0


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def display_name(raw):
    """「LLULL, SERGIO」→「Sergio Llull」。"""
    raw = (raw or "").strip()
    if "," in raw:
        last, first = [x.strip() for x in raw.split(",", 1)]
        raw = f"{first} {last}"
    return " ".join(w.capitalize() if w.isupper() else w for w in raw.split())


def name_key(name):
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return " ".join(sorted(re.findall(r"[a-z]+", s)))


class Box:
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
        self.calls = 0
        self.sample = None

    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, separators=(",", ":"))

    def _fetch(self, season, code):
        self.calls += 1
        try:
            r = requests.get(URL, params={"gamecode": code, "seasoncode": season}, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200 or not r.text.strip().startswith("{"):
                return None
            js = r.json()
        except Exception:  # noqa: BLE001
            return None
        teams = {}
        for st in js.get("Stats") or []:
            for p in st.get("PlayersStats") or []:
                tc = str(p.get("Team") or "").strip()
                if not tc:
                    continue
                teams.setdefault(tc, []).append([display_name(p.get("Player")), round(_mins(p.get("Minutes")), 1), int(_num(p.get("Points"))), 1 if p.get("IsStarter") else 0])
        if self.sample is None and js.get("Stats"):
            st0 = js["Stats"][0]
            self.sample = dict(keys=list(js.keys())[:12], team=st0.get("Team"), player=(st0.get("PlayersStats") or [{}])[0])
        return teams or None

    def sync(self, el, codes_needed):
        """有比賽的球隊（codes_needed）：本季打完、還沒存的歐戰比賽抓下來。"""
        from euroleague import season_code
        n_new = 0
        for og in sorted(el.games, key=lambda x: x["start"] or 0, reverse=True):
            if self.calls >= MAX_CALLS:
                break
            if not og.get("played") or og.get("code") is None or not og.get("start"):
                continue
            if og["home"] not in codes_needed and og["away"] not in codes_needed:
                continue
            season = season_code(og["comp"])
            S = self.data.setdefault(season, {})
            key = str(og["code"])
            if key in S:
                continue
            teams = self._fetch(season, og["code"])
            if teams:
                S[key] = dict(ts=int(og["start"].timestamp()), home=og["home"], away=og["away"], teams=teams)
                n_new += 1
            time.sleep(0.3)
        self.log(f"[eurobasket] 歐戰球員數據：新抓 {n_new} 場（查了 {self.calls} 次），共 {sum(len(v) for v in self.data.values())} 場"
                 + (f"；樣本 {json.dumps(self.sample, ensure_ascii=False)[:300]}" if self.sample else ""))

    def team_log(self, code):
        """這隊每場的球員數據，由舊到新：[(ts, {球員: (分鐘, 得分, 先發)})]。"""
        rows = []
        for S in self.data.values():
            for g in S.values():
                if code in (g.get("home"), g.get("away")) and code in (g.get("teams") or {}):
                    rows.append((g["ts"], {p[0]: (p[1], p[2], p[3]) for p in g["teams"][code]}))
        rows.sort(key=lambda r: r[0])
        return rows


def apply(games, box, log):
    """球隊加上：hot（主力近 5 場 vs 本季）、上一場沒上的主力（當成可能缺陣）。"""
    from players import team_impact
    n_hot = n_dnp = 0
    done = {}
    for g in games:
        if g["status"]["state"] == "post":
            continue
        for side in ("home", "away"):
            t = g[side]
            code = t.get("el_code")
            if not code:
                continue
            if code not in done:
                done[code] = _analyze(box.team_log(code))
            hot, dnp = done[code]
            if hot:
                t["hot"] = hot
                n_hot += 1
            if dnp:
                have = {name_key(x.get("player")) for x in t.get("injuries") or []}
                add = [x for x in dnp if name_key(x["player"]) not in have]
                if add:
                    t["injuries"] = (t.get("injuries") or []) + [dict(x) for x in add]
                    imp = team_impact(t, "el")
                    if imp and imp.get("players"):
                        imp["note"] = "從傷兵報告、新聞和官方數據（上一場沒上）對到球員，依場均得分估算"
                        t["injury_impact"] = imp
                    n_dnp += 1
    log(f"[eurobasket] 球員近況：{n_hot} 隊算出主力手感，{n_dnp} 隊有主力上一場沒上")


def _analyze(rows):
    if len(rows) < 3:
        return [], []
    per = {}
    for i, (_ts, ps) in enumerate(rows):
        for name, (mn, pts, st) in ps.items():
            per.setdefault(name, []).append((i, mn, pts, st))
    last_i = len(rows) - 1
    hot, dnp = [], []
    for name, lst in per.items():
        played = [x for x in lst if x[1] > 0]
        if len(played) < 3:
            continue
        season_pts = mean(x[2] for x in played)
        season_min = mean(x[1] for x in played)
        last5 = played[-5:]
        l5 = mean(x[2] for x in last5)
        delta = (l5 - season_pts) / season_pts * 100 if season_pts > 0 else 0
        label = "平穩"
        if delta >= 15 and l5 >= HOT_MIN:
            label = "火燙"
        elif delta <= -15 and season_pts >= HOT_MIN:
            label = "冰冷"
        min3 = [x[1] for x in played[-3:]]
        base = [x[1] for x in played[:-3]]
        entry = dict(player=name, stat="PTS", last5=round(l5, 1), season=round(season_pts, 1), delta_pct=round(delta), label=label,
                     n_games=len(played), min_last3=round(mean(min3), 1), min_base=round(mean(base), 1) if len(base) >= 3 else None,
                     season_name="歐戰官方數據", games=[dict(v=x[2], mins=x[1]) for x in last5])
        hot.append(entry)
        # 主力上一場沒上：平常打 18 分鐘以上、這季至少 3 場，上一場名單沒有或 0 分鐘
        missed = [i for i in (last_i, last_i - 1) if i >= 0 and not any(x[0] == i and x[1] > 0 for x in lst)]
        if season_min >= STAR_MIN and last_i in missed:
            two = (last_i - 1) in missed
            dnp.append(dict(id=None, player=name, headshot=None, position=None, status="DNP", status_zh="上一場沒上",
                            severity="maybe", sev0="maybe", official=False, source="歐戰官方數據",
                            detail=("最近兩場都沒上場" if two else "上一場沒有上場") + f"（平常場均 {season_min:.0f} 分鐘、{season_pts:.1f} 分），可能受傷或輪休",
                            ppg=round(season_pts, 1), mpg=round(season_min, 1), return_date=None, comment=None, url=None))
    hot.sort(key=lambda x: -x["season"])
    return hot[:3], dnp
