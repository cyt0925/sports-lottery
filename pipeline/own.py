# -*- coding: utf-8 -*-
"""自己的判斷：不看賭盤、不看賠率，只看兩隊實力、近況、傷兵、休息、交手、主力手感、戰意。

做法：
  1. 實力評分（model.rate_game）算出「主隊大概贏幾分」和勝率，總分也一起算。
  2. 誰會贏、信心多少，全部從這裡來。
  3. 算完之後才拿去對台灣運彩：讓分、大小分押哪一邊（我們算的分差／總分 vs 台灣的線），
     賠率划不划算（我們估的勝率 × 台灣賠率）。
盤口只在成績單裡當對照組，看我們長期比盤口準還是不準。"""
from math import erf, sqrt

from model import SIGMA, TOTAL_SIGMA, FACTOR_ZH

CONF = {"basketball": (0.70, 0.57), "hockey": (0.66, 0.56), "volleyball": (0.72, 0.58)}
ML_MIN_DEC = 1.20      # 不讓分賠率低於這個，贏了也幾乎沒賺頭
ATS_MAIN_P = 0.60      # 讓分要有六成把握才主推
OU_MAIN_P = 0.62       # 大小分要有六成二把握才主推
LEAN_P = 0.56          # 大小分「看大／看小」的門檻
LINE_TRUST = 0.5       # 我們算的分差、總分跟台灣的線差多少，只信一半（線是很多人一起算出來的，通常很準）
LINE_P_CAP = 0.70      # 讓分、大小分本來就接近五五波，再有把握也不超過七成
VALUE_GOOD, VALUE_BAD = 0.03, -0.12   # 押 100 長期拿回 103 以上算划算、88 以下算不划算


def _phi(x):
    return 0.5 * (1 + erf(x / sqrt(2)))


def _name(t):
    return t.get("name_zh") or t.get("short") or t.get("name") or ""


def _fmt(v):
    return ("+" if v > 0 else "−" if v < 0 else "") + f"{abs(v):g}"


def estimate(g, lg):
    """我們自己估：主隊勝率、主隊大概贏幾分、總分。沒有實力評分就用近況粗估。"""
    a = g.get("analysis") or {}
    rt = a.get("rating") if isinstance(a, dict) else None
    if rt and rt.get("our_prob_home") is not None:
        parts = rt.get("parts") or {}
        margin = sum(parts.values()) if parts else -(rt.get("our_spread") or 0)
        src = "prev" if "prev" in (rt.get("src_home"), rt.get("src_away")) else "rating"
        return dict(p_home=rt["our_prob_home"], margin=round(margin, 1), total=rt.get("total"), src=src,
                    weak=bool(rt.get("weak")), parts=parts, rating=rt)
    H, A = g["home"], g["away"]
    fh, fa = H.get("form") or [], A.get("form") or []
    if len(fh) >= 3 and len(fa) >= 3:
        wh = sum(1 for r in fh if r["result"] == "W") / len(fh)
        wa = sum(1 for r in fa if r["result"] == "W") / len(fa)
        ph = min(0.8, max(0.2, 0.5 + (wh - wa) * 0.45 + 0.04))
        return dict(p_home=round(ph, 3), margin=None, total=None, src="form", weak=True, parts={}, rating=None)
    return None


def side_probs(g, sport, est):
    """每個選項會中的機率：不讓分用我們的勝率；讓分、大小分用我們算的分差、總分對台灣的線（沒有台灣盤就對國際盤的線）。"""
    tw, o = g.get("tw") or {}, g.get("odds") or {}
    out = {"home": est["p_home"], "away": round(1 - est["p_home"], 3)}
    sig = SIGMA.get(sport)
    sp = tw.get("spread") or {}
    line = sp.get("line_home") if sp.get("line_home") is not None else o.get("spread")
    if sig and line is not None and est.get("margin") is not None:
        p = _phi(LINE_TRUST * (est["margin"] + line) / sig)
        p = min(LINE_P_CAP, max(1 - LINE_P_CAP, p))
        out["ats_home"], out["ats_away"] = round(p, 3), round(1 - p, 3)
    tt = tw.get("total") or {}
    tl = tt.get("line") if tt.get("line") is not None else o.get("total")
    tsig = TOTAL_SIGMA.get(sport)
    if tsig and tl is not None and est.get("total") is not None:
        p = _phi(LINE_TRUST * (est["total"] - tl) / tsig)
        p = min(LINE_P_CAP, max(1 - LINE_P_CAP, p))
        out["over"], out["under"] = round(p, 3), round(1 - p, 3)
    return out


def tw_dec(g, side):
    tw = g.get("tw") or {}
    if side in ("home", "away"):
        return (tw.get("ml") or {}).get(side)
    if side in ("ats_home", "ats_away"):
        return (tw.get("spread") or {}).get(side[4:])
    return (tw.get("total") or {}).get(side)


def value(p, dec):
    """我們估的機率 × 台灣運彩賠率：押 100 元長期大概拿回多少。"""
    if not p or not dec:
        return None
    back = p * dec
    label = "划算" if back - 1 >= VALUE_GOOD else "不划算" if back - 1 <= VALUE_BAD else "普通"
    return dict(back=round(back * 100), label=label, dec=dec, p=round(p, 3))


def factor_lines(est, hn, an):
    """這場怎麼算的：每個因素讓哪一隊多幾分（給網頁和 AI 看）。"""
    parts = est.get("parts") or {}
    rt = est.get("rating") or {}
    out = []
    base = parts.get("base")
    if base is not None:
        hca = rt.get("hca") or 0
        strength = base - hca
        who = hn if strength >= 0 else an
        src = "（開季場數少，主要看上季）" if est.get("src") == "prev" else ""
        out.append(dict(key="base", label="整季實力" + src, team=who if abs(strength) >= 0.5 else None, pts=round(abs(strength), 1)))
        if hca:
            out.append(dict(key="hca", label="主場", team=hn, pts=round(hca, 1)))
    for k in ("notes", "form", "h2h", "rest", "hot", "motive"):
        v = parts.get(k) or 0
        if abs(v) < 0.3:
            continue
        out.append(dict(key=k, label=FACTOR_ZH.get(k, k), team=hn if v > 0 else an, pts=round(abs(v), 1)))
    return out


def build(g, lg):
    sport = lg["sport"]
    H, A = g["home"], g["away"]
    hn, an = _name(H), _name(A)
    res = dict(pick=None, pick_label=None, play="觀望", confidence="低", summary="", reasons=[], cautions=[], totals=None, source="own")
    if g["status"]["state"] == "post":
        res["summary"] = "這場打完了"
        return res
    est = estimate(g, lg)
    if not est:
        res["summary"] = "兩隊這季還沒打幾場，資料不夠，先看看就好"
        res["cautions"].append("開季前幾場沒有戰績和近況，網站先不判斷")
        return res
    probs = side_probs(g, sport, est)
    res.update(est=dict(p_home=est["p_home"], margin=est["margin"], total=est["total"], src=est["src"], weak=est["weak"]),
               probs=probs, factors=factor_lines(est, hn, an))
    ph = est["p_home"]
    fav = "home" if ph >= 0.5 else "away"
    p = max(ph, 1 - ph)
    hi, mid = CONF.get(sport, (0.70, 0.57))
    conf = "高" if p >= hi else "中" if p >= mid else "低"
    capped = est["weak"] or est["src"] == "form" or g.get("season_type") == 1 or g.get("far")
    if capped and conf == "高":
        conf = "中"
    res["fav"], res["p_est"] = fav, round(p, 3)
    fn = hn if fav == "home" else an
    cautions = res["cautions"]
    if est["weak"]:
        cautions.append("兩隊這季才打幾場，實力還看不準，信心打折" + ("（先用上季實力）" if est["src"] == "prev" else ""))
    if est["src"] == "form":
        cautions.append("這個聯盟沒有完整數據，勝率是看近況粗估的")

    pick, play, pconf = None, None, None
    ml_dec = tw_dec(g, fav)
    if conf != "低":
        if ml_dec and ml_dec < ML_MIN_DEC:
            ats = [s for s in ("ats_home", "ats_away") if probs.get(s) is not None]
            best = max(ats, key=lambda s: probs[s]) if ats else None
            cautions.append(f"台灣運彩不讓分只賠 {ml_dec}，贏了也幾乎沒賺頭")
            if best and probs[best] >= 0.55 and tw_dec(g, best):
                pick, play, pconf = best[4:], "讓分", "中"
            else:
                pick, play, pconf = fav, "不讓分", "中" if conf == "高" else conf
        else:
            pick, play, pconf = fav, "不讓分", conf
    else:
        ats = [s for s in ("ats_home", "ats_away") if probs.get(s) is not None]
        best = max(ats, key=lambda s: probs[s]) if ats else None
        if best and probs[best] >= ATS_MAIN_P:
            pick, play, pconf = best[4:], "讓分", "中"
    # 大小分：我們算的總分跟台灣的線差很多，而且輸贏那邊沒有很大把握，就改玩大小分
    tot_side = None
    if probs.get("over") is not None:
        tot_side = "over" if probs["over"] >= probs["under"] else "under"
        tt = (g.get("tw") or {}).get("total") or {}
        line_t = tt.get("line") if tt.get("line") is not None else (g.get("odds") or {}).get("total")
        res["totals"] = dict(lean=("大" if tot_side == "over" else "小") if probs[tot_side] >= LEAN_P else "無明顯方向",
                             line=line_t, line_tw=tt.get("line"), expected=est["total"], method="評分", prob=probs[tot_side])
        if probs[tot_side] >= OU_MAIN_P and pconf != "高" and g["status"]["state"] == "pre" and not est["weak"]:
            side_before = dict(pick=pick, pick_label=(hn if pick == "home" else an) if pick else None, play=play, confidence=pconf)
            res["side"] = side_before
            pick, play, pconf = tot_side, "大小分", "高" if probs[tot_side] >= 0.68 else "中"
            res["totals"]["main"] = True
    if not pick:
        res["summary"] = "兩隊差不多，看不出誰比較穩，先不下"
        res["model"] = _model(est)
        return res
    if play == "大小分":
        label = "大分" if pick == "over" else "小分"
    else:
        label = hn if pick == "home" else an
    key = pick if play == "不讓分" else ("ats_" + pick if play == "讓分" else pick)
    pr = probs.get(key)
    res.update(pick=pick, pick_label=label, play=play, confidence=pconf, prob=pr)
    v = value(pr, tw_dec(g, key))
    if v:
        res["value"] = v
        res["tw_value"], res["tw_dec"], res["tw_ev"] = v["label"], v["dec"], v["back"] - 100
    if play == "讓分":
        sp = (g.get("tw") or {}).get("spread") or {}
        lh = sp.get("line_home") if sp.get("line_home") is not None else (g.get("odds") or {}).get("spread")
        mine = lh if pick == "home" else -lh
        res["summary"] = f"押 {label} {_fmt(mine)}，玩讓分，信心{pconf}"
    elif play == "大小分":
        res["summary"] = f"玩{label} {res['totals']['line']:g}，信心{pconf}"
    else:
        res["summary"] = f"押 {label}，玩不讓分，信心{pconf}"
    res["reasons"] = [f"{f['label']}：{f['team']}多 {f['pts']:g} 分" for f in res["factors"] if f.get("team")]
    res["model"] = _model(est)
    return res


def _model(est):
    rt = est.get("rating") or {}
    if est.get("p_home") is None:
        return None
    ph = est["p_home"]
    return dict(pick="home" if ph >= 0.5 else "away", prob_home=round(ph, 3), spread=rt.get("our_spread"),
                weak=bool(est.get("weak")), variants=rt.get("variants"))


def outside(g):
    """外界怎麼看（不是賭盤）：ESPN 的電腦預測、新聞標題。AI 寫分析時也會讀這些。"""
    a = g.get("analysis") or {}
    out = {}
    pr = a.get("predictor") if isinstance(a, dict) else None
    if pr and pr.get("home") is not None:
        out["espn"] = dict(home=pr["home"], away=pr.get("away"))
    heads = []
    for n in g.get("news") or []:
        if n.get("title"):
            heads.append(dict(title=n["title"], url=n.get("url"), src=n.get("source") or "新聞"))
    for side in ("home", "away"):
        for n in (g[side].get("injury_news") or [])[:2]:
            if n.get("title"):
                heads.append(dict(title=n["title"], url=n.get("url"), src=n.get("source") or "新聞"))
    seen, uniq = set(), []
    for h in heads:
        if h["title"] in seen:
            continue
        seen.add(h["title"])
        uniq.append(h)
    if uniq:
        out["news"] = uniq[:6]
    return out
