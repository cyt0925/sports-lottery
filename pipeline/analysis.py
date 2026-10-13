# -*- coding: utf-8 -*-
"""進階分析資料：
- ESPN 單場 summary：模型勝率（predictor）、讓分盤戰績（ATS）、本季對戰、各莊家盤口與開盤/現盤、先發名單、即時勝率、傷兵
- 休息天數與背靠背（從球隊賽程算）
- NBA 官方傷兵報告（官網 PDF，透過 nba-injury-report 套件）
- 把以上整理成「訊號」給建議引擎加減分

所有函式都不能讓主流程掛掉：抓不到就回 None。
"""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TW = ZoneInfo("Asia/Taipei")
ET = ZoneInfo("America/New_York")


def _num(v):
    try:
        if v is None or v == "":
            return None
        return float(str(v).replace("+", ""))
    except (TypeError, ValueError):
        return None


def _dt(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _as_list(x):
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        return [x]
    return []


def _as_dict(x):
    return x if isinstance(x, dict) else {}


def _line_from(block, key="pointSpread"):
    """homeTeamOdds.open / current 裡的讓分或獨贏。"""
    if not isinstance(block, dict):
        return None
    v = block.get(key)
    if isinstance(v, dict):
        return _num(v.get("american") or v.get("alternateDisplayValue") or v.get("displayValue") or v.get("value"))
    return _num(v)


# ---------- ESPN summary ----------
def fetch_summary(lg, g, get, keep_raw, site, ml_from_block):
    d = get(f"{site}/{lg['path']}/summary", params={"event": g["id"]}, quiet=True)
    if not isinstance(d, dict):
        return None
    try:
        keep_raw(f"summary_{lg['key']}", dict(
            keys=list(d.keys()),
            predictor=d.get("predictor"),
            againstTheSpread=d.get("againstTheSpread"),
            seasonseries=_as_list(d.get("seasonseries"))[:1],
            pickcenter=_as_list(d.get("pickcenter"))[:1],
            rosters=[dict(homeAway=_as_dict(r).get("homeAway"), formation=_as_dict(r).get("formation"), roster=_as_list(_as_dict(r).get("roster"))[:2]) for r in _as_list(d.get("rosters"))[:2]],
            injuries=_as_list(d.get("injuries"))[:1],
            winprobability=_as_list(d.get("winprobability"))[-1:],
            lastFiveGames=_as_list(d.get("lastFiveGames"))[:1],
        ))
    except Exception:  # noqa: BLE001
        pass
    out = dict(predictor=None, live_prob=None, ats=None, h2h=None, line_move=None, lineup=None, books=[],
               raw_injuries=_as_list(d.get("injuries")), errors=[])
    hid, aid = str(g["home"]["id"]), str(g["away"]["id"])

    def guard(name, fn):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            import traceback
            tb = traceback.extract_tb(e.__traceback__)[-1]
            out["errors"].append(f"{name}: {e!r} @ {tb.lineno}")

    def _predictor():
        p = _as_dict(d.get("predictor"))
        if not p:
            return
        ht, at = _as_dict(p.get("homeTeam")), _as_dict(p.get("awayTeam"))
        ph = _num(ht.get("gameProjection"))
        pa = _num(at.get("gameProjection"))
        if ph is None and _num(ht.get("teamChanceLoss")) is not None:
            ph = 100 - _num(ht.get("teamChanceLoss"))
        if ph is not None and pa is None:
            pa = 100 - ph
        if pa is not None and ph is None:
            ph = 100 - pa
        if ph is not None and pa is not None and ph + pa > 0:
            s = ph + pa
            out["predictor"] = dict(home=round(ph / s, 3), away=round(pa / s, 3), source="ESPN")
    guard("predictor", _predictor)

    def _ats():
        ats = {}
        for t in _as_list(d.get("againstTheSpread")):
            t = _as_dict(t)
            tid = str(_as_dict(t.get("team")).get("id") or "")
            recs = [r for r in _as_list(t.get("records")) if isinstance(r, dict)]
            rec = next((r for r in recs if "overall" in str(r.get("type") or r.get("name") or "").lower()), recs[0] if recs else None)
            if tid and rec and rec.get("summary"):
                ats[tid] = rec.get("summary")
        if ats:
            out["ats"] = dict(home=ats.get(hid), away=ats.get(aid))
    guard("ats", _ats)

    def _h2h():
        games = []
        summary = None
        for ss in _as_list(d.get("seasonseries")):
            ss = _as_dict(ss)
            summary = summary or ss.get("summary")
            for ev in _as_list(ss.get("events")):
                ev = _as_dict(ev)
                st = _as_dict(_as_dict(ev.get("status")).get("type"))
                comps = [c for c in _as_list(ev.get("competitors")) if isinstance(c, dict)]
            if len(comps) < 2:
                continue
            if st and not st.get("completed", True):
                continue
            home_c = next((c for c in comps if c.get("homeAway") == "home"), comps[0])
            away_c = next((c for c in comps if c.get("homeAway") == "away"), comps[1])
            hs, a_s = _num(home_c.get("score")), _num(away_c.get("score"))
            if hs is None or a_s is None:
                continue
            def abbr(c):
                t = c.get("team") or {}
                a = t.get("abbreviation")
                if a:
                    return a
                return g["home"]["abbr"] if str(c.get("id")) == hid else (g["away"]["abbr"] if str(c.get("id")) == aid else "?")
            dt = _dt(ev.get("date"))
            # 以「這場比賽」的主客隊視角標勝方
            h_is_our_home = str(home_c.get("id") or (home_c.get("team") or {}).get("id")) == hid
            winner = "home" if hs > a_s else ("away" if a_s > hs else "draw")
            if not h_is_our_home and winner != "draw":
                winner = "away" if winner == "home" else "home"
            games.append(dict(date=dt.astimezone(TW).strftime("%m/%d") if dt else "", home=abbr(home_c), away=abbr(away_c),
                              hs=int(hs), **{"as": int(a_s)}, winner=winner, ts=dt.timestamp() if dt else 0))
        if games:
            games.sort(key=lambda x: -x["ts"])
            for x in games:
                x.pop("ts", None)
            out["h2h"] = dict(summary=summary, games=games[:6])
    guard("h2h", _h2h)

    books = []

    def _books():
        for o in _as_list(d.get("pickcenter")):
            if not isinstance(o, dict):
                continue
            hb, ab = _as_dict(o.get("homeTeamOdds")), _as_dict(o.get("awayTeamOdds"))
            ml_h, ml_a = ml_from_block(hb), ml_from_block(ab)
            dec = lambda a: (round(1 + (a / 100 if a > 0 else 100 / abs(a)), 2) if a else None)  # noqa: E731
            spread_open = _line_from(hb.get("open")) if isinstance(hb.get("open"), dict) else None
            spread_now = _line_from(hb.get("current")) if isinstance(hb.get("current"), dict) else None
            tot_open = _line_from(o.get("open"), "total") if isinstance(o.get("open"), dict) else None
            tot_now = _line_from(o.get("current"), "total") if isinstance(o.get("current"), dict) else None
            books.append(dict(provider=_as_dict(o.get("provider")).get("name") or "?", spread=_num(o.get("spread")), total=_num(o.get("overUnder")),
                              dec_home=dec(ml_h), dec_away=dec(ml_a),
                              spread_open=spread_open, spread_now=spread_now if spread_now is not None else _num(o.get("spread")),
                              total_open=tot_open, total_now=tot_now if tot_now is not None else _num(o.get("overUnder"))))
        out["books"] = books
        mv = next((b for b in books if b.get("spread_open") is not None or b.get("total_open") is not None), None)
        if mv:
            out["line_move"] = dict(provider=mv["provider"], spread_open=mv["spread_open"], spread_now=mv["spread_now"],
                                    total_open=mv["total_open"], total_now=mv["total_now"])
    guard("books", _books)

    def _lineup():
        lineup = {}
        for r in _as_list(d.get("rosters")):
            r = _as_dict(r)
            side = r.get("homeAway")
            if side not in ("home", "away"):
                continue
            starters = []
            for pl in _as_list(r.get("roster")):
                pl = _as_dict(pl)
                if pl.get("starter"):
                    a = _as_dict(pl.get("athlete"))
                    starters.append(a.get("displayName") or a.get("fullName") or "")
            starters = [s for s in starters if s]
            lineup[side] = dict(announced=bool(starters), formation=r.get("formation"), starters=starters[:11])
        if lineup:
            out["lineup"] = lineup
    guard("lineup", _lineup)

    def _predictor_core():
        if out.get("predictor") or lg["sport"] not in ("basketball", "football", "hockey"):
            return
        sport, league = lg["path"].split("/")
        core = get(f"https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{g['id']}/competitions/{g['id']}/predictor", quiet=True)
        if not isinstance(core, dict):
            return
        keep_raw(f"predictor_{lg['key']}", core)

        def proj(side):
            blk = _as_dict(core.get(side))
            for st in _as_list(blk.get("statistics")):
                st = _as_dict(st)
                if st.get("name") == "gameProjection":
                    return _num(st.get("value") if st.get("value") is not None else st.get("displayValue"))
            return None
        ph, pa = proj("homeTeam"), proj("awayTeam")
        if ph is not None and pa is None:
            pa = 100 - ph
        if pa is not None and ph is None:
            ph = 100 - pa
        if ph is not None and pa is not None and ph + pa > 0:
            t = ph + pa
            out["predictor"] = dict(home=round(ph / t, 3), away=round(pa / t, 3), source="ESPN")
    guard("predictor_core", _predictor_core)

    def _live():
        wp = _as_list(d.get("winprobability"))
        if wp and isinstance(wp[-1], dict) and wp[-1].get("homeWinPercentage") is not None:
            out["live_prob"] = dict(home=round(float(wp[-1]["homeWinPercentage"]), 3))
    guard("live", _live)
    return out


# ---------- 休息天數 ----------
def compute_rest(team, game_start):
    """team["form"] 的每列要有 date_iso。回傳 {days, b2b, last7}；沒有賽程就回 None。"""
    rows = [r for r in (team.get("form") or []) if r.get("date_iso")]
    if not rows or not game_start:
        return None
    before = []
    for r in rows:
        dt = _dt(r["date_iso"])
        if dt and dt < game_start:
            before.append(dt)
    if not before:
        return dict(days=None, b2b=False, last7=0)
    last = max(before)
    hours = (game_start - last).total_seconds() / 3600
    days = int(hours // 24)
    last7 = sum(1 for dt in before if (game_start - dt).total_seconds() <= 7 * 86400)
    return dict(days=days, b2b=hours < 30, last7=last7)


# ---------- NBA 官方傷兵報告 ----------
NBA_STATUS_ZH = {"Out": "缺陣", "Doubtful": "可能缺陣", "Questionable": "存疑", "Probable": "可能上場", "Available": "可上場"}


def nba_official_report(log):
    try:
        from nba_injury_report import get_injury_report
    except Exception as e:  # noqa: BLE001
        log(f"NBA 官方傷報套件不可用：{e!r}")
        return None
    now_et = datetime.now(ET)
    last = None
    for back in range(0, 12):
        ts = (now_et - timedelta(hours=back)).replace(minute=35, second=0, microsecond=0)
        try:
            rep = get_injury_report(ts.strftime("%Y-%m-%dT%H:%M:%S"))
            entries = rep.to_list()
            if entries:
                log(f"NBA 官方傷報：{rep.published_timestamp}（美東），{len(entries)} 筆")
                return dict(published=rep.published_timestamp, entries=entries)
        except Exception as e:  # noqa: BLE001
            last = repr(e)[:120]
            continue
    log(f"NBA 官方傷報：最近 12 小時都抓不到（{last}）")
    return None


def _flip_name(n):
    """官方報告是「姓, 名」，ESPN 是「名 姓」。"""
    n = (n or "").strip()
    if "," in n:
        last, first = [x.strip() for x in n.split(",", 1)]
        return f"{first} {last}"
    return n


def _norm_name(n):
    return re.sub(r"[^a-z]", "", (n or "").lower())


def merge_official(g, report, headshot_lookup=None):
    """把官方傷報併進 NBA 兩隊的 injuries；回傳新增/更新的筆數。"""
    if not report:
        return 0
    start = _dt(g.get("start"))
    us_date = start.astimezone(ET).strftime("%m/%d/%Y") if start else None
    n = 0
    for side in ("home", "away"):
        t = g[side]
        team_name = (t.get("name") or "").lower()
        existing = {_norm_name(x.get("player")): x for x in t.get("injuries") or []}
        for e in report["entries"]:
            if (e.get("Team") or "").lower() != team_name:
                continue
            if us_date and e.get("Game Date") and e["Game Date"] != us_date:
                continue
            name = _flip_name(e.get("Player Name"))
            status = (e.get("Current Status") or "").strip()
            reason = (e.get("Reason") or "").strip()
            if not name or not status:
                continue
            sev = {"Out": "out", "Doubtful": "out", "Questionable": "maybe", "Probable": "maybe", "Available": "ok"}.get(status, "other")
            key = _norm_name(name)
            if key in existing:
                x = existing[key]
                x["status"] = status
                x["status_zh"] = NBA_STATUS_ZH.get(status, status)
                x["severity"] = sev
                x["official"] = True
                if reason and not x.get("detail"):
                    x["detail"] = reason
                x["comment"] = (x.get("comment") or "") if not reason else f"官方傷報：{reason}" + (("；" + x["comment"]) if x.get("comment") else "")
            else:
                t.setdefault("injuries", []).append(dict(
                    id="", player=name, headshot=(headshot_lookup(name) if headshot_lookup else None), position=None, position_zh=None,
                    status=status, status_zh=NBA_STATUS_ZH.get(status, status), severity=sev, detail=reason, side=None,
                    return_date=None, comment=f"官方傷報：{reason}" if reason else None, date=report.get("published"), official=True))
            n += 1
    return n


# ---------- 訊號 ----------
def extra_signals(g, lg):
    """從 analysis 產生訊號：side 是該訊號偏向哪一隊，weight 是給看好方的加減分（偏向看好方為正）。"""
    a = g.get("analysis") or {}
    o = g.get("odds") or {}
    sp = lg["sport"]
    H, A = g["home"], g["away"]
    hn = H.get("name_zh") or H.get("name")
    an = A.get("name_zh") or A.get("name")
    sigs = []

    pred = a.get("predictor")
    if pred and o.get("prob_home") is not None and o.get("prob_source") == "moneyline":
        diff = pred["home"] - o["prob_home"]
        if abs(diff) >= 0.05:
            side = "home" if diff > 0 else "away"
            sigs.append(dict(label="ESPN 模型", side=side, weight=0.4,
                             text=f"模型給{hn if side == 'home' else an}的勝率比盤口高 {abs(diff) * 100:.0f} 個百分點"))
        else:
            sigs.append(dict(label="ESPN 模型", side=None, weight=0,
                             text=f"模型勝率主隊 {pred['home'] * 100:.0f}%，與盤口一致"))

    rest = a.get("rest") or {}
    rh, ra = rest.get("home"), rest.get("away")
    if rh and ra:
        if rh.get("b2b") and not ra.get("b2b"):
            sigs.append(dict(label="休息", side="away", weight=0.4, text=f"{hn} 背靠背第二天，{an} 休息 {ra.get('days') if ra.get('days') is not None else '多'} 天"))
        elif ra.get("b2b") and not rh.get("b2b"):
            sigs.append(dict(label="休息", side="home", weight=0.4, text=f"{an} 背靠背第二天，{hn} 休息 {rh.get('days') if rh.get('days') is not None else '多'} 天"))
        elif rh.get("b2b") and ra.get("b2b"):
            sigs.append(dict(label="休息", side=None, weight=0, text="兩隊都是背靠背"))
        elif rh.get("days") is not None and ra.get("days") is not None and abs(rh["days"] - ra["days"]) >= 3:
            side = "home" if rh["days"] > ra["days"] else "away"
            sigs.append(dict(label="休息", side=side, weight=0.2, text=f"{hn} 休 {rh['days']} 天、{an} 休 {ra['days']} 天"))

    lm = a.get("line_move")
    if lm and lm.get("spread_open") is not None and lm.get("spread_now") is not None:
        th = {"basketball": 1.0, "football": 1.0, "hockey": 0.5, "soccer": 0.25}.get(sp, 1.0)
        d = lm["spread_now"] - lm["spread_open"]
        if abs(d) >= th:
            side = "home" if d < 0 else "away"
            sigs.append(dict(label="盤口變動", side=side, weight=0.3,
                             text=f"主隊讓分從 {lm['spread_open']:+g} 變成 {lm['spread_now']:+g}，市場資金往{hn if side == 'home' else an}"))
        else:
            sigs.append(dict(label="盤口變動", side=None, weight=0, text="開盤到現在幾乎沒動"))

    ats = a.get("ats")
    if ats:
        def rate(s):
            m = re.match(r"(\d+)-(\d+)(?:-(\d+))?", s or "")
            if not m:
                return None, 0
            w, l = int(m.group(1)), int(m.group(2))
            return (w / (w + l) if w + l else None), w + l
        rh_, nh = rate(ats.get("home"))
        ra_, na = rate(ats.get("away"))
        if nh >= 5 and rh_ is not None and rh_ >= 0.65:
            sigs.append(dict(label="讓分盤戰績", side="home", weight=0.2, text=f"{hn} 本季讓分盤 {ats['home']}，過盤率高"))
        if na >= 5 and ra_ is not None and ra_ >= 0.65:
            sigs.append(dict(label="讓分盤戰績", side="away", weight=0.2, text=f"{an} 本季讓分盤 {ats['away']}，過盤率高"))
        if nh >= 5 and rh_ is not None and rh_ <= 0.35:
            sigs.append(dict(label="讓分盤戰績", side="away", weight=0.2, text=f"{hn} 本季讓分盤 {ats['home']}，常不過盤"))
        if na >= 5 and ra_ is not None and ra_ <= 0.35:
            sigs.append(dict(label="讓分盤戰績", side="home", weight=0.2, text=f"{an} 本季讓分盤 {ats['away']}，常不過盤"))

    h2h = a.get("h2h")
    if h2h and h2h.get("games"):
        hw = sum(1 for x in h2h["games"] if x["winner"] == "home")
        aw = sum(1 for x in h2h["games"] if x["winner"] == "away")
        if hw + aw >= 2 and hw != aw:
            side = "home" if hw > aw else "away"
            sigs.append(dict(label="近期對戰", side=side, weight=0.15, text=f"近 {len(h2h['games'])} 次交手 {hn} {hw} 勝 {aw} 敗"))

    lu = a.get("lineup") or {}
    for side, t in (("home", H), ("away", A)):
        x = lu.get(side)
        if x and x.get("announced"):
            out_names = {n.lower() for n in (t.get("key_out") or [])}
            missing = [n for n in out_names if not any(n in s.lower() for s in x["starters"])]
            sigs.append(dict(label="先發公布", side=None, weight=0, text=f"{t.get('name_zh') or t.get('name')} 先發已公布" + ("，主力確定缺席" if missing else "")))
    return sigs
