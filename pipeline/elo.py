# -*- coding: utf-8 -*-
"""逐場更新的實力分（像西洋棋的 Elo，但用分差）：每打完一場，照「贏多少、對手多強、在誰的主場」調整。

  預期分差 = 主隊實力 − 客隊實力 + 主場優勢（這個賽事的 + 這隊自己主場多出來的）
  打完：誤差 = 實際分差 − 預期分差（大比分只算到 ±22 分，最後幾分鐘垃圾時間不算數）
  主隊實力 += K × 誤差，客隊實力 −= K × 誤差；本季前幾場 K 大一點（換了人，要快點跟上）
  新球季開始：實力打折往中間拉（換人、老化）
  主場優勢：每個賽事的主場值幾分、每隊自己的主場加成（最多 ±3 分），也跟著比賽一起慢慢學

學習：每次都拿過去兩季的比賽重算一遍，試幾組 K 和打折的比例，挑「預測最準」的那組（Brier 分數最低）。
所以網站錯得越多，數字就會自己往對的方向修。"""
from math import erf, exp, sqrt

SIGMA = 11.0
CLIP = 22.0
OFF_CAP = 3.0
DEFAULT = dict(k=0.07, k0=0.08, regress=0.7, kh=0.004, kt=0.012)
GRID = [dict(k=k, k0=k0, regress=rg) for k in (0.04, 0.06, 0.08, 0.10) for k0 in (0.0, 0.08) for rg in (0.6, 0.75)]
WARMUP = 150      # 前面這幾場當暖身，不拿來評分
# 只打國內聯賽的球隊，起點比歐冠平均低幾分（聯賽越強越接近歐冠）
LEAGUE_PRIOR = {"acb": -6.0, "bsl": -6.0, "lba": -7.0, "gbl": -8.0, "lnb": -7.0, "bbl": -7.0, "aba": -7.0, "isr": -8.0, "lkl": -9.0}


def _phi(x):
    return 0.5 * (1 + erf(x / sqrt(2)))


def rate(games, hca0, params=None, hca_default=3.0, prior=None):
    """games：由舊到新 [dict(ts, h, a, hs, as_, comp, season, neutral)]。回傳最後的實力、主場、每場賽前的預測。
    prior：每隊的起點（歐冠球隊 0、歐盃 −4、各國國內球隊照聯賽強弱 −6～−9），新球季也是往起點拉，不是往 0。"""
    P = dict(DEFAULT, **(params or {}))
    prior = prior or {}
    R, N, NT, HC, OFF = {}, {}, {}, dict(hca0), {}
    preds = []
    season = None
    for g in games:
        if g["season"] != season:
            if season is not None:
                R = {k: prior.get(k, 0.0) + (v - prior.get(k, 0.0)) * P["regress"] for k, v in R.items()}
                OFF = {k: v * 0.8 for k, v in OFF.items()}
                N = {}
            season = g["season"]
        h, a = g["h"], g["a"]
        rh, ra = R.get(h, prior.get(h, 0.0)), R.get(a, prior.get(a, 0.0))
        neutral = bool(g.get("neutral"))
        hc = 0.0 if neutral else HC.get(g["comp"], hca_default) + OFF.get(h, 0.0)
        exp_m = rh - ra + hc
        m = g["hs"] - g["as_"]
        preds.append((g["ts"], g["comp"], exp_m, m, min(NT.get(h, 0), NT.get(a, 0)), g["season"]))
        e = max(-CLIP, min(CLIP, m - exp_m))
        kh = P["k"] + P["k0"] * exp(-N.get(h, 0) / 6)
        ka = P["k"] + P["k0"] * exp(-N.get(a, 0) / 6)
        R[h], R[a] = rh + kh * e, ra - ka * e
        if not neutral:
            HC[g["comp"]] = HC.get(g["comp"], hca_default) + P["kh"] * e
            OFF[h] = max(-OFF_CAP, min(OFF_CAP, OFF.get(h, 0.0) * 0.995 + P["kt"] * e))
        for t in (h, a):
            N[t] = N.get(t, 0) + 1
            NT[t] = NT.get(t, 0) + 1
    return dict(R=R, N=N, NT=NT, HC=HC, OFF=OFF, preds=preds, params=P)


def score(preds, since_ts=None):
    """賽前預測準不準：Brier（越低越準，0.25 等於丟銅板）、猜中幾成、分差平均差幾分。"""
    rows = [p for p in preds[WARMUP:] if p[3] != 0 and (since_ts is None or p[0] >= since_ts)]
    if not rows:
        return None
    br = hit = mae = 0.0
    for _ts, _c, e, m, _n, _s in rows:
        p = _phi(e / SIGMA)
        y = 1.0 if m > 0 else 0.0
        br += (p - y) ** 2
        hit += 1 if (e > 0) == (m > 0) else 0
        mae += abs(m - e)
    n = len(rows)
    return dict(n=n, brier=round(br / n, 4), hit=round(hit / n, 3), mae=round(mae / n, 1))


def tune(games, hca0, hca_default=3.0, since_ts=None, prior=None):
    """試幾組參數，挑預測最準的。回傳 (最好的結果, 分數, 預設參數的分數)。"""
    best, best_s = None, None
    base = rate(games, hca0, None, hca_default, prior)
    base_s = score(base["preds"], since_ts)
    for P in GRID:
        st = rate(games, hca0, P, hca_default, prior)
        s = score(st["preds"], since_ts)
        if s and (best_s is None or s["brier"] < best_s["brier"]):
            best, best_s = st, s
    if best is None or (base_s and best_s and base_s["brier"] <= best_s["brier"]):
        return base, base_s, base_s
    return best, best_s, base_s


def predict(st, h, a, comp, hca_default=3.0, neutral=False):
    rh, ra = st["R"].get(h), st["R"].get(a)
    if rh is None and ra is None:
        return None
    rh, ra = rh or 0.0, ra or 0.0
    league_h = 0.0 if neutral else st["HC"].get(comp, hca_default)
    off = 0.0 if neutral else st["OFF"].get(h, 0.0)
    return dict(home=round(rh, 1), away=round(ra, 1), hca=round(league_h + off, 1), hca_league=round(league_h, 1), off_home=round(off, 1),
                n_home=st["N"].get(h, 0), n_away=st["N"].get(a, 0), nt_home=st["NT"].get(h, 0), nt_away=st["NT"].get(a, 0),
                margin=round(rh - ra + league_h + off, 1))
