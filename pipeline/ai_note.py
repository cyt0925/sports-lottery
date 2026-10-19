# -*- coding: utf-8 -*-
"""AI 寫分析：把每場的事實（實力、近況、傷兵、手感、休息、交手、戰意、外界看法、我們的計算）交給
Google Gemini 的免費額度，請它像老球迷一樣寫一段分析，第一行寫它看好誰。
金鑰放在 GitHub 的 Secrets：GEMINI_API_KEY（到 Google AI Studio 免費申請）。沒有金鑰就不寫，網站照常。

免費額度有限，所以：
  - 只寫 36 小時內、爸爸要看的球種、還沒開打的比賽
  - 同一場事實沒變就不重寫；有變也至少隔 2 小時才重寫；每天最多 120 次、每次跑最多 20 場
  - 沒有權杖、額度用完、AI 出錯都沒關係：那場就不顯示 AI 那一段
AI 看好誰也記下來，打完對答案，成績單看 AI、我們的計算、盤口哪個準。"""
import hashlib
import json
import os
import re
import time
import html as htmlmod
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

TW = timezone(timedelta(hours=8))
DAILY_CAP = 120
RUN_CAP = 20
NEAR_H = 36
MIN_GAP_H = 2          # 事實有變，至少隔 2 小時才重寫
MAX_AGE_H = 12         # 事實沒變，超過 12 小時也重寫一次（新聞會變）
GAP_S = 7.0            # 每分鐘最多 8～9 次，免費額度比較安全
KEEP_DAYS = 45

SYSTEM = """你是一位什麼運動都看、很會分析的台灣老球迷，正在跟家人聊等一下的比賽。
規則：
1. 用台灣繁體中文、口語、講人話，像朋友聊天。不要條列、不要標題、不要英文縮寫堆砌。
2. 只能根據提供的資料。資料裡沒有的球員、數據、新聞，一個字都不能編；不確定就說不確定。
3. 判斷誰會贏只看：兩隊實力、最近狀況、傷兵和誰會不會上、主力手感、休息和背靠背、交手紀錄、打法對位、戰意、外界的看法（新聞標題、ESPN 電腦預測）。不要用賭盤、賠率、盤口、網友押哪邊來判斷誰會贏。
4. 可以在最後用一句話，根據「網站估的機率」和台灣運彩賠率，說划不划算。
5. 第一行固定格式：「看好：隊名（幾成）」，例如「看好：湖人（六成五）」，意思是你覺得哪一隊會贏球（不是讓分押哪邊）；真的看不出來就寫「看好：兩隊差不多」。隊名用資料裡的中文隊名。讓分、大小分的看法寫在內文裡。
6. 第一行之後寫 120 到 200 字，分 2 到 3 小段：最關鍵的一兩件事、要小心什麼、結論。
7. 你的看法可以跟網站的計算不同，不同的話要說為什麼。"""

CHENG_DIGITS = "零一二三四五六七八九十"


def _cheng(p):
    v = round(p * 20) / 2
    w, h = int(v), (v - int(v)) >= 0.5
    if w >= 10:
        return "九成五以上"
    return f"{CHENG_DIGITS[w]}成" + ("五" if h else "")


def _name(t):
    return t.get("name_zh") or t.get("short") or t.get("name") or ""


def _form_text(t):
    rows = [r for r in (t.get("form") or []) if r.get("pf") is not None]
    if not rows:
        return None
    w = sum(1 for r in rows if r.get("result") == "W")
    last = "、".join(f"{'贏' if r.get('result') == 'W' else '輸'}{r.get('opp_zh') or r.get('opp') or ''} {int(r['pf'])}-{int(r['pa'])}" for r in rows[-5:])
    return f"近 {len(rows)} 場 {w} 勝 {len(rows) - w} 敗（最近：{last}）"


def facts(g, sport):
    s = g.get("suggestion") or {}
    a = g.get("analysis") or {}
    rt = a.get("rating") or {}
    H, A = g["home"], g["away"]
    hn, an = _name(H), _name(A)
    f = {"聯盟": g.get("league_zh"), "開打": f"{g.get('day_tw')} {g.get('time_tw')}（台灣時間）", "主隊": hn, "客隊": an}
    if g.get("season_type") == 1:
        f["注意"] = "這是季前賽，主力常輪休、打不久"
    rec = {}
    for t, n in ((H, hn), (A, an)):
        bits = [x for x in (t.get("record"), t.get("rank_note")) if x]
        if bits:
            rec[n] = "，".join(bits)
    if rec:
        f["戰績"] = rec
    pv = ((a.get("bg") or {}).get("prev")) or {}
    last = {}
    for side, n in (("home", hn), ("away", an)):
        p = pv.get(side)
        if p and p.get("absent"):
            last[n] = f"上季{p['comp_zh']}的資料裡沒有這隊（可能剛升上來）"
        elif p:
            last[n] = f"上季{'例行賽' if p['comp'] == 'nba' else p['comp_zh']}{('前 ' + str(p['partial']) + ' 輪') if p.get('partial') else ''} {p['w']} 勝 {p['l']} 敗，{p['of']} 隊裡排第 {p['rank']}"
    if last:
        f["上季"] = last
    form = {n: _form_text(t) for t, n in ((H, hn), (A, an)) if _form_text(t)}
    if form:
        f["最近比賽"] = form
    adj = {}
    for side, n in (("home", hn), ("away", an)):
        fv = rt.get("form_" + side)
        if fv:
            adj[n] = f"最近 {fv['n']} 場扣掉對手強弱，平均{'贏' if fv['recent'] >= 0 else '輸'} {abs(fv['recent']):.0f} 分（對手平均強弱 {fv['opp_avg']:+.0f}）"
    if adj:
        f["扣掉對手強弱的近況"] = adj
    inj = {}
    for t, n in ((H, hn), (A, an)):
        lst = []
        for x in (t.get("injuries") or [])[:6]:
            st = x.get("status_zh") or x.get("status") or ""
            why = x.get("why") or ""
            ppg = f"，場均 {x['ppg']:.0f} 分" if x.get("ppg") else ""
            lst.append(f"{x.get('player')}：{st}{('（' + why + '）') if why else ''}{ppg}")
        if lst:
            inj[n] = lst
        elif t.get("injury_note"):
            inj[n] = [t["injury_note"]]
    if inj:
        f["傷兵和上場狀況"] = inj
    hot = {}
    for t, n in ((H, hn), (A, an)):
        lst = [f"{p['player']} 近 5 場 {p['last5']:g}、平常 {p['season']:g}（{p['label']}）" for p in (t.get("hot") or []) if p.get("label") in ("火燙", "冰冷")]
        if lst:
            hot[n] = lst
    if hot:
        f["主力手感"] = hot
    rest = a.get("rest") or {}
    if isinstance(rest, dict) and (rest.get("home") or rest.get("away")):
        def _r(x):
            if not x:
                return "無資料"
            base = "背靠背第二場" if x.get("b2b") else "本季首戰" if x.get("days") is None else f"休 {x['days']} 天"
            extra = f"，前 7 天打了 {x['last7']} 場" if x.get("last7") else ""
            return base + extra + ("，週中剛打完歐戰" if x.get("euro") else "")
        f["休息"] = {hn: _r(rest.get("home")), an: _r(rest.get("away"))}
    tr = a.get("travel") or {}
    if tr:
        mv = {}
        if tr.get("away_home_km") is not None:
            mv[an] = f"從{tr.get('away_city')}來，離家大概 {tr['away_home_km']} 公里"
        for side, n in (("home", hn), ("away", an)):
            p = tr.get(side + "_prev")
            if p:
                mv[n + "上一場"] = f"{p['days']:g} 天前在{p['city']}打{p.get('comp') or ''}，到這裡大概 {p['km']} 公里"
        if tr.get("tz_shift"):
            mv["時差"] = f"客隊往東飛 {tr['tz_shift']} 小時" if tr["tz_shift"] > 0 else f"客隊往西飛 {-tr['tz_shift']} 小時"
        f["移動距離（比賽在" + tr.get("venue", "") + "）"] = mv
    hl = a.get("h2h_long") or {}
    if hl.get("n"):
        f["交手"] = f"近 {hl['n']} 次交手，{hn} {hl.get('w')} 勝 {hl.get('l')} 敗，平均{'贏' if (hl.get('avg_margin') or 0) >= 0 else '輸'} {abs(hl.get('avg_margin') or 0):.0f} 分" + ("（剋星）" if hl.get("jinx") else "")
        if hl.get("games"):
            f["交手每場"] = [f"{x.get('date')} {x.get('season', '')}{x.get('comp', '')}，{hn}{'主場' if x.get('home') else '作客'} {x.get('pf')}:{x.get('pa')}" for x in hl["games"]]
    st_ = a.get("style") or {}
    if st_.get("lines"):
        f["打法對位"] = st_["lines"][:3]
    sig = {n: [f"{x['zh']}：{x.get('title') or ''}" for x in t.get("signals") or []] for t, n in ((H, hn), (A, an)) if t.get("signals")}
    if sig:
        f["場外消息（新聞、論壇）"] = sig
    if a.get("derby"):
        f["德比"] = f"這場是{a['derby']}，火氣大、強弱常常不準"
    mot = {n: rt.get("motive_" + side) for side, n in (("home", hn), ("away", an)) if rt.get("motive_" + side)}
    if mot:
        f["戰意"] = mot
    out = s.get("outside") or {}
    ext = {}
    if out.get("espn"):
        ep = out["espn"]["home"]
        ext["ESPN 電腦預測"] = f"{hn if ep >= 0.5 else an} {round(max(ep, 1 - ep) * 100)}%"
    heads = [n["title"] for n in (out.get("news") or [])] + [n["title"] for n in (g.get("_previews") or [])]
    if heads:
        ext["新聞標題"] = heads[:8]
    if ext:
        f["外界看法"] = ext
    est = s.get("est") or {}
    if est.get("p_home") is not None:
        fav = hn if est["p_home"] >= 0.5 else an
        calc = {"看好": fav, "勝率": f"{round(max(est['p_home'], 1 - est['p_home']) * 100)}%"}
        if est.get("margin") is not None:
            calc["大概贏幾分"] = abs(round(est["margin"]))
        if est.get("total") is not None:
            calc["總分大概"] = round(est["total"])
        if s.get("factors"):
            calc["各因素"] = [f"{x['label']}：{x['team'] or '差不多'} {x['pts']:g} 分" for x in s["factors"]]
        if est.get("weak"):
            calc["注意"] = "兩隊這季場數少，計算還不準"
        f["網站的計算"] = calc
    tw = g.get("tw") or {}
    ml, sp, tt = tw.get("ml") or {}, tw.get("spread") or {}, tw.get("total") or {}
    twd = {}
    if ml.get("home") or ml.get("away"):
        twd["不讓分"] = f"{an} {ml.get('away')}、{hn} {ml.get('home')}"
    if sp.get("line"):
        twd["讓分"] = sp["line"]
    if tt.get("line") is not None:
        twd["大小"] = tt["line"]
    if s.get("summary"):
        twd["網站的建議"] = s["summary"]
    v = s.get("value")
    if v:
        twd["划不划算"] = f"照網站估的 {round(v['p'] * 100)}%，賠 {v['dec']}，押 100 長期拿回 {v['back']} 元（{v['label']}）"
    if twd:
        f["台灣運彩"] = twd
    return f


def _hash(f):
    stable = {k: v for k, v in f.items() if k != "台灣運彩"}
    return hashlib.md5(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def previews(g, log=None):
    """Google 新聞找賽前分析（preview / prediction / 展望）。只在要寫 AI 分析時才找。"""
    H, A = g["home"], g["away"]
    hn = H.get("name") if H.get("name") and H.get("name").isascii() else (H.get("jp_name") or H.get("en_key") or "")
    an = A.get("name") if A.get("name") and A.get("name").isascii() else (A.get("jp_name") or A.get("en_key") or "")
    if not hn or not an:
        return []
    ja = not hn.isascii()
    q = f'"{hn}" "{an}" when:3d'
    url = f"https://news.google.com/rss/search?q={quote(q)}&hl={'ja&gl=JP&ceid=JP:ja' if ja else 'en-US&gl=US&ceid=US:en'}"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        root = ET.fromstring(r.content)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for it in root.iter("item"):
        title = htmlmod.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        src = it.find("source")
        if title:
            out.append(dict(title=title.split(" - ")[0], url=link, src=(src.text or "").strip() if src is not None else "新聞"))
        if len(out) >= 4:
            break
    time.sleep(0.5)
    return out


# Google Gemini（免費額度，只要 Google 帳號申請金鑰，不用信用卡）。
# GitHub 的免費 AI（GitHub Models）2026/7/30 已經停了，舊的 Azure 網址也沒了。
GEMINI = "https://generativelanguage.googleapis.com/v1beta"
PREFER = ("flash-lite", "flash")          # 免費額度給 Flash、Flash-Lite；Lite 額度最多
SKIP_WORDS = ("pro", "thinking", "image", "tts", "audio", "live", "embedding", "vision", "exp", "preview")
_MODEL = []
_LOGGED = set()


def _pick_model(key, log):
    """問 Google 現在有哪些模型，挑最新的 Flash-Lite（沒有就 Flash）。"""
    if _MODEL:
        return _MODEL[0]
    try:
        r = requests.get(f"{GEMINI}/models", params={"pageSize": 200}, headers={"x-goog-api-key": key}, timeout=20)
        names = [m.get("name", "").split("/")[-1] for m in (r.json().get("models") or [])
                 if "generateContent" in (m.get("supportedGenerationMethods") or [])]
    except Exception as e:  # noqa: BLE001
        log(f"[AI] 拿不到模型清單：{type(e).__name__}")
        names = []
    def ver(n):
        m = re.search(r"(\d+(?:\.\d+)?)", n)
        return float(m.group(1)) if m else 0.0
    for want in PREFER:
        cands = [n for n in names if want in n and not any(w in n for w in SKIP_WORDS if w not in want)]
        if want == "flash":
            cands = [n for n in cands if "lite" not in n]
        if cands:
            best = sorted(cands, key=lambda n: (ver(n), "latest" in n, -len(n)), reverse=True)[0]
            _MODEL.append(best)
            log(f"[AI] 用 Gemini 模型 {best}（可用的：{', '.join(sorted(names)[:12])}）")
            return best
    _MODEL.append("gemini-flash-lite-latest")
    return _MODEL[0]


def _call(key, f, log):
    model = _pick_model(key, log)
    body = dict(
        systemInstruction=dict(parts=[dict(text=SYSTEM)]),
        contents=[dict(role="user", parts=[dict(text="比賽資料（JSON）：\n" + json.dumps(f, ensure_ascii=False, indent=1))])],
        generationConfig=dict(temperature=0.4, maxOutputTokens=700),
    )
    try:
        # 金鑰放在標頭，不放網址：出錯訊息會印網址，不能讓金鑰跑進公開的資料檔
        r = requests.post(f"{GEMINI}/models/{model}:generateContent", headers={"x-goog-api-key": key}, json=body, timeout=60)
    except requests.RequestException as e:
        return dict(error=f"{model} 連不上：{e!r}"[:300], unreachable=True)
    text = None
    if r.status_code == 200:
        try:
            parts = r.json()["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
        except (KeyError, IndexError, ValueError, TypeError):
            text = None
    if text:
        return dict(text=text, model=model, headers={})
    err = f"{model}：HTTP {r.status_code} {r.text[:300]!r}"
    if model not in _LOGGED:
        _LOGGED.add(model)
        log(f"[AI] 不行：{err}")
    if r.status_code == 429:
        return dict(error=err, rate_limited=True)
    if r.status_code in (400, 401, 403):
        return dict(error=err, denied=True)
    return dict(error=err)


def parse(text, hn, an):
    """第一行「看好：隊名（幾成）」→ (lean, p, 其餘內文)。"""
    lines = [x.strip() for x in text.strip().splitlines() if x.strip()]
    lean, p, body = None, None, text.strip()
    if lines:
        m = re.match(r"^[*「#\s]*看好[:：]\s*(.+?)[*」\s]*$", lines[0])
        if m:
            body = "\n".join(lines[1:]).strip()
            who = m.group(1)
            if hn and hn in who or (len(hn) >= 2 and hn[:2] in who and not (an and an[:2] in who)):
                lean = "home"
            elif an and an in who or (len(an) >= 2 and an[:2] in who):
                lean = "away"
            mm = re.search(r"([一二三四五六七八九])成(五)?", who)
            if mm and lean:
                p = (CHENG_DIGITS.index(mm.group(1)) + (0.5 if mm.group(2) else 0)) / 10
    body = re.sub(r"\*\*", "", body)
    return lean, p, body


def run(games, path, now, main_chips, log, errors):
    """寫 AI 分析，掛在 g["ai"]。回傳 (寫了幾場, 用了快取幾場)。"""
    try:
        with open(path, encoding="utf-8") as fh:
            store = json.load(fh)
    except (OSError, ValueError):
        store = {}
    notes = store.setdefault("notes", {})
    usage = store.setdefault("usage", {})
    today = now.astimezone(TW).strftime("%Y-%m-%d")
    used_today = usage.get(today, 0)
    token = os.environ.get("GEMINI_API_KEY")
    n_new = n_cache = 0
    fails = 0
    stop = None
    cands = []
    for g in games:
        if (g.get("chip") or g["sport"]) not in main_chips or g["status"]["state"] != "pre":
            continue
        try:
            st = datetime.fromisoformat(str(g["start"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if st - now > timedelta(hours=NEAR_H):
            continue
        s = g.get("suggestion") or {}
        if not s.get("est") and not (s.get("outside") or {}).get("news"):
            continue
        cands.append((st, g))
    cands.sort(key=lambda x: x[0])
    for st, g in cands:
        gid = g["id"]
        old = notes.get(gid)
        f = facts(g, g["sport"])
        h = _hash(f)
        age_h = None
        if old and old.get("at"):
            try:
                age_h = (now - datetime.fromisoformat(old["at"])).total_seconds() / 3600
            except ValueError:
                age_h = None
        need = not old or (old.get("hash") != h and (age_h is None or age_h >= MIN_GAP_H)) or (age_h is not None and age_h >= MAX_AGE_H)
        if need and not stop:
            if not token:
                stop = "還沒設定 GEMINI_API_KEY（到 Google AI Studio 免費申請，放進 GitHub Secrets）"
            elif used_today >= DAILY_CAP:
                stop = f"今天已經寫了 {used_today} 次，到上限"
            elif n_new >= RUN_CAP:
                stop = f"這次已經寫 {n_new} 場，下次再寫"
        if need and not stop:
            pv = previews(g, log)
            if pv:
                g["_previews"] = pv
                f = facts(g, g["sport"])
            res = _call(token, f, log)
            if not res.get("unreachable"):
                used_today += 1
            if res.get("text"):
                fails = 0
                lean, p, body = parse(res["text"], _name(g["home"]), _name(g["away"]))
                notes[gid] = dict(hash=h, at=now.isoformat(timespec="minutes"), model=res["model"], text=body, lean=lean, p=p,
                                  previews=pv, day=g.get("day_tw"))
                n_new += 1
                if n_new == 1:
                    log(f"[AI] 第一篇（{res['model']}）：{res['text'][:160]!r}；額度：{res.get('headers')}")
                time.sleep(GAP_S)
            else:
                fails += 1
                errors.append(f"AI 分析失敗 {gid}: {res.get('error')}")
                log(f"[AI] 失敗：{res.get('error')}")
                if res.get("rate_limited"):
                    stop = "Gemini 免費額度這分鐘或今天用完了"
                elif res.get("denied"):
                    stop = "Gemini 金鑰不對或沒有權限"
                elif fails >= 2:
                    stop = "連續失敗兩次，這次先不寫"
        elif not need:
            n_cache += 1
        nt = notes.get(gid)
        if nt and nt.get("text"):
            g["ai"] = dict(text=nt["text"], lean=nt.get("lean"), p=nt.get("p"), at=nt.get("at"), model=nt.get("model"),
                           previews=nt.get("previews") or [])
        g.pop("_previews", None)
    usage[today] = used_today
    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    store["notes"] = {k: v for k, v in notes.items() if (v.get("day") or "9") >= cutoff}
    store["usage"] = {k: v for k, v in usage.items() if k >= cutoff}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(store, fh, ensure_ascii=False, separators=(",", ":"))
    log(f"[AI] 這次寫了 {n_new} 場、沿用 {n_cache} 場；今天累計 {used_today} 次" + (f"；停下來的原因：{stop}" if stop else ""))
    return n_new, n_cache


# ---------- 成績單：AI 看好的對不對 ----------
def track(hist, games, now):
    ai = hist.setdefault("ai", {})
    results = hist.get("results") or {}
    for g in games:
        gid = g["id"]
        if g["status"]["state"] == "pre" and (g.get("ai") or {}).get("lean"):
            ai[gid] = dict(day=g.get("day_tw"), lean=g["ai"]["lean"], p=g["ai"].get("p"), league=g["league"],
                           ours=((g.get("suggestion") or {}).get("model") or {}).get("pick"))
    for gid, e in ai.items():
        if "hit" in e:
            continue
        r = results.get(gid)
        if not r or r.get("hs") is None or r.get("as_") is None or r["hs"] == r["as_"]:
            continue
        home_won = r["hs"] > r["as_"]
        e["hit"] = (e["lean"] == "home") == home_won
        if e.get("ours"):
            e["ours_hit"] = (e["ours"] == "home") == home_won
        m = (hist.get("model") or {}).get(gid) or {}
        if m.get("mkt_home") is not None:
            e["mkt_hit"] = (m["mkt_home"] >= 0.5) == home_won
    cutoff = (now - timedelta(days=60)).strftime("%Y-%m-%d")
    hist["ai"] = {k: v for k, v in ai.items() if (v.get("day") or "9") >= cutoff}


def summary(hist, now, days=30):
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = [e for e in (hist.get("ai") or {}).values() if "hit" in e and (e.get("day") or "") >= cutoff]
    n = len(rows)
    out = dict(days=days, n=n, hit=sum(1 for e in rows if e["hit"]))
    both = [e for e in rows if "ours_hit" in e]
    mk = [e for e in rows if "mkt_hit" in e]
    out.update(n_ours=len(both), ours_hit=sum(1 for e in both if e["ours_hit"]),
               n_mkt=len(mk), mkt_hit=sum(1 for e in mk if e["mkt_hit"]),
               pending=sum(1 for e in (hist.get("ai") or {}).values() if "hit" not in e))
    return out
