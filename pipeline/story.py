# -*- coding: utf-8 -*-
"""把一場比賽的資料寫成幾段白話文，像朋友在解釋一樣。資料缺什麼就講什麼，不留空白。"""


def _n(t):
    return t.get("name_zh") or t.get("short") or t.get("name") or "對手"


def _pct(p):
    return f"{round(p * 100)}%"


def build_story(g, sport):
    H, A = g["home"], g["away"]
    hn, an = _n(H), _n(A)
    o = g.get("odds") or {}
    s = g.get("suggestion") or {}
    a = g.get("analysis") or {}
    tw = g.get("tw") or {}
    notes = g.get("notes") or {}
    tennis = bool(g.get("tennis"))
    paras = []

    # 1. 盤口與勝率
    ph, pa = o.get("prob_home"), o.get("prob_away")
    if ph is not None and pa is not None:
        fav = "home" if ph >= pa else "away"
        fn = hn if fav == "home" else an
        p = max(ph, pa)
        src = "依讓分盤推估" if o.get("prob_source") == "spread" else "國際盤"
        t = f"這場{'是 ' + an + ' 作客 ' + hn if not tennis else an + ' 對上 ' + hn}。{src}比較看好{fn}，換算勝率大約 {_pct(p)}，差不多是十場贏 {round(p * 10)} 場的意思"
        if o.get("prob_draw"):
            t += f"，和局機率約 {_pct(o['prob_draw'])}"
        pred = a.get("predictor")
        if pred:
            pv = pred["home"] if fav == "home" else pred["away"]
            diff = pv - p
            mood = "比盤口更看好" if diff >= 0.04 else ("比盤口保守一點" if diff <= -0.04 else "跟盤口看法差不多")
            t += f"；ESPN 的模型給{fn} {_pct(pv)}，{mood}。"
        else:
            t += "。"
        ml = tw.get("ml") or {}
        dec = ml.get(fav)
        if dec:
            val = s.get("tw_value")
            tail = {"划算": "比平常划算，可以考慮", "偏差": "比平常差，想下的話注碼小一點", "正常": "算正常水準"}.get(val, "")
            t += f" 台灣運彩不讓分賠率{fn} {dec:.2f}，{tail}。" if tail else f" 台灣運彩不讓分賠率{fn} {dec:.2f}。"
        elif tw.get("spread") or tw.get("total"):
            t += " 台灣運彩這場有開讓分和大小，不讓分還沒開。"
        elif notes.get("tw"):
            t += " " + notes["tw"]
        paras.append(t)
    else:
        paras.append(notes.get("odds") or f"這場目前還沒有盤口。通常開賽前一天盤口才會出現，先看下面的近況和傷兵。")

    if tennis:
        if s.get("pick"):
            paras.append(f"綜合起來我會偏向{s['pick_label']}，信心{s['confidence']}。")
        return paras

    # 2. 傷兵
    inj_parts = []
    for t, name in ((H, hn), (A, an)):
        inj = t.get("injuries") or []
        key_out = t.get("key_out") or []
        key_maybe = t.get("key_maybe") or []
        outs = [x for x in inj if x.get("severity") in ("out", "ir")]
        maybes = [x for x in inj if x.get("severity") == "maybe"]
        if key_out:
            who = "、".join(key_out[:3])
            reason = next((x.get("detail") for x in outs if x.get("player") in key_out and x.get("detail")), None)
            inj_parts.append(f"{name}的主力 {who} 確定缺陣" + (f"（{reason}）" if reason else "") + "，這個影響最大")
        elif outs:
            inj_parts.append(f"{name}有 {len(outs)} 名球員缺陣，但都不是主要得分來源")
        if key_maybe:
            inj_parts.append(f"{name}的 {'、'.join(key_maybe[:2])} 要到賽前才會決定上不上，開賽前再看一次")
        elif maybes:
            inj_parts.append(f"{name}另有 {len(maybes)} 人狀態存疑")
        if not inj and not outs and not maybes:
            if notes.get("injuries"):
                inj_parts.append(f"{name}{notes['injuries']}")
            else:
                inj_parts.append(f"{name}目前沒有傷兵回報")
    if inj_parts:
        paras.append("傷兵方面，" + "；".join(inj_parts) + "。")

    # 3. 近況、休息、手感
    form_parts = []
    for t, name, side in ((H, hn, "home"), (A, an, "away")):
        if t.get("last10"):
            f = f"{name}近 {len(t.get('form') or [])} 場 {t['last10']}"
            if t.get("streak"):
                f += f"，目前{t['streak']}"
            form_parts.append(f)
        rest = (a.get("rest") or {}).get(side)
        if rest:
            if rest.get("b2b"):
                form_parts.append(f"{name}昨天才打完，今天是背靠背第二天，體力和命中率通常會掉一點")
            elif rest.get("days") is not None and rest["days"] >= 3:
                form_parts.append(f"{name}休了 {rest['days']} 天，體力充足")
        for p in t.get("hot") or []:
            if p.get("label") == "火燙":
                form_parts.append(f"{name}的 {p['player']} 最近手感很燙，近 5 場場均 {p['last5']} {p['stat']}，季平均才 {p['season']}")
            elif p.get("label") == "冰冷":
                form_parts.append(f"{name}的 {p['player']} 最近手感偏冷，近 5 場場均 {p['last5']} {p['stat']}，比季平均低不少")
    h2h = a.get("h2h")
    if h2h and h2h.get("games"):
        hw = sum(1 for x in h2h["games"] if x["winner"] == "home")
        aw = sum(1 for x in h2h["games"] if x["winner"] == "away")
        if hw + aw:
            form_parts.append(f"兩隊最近 {hw + aw} 次交手{hn} {hw} 勝 {aw} 敗")
    lm = a.get("line_move")
    if lm and lm.get("spread_open") is not None and lm.get("spread_now") is not None and abs(lm["spread_now"] - lm["spread_open"]) >= 0.5:
        who = hn if lm["spread_now"] < lm["spread_open"] else an
        form_parts.append(f"盤口從開盤的 {lm['spread_open']:+g} 變成 {lm['spread_now']:+g}，代表錢往{who}那邊流")
    crowd = a.get("crowd")
    if crowd and crowd.get("ml_home") is not None:
        side = hn if crowd["ml_home"] >= 50 else an
        v = max(crowd["ml_home"], 100 - crowd["ml_home"])
        form_parts.append(f"玩運彩上有 {v}% 的玩家押{side}" + ("，一面倒的時候反而要小心" if v >= 75 else ""))
    if form_parts:
        paras.append("近況方面，" + "；".join(form_parts) + "。")
    elif notes.get("form"):
        paras.append(notes["form"])

    # 4. 結論
    if s.get("pick"):
        t = f"綜合起來，我會偏向{s['pick_label']}，玩法建議「{s['play']}」，信心{s['confidence']}。"
        if s.get("cautions"):
            t += f"要注意的是：{s['cautions'][0]}。"
        tot = s.get("totals")
        if tot and tot.get("lean") in ("大", "小"):
            t += f" 大小分方面，兩隊近五場平均總分 {tot['expected']}，盤口開 {tot['line']}，偏向「{tot['lean']}」。"
        paras.append(t)
    else:
        t = "綜合起來這場訊號互相矛盾或資料不夠，我會先觀望，等開賽前再看一次傷兵名單和盤口有沒有變動。"
        if s.get("summary") and "沒有盤口" in s["summary"]:
            t = "盤口還沒開，先不下結論。等盤口出來，上面的勝率和建議會自動更新。"
        paras.append(t)
    return paras
