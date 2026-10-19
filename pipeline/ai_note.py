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
DAILY_CAP = 450        # 免費額度一天大約 1000 次，留很多餘裕（加了 CBA，一天多 10 幾場）
RUN_CAP = 30
RESERVE = 80           # 每天留 50 次給還沒寫過的比賽（重寫舊的不能用掉）
NEAR_H = 72            # 跟完整分析一樣：72 小時內的比賽都寫（開打前三天就會有）
MIN_GAP_H = 2          # 事實有變，至少隔 2 小時才重寫
MIN_GAP_SOON_H = 1     # 6 小時內就要開打：傷兵名單常常臨時更新，隔 1 小時就可以重寫
MAX_AGE_H = 12         # 事實沒變，超過 12 小時也重寫一次（新聞會變）
SOON_REFRESH = (4, 3)  # 4 小時內開打、分析已經寫了 3 小時以上：開打前再寫一次最新的
PROMPT_VER = 12         # 寫法改了就加一：舊的分析不用等 2 小時，馬上重寫
GAP_S = 4.5            # 每分鐘最多 13 次左右，在免費額度（每分鐘 15 次）以內
KEEP_DAYS = 45

SYSTEM = """你是一位什麼運動都看、很會分析的台灣老球迷，正在跟家人聊等一下的比賽。讀的人是不太看數字、也看不懂外文新聞的長輩。

下筆前先想清楚：
- 兩隊今年各自是什麼狀態：爭冠、季後賽邊緣、年輕隊在崛起、重建或擺爛、主力傷癒回歸。上季戰績差不一定弱（例如主力整季受傷、球隊乾脆擺爛養新秀），上季好也可能主力走了，要講出原因。
- 這季補了誰、少了誰，新人跟球隊合不合，少了誰會缺什麼（得分、禁區、防守、控球）。
- 球員的心態：季前賽輸贏不重要、主力打不多；開季頭幾場新陣容還在磨合；開幕戰、碰老東家、連輸想止敗、德比、全國轉播通常比較認真；背靠背、排名已定、季末沒希望的隊可能不會太拚。
- 兩隊各有誰最值得看（「球員看點」：這季打得怎樣、手感、上場時間、新來的、傷癒回來），點名一兩個人講他這場的角色。
- CBA 的比賽先看外援：誰是外援、有沒有換人、外援受傷或還沒到隊，常常直接決定勝負；國家隊主力回來、長途客場（新疆、東北飛南方）也要注意。
- 這場「最有意思的故事」是什麼，就從那裡開始講。

寫法：
1. 第一行固定：「看好：隊名（幾成）」，例如「看好：湖人（六成五）」，意思是你覺得哪一隊會贏球（不是讓分押哪邊）；真的看不出來就寫「看好：兩隊差不多」。隊名用資料裡的中文隊名。
2. 第一行之後寫 150 到 250 字，2 到 3 小段，像聊天，不要條列、不要標題。不用照「重點、小心、結論」的固定順序，每篇的開頭都要不一樣。
3. 不要重複網站算的數字（勝率幾成、贏幾分、總分幾分），網頁下面已經有「算法」那一段；你的看法跟網站不同時，用一句話說為什麼就好。
4. 少用這些套話：「網站計算」「主場優勢加持」「舟車勞頓」「以逸待勞」「實力不容小覷」「卯足全力」「值得期待」「非常有看頭」。
5. 講人話：不稱呼讀者（不要寫「老爸」「爸媽」「你看」），直接講比賽；數字用阿拉伯數字（「5 勝 3 敗」「贏 8 分」），機率用「六成五」這種講法（不要寫「6.5 成」）；外國人名用英文拼法，不要自己音譯；
   資料裡用日文片假名寫的外國球員，改寫成英文拼法（例如 ジャレット・カルバー 寫成 Jarrett Culver），日本球員的漢字名字照用；
   CBA 的資料、新聞裡外援是中文音譯，照資料的中文名字寫成繁體就好（「塔克」就寫「塔克」，「萨姆纳」寫「薩姆納」），不要寫成英文；大陸用語換成台灣說法（「主帅」寫「總教練」、「季后赛」寫「季後賽」）；全部用繁體字。
6. 是推測就說「應該」「可能」「印象中」。

資料的規則：
7. 新聞標題可能是英文、日文、簡體中文（大陸媒體）、希伯來文、希臘文、土耳其文、西班牙文等，讀懂後把有用的消息（誰受傷、誰回來、換教練、欠薪、隊內問題、這場對誰特別重要）用中文寫進來，可以說「以色列媒體說…」「大陸媒體說…」「外電說…」。不要貼原文標題、不要叫讀者去看新聞；跟這兩隊無關的新聞完全不要提，也不要寫「這則新聞跟比賽無關」。
8. 只用資料裡的球員、數據、新聞，不能編。新聞只寫姓、看不出是誰的，不要猜全名，也不要猜成轉隊；只有「這季陣容」或新聞寫明的人才能說是新來的，主力名單、手感名單上的人不一定是新來的。
9. 你可以用自己對這些球隊的了解（例如誰上季整季受傷、哪隊在重建、哪隊陣容在巔峰），但要寫「印象中」，最新的轉隊、傷病一律以資料和新聞為準；跟資料衝突時聽資料的。
10. 判斷誰會贏只看：實力、近況、傷兵和誰會上、主力手感、休息、交手、打法對位、戰意、心態、新聞、ESPN 電腦預測。不要用賭盤、賠率、盤口、網友押哪邊來判斷誰會贏。
11. 「背靠背」只用在資料寫「背靠背第二場」（連兩天出賽）；標明「季前賽」的戰績不能當成近況或手感（季前賽主力打不多），最多提一句。
12. 「網站的建議」「網站的第二選擇」是我們網站自己算的；台灣運彩只提供賠率，不會建議押誰，不要寫「運彩說」「運彩建議」。資料裡有台灣運彩賠率，才可以在最後用一句話說划不划算；沒有賠率就不要講划不划算、也不要提賠率。有「網站的第二選擇」的話，可以用一句話評它合不合理。

口氣範例（只學口氣，內容和球隊不要照抄）：
「這兩隊今年走的是完全不同的路。一邊把陣容整個打掉重來，開季三連敗其實不意外，年輕人還在學怎麼贏球；另一邊核心都還在，只是少了上季最會防守的那個人，最近外線被打得有點慘。這場要看的是最後五分鐘誰穩得住。」
「說真的，這場比的是誰先回神。客隊週中才在歐戰打了延長賽，幾個主力都打滿三十分鐘以上；主隊整整休了一週，教練賽前也說這場一定要止敗。換作是我會站有休息的那一邊，不過應該贏不了太多。」"""

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
        elif p and p.get("conf"):
            last[n] = f"上季例行賽 {p['w']} 勝 {p['l']} 敗（勝場 {p['w']}、敗場 {p['l']}），{p['conf']}排第 {p['conf_rank']}；{p.get('playoff_zh') or '季後賽成績不知道'}"
        elif p:
            last[n] = f"上季{p['comp_zh']}{('前 ' + str(p['partial']) + ' 輪') if p.get('partial') else ''} {p['w']} 勝 {p['l']} 敗，{p['of']} 隊裡排第 {p['rank']}"
    if last:
        f["上季"] = last
    # 例行賽剛開打、還沒打正式比賽的隊：近況只有季前賽，要講清楚（主力打不多，不能當近況）
    pre = {side: t.get("form_note") == "季前賽" and g.get("season_type") != 1 for side, t in (("home", H), ("away", A))}
    form = {n: (("季前賽（主力打不多、不能當成近況）" if pre[side] else "") + _form_text(t))
            for side, t, n in (("home", H, hn), ("away", A, an)) if _form_text(t)}
    if form:
        f["最近比賽"] = form
    adj = {}
    for side, n in (("home", hn), ("away", an)):
        fv = rt.get("form_" + side)
        if fv and not pre[side]:
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
    spot = {n: [f"{x['player']}：{x['text']}" + (f"（{x['status_zh']}）" if x.get("status_zh") else "") for x in t.get("spot") or []]
            for t, n in ((H, hn), (A, an)) if t.get("spot")}
    if spot:
        f["球員看點"] = spot
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
    from newsread import media_of, relevant, team_words
    heads = [n["title"] for n in (g.get("_previews") or [])]
    if heads:
        ext["賽前分析的標題"] = heads[:5]
    news = {}
    for t, n in ((H, hn), (A, an)):
        lst, seen = [], set()
        words = team_words(t)
        items = [x for x in list(t.get("injury_news") or []) + [x for x in g.get("news") or [] if x.get("team") == ("home" if t is H else "away")]
                 if relevant(x, t, words)]
        items += [dict(title=x.get("title"), lang=x.get("lang"), published=x.get("published")) for x in t.get("signals") or []]
        for x in items:
            if x.get("title") and x["title"] not in seen:
                seen.add(x["title"])
                lst.append(f"[{media_of(x)}{(' ' + str(x.get('published'))[:10]) if x.get('published') else ''}] {x['title'][:140]}")
        if lst:
            news[n] = lst[:6]
    if news:
        f["新聞（請讀懂後用中文寫進分析）"] = news
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
        if s.get("summary"):
            calc["網站的建議"] = s["summary"]
        alt = s.get("alt") or {}
        if alt:
            calc["網站的第二選擇"] = (f"{alt['play']} {alt['pick_label']}" + (f" {alt['line']:g}" if alt.get("line") is not None else "")
                                     + f"，大概 {round(alt['prob'] * 100)}% 會中")
        f["網站的計算"] = calc
    # 這季陣容（歐戰官方名單比對）、休賽季動態（新聞）
    mv, off = {}, {}
    for t, n in ((H, hn), (A, an)):
        m = t.get("moves")
        if m:
            arr = "、".join(x["player"] + (f"（上季在{x['frm_zh']}，場均 {x['ppg_prev']:.0f} 分）" if x.get("frm_zh") and x.get("ppg_prev") is not None else "（新來的）")
                           for x in m.get("arrived", [])[:5])
            lft = "、".join(f"{x['player']}（上季場均 {x['ppg_prev']:.0f} 分{('，去了' + x['to_zh']) if x.get('to_zh') else ''}）"
                           for x in m.get("left", [])[:5] if x.get("ppg_prev") is not None)
            mv[n] = "；".join(x for x in ((f"新來：{arr}" if arr else ""), (f"走了：{lft}" if lft else "")) if x)
        if t.get("offseason"):
            off[n] = [f"[{media_of(x)}{(' ' + str(x.get('published'))[:10]) if x.get('published') else ''}] {x['title'][:140]}" for x in t["offseason"][:10]]
    if mv:
        f["這季陣容（官方名單比對）"] = mv
    if off:
        f["休賽季動態（新聞：簽約、交易、轉會，請讀懂後寫成補了誰、少了誰）"] = off
    # 心理和情勢（老球迷會想的）
    psy = []
    stype = g.get("season_type")
    if stype == 1:
        psy.append("這是季前賽：輸贏不重要，主力打不多，教練在試陣容、給年輕人機會")
    for t, n in ((H, hn), (A, an)):
        try:
            w_, l_ = [int(x) for x in str(t.get("record") or "").split("-")[:2]]
        except ValueError:
            w_ = l_ = None
        if stype != 1 and w_ is not None:
            if w_ + l_ == 0:
                psy.append(f"{n}這季第一場正式比賽（開幕戰）")
            elif w_ + l_ <= 5:
                psy.append(f"{n}開季才打 {w_ + l_} 場，新陣容還在磨合")
        sk = "" if (t.get("form_note") == "季前賽" and stype != 1) else str(t.get("streak") or "")   # 季前賽的連勝連敗不算
        if sk.startswith("連敗") and sk[2:].isdigit() and int(sk[2:]) >= 3:
            psy.append(f"{n}連輸 {sk[2:]} 場，會想止敗")
        elif sk.startswith("連勝") and sk[2:].isdigit() and int(sk[2:]) >= 5:
            psy.append(f"{n}連贏 {sk[2:]} 場，氣勢正旺，但也容易鬆懈")
    for side, n, on in (("home", hn, an), ("away", an, hn)):
        rv = (a.get("revenge") or {}).get(side)
        if rv:
            psy.append(f"{n}的 {'、'.join(rv)} 上季在{on}，這場碰老東家")
    if g.get("league") == "nba" and re.search(r"\b(ESPN|ABC|TNT|NBC|Prime|Peacock)\b", str(g.get("broadcast") or "")):
        psy.append("全國轉播的比賽，大牌球員通常比較認真")
    if psy:
        f["心理和情勢"] = psy
    tw = g.get("tw") or {}
    ml, sp, tt = tw.get("ml") or {}, tw.get("spread") or {}, tw.get("total") or {}
    twd = {}
    if ml.get("home") or ml.get("away"):
        twd["不讓分"] = f"{an} {ml.get('away')}、{hn} {ml.get('home')}"
    if sp.get("line"):
        twd["讓分"] = sp["line"]
    if tt.get("line") is not None:
        twd["大小"] = tt["line"]
    v = s.get("value")
    if v:
        twd["划不划算"] = f"照網站估的 {round(v['p'] * 100)}%，賠 {v['dec']}，押 100 長期拿回 {v['back']} 元（{v['label']}）"
    if twd:
        f["台灣運彩"] = twd
    else:
        f["台灣運彩"] = "這場網站讀不到台灣運彩的賠率，不要講划不划算"
    return f


def _hash(f):
    stable = {k: v for k, v in f.items() if k != "台灣運彩"}
    return hashlib.md5(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def previews(g, log=None):
    """Google 新聞找賽前分析（preview / prediction / 展望）。只在要寫 AI 分析時才找。"""
    H, A = g["home"], g["away"]
    cn = g.get("league") == "cba"
    if cn:          # CBA：大陸媒體（簡體）
        hn, an = H.get("cn_name") or "", A.get("cn_name") or ""
    else:
        hn = H.get("name") if H.get("name") and H.get("name").isascii() else (H.get("jp_name") or H.get("en_key") or "")
        an = A.get("name") if A.get("name") and A.get("name").isascii() else (A.get("jp_name") or A.get("en_key") or "")
    if not hn or not an:
        return []
    ja = not hn.isascii()
    q = f'"{hn}" "{an}" when:3d'
    hl = "zh-CN&gl=CN&ceid=CN:zh-Hans" if cn else "ja&gl=JP&ceid=JP:ja" if ja else "en-US&gl=US&ceid=US:en"
    url = f"https://news.google.com/rss/search?q={quote(q)}&hl={hl}"
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
        from newsread import NOISE
        if title and not NOISE.search(title):      # 博彩網站的賠率、預測頁不算（網站不看賭盤）
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
    """Gemini 偶爾回「現在太忙」（503）：等 15 秒再試一次。"""
    res = _call_once(key, f, log)
    if res.get("busy"):
        time.sleep(15)
        res = _call_once(key, f, log)
    return res


def _call_once(key, f, log):
    model = _pick_model(key, log)
    body = dict(
        systemInstruction=dict(parts=[dict(text=SYSTEM)]),
        contents=[dict(role="user", parts=[dict(text="比賽資料（JSON）：\n" + json.dumps(f, ensure_ascii=False, indent=1))])],
        generationConfig=dict(temperature=0.8, maxOutputTokens=900),
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
    return dict(error=err, busy=r.status_code >= 500)


# 模型偶爾混進簡體字：常見的直接換成繁體（只收在繁體裡沒有別的意思的字）
S2T = str.maketrans("难气这个们场战队赛胜败进还么对时会说让过为从来关于与应该现状态实际样点线级经验头号优势强结单双换补伤养轮练员联东区习惯顺风运动远连输赢击篮罚帮节调压纪录稳预测认观众见觉机两体况积极绝断继续适争显虽给别开门问题间长张带领导将专业广岛鸟鹳挡档摆烂归释读写尽虑担忧后发",
                    "難氣這個們場戰隊賽勝敗進還麼對時會說讓過為從來關於與應該現狀態實際樣點線級經驗頭號優勢強結單雙換補傷養輪練員聯東區習慣順風運動遠連輸贏擊籃罰幫節調壓紀錄穩預測認觀眾見覺機兩體況積極絕斷繼續適爭顯雖給別開門問題間長張帶領導將專業廣島鳥鸛擋檔擺爛歸釋讀寫盡慮擔憂後發")


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


def run(games, path, now, main_chips, log, errors, deadline=None):
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
    # 還沒寫過的先寫（每一場開打前都要有），再來才是重寫舊的；同一種裡先開打的先寫
    cands.sort(key=lambda x: (x[1]["id"] in notes, x[0]))
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
        to_start_h = (st - now).total_seconds() / 3600
        gap = MIN_GAP_SOON_H if to_start_h <= 6 else MIN_GAP_H
        need = (not old or old.get("ver") != PROMPT_VER or (old.get("hash") != h and (age_h is None or age_h >= gap))
                or (age_h is not None and age_h >= MAX_AGE_H)
                or (age_h is not None and to_start_h <= SOON_REFRESH[0] and age_h >= SOON_REFRESH[1]))
        if need and not stop:
            if not token:
                stop = "還沒設定 GEMINI_API_KEY（到 Google AI Studio 免費申請，放進 GitHub Secrets）"
            elif used_today >= DAILY_CAP:
                stop = f"今天已經寫了 {used_today} 次，到上限"
            elif n_new >= RUN_CAP:
                stop = f"這次已經寫 {n_new} 場，下次再寫"
            elif deadline and time.time() > deadline:
                stop = f"這次更新跑太久（寫了 {n_new} 場），剩下的下次再寫"
        if need and not stop and old and old.get("text") and used_today >= DAILY_CAP - RESERVE:
            need = False          # 額度快用完：留給還沒寫過的比賽，舊的先沿用
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
                                  previews=pv, day=g.get("day_tw"), ver=PROMPT_VER)
                n_new += 1
                if n_new == 1:
                    log(f"[AI] 第一篇（{res['model']}）：{res['text'][:160]!r}；額度：{res.get('headers')}")
                time.sleep(GAP_S)
            else:
                fails += 1
                if not res.get("busy"):          # Gemini 一時太忙不算錯，下一次更新會再寫
                    errors.append(f"AI 分析失敗 {gid}: {res.get('error')}")
                log(f"[AI] 失敗：{(res.get('error') or '')[:160]}")
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
            g["ai"] = dict(text=nt["text"].translate(S2T), lean=nt.get("lean"), p=nt.get("p"), at=nt.get("at"), model=nt.get("model"),
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
