# -*- coding: utf-8 -*-
"""這季陣容跟上季比：補了誰、少了誰（老球迷開季一定先講的事）。

  歐冠、歐盃：官方球員數據（這季、上季各一份）直接比，誰是新來的（上季在哪一隊、場均幾分）、誰走了（去了哪裡）。
  新來的球員上季就在這場的對手那邊 → 「碰老東家」。
  其他聯盟（NBA、國內聯賽、日本籃球）沒有這種名單，改看休賽季的新聞（簽約、交易、轉會），交給 AI 讀（offseason.py）。"""

MIN_PREV_MPG = 12.0     # 上季打 12 分鐘以上才算主力，走了才值得講


def el_moves(now, prev):
    """now、prev：{隊伍代碼: [球員]}（players.fetch_el_players）。回傳 {代碼: dict(arrived=[...], left=[...])}。"""
    prev_team = {}
    for code, lst in prev.items():
        for p in lst:
            if p.get("id") and (p.get("gp") or 0) > 0:
                old = prev_team.get(p["id"])
                if not old or (p.get("gp") or 0) > (old[1].get("gp") or 0):
                    prev_team[p["id"]] = (code, p)
    now_team = {}
    for code, lst in now.items():
        for p in lst:
            if p.get("id"):
                now_team[p["id"]] = (code, p)
    out = {}
    for code, lst in now.items():
        if code not in prev:
            continue          # 上季沒打歐戰的隊，看不出誰是新來的
        prev_ids = {p["id"] for p in prev[code] if p.get("id")}
        arrived = []
        for p in sorted(lst, key=lambda x: -(x.get("ppg") or 0)):
            if not p.get("id") or p["id"] in prev_ids or (p.get("gp") or 0) == 0:
                continue
            frm = prev_team.get(p["id"])
            arrived.append(dict(player=p["name"], ppg=p.get("ppg"), mpg=p.get("mpg"),
                                frm=frm[0] if frm else None, ppg_prev=(frm[1].get("ppg") if frm else None)))
        left = []
        now_ids = {p["id"] for p in lst if p.get("id")}
        for p in sorted(prev[code], key=lambda x: -(x.get("ppg") or 0)):
            if not p.get("id") or p["id"] in now_ids or (p.get("mpg") or 0) < MIN_PREV_MPG or (p.get("gp") or 0) < 8:
                continue
            to = now_team.get(p["id"])
            left.append(dict(player=p["name"], ppg_prev=p.get("ppg"), to=to[0] if to else None))
        if arrived or left:
            out[code] = dict(arrived=arrived[:6], left=left[:6])
    return out


def attach(games, moves, zh, log):
    """球隊加上 t["moves"]（中文隊名填好，zh：代碼 -> 中文名的函式）；新來的上季在對手那邊 → g.analysis.revenge。"""
    n = n_rev = 0
    for g in games:
        for side, other in (("home", "away"), ("away", "home")):
            t = g[side]
            m = moves.get(t.get("el_code"))
            if not m:
                continue
            m = dict(arrived=[dict(x, frm_zh=zh(x["frm"]) if x.get("frm") else None) for x in m["arrived"]],
                     left=[dict(x, to_zh=zh(x["to"]) if x.get("to") else None) for x in m["left"]])
            t["moves"] = m
            n += 1
            opp = g[other].get("el_code")
            rev = [x["player"] for x in m["arrived"] if opp and x.get("frm") == opp]
            if rev:
                g.setdefault("analysis", {}).setdefault("revenge", {})[side] = rev
                n_rev += 1
    log(f"[eurobasket] 陣容變化：{n} 隊算出補了誰、少了誰；{n_rev} 隊有球員碰老東家")
