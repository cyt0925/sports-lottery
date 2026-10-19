# -*- coding: utf-8 -*-
"""歐洲各國國內籃球聯賽：TheSportsDB 免費版（www.thesportsdb.com，金鑰 123）。

台灣運彩有開這些聯賽，但官網只開放台灣的網路，網站主機（在美國）讀不到賠率，所以這些比賽只有我們自己的分析。
免費版的限制：整季列表只給 15 場、問太快會被擋（大約一分鐘 10 次）；但「一輪一輪」查可以拿到整輪的比賽和比分。
所以打完的輪次存在 data/tsdb.json 不再重抓，每次只重抓快要打、正在打、剛打完的輪次，剩下的次數慢慢補本季和上季缺的輪次。
上季的戰績拿來當開季的實力底子（跟 NBA 一樣：開季場數少，先看上季）。"""
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

B = "https://www.thesportsdb.com/api/v1/json/123"
UTC = timezone.utc
TW = timezone(timedelta(hours=8))
GAP_S = 6.5          # 每次查詢間隔（免費版問太快會被擋）
RUN_CALLS = 28       # 每次更新最多查幾次（大約 3 分鐘）
TIME_CAP = 200       # 最多花幾秒（對方回得慢的時候，不要拖累整個更新）
REFRESH_MIN = 50     # 快要打、正在打、剛打完的輪次，多久重抓一次
EMPTY_RETRY_H = 6    # 還沒排出來的下一輪，隔多久再問一次
LEAGUES = [
    dict(id="4408", key="acb", zh="西班牙聯賽", hca=3.0),
    dict(id="4433", key="lba", zh="義大利聯賽", hca=3.0),
    dict(id="4475", key="bsl", zh="土耳其聯賽", hca=3.5),
    dict(id="4452", key="gbl", zh="希臘聯賽", hca=3.5),
    dict(id="4423", key="lnb", zh="法國聯賽", hca=3.0),
    dict(id="4441", key="bbl", zh="德國聯賽", hca=3.0),
    dict(id="4478", key="lkl", zh="立陶宛聯賽", hca=3.0),
    dict(id="4474", key="isr", zh="以色列聯賽", hca=3.0),
    dict(id=None, key="aba", zh="亞得里亞海聯賽", hca=3.5, find=("Partizan", "Crvena Zvezda", "Spartak Subotica")),
]


def season_of(now):
    y = now.year if now.month >= 8 else now.year - 1
    return f"{y}-{y + 1}", f"{y - 1}-{y}"


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _ts(e):
    s = (e.get("strTimestamp") or "").strip()
    if s:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return int((dt if dt.tzinfo else dt.replace(tzinfo=UTC)).timestamp())
        except ValueError:
            pass
    d, t = (e.get("dateEvent") or "").strip(), (e.get("strTime") or "00:00:00").strip()[:8]
    if not d:
        return None
    try:
        return int(datetime.fromisoformat(f"{d}T{t or '00:00:00'}").replace(tzinfo=UTC).timestamp())
    except ValueError:
        return None


class TSDB:
    def __init__(self, path, log, errors):
        self.path, self.log, self.errors = path, log, errors
        self.calls = 0
        self.blocked = False
        self._last = 0.0
        self.data = dict(v=1, leagues={}, teams={})
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and d.get("v") == 1:
                self.data = d
        except (OSError, ValueError):
            pass
        self.data.setdefault("leagues", {})
        self.data.setdefault("teams", {})
        self.stats = dict(fetched=0, new_rounds=0, refreshed=0, prev=0)

    # ---------- 查詢 ----------
    def _get(self, path, **params):
        if self.blocked or self.calls >= RUN_CALLS:
            return None
        for attempt in range(2):
            wait = GAP_S - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            self.calls += 1
            try:
                r = requests.get(f"{B}/{path}", params=params, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                txt = r.text.strip()
                if r.status_code == 200 and txt.startswith("{"):
                    return r.json()
            except Exception:  # noqa: BLE001
                pass
            if attempt == 0:
                time.sleep(25)       # 多半是問太快被擋：等一下再試一次
        self.blocked = True
        self.errors.append(f"國內聯賽 TheSportsDB 問太快被擋，這次先停（{path}）")
        return None

    def _round(self, lid, season, r):
        d = self._get("eventsround.php", id=lid, r=r, s=season)
        if d is None:
            return None
        ev = []
        for e in d.get("events") or []:
            ts = _ts(e)
            hid, aid = str(e.get("idHomeTeam") or ""), str(e.get("idAwayTeam") or "")
            if not hid or not aid or ts is None:
                continue
            for tid, nm, badge in ((hid, e.get("strHomeTeam"), e.get("strHomeTeamBadge")), (aid, e.get("strAwayTeam"), e.get("strAwayTeamBadge"))):
                old = self.data["teams"].get(tid) or [None, None]
                self.data["teams"][tid] = [nm or old[0], badge or old[1]]
            status = (e.get("strStatus") or "").strip()
            if (e.get("strPostponed") or "").lower() == "yes":
                status = "Postponed"
            ev.append([str(e.get("idEvent")), ts, hid, aid, _int(e.get("intHomeScore")), _int(e.get("intAwayScore")), status, (e.get("strVenue") or "")[:40]])
        self.stats["fetched"] += 1
        return ev

    # ---------- 同步 ----------
    def _league_id(self, lg):
        if lg["id"]:
            return lg["id"]
        known = self.data.get("ids", {}).get(lg["key"])
        if known:
            return known
        if self.data.get("ids_tried", {}).get(lg["key"], 0) > time.time() - 86400:
            return None
        self.data.setdefault("ids_tried", {})[lg["key"]] = time.time()
        seen = []
        for team in lg.get("find") or ():
            d = self._get("searchteams.php", t=team)
            seen.append(f"{team}：{len((d or {}).get('teams') or [])} 隊")
            for t in (d or {}).get("teams") or []:
                if (t.get("strSport") or "") != "Basketball":
                    continue
                pairs = [(t.get("idLeague"), t.get("strLeague"))] + [(t.get(f"idLeague{i}"), t.get(f"strLeague{i}")) for i in range(2, 8)]
                self.log(f"[eurodom] 找聯賽代碼：{t.get('strTeam')} 參加 {[p for p in pairs if p[0]]}")
                for lid, name in pairs:
                    if lid and name and any(k in name for k in ("ABA", "Adriatic")):
                        self.data.setdefault("ids", {})[lg["key"]] = str(lid)
                        return str(lid)
        self.log(f"[eurodom] {lg['zh']}的聯賽代碼找不到（{'、'.join(seen)}），明天再找")
        return None

    def _plan(self, tnow, cur, prev):
        """還要查哪些輪次：(優先順序, 次序, 聯賽代碼, 球季, 輪次, 原因)。"""
        jobs = []
        for lg in LEAGUES:
            lid = self._league_id(lg)
            if not lid:
                continue
            L = self.data["leagues"].setdefault(lid, dict(key=lg["key"], seasons={}))
            S = L["seasons"].setdefault(cur, dict(rounds={}, empty={}))
            R = S["rounds"]
            have_n = len(R)
            if not R:
                if tnow - S["empty"].get("1", 0) >= EMPTY_RETRY_H * 3600:
                    jobs.append((1, 0, lid, cur, 1, "new"))
            for r, rd in R.items():
                evs = rd.get("ev") or []
                near = any(tnow - 2 * 86400 <= e[1] <= tnow + 4 * 86400 for e in evs)
                open_ = any(e[4] is None and tnow - 5 * 86400 <= e[1] <= tnow + 4 * 86400 and e[6] != "Postponed" for e in evs)
                if (near or open_) and tnow - rd.get("t", 0) >= REFRESH_MIN * 60:
                    soon = min((abs(e[1] - tnow) for e in evs), default=9e9)
                    jobs.append((0, soon, lid, cur, int(r), "refresh"))
            if R:
                mx = max(int(r) for r in R)
                last_ts = max((e[1] for e in R[str(mx)].get("ev") or []), default=0)
                # 大部分聯賽一週一輪：照日期估現在打到第幾輪，直接跳過去（中間的之後再補）
                jump = mx + int((tnow - last_ts) // (7 * 86400))
                if jump > mx + 1 and tnow - S["empty"].get(str(jump), 0) >= EMPTY_RETRY_H * 3600:
                    jobs.append((1, have_n, lid, cur, jump, "next"))
                elif last_ts <= tnow + 4 * 86400 and tnow - S["empty"].get(str(mx + 1), 0) >= EMPTY_RETRY_H * 3600:
                    jobs.append((1, have_n, lid, cur, mx + 1, "next"))
                for r in range(1, mx):
                    if str(r) not in R and tnow - S["empty"].get(str(r), 0) >= 86400:
                        jobs.append((2, r, lid, cur, r, "backfill"))
            # 上季：從第 1 輪往後補，補到空的輪次為止
            P = L["seasons"].setdefault(prev, dict(rounds={}, empty={}, done=False))
            if not P.get("done"):
                have = [int(r) for r in P["rounds"]]
                jobs.append((3, len(have), lid, prev, (max(have) + 1) if have else 1, "prev"))
        return jobs

    def sync(self, now=None):
        now = now or datetime.now(UTC)
        cur, prev = season_of(now)
        t0 = time.time()
        while not self.blocked and self.calls < RUN_CALLS and time.time() - t0 < TIME_CAP:
            jobs = self._plan(now.timestamp(), cur, prev)
            if not jobs:
                break
            _p, _o, lid, season, r, why = min(jobs)
            ev = self._round(lid, season, r)
            if ev is None:
                break
            S = self.data["leagues"][lid]["seasons"][season]
            if ev:
                is_new = str(r) not in S["rounds"]
                S["rounds"][str(r)] = dict(t=int(time.time()), ev=ev)
                key = "prev" if why == "prev" else ("new_rounds" if is_new else "refreshed")
                self.stats[key] += 1
            else:
                S["empty"][str(r)] = int(time.time())
                if why == "prev":
                    S["done"] = True
                elif why == "refresh":
                    S["rounds"][str(r)]["t"] = int(time.time())
        n_ev = sum(len(rd.get("ev") or []) for L in self.data["leagues"].values() for S in (L.get("seasons") or {}).values() for rd in (S.get("rounds") or {}).values())
        self.log(f"[eurodom] TheSportsDB：{time.time() - t0:.0f} 秒查了 {self.calls} 次（新輪次 {self.stats['new_rounds']}、重抓 {self.stats['refreshed']}、上季 {self.stats['prev']}），"
                 f"存了 {n_ev} 場" + ("；問太快被擋，下次再補" if self.blocked else ""))

    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, separators=(",", ":"))

    # ---------- 整理 ----------
    def league_meta(self, lid):
        key = (self.data["leagues"].get(lid) or {}).get("key")
        return next((lg for lg in LEAGUES if lg["key"] == key), None)

    def events(self, season):
        """[(聯賽 meta, 輪次, event)]"""
        out = []
        for lid, L in self.data["leagues"].items():
            meta = self.league_meta(lid)
            S = (L.get("seasons") or {}).get(season) or {}
            for r, rd in (S.get("rounds") or {}).items():
                for e in rd.get("ev") or []:
                    out.append((meta, int(r), e))
        out.sort(key=lambda x: x[2][1])
        return out

    def progress(self, season):
        """{聯賽 key: (抓完了沒, 抓到第幾輪)}：上季還在慢慢補的時候，講上季戰績要說「前幾輪」。"""
        out = {}
        for lid, L in self.data["leagues"].items():
            meta = self.league_meta(lid)
            S = (L.get("seasons") or {}).get(season) or {}
            if meta and S.get("rounds"):
                out[meta["key"]] = (bool(S.get("done")), max(int(r) for r in S["rounds"]))
        return out

    def team(self, tid):
        nm, badge = self.data["teams"].get(tid) or [None, None]
        return nm or tid, badge

    def table(self, season, before_ts=None):
        """每個聯賽的戰績表：{聯賽 key: {team_id: dict(w, l, gp, pf, pa)}}（只算打完的）。"""
        out = {}
        for meta, _r, e in self.events(season):
            if not meta or e[4] is None or e[5] is None or (before_ts and e[1] >= before_ts):
                continue
            tab = out.setdefault(meta["key"], {})
            for tid, pf, pa in ((e[2], e[4], e[5]), (e[3], e[5], e[4])):
                s = tab.setdefault(tid, dict(w=0, l=0, gp=0, pf=0.0, pa=0.0))
                s["gp"] += 1
                s["pf"] += pf
                s["pa"] += pa
                s["w" if pf > pa else "l"] += 1
        return out

    def results(self, season):
        """每隊打完的比賽（由舊到新），格式跟其他聯盟的近況列一樣。"""
        out = {}
        for meta, r, e in self.events(season):
            if not meta or e[4] is None or e[5] is None:
                continue
            for me, opp, home, pf, pa in ((e[2], e[3], True, e[4], e[5]), (e[3], e[2], False, e[5], e[4])):
                onm, obadge = self.team(opp)
                out.setdefault(me, []).append(dict(
                    ts=e[1], date_iso=datetime.fromtimestamp(e[1], UTC).isoformat(timespec="minutes"),
                    date=datetime.fromtimestamp(e[1], TW).strftime("%m/%d"),
                    opp=onm, opp_id=f"tsdb{opp}", opp_logo=obadge, home=home, pf=pf, pa=pa,
                    result="W" if pf > pa else ("L" if pf < pa else "D"), comp=meta["zh"], round=r))
        return out


class Loader:
    """背景先把資料抓好（每次要等好幾秒，跟其他聯盟一起跑比較快）。"""

    def __init__(self, path, log, errors):
        self.td = TSDB(path, log, errors)
        self.err = None
        self.th = threading.Thread(target=self._run, daemon=True)
        self.th.start()

    def _run(self):
        try:
            self.td.sync()
        except Exception as e:  # noqa: BLE001
            self.err = e

    def get(self):
        self.th.join(timeout=600)
        if self.err:
            self.td.errors.append(f"國內聯賽同步失敗: {self.err!r}")
        return self.td


def link_clubs(td, names):
    """歐冠、歐盃官方的球隊（代碼 -> 英文隊名）對到國內聯賽的球隊代碼；對不到、或對到兩隊以上的就不對。"""
    from eurodom_names import same_club
    out = {}
    teams = [(tid, v[0]) for tid, v in td.data["teams"].items() if v and v[0]]
    for code, nm in names.items():
        hits = [tid for tid, tn in teams if same_club(nm, tn)]
        if len(hits) == 1:
            out[code] = hits[0]
    return out
