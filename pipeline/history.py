# -*- coding: utf-8 -*-
"""成績單：把每一場的建議存下來（第一次看到的賠率、開賽前最後的賠率），賽後對答案。
存在 data/history.json，每次排程更新。看的指標：
  不讓分勝敗、讓分過盤、大小分、跟收盤線比（我們推薦時拿到的線 vs 開賽前最後的線）。"""
import json
import os
from statistics import mean
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


def _snap(g, s, now):
    pick = s["pick"]
    o = g.get("odds") or {}
    tw = g.get("tw") or {}
    ml = tw.get("ml") or {}
    sp = tw.get("spread") or {}
    tt = tw.get("total") or {}
    spread_home = sp.get("line_home") if sp.get("line_home") is not None else o.get("spread")
    total = tt.get("line") if tt.get("line") is not None else o.get("total")
    if s.get("play") == "大小分":
        dec = tt.get("over") if pick == "over" else tt.get("under")
        prob = (s.get("totals") or {}).get("prob")
        has_tw = bool(dec)
    else:
        dec = ml.get(pick) if ml.get(pick) else o.get(f"dec_{pick}")
        prob = o.get(f"prob_{pick}")
        has_tw = bool(ml.get(pick))
    return dict(t=now.isoformat(timespec="minutes"), dec=dec, spread_home=spread_home, total=total, prob=prob, tw=has_tw)


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
    totals_main = e.get("play") == "大小分"
    sh = close.get("spread_home")
    if not totals_main:
        # 不讓分
        if margin == 0:
            res["ml"] = "push"
        else:
            res["ml"] = "win" if (margin > 0) == (pick == "home") else "loss"
        # 讓分（用開賽前最後的線）
        if sh is not None:
            v = margin + sh if pick == "home" else -(margin + sh)
            res["ats"] = "push" if v == 0 else ("win" if v > 0 else "loss")
            res["ats_line"] = sh if pick == "home" else -sh
    # 大小分（建議有方向才算；主建議是大小分的話這就是對錯）
    tl = close.get("total")
    lean = e.get("total_lean")
    if tl is not None and lean in ("大", "小"):
        tot = hs + as_
        res["total"] = tot
        res["total_line"] = tl
        res["ou"] = "push" if tot == tl else ("win" if (tot > tl) == (lean == "大") else "loss")
        if first.get("total") is not None:
            res["clv_total"] = round((tl - first["total"]) if lean == "大" else (first["total"] - tl), 1)
    # 跟收盤線比：正數＝我們拿到的線比收盤好
    if not totals_main and first.get("spread_home") is not None and sh is not None:
        res["clv_spread"] = round((first["spread_home"] - sh) if pick == "home" else (sh - first["spread_home"]), 1)
    if first.get("dec") and close.get("dec"):
        res["clv_dec"] = round(first["dec"] - close["dec"], 2)
    e["result"] = res
    return True


RESULT_DAYS = 60


def _lines(g):
    """開賽前最後的線（台灣盤優先，沒有就國際盤）。"""
    o = g.get("odds") or {}
    tw = g.get("tw") or {}
    ml, sp, tt = tw.get("ml") or {}, tw.get("spread") or {}, tw.get("total") or {}
    return dict(
        spread_home=sp.get("line_home") if sp.get("line_home") is not None else o.get("spread"),
        total=tt.get("line") if tt.get("line") is not None else o.get("total"),
        dec_home=ml.get("home") or o.get("dec_home"), dec_away=ml.get("away") or o.get("dec_away"),
        prob_home=o.get("prob_home") if o.get("prob_source") != "form" else None,
    )


def _track_all(hist, g, now):
    """每一場都記：賽前最後的線（lines），打完的比分（results）。給「爸爸的預測」賽後對答案用。"""
    gid = g["id"]
    state = g["status"]["state"]
    lines = hist.setdefault("lines", {})
    results = hist.setdefault("results", {})
    if state == "pre":
        ln = _lines(g)
        ln["t"] = now.isoformat(timespec="minutes")
        ln["day"] = g["day_tw"]
        lines[gid] = ln
        return
    if state == "post" and gid not in results:
        hs, as_ = _score(g["home"]), _score(g["away"])
        if hs is None or as_ is None:
            return
        ln = lines.pop(gid, None) or _lines(g)
        results[gid] = dict(day=g["day_tw"], hs=hs, as_=as_, spread_home=ln.get("spread_home"), total=ln.get("total"),
                            dec_home=ln.get("dec_home"), dec_away=ln.get("dec_away"), prob_home=ln.get("prob_home"))


def _track_model(hist, g, now):
    """純模型（只用實力評分，不看賠率）跟盤口各自說誰會贏，賽後比誰準。"""
    s = g.get("suggestion") or {}
    m = s.get("model") or {}
    gid = g["id"]
    models = hist.setdefault("model", {})
    state = g["status"]["state"]
    o = g.get("odds") or {}
    if state == "pre" and m.get("prob_home") is not None and o.get("prob_home") is not None and o.get("prob_source") != "form":
        e = models.get(gid) or dict(day=g["day_tw"], league=g["league"], chip=g.get("chip") or g["sport"])
        e.update(model_home=m["prob_home"], mkt_home=o["prob_home"], weak=bool(m.get("weak")))
        if m.get("variants"):
            e["var"] = m["variants"]
        models[gid] = e
    elif state == "post" and gid in models and "res" not in models[gid]:
        hs, as_ = _score(g["home"]), _score(g["away"])
        if hs is None or as_ is None or hs == as_:
            return
        e = models[gid]
        home_won = hs > as_
        y = 1 if home_won else 0
        e["res"] = dict(home_won=home_won,
                        model_hit=(e["model_home"] >= 0.5) == home_won, mkt_hit=(e["mkt_home"] >= 0.5) == home_won,
                        model_brier=round((e["model_home"] - y) ** 2, 4),
                        mkt_brier=round((e["mkt_home"] - y) ** 2, 4))
        if e.get("var"):
            e["res"]["var_brier"] = {k: round((v - y) ** 2, 4) for k, v in e["var"].items() if v is not None}


def update(hist, games, now=None):
    now = now or datetime.now(TW)
    entries = hist.setdefault("entries", {})
    n_new = n_upd = n_set = 0
    for g in games:
        try:
            _track_all(hist, g, now)
            _track_model(hist, g, now)
        except Exception:  # noqa: BLE001
            pass
        s = g.get("suggestion") or {}
        e = entries.get(g["id"])
        state = g["status"]["state"]
        if state == "pre" and s.get("pick"):
            snap = _snap(g, s, now)
            if e is None:
                tot = s.get("totals") or {}
                entries[g["id"]] = dict(
                    id=g["id"], league=g["league"], league_zh=g["league_zh"], chip=g.get("chip") or g["sport"],
                    day_tw=g["day_tw"], time_tw=g["time_tw"], start=g["start"],
                    home=g["home"].get("name_zh") or g["home"].get("name"), away=g["away"].get("name_zh") or g["away"].get("name"),
                    pick=s["pick"], pick_label=s.get("pick_label"), play=s.get("play"), confidence=s.get("confidence"),
                    total_lean=tot.get("lean") if tot.get("lean") in ("大", "小") else None,
                    side=(s.get("side") or {}).get("pick_label") if s.get("play") == "大小分" else None,
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
    cut_r = (now - timedelta(days=RESULT_DAYS)).strftime("%Y-%m-%d")
    for key in ("results", "model"):
        d = hist.get(key) or {}
        for k in [k for k, v in d.items() if v.get("day", "") < cut_r]:
            d.pop(k, None)
    cut_l = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    for k in [k for k, v in (hist.get("lines") or {}).items() if v.get("day", "") < cut_l]:
        hist["lines"].pop(k, None)
    hist["updated"] = now.isoformat(timespec="minutes")
    return n_new, n_upd, n_set


def results_payload(hist, now=None, days=RESULT_DAYS):
    """給前端對答案用的精簡版：{id: [日期, 主隊分, 客隊分, 主隊讓分, 大小線, 主賠, 客賠]}。"""
    now = now or datetime.now(TW)
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    out = {}
    for k, v in (hist.get("results") or {}).items():
        if v.get("day", "") >= cutoff:
            out[k] = [v["day"], v["hs"], v["as_"], v.get("spread_home"), v.get("total"), v.get("dec_home"), v.get("dec_away")]
    return dict(updated=now.isoformat(timespec="minutes"), days=days, results=out)


def model_summary(hist, now=None, days=30):
    """純模型 vs 盤口：命中率、Brier（越低越準），整體與各球種；意見不同的場次誰對。"""
    now = now or datetime.now(TW)
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = [e for e in (hist.get("model") or {}).values() if e.get("res") and e.get("day", "") >= cutoff]

    def bucket(lst):
        n = len(lst)
        if not n:
            return dict(n=0)
        mh = sum(1 for e in lst if e["res"]["model_hit"])
        kh = sum(1 for e in lst if e["res"]["mkt_hit"])
        dis = [e for e in lst if (e["model_home"] >= 0.5) != (e["mkt_home"] >= 0.5)]
        return dict(
            n=n, model_rate=round(mh / n * 100), mkt_rate=round(kh / n * 100),
            model_brier=round(sum(e["res"]["model_brier"] for e in lst) / n, 3), mkt_brier=round(sum(e["res"]["mkt_brier"] for e in lst) / n, 3),
            disagree=len(dis), disagree_model_right=sum(1 for e in dis if e["res"]["model_hit"]),
            disagree_mkt_right=sum(1 for e in dis if e["res"]["mkt_hit"]),
        )
    by = {}
    for e in rows:
        by.setdefault(e.get("chip") or e["league"], []).append(e)
    pending = sum(1 for e in (hist.get("model") or {}).values() if not e.get("res"))
    # 每個因素：加了 vs 沒加，誰比較準（Brier 越低越準）
    from model import FACTORS, FACTOR_ZH
    factors = []
    vb = [e["res"]["var_brier"] for e in rows if (e.get("res") or {}).get("var_brier")]
    for f in FACTORS:
        pairs = [(b["full"], b["no_" + f]) for b in vb if "full" in b and ("no_" + f) in b and abs(b["full"] - b["no_" + f]) > 1e-6]
        if not pairs:
            factors.append(dict(key=f, label=FACTOR_ZH[f], n=0))
            continue
        w = round(mean(p[0] for p in pairs), 4)
        wo = round(mean(p[1] for p in pairs), 4)
        better = sum(1 for p in pairs if p[0] < p[1])
        factors.append(dict(key=f, label=FACTOR_ZH[f], n=len(pairs), with_=w, without=wo, better=better,
                            verdict="有幫助" if wo - w >= 0.002 else ("反而變差" if w - wo >= 0.002 else "差不多")))
    base_pairs = [(b["full"], b["base"]) for b in vb if "full" in b and "base" in b]
    overall_vs_base = None
    if base_pairs:
        overall_vs_base = dict(n=len(base_pairs), full=round(mean(p[0] for p in base_pairs), 4), base=round(mean(p[1] for p in base_pairs), 4))
    return dict(days=days, pending=pending, overall=bucket(rows), by_league={k: bucket(v) for k, v in by.items()},
                factors=factors, vs_base=overall_vs_base)


def _bucket():
    return dict(n=0, ml_w=0, ml_l=0, ml_p=0, ats_w=0, ats_l=0, ats_p=0, ou_w=0, ou_l=0, tot_w=0, tot_l=0, clv=[], clv_dec=[], clv_total=[])


def _add(b, e):
    r = e["result"]
    b["n"] += 1
    if r.get("ml"):
        b["ml_" + {"win": "w", "loss": "l", "push": "p"}[r["ml"]]] += 1
    if e.get("play") == "大小分" and r.get("ou") in ("win", "loss"):
        b["tot_" + ("w" if r["ou"] == "win" else "l")] += 1
        if r.get("clv_total") is not None:
            b["clv_total"].append(r["clv_total"])
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
    b["clv_total_avg"] = round(sum(b["clv_total"]) / len(b["clv_total"]), 1) if b["clv_total"] else None
    b.pop("clv", None)
    b.pop("clv_dec", None)
    b.pop("clv_total", None)
    tot = b["ml_w"] + b["ml_l"]
    b["ml_rate"] = round(b["ml_w"] / tot * 100) if tot else None
    tot = b["ats_w"] + b["ats_l"]
    b["ats_rate"] = round(b["ats_w"] / tot * 100) if tot else None
    tot = b["ou_w"] + b["ou_l"]
    b["ou_rate"] = round(b["ou_w"] / tot * 100) if tot else None
    tot = b["tot_w"] + b["tot_l"]
    b["tot_rate"] = round(b["tot_w"] / tot * 100) if tot else None
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
                     hs=e["result"]["hs"], as_=e["result"]["as_"], ml=e["result"].get("ml"), ats=e["result"].get("ats"), ou=e["result"].get("ou"),
                     clv=e["result"].get("clv_spread"), total_lean=e.get("total_lean"), total_line=e["result"].get("total_line")) for e in recent],
    )
