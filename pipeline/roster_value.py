# -*- coding: utf-8 -*-
"""今年陣容跟上季比，實力差多少（NBA、歐冠歐盃、CBA）：老球迷講的「這隊今年補了誰、少了誰」換成分數。

  逐場實力分（elo.py）開季時是從上季戰績帶過來的，看不到休賽季的補強（七六人補了 LeBron、Jaylen Brown，
  上季才 45 勝也不代表今年弱）。所以另外算「陣容變化」：
  1. 每個球員的貢獻 =（得分 + 0.8×籃板 + 1.2×助攻）× 出賽比例，一隊算前 10 個人。
  2. 上季的陣容：上季在這隊打的人、照真的出賽場數（主力整季受傷就少算，像溜馬少了 Haliburton）。
  3. 這季的名單：每個人最近一個健康球季的數字（上季整季受傷的看前一季）。
  4. 貢獻 1 單位值幾分：拿上季 30 隊的「陣容貢獻」對「場均淨勝分」算斜率，網站自己從資料學。
  5. 開季越久越不用：實力分會跟著真的比賽結果走，這季打 20 場以後就不加了。

  歐冠、歐盃：貢獻用官方的效率值（PIR）；從別的聯盟來的新人沒有上季的歐戰數據，先用他這季打的幾場（場數少的往一般輪換球員拉）。
  CBA：貢獻用新浪的效率值；新外援沒有上季的 CBA 數據，一樣先用這季打的幾場。
"""

import re

TOP = 10            # 一隊算前幾個人
FADE_GAMES = 20     # 這季打幾場之後就不再加陣容變化
SHRINK = 0.8        # 只信八成（新隊友要磨合、數字也有雜訊）
CAP = 9.0           # 最多加減幾分
K_DEFAULT = 0.25    # 學不到斜率的時候用的
MIN_GP = 20         # 上季打不到 20 場的，看前一季


def pra(s):
    return (s.get("ppg") or 0) + 0.8 * (s.get("rpg") or 0) + 1.2 * (s.get("apg") or 0)


def _actual(s):
    """那一季真的貢獻了多少（照出賽場數）。"""
    return pra(s) * min(1.0, (s.get("gp") or 0) / 82)


def _expected(pid, prev, prev2):
    """這季預期的貢獻：最近一個健康球季的數字（上季打不到 20 場、前一季有打的，看前一季）。回傳 (貢獻, 用的數字, 是不是傷癒回來)。"""
    pv, p2 = prev.get(pid), prev2.get(pid)
    use, back = pv, False
    if (not pv or (pv.get("gp") or 0) < MIN_GP) and p2 and (p2.get("gp") or 0) >= MIN_GP:
        use, back = p2, True
    if not use:
        return 0.0, None, False
    gps = [x.get("gp") or 0 for x in (pv, p2) if x]
    gp = max(use.get("gp") or 0, sum(gps) / len(gps))       # 出賽比例看最近兩季的平均（受傷打不多的那季不要扣太多）
    return pra(use) * min(1.0, gp / 75), use, back


def _top(vals):
    return sum(sorted(vals, reverse=True)[:TOP])


def team_values(stats):
    """{球隊: 那一季的陣容貢獻}（照真的出賽，前 10 個人）。"""
    by = {}
    for s in stats.values():
        if s.get("team"):
            by.setdefault(s["team"], []).append(_actual(s))
    return {t: _top(v) for t, v in by.items()}


def fit_k(values, margins):
    """陣容貢獻 1 單位值幾分：30 隊的「陣容貢獻」對「場均淨勝分」的斜率。回傳 (斜率, 相關係數, 隊數)。"""
    xs = [(values[t], margins[t]) for t in values if t in margins]
    if len(xs) < 20:
        return K_DEFAULT, None, len(xs)
    mx = sum(x for x, _ in xs) / len(xs)
    my = sum(y for _, y in xs) / len(xs)
    sxy = sum((x - mx) * (y - my) for x, y in xs)
    sxx = sum((x - mx) ** 2 for x, _ in xs)
    syy = sum((y - my) ** 2 for _, y in xs)
    if sxx <= 0 or syy <= 0:
        return K_DEFAULT, None, len(xs)
    k = sxy / sxx
    r = sxy / (sxx * syy) ** 0.5
    if r < 0.4:                 # 對不太起來（資料怪怪的）：用預設值
        return K_DEFAULT, round(r, 2), len(xs)
    return round(max(0.05, min(0.6, k)), 3), round(r, 2), len(xs)


def margins(games):
    """上季例行賽每隊場均淨勝分。games：nba_elo 用的比賽列表（background.nba_split 標好 rs）。"""
    tot, n = {}, {}
    for x in games:
        if x.get("season") != 0 or not x.get("rs"):
            continue
        d = x["hs"] - x["as_"]
        for t, v in ((x["h"], d), (x["a"], -d)):
            tot[t] = tot.get(t, 0) + v
            n[t] = n.get(t, 0) + 1
    return {t: tot[t] / n[t] for t in tot if n[t] >= 40}


def attach(games, data, season_games, log):
    """每隊 t["roster_change"]，每場 g.analysis.roster（主客隊各加幾分）。
    data：spotlight.nba_prepare 存的 dict(rosters={隊: [(球員 id, 名字)]}, prev=上季平均, prev2=前一季平均)。"""
    from background import NBA_ID
    from names_zh import NBA as NBA_ZH
    prev, prev2, rosters = data.get("prev") or {}, data.get("prev2") or {}, data.get("rosters") or {}
    if not prev or not rosters:
        return
    k, r, n_fit = fit_k(team_values(prev), margins(season_games))
    names = {pid: nm for ro in rosters.values() for pid, nm in ro}
    zh = lambda tid: NBA_ZH.get(NBA_ID.get(tid, ""), "")  # noqa: E731
    out = {}
    for tid, ro in rosters.items():
        ids = {pid for pid, _ in ro}
        now = []
        gained, back = [], []
        for pid, nm in ro:
            v, use, is_back = _expected(pid, prev, prev2)
            now.append(v)
            pv = prev.get(pid)
            if pv and pv.get("team") and pv["team"] != tid and v >= 12:
                gained.append(dict(player=nm, v=round(v, 1), frm=zh(pv["team"]), ppg=pv.get("ppg")))
            if is_back and v >= 12:
                back.append(dict(player=nm, v=round(v, 1), ppg=(use or {}).get("ppg")))
        lost = [dict(player=s.get("name") or names.get(pid) or "", v=round(_actual(s), 1), ppg=s.get("ppg"))
                for pid, s in prev.items() if s.get("team") == tid and pid not in ids and _actual(s) >= 8]
        v_now = _top(now)
        v_prev = _top([_actual(s) for s in prev.values() if s.get("team") == tid])
        raw = SHRINK * k * (v_now - v_prev)
        out[tid] = dict(raw=raw, v_now=round(v_now, 1), v_prev=round(v_prev, 1),
                        gained=sorted(gained, key=lambda x: -x["v"])[:3], back=sorted(back, key=lambda x: -x["v"])[:2],
                        lost=sorted(lost, key=lambda x: -x["v"])[:3])
    _center(out)
    n = 0
    for g in games:
        if g["league"] != "nba" or g["status"]["state"] == "post":
            continue
        el = (g.get("analysis") or {}).get("elo") or {}
        adj = {}
        for side in ("home", "away"):
            t = g[side]
            rc = out.get(str(t.get("id") or ""))
            if not rc:
                continue
            gp = el.get("n_" + side) or 0                # 這季已經打幾場
            fade = max(0.0, 1 - gp / FADE_GAMES)
            t["roster_change"] = dict(rc, pts=round(rc["raw"] * fade, 1), fade=round(fade, 2))
            adj[side] = t["roster_change"]["pts"]
        if adj:
            g.setdefault("analysis", {})["roster"] = dict(home=adj.get("home", 0.0), away=adj.get("away", 0.0), k=k)
            n += 1
    top = sorted(out.items(), key=lambda kv: -kv[1]["raw"])
    log(f"[nba] 陣容變化：貢獻 1 單位值 {k} 分（上季 {n_fit} 隊算的，相關 {r}）；用在 {n} 場；"
        f"變強最多 {[(zh(t), v['raw']) for t, v in top[:4]]}；變弱最多 {[(zh(t), v['raw']) for t, v in top[-3:]]}")


def _center(out, group=None):
    """跟聯盟平均比：整個聯盟不會每隊都變強（這季名單用每個人最好的一季、上季照真的出賽，會整體偏高），
    扣掉同一組（同一個聯盟、歐冠或歐盃）的平均，再限制最多加減幾分。"""
    by = {}
    for key, v in out.items():
        by.setdefault(group(key) if group else None, []).append(v["raw"])
    mean = {g: sum(v) / len(v) for g, v in by.items() if v}
    for key, v in out.items():
        r = v["raw"] - mean.get(group(key) if group else None, 0.0)
        v["raw"] = round(max(-CAP, min(CAP, r)), 1)


def line(t, name):
    """白話：「七六人今年補了 LeBron James（上季在湖人場均 21 分）、Jaylen Brown，少了…，網站估計陣容比上季強 5 分。」"""
    rc = t.get("roster_change") or {}
    if not rc or (abs(rc.get("raw") or 0) < 1.5 and not rc.get("gained") and not rc.get("back")):
        return None
    bits = []
    if rc.get("gained"):
        bits.append("今年補了 " + "、".join(f"{x['player']}" + (("（新來的，這季場均 {:.0f} 分）" if x.get("new") else f"（上季在{x['frm']}場均 {{:.0f}} 分）").format(x["ppg"])
                                                                if x.get("frm") and x.get("ppg") else "")
                                         for x in rc["gained"][:2]))
    if rc.get("back"):
        bits.append("、".join(x["player"] for x in rc["back"]) + " 傷癒回來")
    if rc.get("lost"):
        bits.append("少了 " + "、".join(x["player"] for x in rc["lost"][:2]))
    raw = rc.get("raw") or 0
    how = f"網站估計陣容比上季強 {raw:.0f} 分" if raw >= 1 else f"網站估計陣容比上季弱 {-raw:.0f} 分" if raw <= -1 else "陣容強弱跟上季差不多"
    return f"{name}" + "，".join(bits) + f"，{how}。"


# ---------- 共用：每隊的陣容變化 → 每場加幾分 ----------
REPLACE = {"el": 5.0, "cba": 8.0}      # 沒有上季數據的新人：先當成一般輪換球員（效率值），這季打越多場越看他自己
NEW_W = 3                              # 新人這季的數字要打幾場才全信（往一般輪換球員拉幾場）
AVAIL_NEW = 0.85                       # 新人整季大概打幾成的比賽（老球員是照上季真的出賽比例）


def _fit_grouped(rows):
    """rows：[(組別, 陣容貢獻, 場均淨勝分)]；每組（歐冠、歐盃各一組）先扣掉平均再一起算斜率。"""
    by = {}
    for grp, x, y in rows:
        by.setdefault(grp, []).append((x, y))
    xs = []
    for lst in by.values():
        if len(lst) < 6:
            continue
        mx, my = sum(x for x, _ in lst) / len(lst), sum(y for _, y in lst) / len(lst)
        xs += [(x - mx, y - my) for x, y in lst]
    if len(xs) < 12:
        return K_DEFAULT, None, len(xs)
    sxy, sxx, syy = sum(x * y for x, y in xs), sum(x * x for x, _ in xs), sum(y * y for _, y in xs)
    if sxx <= 0 or syy <= 0:
        return K_DEFAULT, None, len(xs)
    r = sxy / (sxx * syy) ** 0.5
    if r < 0.4:
        return K_DEFAULT, round(r, 2), len(xs)
    return round(max(0.05, min(1.5, sxy / sxx)), 3), round(r, 2), len(xs)


def _apply(games, out, key_fn, gp_fn, k, leagues):
    """每場 g.analysis.roster、每隊 t["roster_change"]；這季打越多場越不加。"""
    n = 0
    for g in games:
        if g["league"] not in leagues or g["status"]["state"] == "post":
            continue
        adj = {}
        for side in ("home", "away"):
            t = g[side]
            rc = out.get(key_fn(t))
            if not rc:
                continue
            fade = max(0.0, 1 - (gp_fn(g, side) or 0) / FADE_GAMES)
            t["roster_change"] = dict(rc, pts=round(rc["raw"] * fade, 1), fade=round(fade, 2))
            adj[side] = t["roster_change"]["pts"]
        if adj:
            g.setdefault("analysis", {})["roster"] = dict(home=adj.get("home", 0.0), away=adj.get("away", 0.0), k=k)
            n += 1
    return n


def _team_change(now, prev_actual, k):
    """now：這季名單每個人 (預期貢獻, 名字, 上季球隊或 None, 上季場均, 新人沒數據, 傷癒)；prev_actual：上季這隊每個人 (真的貢獻, 名字, 場均, 還在不在)。"""
    v_now = _top([x[0] for x in now])
    v_prev = _top([x[0] for x in prev_actual])
    raw = SHRINK * k * (v_now - v_prev)
    gained = sorted([dict(player=nm, v=round(v, 1), frm=frm, ppg=ppg, new=new) for v, nm, frm, ppg, new, _b in now if frm and v >= 6],
                    key=lambda x: -x["v"])[:3]
    back = sorted([dict(player=nm, v=round(v, 1), ppg=ppg) for v, nm, _f, ppg, _n, b in now if b and v >= 6], key=lambda x: -x["v"])[:2]
    lost = sorted([dict(player=nm, v=round(v, 1), ppg=ppg) for v, nm, ppg, stay in prev_actual if not stay and v >= 4], key=lambda x: -x["v"])[:3]
    return dict(raw=raw, v_now=round(v_now, 1), v_prev=round(v_prev, 1), gained=gained, back=back, lost=lost)


def _val(p, key="pir"):
    v = p.get(key)
    return float(v) if v is not None else pra(p)


# ---------- 歐冠、歐盃 ----------
def el_attach(games, el_state, log):
    """el_state：fetch 的 EL_STATE（rosters＝這季每隊名單和數據、prev_players＝上季每個球員、el＝官方資料）。"""
    rosters, prev = el_state.get("rosters") or {}, el_state.get("prev_players") or {}
    el = el_state.get("el")
    if not rosters or not prev or not el:
        return
    # 上季每隊打幾場（出賽比例用）、場均淨勝分（算斜率用）
    team_g, comp_of, tot, cnt = {}, {}, {}, {}
    for x in el.prev_games():
        if not x.get("rs"):
            continue
        d = x["hs"] - x["as_"]
        for c, v in ((x["home"], d), (x["away"], -d)):
            tot[c] = tot.get(c, 0) + v
            cnt[c] = cnt.get(c, 0) + 1
            comp_of[c] = x["comp"]
    for p in prev.values():
        team_g[p["team"]] = max(team_g.get(p["team"], 0), p.get("gp") or 0)
    actual = lambda p: _val(p) * min(1.0, (p.get("gp") or 0) / max(1, team_g.get(p["team"], 0)))  # noqa: E731
    vals = {}
    for p in prev.values():
        vals.setdefault(p["team"], []).append(actual(p))
    k, r, n_fit = _fit_grouped([(comp_of[c], _top(v), tot[c] / cnt[c]) for c, v in vals.items() if c in cnt and cnt[c] >= 10])
    zh = el.zh_name
    out = {}
    for code, lst in rosters.items():
        if code not in vals:
            continue            # 上季沒打歐戰的隊：沒有上季可以比
        ids = {p.get("id") for p in lst}
        now = []
        for p in lst:
            pv = prev.get(p.get("id"))
            if pv and (pv.get("gp") or 0) >= 6:
                v, new = actual(pv), False
            else:               # 從別的聯盟來的：這季的數字，往一般輪換球員拉
                gp = p.get("gp") or 0
                v, new = AVAIL_NEW * (_val(p) * gp + REPLACE["el"] * NEW_W) / (gp + NEW_W), True
            frm = (zh(pv["team"]) if pv else "別的聯盟") if (not pv or pv.get("team") != code) else None
            now.append((v, p.get("name") or "", frm, (pv or p).get("ppg"), new, False))
        prev_actual = [(actual(p), p.get("name") or "", p.get("ppg"), p.get("id") in ids) for p in prev.values() if p["team"] == code]
        out[code] = _team_change(now, prev_actual, k)
    _center(out, lambda c: comp_of.get(c))
    n = _apply(games, out, lambda t: t.get("el_code"), lambda g, s: ((g.get("analysis") or {}).get("elo") or {}).get("n_" + s), k,
               ("eurobasket", "eurodom"))
    top = sorted(out.items(), key=lambda kv: -kv[1]["raw"])
    log(f"[eurobasket] 陣容變化：效率值 1 單位值 {k} 分（上季 {n_fit} 隊算的，相關 {r}）；用在 {n} 場；"
        f"變強最多 {[(zh(c), v['raw']) for c, v in top[:4]]}；變弱最多 {[(zh(c), v['raw']) for c, v in top[-3:]]}")


# ---------- CBA ----------
def cba_attach(games, cur, prev, rosters, prev_rows, log):
    """cur、prev：新浪球員數據 {球員 id: dict(name, team 簡稱, gp, ppg, rpg, apg, eff)}；rosters：{新浪球隊代碼: [(球員 id, 名字)]}；
    prev_rows：上季排名表（每隊場均得失分，算斜率用）。"""
    import cba
    from cba import key_of
    if not prev or not rosters:
        return
    team_g = {}
    for p in prev.values():
        k_ = key_of(p.get("team"))
        team_g[k_] = max(team_g.get(k_, 0), p.get("gp") or 0)
    actual = lambda p: _val(p, "eff") * min(1.0, (p.get("gp") or 0) / max(1, team_g.get(key_of(p.get("team")), 0)))  # noqa: E731
    vals = {}
    for p in prev.values():
        vals.setdefault(key_of(p.get("team")), []).append(actual(p))
    margins_ = {key_of(r["team"]): r["pf"] - r["pa"] for r in prev_rows or [] if r.get("w", 0) + r.get("l", 0) >= 10}
    k, r, n_fit = fit_k({t: _top(v) for t, v in vals.items() if t}, margins_)
    # 新外援的起點：CBA 的外援通常是隊上最強的一兩個人，用上季各隊第 2 強的人的貢獻（中位數）
    seconds = sorted(sorted(v, reverse=True)[1] for v in vals.values() if len(v) >= 2)
    foreign_prior = seconds[len(seconds) // 2] if seconds else REPLACE["cba"]
    out = {}
    for sid, ro in rosters.items():
        team_key = next((key_of(p.get("team")) for pid, _ in ro for p in [cur.get(pid) or {}] if p.get("team")), None)
        if not team_key:
            continue
        ids = {pid for pid, _ in ro}
        now = []
        for pid, nm in ro:
            pv, c = prev.get(pid), cur.get(pid)
            if pv and (pv.get("gp") or 0) >= 8:
                v, new = actual(pv), False
            elif c:             # 新外援、新秀：這季打的幾場，新外援往一般外援的水準拉、新秀往一般輪換球員拉
                gp = c.get("gp") or 0
                prior = foreign_prior if re.search(r"[·・\-]", nm) else REPLACE["cba"]
                v, new = AVAIL_NEW * (_val(c, "eff") * gp + prior * NEW_W) / (gp + NEW_W), True
            else:
                continue        # 名單上但這季還沒上場、上季也沒數據
            frm = (cba.FULL.get(key_of(pv["team"])) or pv["team"]) if pv and key_of(pv.get("team")) != team_key else ("新外援或新秀" if not pv else None)
            now.append((v, cba._zh(nm), frm, (pv or c).get("ppg"), new, False))
        prev_actual = [(actual(p), cba._zh(p.get("name") or ""), p.get("ppg"), pid in ids) for pid, p in prev.items() if key_of(p.get("team")) == team_key]
        out[team_key] = _team_change(now, prev_actual, k)
    _center(out)

    def gp_of(g, side):
        rec = str(g[side].get("record") or "")
        try:
            w, l_ = rec.split("-")
            return int(w) + int(l_)
        except ValueError:
            return 0
    n = _apply(games, out, lambda t: key_of(t.get("name")), gp_of, k, ("cba",))
    top = sorted(out.items(), key=lambda kv: -kv[1]["raw"])
    log(f"[cba] 陣容變化：效率值 1 單位值 {k} 分（上季 {n_fit} 隊算的，相關 {r}），新外援起點 {foreign_prior:.1f}；用在 {n} 場；"
        f"變強最多 {[(cba.FULL.get(t, t), v['raw']) for t, v in top[:4]]}；變弱最多 {[(cba.FULL.get(t, t), v['raw']) for t, v in top[-3:]]}")
