# -*- coding: utf-8 -*-
"""把新聞「讀」成中文：爸爸不會去點新聞，更不會看外文標題，所以新聞裡挖到的東西要變成分析裡的一句中文。

  1. 誰受傷、誰回來：標題裡有這隊球員的名字（主力名單、手感名單），又有受傷或回來的字眼，就記成那個人的狀況
     （英文、日文已經有對名字的程式；這裡補西、義、土、法、德、立陶宛文。希臘文、希伯來文名字是當地文字，留給 AI 讀）
  2. 從新聞對出來的傷兵：說明改成中文（「土耳其媒體的消息」），原文標題留著給 AI 讀、給來源連結
  3. 沒對到球員的傷兵標題不用（常常是同名的別的新聞，像「富山灣遊覽船故障」）
  4. 每場整理一份「資料來源」（媒體、原文標題、連結），只放在分析最下面，點開才看"""
import re

from eurodom_names import norm

MEDIA = {"en": "外電", "ja": "日本媒體", "zh": "台灣媒體", "he": "以色列媒體", "el": "希臘媒體", "tr": "土耳其媒體", "es": "西班牙媒體",
         "it": "義大利媒體", "fr": "法國媒體", "de": "德國媒體", "lt": "立陶宛媒體"}
# 當地語言：回來了、這場不能上（比對前先去重音、轉小寫）
BACK = {
    "es": re.compile(r"vuelve|regresa|reaparece|recuperad|alta medica"), "it": re.compile(r"rientr|recuperat|torna|di nuovo in campo"),
    "tr": re.compile(r"geri don|donuyor|iyilesti|sahalara don"), "fr": re.compile(r"retour|revient|de retour|retrouve"),
    "de": re.compile(r"ruckkehr|zuruck|wieder fit|comeback"), "lt": re.compile(r"sugriz|grizta|pasveik"),
}
OUT = {
    "es": re.compile(r"se pierde|baja para|baja ante|fuera de|no jugara|operad|rotura|semanas de baja"),
    "it": re.compile(r"salta|assente|out per|stop di|operat|frattura|settimane"),
    "tr": re.compile(r"forma giyemeyecek|oynayamayacak|kadroda yok|kadroda yer almad|ameliyat|haftalarca"),
    "fr": re.compile(r"forfait|absent|indisponible|opere|fracture|semaines"),
    "de": re.compile(r"fallt aus|fehlt|ausfall|operiert|wochen|zwangspause"),
    "lt": re.compile(r"nezais|praleis|operac|savaic"),
}
INJ = re.compile(r"lesi[oó]n|lesionad|molestias|esguince|infortun|lesion|distorsion|sakat|tedavi|bless|entorse|verletz|angeschlagen|traum")
FOREIGN = re.compile(r"[぀-ヿ]|[A-Za-zÀ-ɏͰ-Ͽ֐-׿]{3,}")


def media_of(item):
    lang = item.get("lang")
    if not lang:
        t = item.get("title") or ""
        lang = "ja" if re.search(r"[぀-ヿ]", t) else "he" if re.search(r"[֐-׿]", t) else "el" if re.search(r"[Ͱ-Ͽ]", t) else "en"
    return MEDIA.get(lang, "外電")


def _candidates(t):
    """這隊可以拿來對名字的球員：主力名單、手感名單、傷兵名單。只用姓（4 個字母以上，避免撞到普通的字）。"""
    out = {}
    for x in (t.get("stars") or []) + (t.get("hot") or []) + (t.get("injuries") or []):
        name = x.get("player") or ""
        if not name or not re.search(r"[A-Za-z]", name):
            continue
        sur = norm(name).split(" ")[-1]
        if len(sur) >= 4 and sur not in out:
            out[sur] = x
    return out


def _local_injuries(t):
    """當地語言（拉丁字母）的傷兵標題對到主力名字：記成那個人的狀況。"""
    from players import team_impact
    cands = _candidates(t)
    if not cands:
        return 0
    have = {norm(x.get("player") or "") for x in t.get("injuries") or []}
    added = 0
    for a in t.get("injury_news") or []:
        lang = a.get("lang")
        if lang not in BACK:
            continue
        title = norm(a.get("title") or "")
        for sur, p in cands.items():
            if not re.search(r"(?<![a-z])" + re.escape(sur) + r"(?![a-z])", title) or norm(p.get("player") or "") in have:
                continue
            if BACK[lang].search(title):
                sev, zh = "ok", "回歸"
            elif OUT[lang].search(title):
                sev, zh = "out", "缺陣"
            elif INJ.search(title):
                sev, zh = "maybe", "存疑"
            else:
                continue
            t.setdefault("injuries", []).append(dict(
                id=p.get("id"), player=p.get("player"), headshot=p.get("headshot"), position=p.get("position"), status=sev, status_zh=zh,
                severity=sev, sev0=sev, official=False, source=a.get("source"), lang=lang, url=a.get("url"), detail=a.get("title"),
                ppg=p.get("ppg") if p.get("ppg") is not None else p.get("season"), mpg=p.get("mpg"), return_date=None, comment=None))
            have.add(norm(p.get("player") or ""))
            added += 1
    if added:
        imp = team_impact(t, "el")
        if imp and imp.get("players"):
            imp["note"] = "從傷兵報告和新聞對到球員，依場均得分估算"
            t["injury_impact"] = imp
    return added


def _zh_detail(x):
    """新聞對出來的傷兵：說明改成中文。原文留在 detail 給 AI 讀。"""
    if x.get("official") or not x.get("url"):
        return
    raw = x.get("detail") or ""
    if not FOREIGN.search(raw) and not x.get("source"):
        return
    who = media_of(dict(title=raw, lang=x.get("lang")))
    st = {"ok": "說他傷好回來了", "out": "說他這場不能上", "maybe": "說他有傷，還不確定能不能上", "limited": "說他帶傷上、可能打不久"}.get(x.get("severity"), "有提到他的傷")
    x["detail_zh"] = f"{who}{st}"
    x["media"] = who


def sources(g):
    """這場分析用到的新聞：(媒體, 原文標題, 連結, 來源網站)，給分析最下面的「資料來源」。"""
    out, seen = [], set()
    items = []
    for side in ("home", "away"):
        t = g[side]
        items += [x for x in t.get("injuries") or [] if x.get("url") and not x.get("official")]
        items += [dict(title=s.get("title"), url=s.get("url"), lang=s.get("lang")) for s in t.get("signals") or [] if s.get("title")]
        items += t.get("injury_news") or []
    items += g.get("news") or []
    items += ((g.get("ai") or {}).get("previews")) or []
    for x in items:
        title = x.get("detail") if x.get("player") else x.get("title")
        if not title or title in seen:
            continue
        seen.add(title)
        out.append(dict(media=media_of(dict(title=title, lang=x.get("lang"))), title=title[:120], url=x.get("url"), src=x.get("source") or x.get("src")))
    return out[:8]


def apply(games, log):
    n_add = n_zh = 0
    for g in games:
        if g["status"]["state"] == "post":
            continue
        for side in ("home", "away"):
            t = g[side]
            n_add += _local_injuries(t)
            # 沒對到球員的傷兵標題不用（只留給 AI 讀、放在資料來源）
            for x in t.get("injuries") or []:
                _zh_detail(x)
                n_zh += bool(x.get("detail_zh"))
    log(f"讀新聞：當地語言新聞對到 {n_add} 個球員的狀況，{n_zh} 筆新聞來的傷兵改成中文說明")
