# -*- coding: utf-8 -*-
"""把一場比賽講成人話：先講結論，再講為什麼、要小心什麼，最後一行賠率。
爸爸要看的球種是「自己判斷」（suggestion.source == "own"）：理由只講實力、近況、傷兵、休息、交手、手感、戰意，
不講盤口看好誰、錢往哪邊跑、網友押哪邊；賠率只用來說划不划算。
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


def _r(v):
    """四捨五入取整數（跟網頁一樣 .5 進位）。"""
    return int(abs(v) + 0.5)


def _short(t, limit=7):
    """隊名太長就用短名（玩運彩即時比分裡的三字短名），沒有就照用。"""
    name = _n(t)
    if len(name) > limit and t.get("short_zh"):
        return t["short_zh"]
    return name


def _last(name):
    toks = [x for x in (name or "").split(" ") if x.rstrip(".").lower() not in ("jr", "sr", "ii", "iii", "iv")]
    return toks[-1] if toks else (name or "")


def _star(x):
    """這個人算不算主力：缺他影響 2.5 分以上，或場均 15 分以上。"""
    return (x.get("full_impact") or 0) >= 2.5 or (x.get("ppg") or 0) >= 15


def _dense_line(rest, hn, an, league):
    """賽程密度：前 7 天多打一兩場（歐洲球隊週中打歐戰、週末打國內賽），大球隊這種比賽常讓主力少打。"""
    from model import DENSE_MIN
    h, a = rest.get("home") or {}, rest.get("away") or {}
    lh, la = h.get("last7"), a.get("last7")
    if lh is None or la is None or lh == la or max(lh, la) < DENSE_MIN.get(league, 2) or h.get("b2b") or a.get("b2b"):
        return None
    tired, fresh, t = (hn, an, h) if lh > la else (an, hn, a)
    n = max(lh, la)
    if t.get("euro"):
        return f"{tired}週中剛打完歐戰，前 7 天已經打了 {n} 場，{fresh}比較有休息；這種賽程大球隊常讓主力少打一點，後段體力也吃虧。"
    return f"{tired}前 7 天已經打了 {n} 場，比{fresh}多，後段體力比較吃虧。"


def _pre_only(g, t):
    """這隊的近況只有季前賽（例行賽剛開打，還沒打正式比賽）：季前賽主力打不多，近況不能當真。"""
    return t.get("form_note") == "季前賽" and g.get("season_type") != 1


def _rec(t):
    """這季戰績 (勝, 敗)；沒有就 None。"""
    try:
        w, l = [int(x) for x in str(t.get("record") or "").split("-")[:2]]
        return w, l
    except ValueError:
        return None


def _prev_one(p, name, first=True):
    if p.get("absent"):
        if p["comp"] in ("E", "U"):
            return f"{name}上季沒打{p['comp_zh']}"
        return f"上季{p['comp_zh']}的資料裡沒有{name}（可能剛升上來）"
    head = ("上季" if p["comp"] == "nba" else f"上季{p['comp_zh']}") if first else ""
    part = f"前 {p['partial']} 輪" if p.get("partial") and first else ""
    rk = f"排聯盟第 {p['rank']}" if p["comp"] == "nba" else f"排第 {p['rank']}"
    return f"{name}{head}{part} {p['w']} 勝 {p['l']} 敗、{rk}".strip()


def bg_lines(g, hn, an):
    """比賽的背景，用具體的事講（上季打得怎樣、這季開季怎樣、主場、交手）。每句都是完整的一句話。"""
    a = g.get("analysis") or {}
    H, A = g["home"], g["away"]
    pv = (a.get("bg") or {}).get("prev") or {}
    ph, pa = pv.get("home"), pv.get("away")
    out = []
    # 上季
    if ph and pa and not ph.get("absent") and not pa.get("absent"):
        (b, bn), (w, wn) = sorted(((ph, hn), (pa, an)), key=lambda x: x[0]["rank"])
        gap = w["rank"] - b["rank"]
        if gap <= 2:
            out.append(f"兩隊上季差不多：{_prev_one(b, bn)}，{_prev_one(w, wn, False)}。")
        else:
            out.append(f"{_prev_one(b, bn)}，{wn}{'才' if gap >= 5 else ''} {_prev_one(w, '', False)}。")
    else:
        lines = [_prev_one(p, nm) for p, nm in ((ph, hn), (pa, an)) if p]
        if lines:
            out.append("，".join(lines) + "。")
    # 這季開季（跟上季比）
    rh, ra = _rec(H), _rec(A)
    if rh and ra and sum(rh) + sum(ra) > 0:
        gp = max(sum(rh), sum(ra))
        when = "開季" if gp <= 8 else "這季"
        bits = []
        bits, cmp_ = [], []
        for (w_, l_), nm, p in ((rh, hn, ph), (ra, an, pa)):
            if not w_ + l_:
                continue
            bits.append(f"{nm} {w_} 勝 {l_} 敗")
            if p and not p.get("absent") and w_ + l_ >= 3:
                now_pct, then_pct = w_ / (w_ + l_), p["w"] / max(1, p["w"] + p["l"])
                if now_pct - then_pct >= 0.25:
                    cmp_.append((nm, "比上季好"))
                elif then_pct - now_pct >= 0.25:
                    cmp_.append((nm, "沒有上季好"))
        if rh == ra and len(bits) == 2:
            out.append(f"{when}兩隊都是 {rh[0]} 勝 {rh[1]} 敗" + "".join(f"，{nm}{c}" for nm, c in cmp_) + "。")
        elif bits:
            # 「A 2 勝 1 敗，比上季好，B 0 勝 3 敗」：比較接在那一隊後面
            parts = [b + "".join(f"，{c}" for nm, c in cmp_ if b.startswith(nm + " ")) for b in bits]
            out.append(f"{when}" + "，".join(parts) + "。")
    # 主場
    e = a.get("elo") or {}
    if not g.get("neutral") and e.get("off_home") is not None and (e.get("nt_home") or 0) >= 15:
        if e["off_home"] >= 1.5:
            out.append(f"{hn}的主場特別難打，比一般球隊的主場多值 {e['off_home']:.0f} 分左右。")
        elif e["off_home"] <= -1.5:
            out.append(f"{hn}在自己主場沒什麼優勢，主場比一般球隊少 {abs(e['off_home']):.0f} 分左右。")
    # 交手（沒有剋星的時候，簡單講一下碰過幾次）
    hl = a.get("h2h_long") or {}
    if hl.get("n") and not hl.get("jinx"):
        if hl["n"] == 1:
            x = (hl.get("games") or [{}])[-1]
            if x.get("pf") is not None:
                who = hn if x["margin"] > 0 else an
                comp = x.get("comp") or ""
                out.append(f"兩隊近兩季只碰過一次（{x.get('season', '')}{(' ' + comp) if comp.isascii() else comp}），{who}贏 {abs(x['margin'])} 分。")
        elif hl["w"] != hl["l"]:
            more = hn if hl["w"] > hl["l"] else an
            out.append(f"近兩季碰過 {hl['n']} 次，{more}贏 {max(hl['w'], hl['l'])} 次。")
        else:
            out.append(f"近兩季碰過 {hl['n']} 次，各贏 {hl['w']} 次。")
    return out


def sum_line(g, hn, an):
    """把我們的計算講成一句話：誰實力強幾分、主場值幾分、其他加減，算下來誰有利。"""
    s = g.get("suggestion") or {}
    est = s.get("est") or {}
    fs = [f for f in s.get("factors") or [] if f.get("key") == "base" or (f.get("team") and f.get("pts"))]
    if est.get("p_home") is None or not fs:
        return None
    fav = hn if est["p_home"] >= 0.5 else an
    p = max(est["p_home"], 1 - est["p_home"])
    bits = []
    for f in fs[:4]:
        k, v, t = f.get("key"), f.get("pts") or 0, f.get("team")
        if k == "base":
            bits.append(f"實力{t}強大概 {_r(v) or 1} 分" if t and v >= 0.5 else "實力兩隊差不多")
        elif k == "hca":
            bits.append(f"{t}在主場大概值 {_r(v) or 1} 分")
        elif v >= 0.5:
            bits.append(f"{FACTOR_TALK.get(k, f.get('label') or '其他')}{t}多 {_r(v) or 1} 分")
    if not bits:
        return None
    m = est.get("margin")
    by = f"，大概贏 {_r(m)} 分" if m is not None and abs(m) >= 1 else ""
    how = "稍微有利" if p < 0.58 else "比較有利" if p < 0.7 else "贏面大"
    return f"我們的算法：{'，'.join(bits)}；加起來{fav}{how}（大概{_cheng(p)}會贏{by}）。"


# 計算裡每個因素用聊天的講法
FACTOR_TALK = {"rest": "體力", "form": "最近狀況", "h2h": "交手", "hot": "主力手感", "motive": "戰意", "news": "場外消息", "derby": "德比",
               "notes": "傷兵", "injury": "傷兵", "inj": "傷兵"}


def signal_lines(g, hn, an):
    """場外消息（context.py 從新聞挖的，可能是外文新聞）講成中文，說是哪裡的媒體報的。"""
    from newsread import media_of
    out = []
    for t, name in ((g["home"], hn), (g["away"], an)):
        for sg in t.get("signals") or []:
            who = f"{media_of(sg)}報導，" if sg.get("title") else ""
            if sg["kind"] == "coach":
                out.append(f"{who}{name}剛換教練，新教練頭幾場球員通常比較拚，但戰術還在磨合。")
            elif sg["kind"] == "money":
                out.append(f"{who}{name}傳出欠薪或財務問題，這種隊伍場上常常不夠拚。")
            elif sg["kind"] == "turmoil":
                out.append(f"{who}{name}最近有禁賽或隊內不和的消息，要小心。")
    return out


def _fan_take(g, sport, hn, an, pick, used):
    """老球迷怎麼看：挑這場最關鍵的一兩件事，用聊天的口氣講。"""
    H, A = g["home"], g["away"]
    a = g.get("analysis") or {}
    r = a.get("rating") or {}
    out = []
    # 1) 主力打不打、打多久
    best = None
    for t, name, side in ((H, hn, "home"), (A, an, "away")):
        for x in t.get("injuries") or []:
            if not _star(x):
                continue
            sev, st = x.get("severity"), x.get("status_zh") or ""
            if sev == "limited" or st == "背靠背常輪休" or (sev == "maybe" and 0.3 <= (x.get("p_out") or 0.5) <= 0.8):
                score = (x.get("full_impact") or 2) * (1 if sev != "limited" else 0.8)
                if not best or score > best[0]:
                    best = (score, x, name, side)
    if best:
        _, x, name, side = best
        who = _last(x["player"])
        st = x.get("status_zh") or ""
        used.add(x["player"])
        if x.get("severity") == "limited":
            out.append(f"這場重點是 {who} 能打多久。他會上，但{x.get('why') or '上場時間被控制'}，{name}少了他後段比較沒人能收尾，別把{name}當完整戰力看。")
        elif st == "背靠背常輪休":
            out.append(f"今天是{name}背靠背第二場，{who}{('，' + x['why']) if x.get('why') else '這種比賽常休息'}，很可能又不打。開賽前一小時看先發名單再決定。")
        else:
            if st == "上一場沒上":
                reason = x.get("detail") or "上一場沒上場，可能受傷或輪休"
            else:
                reason = x.get("why") or x.get("detail_zh") or ("名單上寫" + st if st else "還不確定會不會打")
            out.append(f"{who} 打不打是這場最大的變數：{reason}。他上的話{name}強很多，賽前一定要再看一次。")
    # 1.5) 場外消息（換教練、欠薪、禁賽）：老球迷第一句就會講
    if len(out) < 2 and g["status"]["state"] != "post":
        for line in signal_lines(g, hn, an)[:2 - len(out)]:
            out.append(line)
    # 2) 季前賽
    if g.get("season_type") == 1:
        out.append("季前賽主力常常打半場就下來，輸贏看看就好，別下重注。")
    # 3) 近況跟帳面不一樣
    if len(out) < 2 and r:
        for side, t, name in (("home", H, hn), ("away", A, an)):
            fv = r.get("form_" + side)
            sd = r.get("season_diff_" + side)
            if not fv or sd is None or (r.get("gp_" + side) or 0) < 8 or _pre_only(g, t):
                continue
            gap = fv["recent"] - sd
            if gap <= -6:
                out.append(f"{name}帳面看起來不錯，但最近 {fv['n']} 場扣掉對手強弱，打得比整季差 {abs(gap):.0f} 分，狀況在往下掉。")
                break
            if gap >= 6:
                out.append(f"{name}整季帳面普通，但最近 {fv['n']} 場打得比整季好 {gap:.0f} 分，正在變強，帳面還看不出來。")
                break
            if fv.get("streak_kind") == "W" and fv.get("streak_n", 0) >= 3 and (fv.get("streak_opp_avg") or 0) <= -3:
                out.append(f"{name}雖然連贏 {fv['streak_n']} 場，但打的都是後段班，別被連勝騙了。")
                break
            if fv.get("streak_kind") == "L" and fv.get("streak_n", 0) >= 3 and (fv.get("streak_opp_avg") or 0) >= 3:
                out.append(f"{name}連輸 {fv['streak_n']} 場，但碰的都是強隊，沒有看起來那麼差。")
                break
        if len(out) < 2:
            # 季初場數少，帳面就是近況：只講特別順或特別差的
            for side, t, name in (("home", H, hn), ("away", A, an)):
                fv = r.get("form_" + side)
                if not fv or (r.get("gp_" + side) or 0) >= 8 or _pre_only(g, t):
                    continue
                if fv["recent"] >= 10:
                    out.append(f"{name}開季打得很順，扣掉對手強弱平均贏 {fv['recent']:.0f} 分，不是只靠賽程。")
                    break
                if fv["recent"] <= -8:
                    out.append(f"{name}開季打得很掙扎，扣掉對手強弱平均輸 {abs(fv['recent']):.0f} 分。")
                    break
    # 4) 剋星
    h = a.get("h2h_long") or {}
    if len(out) < 2 and h.get("jinx"):
        win, lose = (hn, an) if h["jinx"] == "home" else (an, hn)
        ww = h["w"] if h["jinx"] == "home" else h["l"]
        extra = ""
        if h.get("avg_over") is not None:
            extra = f"平均比預期多贏 {abs(h['avg_over']):.0f} 分"
        elif h.get("avg_margin") is not None:
            extra = f"平均贏 {abs(h['avg_margin']):.0f} 分"
        out.append(f"{win}碰{lose}就是有辦法，近 {h['n']} 次交手贏 {ww} 次{('，' + extra) if extra else ''}。交手場數不多，參考就好。")
    # 5) 背靠背
    rest = a.get("rest") or {}
    if len(out) < 2 and isinstance(rest, dict) and sport == "basketball":
        rh_b, ra_b = bool((rest.get("home") or {}).get("b2b")), bool((rest.get("away") or {}).get("b2b"))
        if rh_b != ra_b:
            tired = hn if rh_b else an
            out.append(f"{tired}昨天才打完，今天背靠背，第四節腳會比較沉，讓分別讓太多。")
        else:
            line = _dense_line(rest, hn, an, g.get("league"))
            if line:
                out.append(line)
    # 5.5) 長途移動（週中剛在別的城市打完、又要飛很遠）
    if len(out) < 2 and sport == "basketball":
        import geo
        for line in geo.lines(g, hn, an)[:1]:
            out.append(line)
    # 6) 打法對位
    st_ = a.get("style") or {}
    if len(out) < 2 and st_.get("lines"):
        out.append(st_["lines"][0])
    # 7) 實力差很多：要擔心的不是輸贏，是讓分
    if not out and r and not r.get("weak") and abs(r.get("our_spread") or 0) >= 10:
        fav = hn if (r.get("our_spread") or 0) < 0 else an
        out.append(f"兩隊實力差很多，{fav}贏面大，但這種比賽要擔心的不是輸贏，是讓分讓太深、後段換替補被追分。")
    # 8) 沒有特別的變數：講背景（上季、開季、主場、交手），再講算下來誰有利
    if len(out) < 2:
        for line in bg_lines(g, hn, an):
            if len(out) >= 2:
                break
            if line not in out:
                out.append(line)
    if len(out) < 2:
        sl = sum_line(g, hn, an)
        if sl:
            out.append(sl.replace("我們的算法：", "算下來，"))
    if not out:
        if pick in ("home", "away"):
            out.append(f"兩隊資料還不多，照實力看{hn if pick == 'home' else an}稍微好一點，開賽前再看傷兵消息。")
        elif g["status"]["state"] == "pre":
            out.append("兩隊實力接近、資料也不多，這種比賽最難猜，看看就好。")
    return " ".join(out[:2])


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
    own = s.get("source") == "own"
    est = s.get("est") or {}
    rt0 = a.get("rating") or {}

    why, care = [], []

    # ---- 結論 ----
    if g["status"]["state"] == "post":
        verdict = "這場打完了。"
    elif s.get("play") == "大小分" and s.get("pick_label"):
        tot_ = s.get("totals") or {}
        line_ = tot_.get("line_tw") if tot_.get("line_tw") is not None else tot_.get("line")
        verdict = f"這場我會玩{s['pick_label']}（台灣運彩的線 {line_:g}），信心{s.get('confidence', '中')}。" if line_ is not None else f"這場我會玩{s['pick_label']}，信心{s.get('confidence', '中')}。"
    elif pn:
        play = s.get("play") or "不讓分"
        extra = ""
        tw_sp = ((g.get("tw") or {}).get("spread") or {}).get("line_home")
        line_h = tw_sp if tw_sp is not None else o.get("spread")
        if play == "讓分" and line_h is not None:
            mine = line_h if s.get("pick") == "home" else -line_h
            extra = f"（{'讓' if mine < 0 else '受讓'} {abs(mine):g} 分）"
        verdict = f"這場我會押{pn}，玩{play}{extra}，信心{s.get('confidence', '中')}。"
    elif own and s.get("summary"):
        verdict = s["summary"].rstrip("。") + "。"
    elif ph is None:
        verdict = "還沒開盤，等盤出來再說。" if not sets else "這場沒有盤口，看球用的。"
    else:
        verdict = "這場看不出誰比較穩，我會先不下。"

    # ---- 為什麼（最多 3 點）----
    if own and est.get("p_home") is not None:
        fav = "home" if est["p_home"] >= 0.5 else "away"
        fn = hn if fav == "home" else an
        p = max(est["p_home"], 1 - est["p_home"])
        where = "在主場" if fav == "home" else "作客"
        if est.get("src") == "form":
            why.append(f"這個聯盟數據少，看近況猜{fn}大概{_cheng(p)}會贏。")
        else:
            by = f"，大概贏 {_r(est['margin'])} 分" if est.get("margin") is not None and abs(est["margin"]) >= 1 else ""
            base = "（開季場數少，先看上季實力）" if est.get("src") == "prev" else ""
            if p < 0.55:
                why.append(f"我們算兩隊差不多，{fn}{where}稍微好一點{base}。")
            else:
                why.append(f"我們算{fn}{where}大概{_cheng(p)}會贏{by}{base}。")
    elif ph is not None and pa is not None:
        fav = "home" if ph >= pa else "away"
        fn = hn if fav == "home" else an
        p = max(ph, pa)
        where = "在主場" if fav == "home" else "作客"
        if psrc == "form":
            why.append(f"沒有盤口，看近況猜{fn}大概{_cheng(p)}會贏。")
        else:
            why.append(f"{fn}{where}，盤口看好他，大概{_cheng(p)}會贏。")
    used = set()
    fan = _fan_take(g, sport, hn, an, pick, used) if g["status"]["state"] != "post" else ""
    # 缺陣影響幾分：確定不打、可能不打、限時分開講
    for t, name in ((H, hn), (A, an)):
        imp = t.get("injury_impact") or {}
        mine = pick == ("home" if t is H else "away")
        inj = [x for x in t.get("injuries") or [] if (x.get("impact") or 0) > 0 or _star(x)]
        outs = [x for x in inj if x.get("severity") in ("out", "ir")]
        maybes = [x for x in inj if x.get("severity") == "maybe" and (x.get("p_out") if x.get("p_out") is not None else 0.5) >= 0.3 and x.get("status_zh") != "背靠背常輪休"
                  and x["player"] not in used]       # 老球迷那段已經講過的人不再講一次
        limited = [x for x in inj if x.get("severity") == "limited" and x["player"] not in used]
        b2b = [x for x in inj if x.get("status_zh") == "背靠背常輪休" and x["player"] not in used]

        def _who(lst):
            lst = sorted(lst, key=lambda x: -(x.get("ppg") or 0))
            p0 = lst[0]
            ppg = f"（場均 {p0['ppg']:.0f} 分）" if p0.get("ppg") else ""
            extra = f" 等 {len(lst)} 人" if len(lst) > 1 else ""
            said = f"（{p0['media']}說的）" if p0.get("media") else ""
            return f" {_last(p0['player'])}{extra}{ppg}{said}"
        if imp.get("pts", 0) >= 1 and (outs or maybes):
            parts = []
            if outs:
                rest_only = all((x.get("status_zh") or "").endswith("輪休") for x in outs)
                parts.append(f"{'這場讓' if rest_only else '少了'}{_who(outs)}{'休息' if rest_only else ''}")
            if maybes:
                hi = [x for x in maybes if (x.get("p_out") or 0.5) >= 0.6]
                parts.append(f"{'' if outs else '的'}{_who(maybes)}{'很可能不打' if hi and len(hi) == len(maybes) else '還不確定上不上'}")
            line = f"{name}{'，'.join(parts)}，大概影響 {imp['pts']:g} 分。".replace("， ", "，")
            lm = a.get("line_move") or {}
            if not own and lm.get("spread_open") is not None and lm.get("spread_now") is not None and abs(lm["spread_now"] - lm["spread_open"]) >= 1:
                line += "盤口已經有動，應該反映進去了。"
            (care if mine else why).append(line)
        elif outs or maybes:
            p0 = (outs or maybes)[0]
            why.append(f"{name}少了 {_last(p0['player'])}，不是主力，影響不大。")
        for x in sorted(limited, key=lambda x: -(x.get("full_impact") or 0))[:1]:
            line = f"{name}的 {_last(x['player'])} 會上，但{x.get('why') or '上場時間被控制'}，別把他當完整戰力看。"
            (care if mine else why).append(line)
        for x in b2b[:1]:
            care.append(f"{name}背靠背第二場，{_last(x['player'])}{('：' + x['why']) if x.get('why') else '這種比賽常休息'}。開賽前看先發名單再決定。")
    order = ((H, hn), (A, an)) if pick != "away" else ((A, an), (H, hn))
    for t, name in order:
        if t.get("last10"):
            n = len(t.get("form") or [])
            w = t.get("last10_w", 0)
            line = f"{name}{'季前賽' if _pre_only(g, t) else '近'} {n} 場 {w} 勝 {n - w} 敗"
            if t.get("rank_note"):
                line += f"，{t['rank_note'].replace('第 ', '第').replace(' 名', '名')}"
            if t.get("streak"):
                n_s = t['streak'][2:]
                line += f"，{'連贏' if t['streak'].startswith('連勝') else '連輸'} {n_s} 場"
            why.append(line + "。")
    # 傷兵（上面已經用「少了誰、影響幾分」講過的隊就不再重複）
    for t, name in ((H, hn), (A, an)):
        imp = t.get("injury_impact") or {}
        said = imp.get("pts", 0) >= 1 or any(x.get("severity") == "limited" for x in t.get("injuries") or [])
        said_maybe = said and any(p.get("status") in ("maybe", "limited") for p in imp.get("players") or [])
        if t.get("key_out") and not said and sport == "volleyball":
            who = "、".join(t["key_out"][:2])
            why.append(f"{name}的 {who} 缺陣（新聞說的），少了主力差很多，賽前再確認。")
        elif t.get("key_out") and not said:
            who = "、".join(t["key_out"][:2])
            why.append(f"{name}主力 {who} 不打，影響不小。")
        elif t.get("out_count", 0) >= 3 and not said:
            why.append(f"{name}有 {t['out_count']} 個人缺陣。")
        if t.get("key_maybe") and not said_maybe:
            care.append(f"{name}的 {t['key_maybe'][0]} 要賽前才知道打不打，開賽前再看一次。")
    # 手感
    unit = "分" if sport == "basketball" else "點"
    for t, name in ((H, hn), (A, an)):
        hurt = {x["player"] for x in t.get("injuries") or [] if x.get("severity") in ("maybe", "limited")}
        for p_ in [x for x in (t.get("hot") or []) if x.get("label") in ("火燙", "冰冷")][:1]:
            nm = _last(p_["player"])
            if p_["label"] == "火燙":
                why.append(f"{name}的 {nm} 最近手感很燙（近 5 場平均 {p_['last5']:g} {unit}，平常 {p_['season']:g}），不過手感會回到平常，別追太高。")
            elif p_["player"] in hurt:
                care.append(f"{name}的 {nm} 最近手感冷（近 5 場 {p_['last5']:g} {unit}，平常 {p_['season']:g}），又帶著傷，這不只是低潮，要扣分。")
            else:
                care.append(f"{name}的 {nm} 最近手感冷（近 5 場 {p_['last5']:g} {unit}，平常 {p_['season']:g}），不過這種等級的球員低潮通常幾場就過。")
    # 休息
    rest = a.get("rest") or {}
    for side, name in (("home", hn), ("away", an)):
        r = rest.get(side) if isinstance(rest, dict) else None
        if r and r.get("b2b"):
            if "背靠背" not in fan:
                care.append(f"{name}昨天才打完，今天背靠背第二場，第四節腳會比較沉。")
    dl = _dense_line(rest, hn, an, g.get("league")) if isinstance(rest, dict) and sport == "basketball" else None
    if dl and dl not in fan:
        care.append(dl)
    if sport == "basketball" and g["status"]["state"] != "post":
        import geo
        for line in geo.lines(g, hn, an):
            if line not in fan:
                care.append(line)
    # 對戰
    matchup = []
    hl = a.get("h2h_long") or {}
    h2h = a.get("h2h")
    if hl.get("n"):
        if hl.get("jinx"):
            win, lose = (hn, an) if hl["jinx"] == "home" else (an, hn)
            ww = hl["w"] if hl["jinx"] == "home" else hl["l"]
            line = f"{win}是{lose}的剋星：近 {hl['n']} 次碰面贏了 {ww} 次"
            if hl.get("avg_over") is None and hl.get("avg_margin") is not None:
                line += f"，平均贏 {abs(hl['avg_margin']):.0f} 分。"
            elif hl.get("avg_over") is not None:
                line += f"，而且平均比實力該贏的多贏 {abs(hl['avg_over']):.0f} 分。"
            else:
                line += "。"
        else:
            line = f"近 {hl['n']} 次交手{hn} {hl['w']} 勝 {hl['l']} 敗，看不出誰剋誰。"
        matchup.append(line)
    elif h2h and h2h.get("games"):
        hw = sum(1 for x in h2h["games"] if x["winner"] == "home")
        aw = sum(1 for x in h2h["games"] if x["winner"] == "away")
        if hw + aw >= 2 and hw != aw:
            matchup.append(f"最近交手{hn if hw > aw else an}贏比較多（{max(hw, aw)} 比 {min(hw, aw)}），場數少，參考就好。")
    st_ = a.get("style") or {}
    for line in (st_.get("lines") or [])[:3]:
        if line not in fan:
            matchup.append(line + (st_.get("note") or ""))
    # 近況扣掉對手強弱
    r0 = a.get("rating") or {}
    for side, name in (("home", hn), ("away", an)):
        fv = r0.get("form_" + side)
        if _pre_only(g, g[side]):
            continue        # 季前賽主力打不多，扣掉對手強弱也看不出什麼
        if fv and fv.get("n", 0) >= 3 and (abs(fv["recent"]) >= 5 or abs(fv["opp_avg"]) >= 3):
            if fv["opp_avg"] >= 3:
                sched = f"最近 {fv['n']} 場碰的多是強隊"
            elif fv["opp_avg"] <= -3:
                sched = f"最近 {fv['n']} 場碰的多是弱隊"
            else:
                sched = f"最近 {fv['n']} 場"
            how = f"扣掉對手強弱平均{'贏' if fv['recent'] >= 0 else '輸'} {abs(fv['recent']):.0f} 分" if abs(fv["recent"]) >= 1 else "扣掉對手強弱打得跟對手差不多"
            matchup.append(f"{name}{sched}，{how}。")
    # 盤口變動
    lm = a.get("line_move")
    if not own and lm and lm.get("spread_open") is not None and lm.get("spread_now") is not None and abs(lm["spread_now"] - lm["spread_open"]) >= 1:
        who = hn if lm["spread_now"] < lm["spread_open"] else an
        why.append(f"盤口往{who}那邊移，錢在押他。")
    # 實力評分 vs 盤口
    r = a.get("rating") or {}
    if own:
        # 讓分：我們算的分差 vs 台灣運彩的線
        sp_ = tw.get("spread") or {}
        lh = sp_.get("line_home")
        if est.get("margin") is not None and lh is not None and s.get("play") == "讓分" and pick in ("home", "away"):
            mine = lh if pick == "home" else -lh
            fav_ = hn if est["margin"] >= 0 else an
            pr = (s.get("probs") or {}).get("ats_" + pick)
            gap_ = "我們算的差距沒那麼大" if (fav_ != pn) else "我們算的差距比這還大"
            why.insert(1, f"台灣運彩開{pn}{'讓' if mine < 0 else '受讓'} {abs(mine):g} 分，{gap_}（{fav_}大概贏 {_r(est['margin'])} 分），所以押{pn}過的機會比較大{('（大概' + _cheng(pr) + '）') if pr else ''}。")
        if r.get("weak") and est.get("src") != "prev":
            care.append(f"兩隊這季才打 {min(r['gp_home'], r['gp_away'])} 場，實力還看不準，信心打折。")
        for side_, name in (("home", hn), ("away", an)):
            mw = r.get("motive_" + side_)
            if mw:
                (why if ("拚" in mw) == ((pick == side_) if pick in ("home", "away") else True) else care).append(f"{name}{mw}。")
    elif r and not r.get("weak") and r.get("diff") is not None and r.get("market_spread") is not None:
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
    if not own and crowd.get("ml_home") is not None and crowd.get("ml_away") is not None:
        v = max(crowd["ml_home"], crowd["ml_away"])
        side = hn if crowd["ml_home"] >= crowd["ml_away"] else an
        if v >= 80:
            care.append(f"{_cheng(v / 100)}的人都押{side}，太一面倒的時候反而常翻車。")
    # 台灣賠率划不划算
    v = s.get("value") or {}
    value_line = ""
    if own and v:
        if v["label"] == "划算":
            value_line = f"照我們估的{_cheng(v['p'])}，台灣運彩賠 {v['dec']:g}，押 100 元長期大概拿回 {v['back']} 元，划算。"
            why.append(value_line)
        elif v["label"] == "不划算":
            value_line = f"照我們估的{_cheng(v['p'])}，台灣運彩只賠 {v['dec']:g}，押 100 元長期大概只拿回 {v['back']} 元，不划算，要下就小注。"
            care.append(value_line)
        else:
            value_line = f"照我們估的{_cheng(v['p'])}，台灣運彩賠 {v['dec']:g}，押 100 元長期大概拿回 {v['back']} 元，普通。"
    elif s.get("tw_value") == "偏差":
        care.append(f"台灣運彩賠率 {s.get('tw_dec')} 比平常差，注碼小一點。")
    elif s.get("tw_value") == "划算":
        why.append(f"台灣運彩賠 {s.get('tw_dec')}，比平常好一點。")
    for c in s.get("cautions") or []:
        if "幾乎沒賺頭" in c:
            d_ = ((g.get("tw") or {}).get("ml") or {}).get(s.get("fav") or s.get("pick") or "")
            if s.get("play") == "讓分":
                care.append(f"不讓分只賠{f' {d_}' if d_ else '得很低'}，贏了也幾乎沒賺頭，所以改看讓分；讓分本來就接近五五波，信心最多給「中」。")
            else:
                care.append(f"不讓分只賠{f' {d_}' if d_ else '得很低'}，贏了也幾乎沒賺頭；讓分又不一定過，想下就小注。")
    # 大小分
    tot = s.get("totals")
    if tot and tot.get("lean") in ("大", "小"):
        how = "照兩隊得分和失分算，這場大概" if tot.get("method") == "評分" else "兩隊最近 5 場平均總分"
        line_ = tot.get("line_tw") if tot.get("line_tw") is not None else tot.get("line")
        lead = "" if tot.get("main") else f"大小分看「{tot['lean']}」："
        lname = "台灣運彩的線" if tot.get("line_tw") is not None else "國際盤的線"
        why.insert(0 if tot.get("main") else len(why), f"{lead}{how} {tot['expected']:.0f} 分，{lname} {line_:g}，差了 {abs(tot['expected'] - line_):.0f} 分。")
        if tot.get("main"):
            # 主建議是大小分：這兩句要排在最前面，不能被後面的近況擠掉
            extra = []
            if tot.get("prob"):
                extra.append(f"照這個差距算，{tot['lean']}分大概{_cheng(tot['prob'])}會中。")
            side_ = s.get("side") or {}
            if side_.get("pick") in ("home", "away"):
                sn = hn if side_["pick"] == "home" else an
                extra.append(f"輸贏我偏{sn}，但優勢不大，大小分比較有把握。")
            else:
                extra.append("輸贏看不出誰穩，大小分比較有把握。")
            why[1:1] = extra
    # 沒資料的時候也要講
    if not why:
        why.append(notes.get("form") or "兩隊資料還不多，先看賽前消息。")
    inj_news = any((t.get("injury_news") or []) for t in (H, A))
    matched = any(x.get("severity") in ("out", "maybe") for t in (H, A) for x in (t.get("injuries") or []))
    # 新聞有傷兵字眼、但對不到是哪個球員的：不叫爸爸自己去看新聞（AI 會讀原文，寫進分析）
    if not inj_news and not any(t.get("injuries") for t in (H, A)) and g["status"]["state"] != "post":
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
    elif g.get("league") == "eurodom":
        odds_line = "國內聯賽的台灣運彩賠率網站讀不到（官網只開放台灣的網路），要看賠率請開台灣運彩 App。"
    elif own or (o.get("prob_home") is not None and psrc != "form"):
        odds_line = "台灣運彩還沒開這場，通常前一天才會開。"
    else:
        odds_line = notes.get("odds") or "還沒開盤。"

    # 外界的看法（ESPN 電腦預測、新聞）直接寫進分析，不另外列一塊叫爸爸自己看
    out_ = s.get("outside") or {}
    if out_.get("espn") and est.get("p_home") is not None and g["status"]["state"] != "post":
        ep = out_["espn"]["home"]
        efav = hn if ep >= 0.5 else an
        if (ep >= 0.5) == (est["p_home"] >= 0.5):
            why.append(f"ESPN 的電腦預測也看好{efav}（{_cheng(max(ep, 1 - ep))}）。")
        else:
            care.append(f"ESPN 的電腦預測反而看好{efav}（{_cheng(max(ep, 1 - ep))}），兩邊看法不一樣，下注小一點。")
    # 場外消息、德比（context.py 從新聞挖的）：老球迷最在意的，放最前面
    if g["status"]["state"] != "post":
        extra = []
        extra += signal_lines(g, hn, an)
        if a.get("derby"):
            extra.append(f"這是{a['derby']}，兩隊碰面火氣大，強弱常常不準，別押太重。")
        for x in reversed(extra):
            if x not in care and x not in fan:
                care.insert(0, x)
    if g.get("season_type") == 1 and g["status"]["state"] != "post" and not any("季前賽" in x for x in care) and "季前賽" not in fan:
        care.insert(0, "現在是季前賽，主力常常輪休、打不久，戰績跟數據都不能當真。")
    if value_line and value_line not in why and value_line not in care:
        odds_line = (odds_line + value_line) if odds_line else value_line
    talk = dict(verdict=verdict, fan=fan, why=why[:5], care=care[:3], matchup=matchup[:4], odds=odds_line)
    talk["ai"] = ai_paragraphs(g, hn, an, fan, why, care, matchup)
    if sets:
        talk["note"] = "排球看局數，五局三勝。"
    return talk


def _sentences(text):
    return [x + "。" for x in (text or "").replace("。 ", "。").split("。") if x.strip()]


def ai_paragraphs(g, hn, an, fan, why, care, matchup):
    """「AI 分析」那一塊：把老球迷怎麼看、為什麼、怎麼算的、要小心合成幾段話。
    第一段講最關鍵的事；第二段補背景和理由；第三段把算法講成一句話；最後講要小心什麼。重複的句子拿掉。"""
    import re
    said = set(_sentences(fan))
    paras = []
    if fan:
        paras.append(fan.replace("。 ", "。"))
    calc = sum_line(g, hn, an)
    body = []
    early = False
    for line in bg_lines(g, hn, an):
        if line in said or (matchup and line.startswith(("近兩季碰過", "兩隊近兩季只碰過"))):
            if line.startswith(("開季", "這季")):
                early = line.startswith("開季")
            continue
        early = early or line.startswith("開季")
        body.append(line)
    for line in why:
        if line in said or line in body:
            continue
        if calc and line.startswith(("我們算", "這個聯盟數據少", "沒有盤口，看近況猜")):
            continue
        if early and re.match(r"^.{1,12}近 \d+ 場 \d+ 勝 \d+ 敗", line):
            continue
        body.append(line)
    if body:
        paras.append("".join(body[:6]))
    if calc and calc.replace("我們的算法：", "算下來，") not in fan:
        paras.append(calc)
    c = [x for x in care if x not in said][:3]
    if c:
        paras.append("要小心：" + "".join(c))
    return paras
