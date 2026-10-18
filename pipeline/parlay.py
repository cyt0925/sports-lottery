# -*- coding: utf-8 -*-
"""串關（過關）：每場每個選項估「會中的機率」，再挑「今天最穩的 2 串 1」，並記下來賽後對答案。

台灣運彩規則：至少串 2 場、同一場不能串、賠率相乘、全部都中才有錢。
最穩＝兩場都中的機率最高；但押 100 元中了拿不到 180 元就不值得串。
季前賽（主力常輪休）、沒有盤口只靠近況估的、台灣賠率比平常還差的，都不放進來。
推薦在第一場開打前 45 分鐘鎖定，之後不換，打完照當時的線和賠率對答案。"""
from math import erf, sqrt
from statistics import NormalDist
from datetime import datetime, timedelta, timezone

TW = timezone(timedelta(hours=8))
LOCK_MIN = 45          # 第一場開打前幾分鐘鎖定
SLATE_H = 30           # 只從 30 小時內開打的比賽挑（今天這一輪），更後面的盤口、傷兵都還沒定
MIN_LEG_DEC = 1.20     # 單場賠率太低，串了也沒意義
MIN_LEG_P = 0.55       # 單場至少要有五成五把握
MIN_LEG_EV = 0.85      # 台灣運彩正常大概拿回 85～90%，比這差的不串
MIN_PARLAY_DEC = 1.80  # 押 100 元至少要拿回 180 元
KEEP_GAP = 0.03        # 原本的組合只差一點點就不換，免得一直變
VOID_AFTER_H = 36      # 開打 36 小時還沒有比分，當取消算（賠率 1）
KEEP_DAYS = 60
VERSION = 2            # 估法改了就加 1：還沒鎖定的舊推薦直接重挑
TOTAL_TRUST = 0.5      # 大小分：我們算的總分跟盤口的差距只信一半
LINE_P_CAP = 0.70      # 讓分、大小分本來就接近五五波，再有把握也不超過七成
TOTALS_PROVE_N = 20    # 網站的大小分建議至少對過 20 場、命中 55% 以上，才拿來串
TOTALS_PROVE_RATE = 0.55
PLAY = {"home": "不讓分", "away": "不讓分", "ats_home": "讓分", "ats_away": "讓分", "over": "大小分", "under": "大小分"}


def _phi(x):
    return 0.5 * (1 + erf(x / sqrt(2)))


def _inv(p):
    return NormalDist().inv_cdf(min(0.999, max(0.001, p)))


def side_probs(g, sport, spread_sigma, total_sigma):
    """每個選項會中的機率（對台灣運彩的線；沒有台灣盤就對國際盤）。"""
    s = g.get("suggestion") or {}
    o = g.get("odds") or {}
    tw = g.get("tw") or {}
    out = {}
    ph, pa = o.get("prob_home"), o.get("prob_away")
    fav, pe = s.get("fav"), s.get("p_est")
    ph_est = None
    if ph is not None and pa is not None:
        if fav in ("home", "away") and pe is not None:
            other = max(0.0, 1 - pe - (o.get("prob_draw") or 0))
            out[fav] = pe
            out["away" if fav == "home" else "home"] = other
        else:
            out["home"], out["away"] = ph, pa
        ph_est = out["home"]
    sig = spread_sigma.get(sport)
    sp = tw.get("spread") or {}
    line = sp.get("line_home") if sp.get("line_home") is not None else o.get("spread")
    if sig and line is not None and ph is not None and 0 < ph < 1:
        # 盤口的預期分差，再加上網站的調整（傷兵、近況…）換成的分數
        exp = -o["spread"] if o.get("spread") is not None else sig * _inv(ph)
        if ph_est is not None and 0 < ph_est < 1:
            exp += sig * (_inv(ph_est) - _inv(ph))
        p = _phi((exp + line) / sig)
        out["ats_home"], out["ats_away"] = p, 1 - p
    tot = s.get("totals") or {}
    tt = tw.get("total") or {}
    tl = tt.get("line") if tt.get("line") is not None else o.get("total")
    tsig = total_sigma.get(sport)
    if tsig and tl is not None and tot.get("expected") is not None:
        # 盤口通常很準；我們算的跟盤口差很多，多半是漏了什麼。評分只信一半，近 5 場平均只信四分之一
        w = TOTAL_TRUST if tot.get("method") == "評分" else TOTAL_TRUST / 2
        p = _phi(w * (tot["expected"] - tl) / tsig)
        out["over"], out["under"] = p, 1 - p
    for k in ("ats_home", "ats_away", "over", "under"):
        if k in out:
            out[k] = min(LINE_P_CAP, max(1 - LINE_P_CAP, out[k]))
    return {k: round(v, 3) for k, v in out.items()}


def _tw_dec(g, side):
    tw = g.get("tw") or {}
    if side in ("home", "away"):
        return (tw.get("ml") or {}).get(side)
    if side in ("ats_home", "ats_away"):
        return (tw.get("spread") or {}).get(side[4:])
    return (tw.get("total") or {}).get(side)


def _name(t):
    return t.get("name_zh") or t.get("short") or t.get("name") or ""


def _fmt(v):
    return ("+" if v > 0 else "−" if v < 0 else "") + f"{abs(v):g}"


def _leg(g, side, dec, p):
    tw = g.get("tw") or {}
    sh = (tw.get("spread") or {}).get("line_home")
    tl = (tw.get("total") or {}).get("line")
    h, a = _name(g["home"]), _name(g["away"])
    if side in ("home", "away"):
        label = f"{h if side == 'home' else a} 不讓分"
    elif side == "ats_home":
        label = f"{h} {_fmt(sh)}"
    elif side == "ats_away":
        label = f"{a} {_fmt(-sh)}"
    else:
        label = f"{'大分' if side == 'over' else '小分'} {tl:g}"
    return dict(gid=g["id"], league=g["league"], league_zh=g.get("league_zh"), chip=g.get("chip") or g["sport"],
                day_tw=g.get("day_tw"), time_tw=g.get("time_tw"), start=g["start"], home=h, away=a,
                side=side, play=PLAY[side], label=label, spread_home=sh, total=tl, dec=dec, p=p)


def _start(g):
    try:
        return datetime.fromisoformat(str(g["start"]).replace("Z", "+00:00"))
    except (TypeError, ValueError, KeyError):
        return None


def totals_proven(hist, now, days=30):
    """網站自己的大小分建議準不準：還沒證明之前，串關只用輸贏。"""
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    rs = [((e.get("result") or {}).get("ou")) for e in (hist.get("entries") or {}).values()
          if e.get("play") == "大小分" and e.get("day_tw", "") >= cutoff]
    w, l = rs.count("win"), rs.count("loss")
    return w + l >= TOTALS_PROVE_N and w / (w + l) >= TOTALS_PROVE_RATE


def options(games, now, hidden=(), allow_totals=False):
    """今天可以拿來串的選項：網站主建議那一邊，有台灣運彩賠率、夠穩、賠率不差。"""
    out = []
    for g in games:
        s = g.get("suggestion") or {}
        st = _start(g)
        if g["status"]["state"] != "pre" or not st or st - now < timedelta(minutes=LOCK_MIN + 15) or st - now > timedelta(hours=SLATE_H):
            continue
        if (g.get("chip") or g["sport"]) in hidden or g.get("season_type") == 1:
            continue
        if not s.get("pick") or s.get("confidence") not in ("高", "中") or (g.get("odds") or {}).get("prob_source") == "form":
            continue
        probs = s.get("probs") or {}
        pick = s["pick"]
        lean = (s.get("totals") or {}).get("lean")
        sides = [pick, "ats_" + pick] if pick in ("home", "away") else []
        if allow_totals and lean in ("大", "小"):
            sides.append("over" if lean == "大" else "under")
        for side in sides:
            dec, p = _tw_dec(g, side), probs.get(side)
            if not dec or p is None or dec < MIN_LEG_DEC or p < MIN_LEG_P or p * dec < MIN_LEG_EV:
                continue
            out.append(_leg(g, side, dec, p))
    return out


def _pack(legs):
    dec = 1.0
    p = 1.0
    for x in legs:
        dec *= x["dec"]
        p *= x["p"]
    return dict(legs=legs, dec=round(dec, 2), p=round(p, 3), ev=round(p * dec, 3))


def recommend(games, now, hidden=(), keep=None, allow_totals=False):
    opts = options(games, now, hidden, allow_totals)
    best = None
    for i in range(len(opts)):
        for j in range(i + 1, len(opts)):
            a, b = opts[i], opts[j]
            if a["gid"] == b["gid"] or a["dec"] * b["dec"] < MIN_PARLAY_DEC:
                continue
            key = (a["p"] * b["p"], a["p"] * b["p"] * a["dec"] * b["dec"])
            if best is None or key > best[0]:
                best = (key, [a, b])
    if not best:
        return None
    if keep:
        want = {(x["gid"], x["side"]) for x in keep}
        mine = [x for x in opts if (x["gid"], x["side"]) in want]
        if len(mine) == len(keep) and len({x["gid"] for x in mine}) == len(mine):
            cur = _pack(mine)
            if cur["dec"] >= MIN_PARLAY_DEC and cur["p"] >= best[0][0] - KEEP_GAP:
                return cur
    legs = sorted(best[1], key=lambda x: x["start"])
    return _pack(legs)


# ---------- 記下來、對答案 ----------
def _judge(side, hs, as_, spread_home, total):
    if side in ("home", "away"):
        return "push" if hs == as_ else ("win" if (hs > as_) == (side == "home") else "loss")
    if side in ("ats_home", "ats_away"):
        if spread_home is None:
            return None
        v = hs - as_ + spread_home
        return "push" if v == 0 else ("win" if (v > 0) == (side == "ats_home") else "loss")
    if total is None:
        return None
    t = hs + as_
    return "push" if t == total else ("win" if (t > total) == (side == "over") else "loss")


def _score(t):
    try:
        return float(str(t.get("score")).strip())
    except (TypeError, ValueError):
        return None


def _settle(e, hist, byid, now):
    results = hist.get("results") or {}
    for x in e["legs"]:
        if x.get("r"):
            continue
        g = byid.get(x["gid"])
        hs = as_ = None
        if g and g["status"]["state"] == "post":
            hs, as_ = _score(g["home"]), _score(g["away"])
        elif x["gid"] in results:
            hs, as_ = results[x["gid"]].get("hs"), results[x["gid"]].get("as_")
        if hs is not None and as_ is not None:
            r = _judge(x["side"], hs, as_, x.get("spread_home"), x.get("total"))
            if r:
                x.update(r=r, hs=hs, as_=as_)
                continue
        st = _start(x)
        if st and now - st > timedelta(hours=VOID_AFTER_H):
            x["r"] = "void"
    rs = [x.get("r") for x in e["legs"]]
    if "loss" not in rs and not all(rs):   # 錯一場就整張沒了，不用等其他場
        return False
    if "loss" in rs:
        res = dict(r="loss", pay=0.0)
    elif all(r in ("push", "void") for r in rs):
        res = dict(r="push", pay=1.0)
    else:
        pay = 1.0
        for x in e["legs"]:
            if x["r"] == "win":
                pay *= x["dec"]
        res = dict(r="win", pay=round(pay, 3))
    res["settled"] = now.isoformat(timespec="minutes")
    e["res"] = res
    return True


def _locked(e, byid, now):
    for x in e["legs"]:
        g = byid.get(x["gid"])
        st = _start(x)
        if (g and g["status"]["state"] != "pre") or (st and st - now <= timedelta(minutes=LOCK_MIN)) or (not g and st and st <= now):
            return True
    return False


def track(hist, games, now, hidden=()):
    """更新今天的推薦（還沒鎖定前會跟著最新盤口換），鎖定後等比分對答案。回傳給網頁顯示的內容。"""
    P = hist.setdefault("parlays", [])
    byid = {g["id"]: g for g in games}
    cur = P[-1] if P and "res" not in P[-1] else None
    if cur and not cur.get("locked") and cur.get("v") != VERSION and not _locked(cur, byid, now):
        P.pop()
        cur = None
    if cur and (cur.get("locked") or _locked(cur, byid, now)):
        cur["locked"] = True
        if not _settle(cur, hist, byid, now):
            return dict(current=cur)
        cur = None
    rec = recommend(games, now, hidden, keep=cur["legs"] if cur else None, allow_totals=totals_proven(hist, now))
    if cur and not rec:
        P.pop()
    elif cur and rec:
        cur.update(rec, updated=now.isoformat(timespec="minutes"))
    elif rec:
        P.append(dict(id=now.strftime("%Y%m%d%H%M"), v=VERSION, made=now.isoformat(timespec="minutes"),
                      updated=now.isoformat(timespec="minutes"), locked=False, **rec))
    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y%m%d")
    hist["parlays"] = [e for e in P if e["id"][:8] >= cutoff]
    P = hist["parlays"]
    if P and "res" not in P[-1]:
        return dict(current=P[-1])
    return dict(current=None, note="今天沒有夠穩又值得串的組合，單場就好。")


def summary(hist, now, days=30):
    cutoff = (now - timedelta(days=days)).strftime("%Y%m%d")
    done = [e for e in hist.get("parlays") or [] if e.get("res") and e["id"][:8] >= cutoff]
    graded = [e for e in done if e["res"]["r"] != "push"]
    w = sum(1 for e in graded if e["res"]["r"] == "win")
    money = sum((e["res"]["pay"] - 1) * 100 for e in graded)
    recent = [dict(id=e["id"], dec=e["dec"], p=e["p"], r=e["res"]["r"], pay=e["res"]["pay"],
                   legs=[dict(gid=x["gid"], label=x["label"], league_zh=x.get("league_zh"), day_tw=x.get("day_tw"), r=x.get("r"),
                              hs=x.get("hs"), as_=x.get("as_"), home=x.get("home"), away=x.get("away"), dec=x.get("dec")) for x in e["legs"]])
              for e in sorted(done, key=lambda e: e["id"], reverse=True)[:10]]
    return dict(days=days, n=len(graded), w=w, l=len(graded) - w, money=round(money), recent=recent)
