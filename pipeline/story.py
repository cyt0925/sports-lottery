# -*- coding: utf-8 -*-
"""把一場比賽講成人話：先講結論，再講為什麼、要小心什麼，最後一行賠率。
每句都短，像朋友在旁邊跟你講。資料缺什麼就說缺什麼，不留空白。"""


def _n(t):
    return t.get("name_zh") or t.get("short") or t.get("name") or "對手"


def _cheng(p):
    """0.72 -> 七成、0.55 -> 五成五、0.5 -> 一半。"""
    if p is None:
        return None
    v = round(p * 20) / 2  # 以 0.5 成為單位
    if v >= 9.5:
        return "九成五以上"
    if v <= 1:
        return "一成不到"
    digits = "零一二三四五六七八九十"
    whole, half = int(v), (v - int(v)) >= 0.5
    if whole == 5 and not half:
        return "一半"
    return f"{digits[whole]}成" + ("五" if half else "")


def _short(t, limit=7):
    """隊名太長就用短名（玩運彩即時比分裡的三字短名），沒有就照用。"""
    name = _n(t)
    if len(name) > limit and t.get("short_zh"):
        return t["short_zh"]
    return name


def build_story(g, sport):
    H, A = g["home"], g["away"]
    hn, an = _short(H), _short(A)
    o = g.get("odds") or {}
    s = g.get("suggestion") or {}
    a = g.get("analysis") or {}
    tw = g.get("tw") or {}
    notes = g.get("notes") or {}
    sets = bool(g.get("sets"))
    pick = s.get("pick")
    pn = hn if pick == "home" else an if pick == "away" else None
    psrc = o.get("prob_source")
    ph, pa = o.get("prob_home"), o.get("prob_away")

    why, care = [], []

    # ---- 結論 ----
    if g["status"]["state"] == "post":
        verdict = "這場打完了。"
    elif s.get("play") == "大小分" and s.get("pick_label"):
        tot_ = s.get("totals") or {}
        line_ = tot_.get("line_tw") if tot_.get("line_tw") is not None else tot_.get("line")
        verdict = f"這場我會玩{s['pick_label']}（盤口 {line_:g}），信心{s.get('confidence', '中')}。" if line_ is not None else f"這場我會玩{s['pick_label']}，信心{s.get('confidence', '中')}。"
    elif pn:
        play = s.get("play") or "不讓分"
        extra = ""
        if play == "讓分" and o.get("spread") is not None:
            extra = f"（讓 {abs(o['spread']):g} 分）"
        verdict = f"這場我會押{pn}，玩{play}{extra}，信心{s.get('confidence', '中')}。"
    elif ph is None:
        verdict = "還沒開盤，等盤出來再說。" if not sets else "這場沒有盤口，看球用的。"
    else:
        verdict = "這場看不出誰比較穩，我會先不下。"

    # ---- 為什麼（最多 3 點）----
    if ph is not None and pa is not None:
        fav = "home" if ph >= pa else "away"
        fn = hn if fav == "home" else an
        p = max(ph, pa)
        where = "在主場" if fav == "home" else "作客"
        if psrc == "form":
            why.append(f"沒有盤口，看近況猜{fn}大概{_cheng(p)}會贏。")
        else:
            why.append(f"{fn}{where}，盤口看好他，大概{_cheng(p)}會贏。")
    # 缺陣影響幾分
    for t, name in ((H, hn), (A, an)):
        imp = t.get("injury_impact") or {}
        if imp.get("pts", 0) >= 1:
            outs = [p for p in imp["players"] if p.get("status") in ("out", "ir")]
            maybes = [p for p in imp["players"] if p.get("status") == "maybe"]

            def _who(lst):
                p0 = lst[0]
                toks = [x for x in p0["player"].split(" ") if x.rstrip(".").lower() not in ("jr", "sr", "ii", "iii", "iv")]
                who = toks[-1] if toks else p0["player"]
                ppg = f"（場均 {p0['ppg']:.0f} 分）" if p0.get("ppg") else ""
                extra = f"等 {len(lst)} 人" if len(lst) > 1 else ""
                return f"{who}{extra}{ppg}"
            parts = []
            if outs:
                parts.append(f"少了{_who(outs)}")
            if maybes:
                parts.append(f"{'' if outs else '的'}{_who(maybes)}還不確定上不上")
            line = f"{name}{'，'.join(parts)}，{'大概影響' if outs else '如果都不打大概影響'} {imp['pts']:g} 分。"
            lm = a.get("line_move") or {}
            if lm.get("spread_open") is not None and lm.get("spread_now") is not None and abs(lm["spread_now"] - lm["spread_open"]) >= 1:
                line += "盤口已經有動，應該反映進去了。"
            (care if (pick == ("home" if t is H else "away")) else why).append(line)
        elif imp.get("players"):
            # 只缺替補：講一句就好，不用算分
            p0 = imp["players"][0]
            care.append(f"{name}少了 {p0['player'].split(' ')[-1]}，不是主力，影響不大。")
    order = ((H, hn), (A, an)) if pick != "away" else ((A, an), (H, hn))
    for t, name in order:
        if t.get("last10"):
            n = len(t.get("form") or [])
            w = t.get("last10_w", 0)
            line = f"{name}近 {n} 場 {w} 勝 {n - w} 敗"
            if t.get("rank_note"):
                line += f"，{t['rank_note'].replace('第 ', '第').replace(' 名', '名')}"
            if t.get("streak"):
                n_s = t['streak'][2:]
                line += f"，{'連贏' if t['streak'].startswith('連勝') else '連輸'} {n_s} 場"
            why.append(line + "。")
    # 傷兵（上面已經用「少了誰、影響幾分」講過的隊就不再重複）
    for t, name in ((H, hn), (A, an)):
        imp = t.get("injury_impact") or {}
        said = imp.get("pts", 0) >= 1
        said_maybe = said and any(p.get("status") == "maybe" for p in imp.get("players") or [])
        if t.get("key_out") and not said:
            who = "、".join(t["key_out"][:2])
            why.append(f"{name}主力 {who} 不打，影響不小。")
        elif t.get("out_count", 0) >= 3 and not said:
            why.append(f"{name}有 {t['out_count']} 個人缺陣。")
        if t.get("key_maybe") and not said_maybe:
            care.append(f"{name}的 {t['key_maybe'][0]} 要賽前才知道打不打，開賽前再看一次。")
    # 手感
    for t, name in ((H, hn), (A, an)):
        for p_ in (t.get("hot") or [])[:1]:
            nm = p_["player"].split(" ")[-1]
            if p_.get("label") == "火燙":
                why.append(f"{name}的 {nm} 最近手感很燙，近 5 場平均 {p_['last5']} {p_['stat']}。")
            elif p_.get("label") == "冰冷":
                care.append(f"{name}的 {nm} 最近手感冷，近 5 場只有 {p_['last5']} {p_['stat']}。")
    # 休息
    rest = a.get("rest") or {}
    for side, name in (("home", hn), ("away", an)):
        r = rest.get(side) if isinstance(rest, dict) else None
        if r and r.get("b2b"):
            care.append(f"{name}昨天才打完，今天背靠背，體力會差一點。")
    # 對戰
    h2h = a.get("h2h")
    if h2h and h2h.get("games"):
        hw = sum(1 for x in h2h["games"] if x["winner"] == "home")
        aw = sum(1 for x in h2h["games"] if x["winner"] == "away")
        if hw + aw >= 2 and hw != aw:
            why.append(f"最近交手{hn if hw > aw else an}贏比較多（{max(hw, aw)} 比 {min(hw, aw)}）。")
    # 盤口變動
    lm = a.get("line_move")
    if lm and lm.get("spread_open") is not None and lm.get("spread_now") is not None and abs(lm["spread_now"] - lm["spread_open"]) >= 1:
        who = hn if lm["spread_now"] < lm["spread_open"] else an
        why.append(f"盤口往{who}那邊移，錢在押他。")
    # 實力評分 vs 盤口
    r = a.get("rating") or {}
    if r and not r.get("weak") and r.get("diff") is not None and r.get("market_spread") is not None:
        ours, mk = -r["our_spread"], -r["market_spread"]
        th = 3.0 if sport == "basketball" else 0.45 if sport == "hockey" else 3.0
        def _let(v, who_fav, who_dog):
            # 正的是主隊讓分，負的是主隊受讓；用「誰讓幾分」講，不出現負號
            return f"{who_fav}讓 {abs(v):g} 分" if v >= 0 else f"{who_dog}讓 {abs(v):g} 分"
        if r["diff"] <= -th:
            line = f"照兩隊實力算，大概只該{_let(ours, '主隊', an)}，盤口卻開{_let(mk, '主隊', an)}，讓分盤反而是{an}划算。"
            (why if pick == "away" else care).append(line)
        elif r["diff"] >= th:
            line = f"照兩隊實力算，該{_let(ours, '主隊', an)}，盤口只開{_let(mk, '主隊', an)}，讓分盤{hn}划算。"
            (why if pick == "home" else care).append(line)
        else:
            why.append(f"我們自己算的實力差距跟盤口差不多（主隊讓 {ours:g} 分左右）。")
    elif r and r.get("weak"):
        care.append(f"兩隊才打 {min(r['gp_home'], r['gp_away'])} 場，實力評分還不準，盤口為主。")
    # 玩家一面倒
    crowd = a.get("crowd") or {}
    if crowd.get("ml_home") is not None and crowd.get("ml_away") is not None:
        v = max(crowd["ml_home"], crowd["ml_away"])
        side = hn if crowd["ml_home"] >= crowd["ml_away"] else an
        if v >= 80:
            care.append(f"{_cheng(v / 100)}的人都押{side}，太一面倒的時候反而常翻車。")
    # 台灣賠率划不划算
    if s.get("tw_value") == "偏差":
        care.append(f"台灣運彩賠率 {s.get('tw_dec')} 比平常差，注碼小一點。")
    elif s.get("tw_value") == "划算":
        why.append(f"台灣運彩賠 {s.get('tw_dec')}，比平常好一點。")
    for c in s.get("cautions") or []:
        if "幾乎沒賺頭" in c:
            care.append("不讓分賠率太低，贏了也沒賺頭，要下就下讓分。")
    # 大小分
    tot = s.get("totals")
    if tot and tot.get("lean") in ("大", "小"):
        how = "照兩隊得分和失分算，這場大概" if tot.get("method") == "評分" else "兩隊最近一場平均"
        line_ = tot.get("line_tw") if tot.get("line_tw") is not None else tot.get("line")
        lead = "" if tot.get("main") else f"大小分看「{tot['lean']}」："
        why.insert(0 if tot.get("main") else len(why), f"{lead}{how} {tot['expected']:.0f} 分，盤口 {line_:g}，差了 {abs(tot['expected'] - line_):.0f} 分。")
        if tot.get("main"):
            side_ = s.get("side") or {}
            if side_.get("pick") in ("home", "away"):
                sn = hn if side_["pick"] == "home" else an
                why.append(f"輸贏我偏{sn}，但優勢不大，大小分比較有把握。")
            else:
                why.append("輸贏看不出誰穩，大小分比較有把握。")
            if tot.get("prob"):
                why.append(f"照這個差距算，{tot['lean']}分大概{_cheng(tot['prob'])}會中。")
    # 沒資料的時候也要講
    if not why:
        why.append(notes.get("form") or "兩隊資料還不多，先看賽前消息。")
    inj_news = any((t.get("injury_news") or []) for t in (H, A))
    matched = any(x.get("severity") in ("out", "maybe") for t in (H, A) for x in (t.get("injuries") or []))
    if inj_news and not matched and not any(("不打" in w or "缺陣" in w or "少了" in w or "還不確定" in w) for w in why + care):
        care.append("新聞有提到傷兵消息，點下面的新聞看是誰。")
    elif not inj_news and not any(t.get("injuries") for t in (H, A)) and g["status"]["state"] != "post":
        inj_note = "兩隊都沒看到傷兵消息，應該是全員到齊。" if sport != "volleyball" else "沒看到傷兵消息。"
        why.append(inj_note)

    # ---- 賠率一句話 ----
    ml = tw.get("ml") or {}
    sp = tw.get("spread") or {}
    tt = tw.get("total") or {}
    parts = []
    if ml.get("home") or ml.get("away"):
        parts.append(f"不讓分 {an} {ml.get('away') or '–'}、{hn} {ml.get('home') or '–'}")
    if sp.get("line"):
        parts.append(f"讓分 {sp['line']}")
    if tt.get("line") is not None:
        parts.append(f"大小 {tt['line']:g}")
    if parts:
        odds_line = "台灣運彩：" + "，".join(parts) + "。"
    elif sets:
        odds_line = "台灣運彩沒有開日本排球。"
    elif o.get("prob_home") is not None and psrc != "form":
        odds_line = "台灣運彩還沒開這場，通常前一天才會開。"
    else:
        odds_line = notes.get("odds") or "還沒開盤。"

    talk = dict(verdict=verdict, why=why[:4], care=care[:3], odds=odds_line)
    if sets:
        talk["note"] = "排球看局數，五局三勝。"
    return talk
