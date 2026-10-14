# -*- coding: utf-8 -*-
"""成績單：把每一場的建議存下來（第一次看到的賠率、開賽前最後的賠率），賽後對答案。
存在 data/history.json，每次排程更新。看的指標：
  不讓分勝敗、讓分過盤、大小分、跟收盤線比（我們推薦時拿到的線 vs 開賽前最後的線）。"""
import json
import os
from datetime import datetime, timedelta, timezone

TW = timezone(timedelta(hours=8))
KEEP_DAYS = 120


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("entries"), dict):
            return d
    except (OSError, ValueError):
        pass
    return dict(entries={}, since=datetime.now(TW).strftime("%Y-%m-%d"))


def save(path, hist):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, separators=(",", ":"))


def _snap(g, pick, now):
    o = g.get("odds") or {}
    tw = g.get("tw") or {}
    ml = tw.get("ml") or {}
    sp = tw.get("spread") or {}
    tt = tw.get("total") or {}
    dec = ml.get(pick) if ml.get(pick) else o.get(f"dec_{pick}")
    spread_home = sp.get("line_home") if sp.get("line_home") is not None else o.get("spread")
    total = tt.get("line") if tt.get("line") is not None else o.get("total")
    return dict(t=now.isoformat(timespec="minutes"), dec=dec, spread_home=spread_home, total=total,
                prob=o.get(f"prob_{pick}"), tw=bool(ml.get(pick)))


def _score(t):
    try:
        return float(str(t.get("score")).strip())
    except (TypeError, ValueError):
        return None


def settle(e, g):
    hs, as_ = _score(g["home"]), _score(g["away"])
    if hs is None or as_ is None:
        return False
    margin = hs - as_
    pick = e["pick"]
    close = e.get("latest") or e.get("first") or {}
    first = e.get("first") or {}
    res = dict(hs=hs, as_=as_, margin=margin, settled=datetime.now(TW).isoformat(timespec="minutes"))
    # 不讓分
    if margin == 0:
        res["ml"] = "push"
    else:
        res["ml"] = "win" if (margin > 0) == (pick == "home") else "loss"
    # 讓分（用開賽前最後的線）
    sh = close.get("spread_home")
    if sh is not None:
        v = margin + sh if pick == "home" else -(margin + sh)
        res["ats"] = "push" if v == 0 else ("win" if v > 0 else "loss")
        res["ats_line"] = sh if pick == "home" else -sh
    # 大小分（建議有方向才算）
    tl = close.get("total")
    lean = e.get("total_lean")
    if tl is not None and lean in ("大", "小"):
        tot = hs + as_
        res["total"] = tot
        res["ou"] = "push" if tot == tl else ("win" if (tot > tl) == (lean == "大") else "loss")
    # 跟收盤線比：正數＝我們拿到的線比收盤好
    if first.get("spread_home") is not None and sh is not None:
        res["clv_spread"] = round((first["spread_home"] - sh) if pick == "home" else (sh - first["spread_home"]), 1)
    if first.get("dec") and close.get("dec"):
        res["clv_dec"] = round(first["dec"] - close["dec"], 2)
    e["result"] = res
    return True


def update(hist, games, now=None):
    now = now or datetime.now(TW)
    entries = hist.setdefault("entries", {})
    n_new = n_upd = n_set = 0
    for g in games:
        s = g.get("suggestion") or {}
        e = entries.get(g["id"])
        state = g["status"]["state"]
        if state == "pre" and s.get("pick"):
            snap = _snap(g, s["pick"], now)
            if e is None:
                tot = s.get("totals") or {}
                entries[g["id"]] = dict(
                    id=g["id"], league=g["league"], league_zh=g["league_zh"], chip=g.get("chip") or g["sport"],
                    day_tw=g["day_tw"], time_tw=g["time_tw"], start=g["start"],
                    home=g["home"].get("name_zh") or g["home"].get("name"), away=g["away"].get("name_zh") or g["away"].get("name"),
                    pick=s["pick"], pick_label=s.get("pick_label"), play=s.get("play"), confidence=s.get("confidence"),
                    total_lean=tot.get("lean") if tot.get("lean") in ("大", "小") else None,
                    first=snap, latest=snap,
                )
                n_new += 1
            else:
                e["latest"] = snap
                e["confidence"] = s.get("confidence") or e.get("confidence")
                n_upd += 1
        elif state == "post" and e is not None and not e.get("result"):
            if settle(e, g):
                n_set += 1
    # 太舊的清掉
    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    for k in [k for k, v in entries.items() if v.get("day_tw", "") < cutoff]:
        entries.pop(k, None)
    hist["updated"] = now.isoformat(timespec="minutes")
    return n_new, n_upd, n_set


def _bucket():
    return dict(n=0, ml_w=0, ml_l=0, ml_p=0, ats_w=0, ats_l=0, ats_p=0, ou_w=0, ou_l=0, clv=[], clv_dec=[])


def _add(b, e):
    r = e["result"]
    b["n"] += 1
    b["ml_" + {"win": "w", "loss": "l", "push": "p"}[r["ml"]]] += 1
    if r.get("ats"):
        b["ats_" + {"win": "w", "loss": "l", "push": "p"}[r["ats"]]] += 1
    if r.get("ou") in ("win", "loss"):
        b["ou_" + ("w" if r["ou"] == "win" else "l")] += 1
    if r.get("clv_spread") is not None:
        b["clv"].append(r["clv_spread"])
    if r.get("clv_dec") is not None:
        b["clv_dec"].append(r["clv_dec"])


def _fin(b):
    b["clv_avg"] = round(sum(b["clv"]) / len(b["clv"]), 2) if b["clv"] else None
    b["clv_n"] = len(b["clv"])
    b["clv_dec_avg"] = round(sum(b["clv_dec"]) / len(b["clv_dec"]), 3) if b["clv_dec"] else None
    b.pop("clv", None)
    b.pop("clv_dec", None)
    tot = b["ml_w"] + b["ml_l"]
    b["ml_rate"] = round(b["ml_w"] / tot * 100) if tot else None
    tot = b["ats_w"] + b["ats_l"]
    b["ats_rate"] = round(b["ats_w"] / tot * 100) if tot else None
    return b


def summarize(hist, now=None, days=30):
    now = now or datetime.now(TW)
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    settled = [e for e in hist.get("entries", {}).values() if e.get("result") and e.get("day_tw", "") >= cutoff]
    overall, by_league, by_conf, by_play = _bucket(), {}, {}, {}
    for e in settled:
        _add(overall, e)
        _add(by_league.setdefault(e.get("chip") or e["league"], _bucket()), e)
        _add(by_conf.setdefault(e.get("confidence") or "中", _bucket()), e)
        _add(by_play.setdefault(e.get("play") or "不讓分", _bucket()), e)
    recent = sorted(settled, key=lambda e: (e["day_tw"], e["time_tw"]), reverse=True)[:30]
    pending = sum(1 for e in hist.get("entries", {}).values() if not e.get("result"))
    return dict(
        days=days, since=hist.get("since"), settled=len(settled), pending=pending,
        overall=_fin(overall),
        by_league={k: _fin(v) for k, v in by_league.items()},
        by_conf={k: _fin(v) for k, v in by_conf.items()},
        by_play={k: _fin(v) for k, v in by_play.items()},
        recent=[dict(id=e["id"], league_zh=e["league_zh"], chip=e.get("chip"), day_tw=e["day_tw"], time_tw=e["time_tw"],
                     home=e["home"], away=e["away"], pick=e["pick"], pick_label=e.get("pick_label"), play=e.get("play"),
                     confidence=e.get("confidence"), dec=(e.get("first") or {}).get("dec"), line=(e.get("result") or {}).get("ats_line"),
                     hs=e["result"]["hs"], as_=e["result"]["as_"], ml=e["result"]["ml"], ats=e["result"].get("ats"), ou=e["result"].get("ou"),
                     clv=e["result"].get("clv_spread"), total_lean=e.get("total_lean")) for e in recent],
    )
