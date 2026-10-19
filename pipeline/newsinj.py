# -*- coding: utf-8 -*-
"""沒有官方傷兵名單的聯盟（歐籃、日籃、日排）改用新聞：Google News RSS 免費、不用金鑰。
每隊查一次「傷兵關鍵字」，每場再查一次一般新聞。查不到也會留一句說明，不留空白。"""
import re
import time
import html as htmlmod
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote

from taiwan_odds import fetch

GN = "https://news.google.com/rss/search"
LANG = {
    "en": "hl=en-US&gl=US&ceid=US:en",
    "ja": "hl=ja&gl=JP&ceid=JP:ja",
    "zh": "hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "es": "hl=es&gl=ES&ceid=ES:es", "it": "hl=it&gl=IT&ceid=IT:it", "tr": "hl=tr&gl=TR&ceid=TR:tr", "fr": "hl=fr&gl=FR&ceid=FR:fr",
    "de": "hl=de&gl=DE&ceid=DE:de", "lt": "hl=lt&gl=LT&ceid=LT:lt", "el": "hl=el&gl=GR&ceid=GR:el", "he": "hl=he&gl=IL&ceid=IL:he",
}
LANG_ZH = {"es": "西班牙文", "it": "義大利文", "tr": "土耳其文", "fr": "法文", "de": "德文", "lt": "立陶宛文", "el": "希臘文", "he": "希伯來文"}
# 當地語言標題裡的傷兵字眼（比對前先去掉重音、轉小寫）
LOCAL_INJ = {
    "es": re.compile(r"lesi[oó]n|lesionad|\bbaja\b|se pierde|operad|molestias|rotura|esguince|recupera|vuelve"),
    "it": re.compile(r"infortun|assenz|assente|lesion|operat|distorsion|rientr|\bstop\b|out\b"),
    "tr": re.compile(r"sakat|forma giyemeyecek|ameliyat|kadroda yok|kadroda yer almad|tedavi|donuyor|geri don"),
    "fr": re.compile(r"bless|forfait|absent|indisponible|opere|entorse|retour|incertain"),
    "de": re.compile(r"verletz|fallt aus|ausfall|fehlt|operiert|zwangspause|ruckkehr|angeschlagen"),
    "lt": re.compile(r"traum|nezais|praleis|operac|sugriz"),
    "el": re.compile(r"τραυματ|εκτος|χανει|απουσ|ενοχλ|επιστρ|χειρουργ"),
    "he": re.compile(r"פציע|נפצע|לא ישחק|יחמיץ|מושבת|ניתוח|חוזר לשחק|חזרה"),
}
# 當地語言的足球字眼：同名的足球隊新聞不要
LOCAL_EX = {
    "es": re.compile(r"futbol|laliga|portero|delantero|mbappe|vinicius"), "it": re.compile(r"calcio|serie a\b|portiere|attaccante"),
    "tr": re.compile(r"futbol|super lig|kaleci|forvet"), "fr": re.compile(r"football|ligue 1|gardien|attaquant"),
    "de": re.compile(r"fussball|torwart|sturmer|1\. bundesliga"), "lt": re.compile(r"futbol"),
    "el": re.compile(r"ποδοσφαιρ|τερματοφυλακ|superleague|super league"), "he": re.compile(r"כדורגל"),
}
TITLE_KW = {
    "en": re.compile(r"injur|sidelin|ruled out|out for|out indefinitely|will miss|misses|absen|surgery|doubtful|questionable|return|hurt|sprain|strain|fracture|torn|knee|ankle|hamstring", re.I),
    "ja": re.compile(r"怪我|負傷|欠場|離脱|復帰|手術|故障|骨折|捻挫|肉離れ|不在"),
    "zh": re.compile(r"受傷|傷兵|缺陣|傷退|復出|手術"),
}
SPORT_HINT = {"en": " basketball", "ja": "", "zh": ""}
EXCLUDE = {
    "en": re.compile(r"\bAC Milan\b|soccer|football|Serie A|La ?Liga|Champions League|Europa League|UEFA|goalkeeper|striker|midfielder|winger|Aston Villa|Galatasaray|Juventus|Premier League|Bundesliga|Ligue 1|Super Lig|NCAA|college|motorcycle|cricket|rugby|hockey|Empoli|Ascoli|Mourinho|Gasperini|Svilar|Saelemaekers|Illinois|Serie B|Coppa|Copa del Rey|transfer window", re.I),
    "ja": re.compile(r"サッカー|Jリーグ|野球|ラグビー"),
    "zh": re.compile(r"足球|棒球"),
}
INJ_TERMS = {
    "en": '(injury OR injured OR sidelined OR "ruled out" OR "will miss" OR "out for" OR "out indefinitely" OR surgery)',
    "ja": "(怪我 OR 負傷 OR 欠場 OR 離脱 OR 復帰 OR 手術 OR 故障)",
    "zh": "(受傷 OR 傷兵 OR 缺陣 OR 傷退 OR 復出)",
}
_cache = {}
STATS = {"calls": 0, "fail": 0}
EXAMPLES = []


def _query(q, lang):
    key = (q, lang)
    if key in _cache:
        return _cache[key]
    url = f"{GN}?q={quote(q)}&{LANG.get(lang, LANG['en'])}"
    STATS["calls"] += 1
    text = fetch(url, tries=1)
    items = []
    if text:
        try:
            root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
            for it in root.iter("item"):
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                pub = it.findtext("pubDate") or ""
                src = it.find("source")
                try:
                    published = parsedate_to_datetime(pub).isoformat(timespec="minutes") if pub else None
                except (TypeError, ValueError):
                    published = None
                items.append(dict(title=htmlmod.unescape(title), url=link, published=published,
                                  source=(src.text or "").strip() if src is not None else None, desc=None, image=None))
        except ET.ParseError:
            STATS["fail"] += 1
    else:
        STATS["fail"] += 1
    items.sort(key=lambda x: x.get("published") or "", reverse=True)
    _cache[key] = items
    time.sleep(0.35)
    return items


def _excluded(title, name, ex):
    """標題有足球之類的字就不要；但那個字本來就是隊名的一部分（加拉塔薩雷、尤文圖特）不算。"""
    if not ex:
        return False
    nm = (name or "").lower()
    return any(m.group(0).lower() not in nm for m in ex.finditer(title or ""))


SIG_TERMS = {
    "en": '(coach OR fired OR sacked OR "parts ways" OR salary OR unpaid OR wages OR suspended OR suspension OR "locker room")',
    "ja": "(解任 OR ヘッドコーチ OR 出場停止 OR 給料)",
    "zh": "(換帥 OR 教練 OR 欠薪 OR 禁賽)",
}


def signal_news(name, lang, days=21, hint=None):
    """場外消息（換教練、欠薪、禁賽）：多查一次，交給 context.team_signals 挑。"""
    if not name:
        return []
    hint = SPORT_HINT.get(lang, "") if hint is None else hint
    ex = EXCLUDE.get(lang)
    return [x for x in _query(f'"{name}"{hint} {SIG_TERMS.get(lang, SIG_TERMS["en"])} when:{days}d', lang) if not _excluded(x.get("title"), name, ex)]


def injury_news(name, lang, days=10, limit=3, hint=None):
    if not name:
        return []
    hint = SPORT_HINT.get(lang, "") if hint is None else hint
    q = f'"{name}"{hint} {INJ_TERMS.get(lang, INJ_TERMS["en"])} when:{days}d'
    kw = TITLE_KW.get(lang, TITLE_KW["en"])
    ex = EXCLUDE.get(lang)
    items = [x for x in _query(q, lang) if kw.search(x.get("title") or "") and not _excluded(x.get("title"), name, ex)]
    return items[:limit]


def team_news(name, lang, days=4, limit=3, hint=None):
    if not name:
        return []
    hint = SPORT_HINT.get(lang, "") if hint is None else hint
    ex = EXCLUDE.get(lang)
    return [x for x in _query(f'"{name}"{hint} when:{days}d', lang) if not _excluded(x.get("title"), name, ex)][:limit]


def _norm(s):
    from eurodom_names import norm
    return norm(s)


def has_word(title, words):
    """標題裡有沒有這隊的名字：先去重音、轉小寫；希伯來文前面常黏著介係詞（ל、ב、ו），所以只看有沒有包含。"""
    n = _norm(title)
    for w in words or []:
        w = _norm(w)
        if not w:
            continue
        if re.search(r"[\u0590-\u05ff]", w):
            if w in n:
                return True
        elif re.search(r"(?<!\w)" + re.escape(w), n):
            return True
    return False


def local_news(spec, days=10):
    """當地語言的新聞：一隊只查一次（最近 10 天），再照標題分成傷兵、場外消息、一般新聞。
    spec = (當地隊名, 語言, 查詢加的字, 標題要有的字)。回傳 (傷兵新聞, 一般新聞, 全部)。"""
    q, lang, hint, must = spec
    items = _query(f'"{q}"{(" " + hint) if hint else ""} when:{days}d', lang)
    zh = LANG_ZH.get(lang, lang)
    ex, kw = LOCAL_EX.get(lang), LOCAL_INJ.get(lang)
    keep = []
    for x in items:
        t = x.get("title") or ""
        if not has_word(t, must) or (ex and ex.search(_norm(t))):
            continue
        keep.append(dict(x, source=f"{x.get('source') or '新聞'}（{zh}）", lang=lang))
    inj = [x for x in keep if kw and kw.search(_norm(x["title"]))][:3]
    from datetime import datetime, timedelta, timezone
    cut = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat(timespec="minutes")
    tn = [x for x in keep if (x.get("published") or "") >= cut and x not in inj][:3]
    return inj, tn, keep


def attach(games, name_fn, log, errors, label, hint=None, local_fn=None):
    """name_fn(team) -> (查詢用隊名, 語言) 或 None。掛上 t["injury_news"]、t["injury_note"]、g["news"]。
    local_fn(team) -> eurodom_names.local_query 的結果或 None：另外用當地語言查一次（國內的消息當地媒體最快）。"""
    n_team = n_news = n_sig = 0
    n_local = {}
    done = {}
    for g in games:
        if g["status"]["state"] == "post":
            continue
        picked = []
        for side in ("home", "away"):
            t = g[side]
            nl = name_fn(t)
            if not nl:
                t["injury_note"] = "這隊沒有可查的新聞隊名，傷兵狀況請賽前再確認"
                continue
            name, lang = nl
            if name in done:
                t["injury_news"], t["injury_note"], tn = done[name][:3]
                if done[name][3]:
                    t["signals"] = done[name][3]
            else:
                sig = []
                try:
                    inj = injury_news(name, lang, hint=hint)
                    tn = team_news(name, lang, hint=hint)
                    import context
                    sig = context.team_signals(signal_news(name, lang, hint=hint) + tn, must=context.must_words(name) if lang == "en" else [name])
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{label} 新聞 {name} 失敗: {e!r}")
                    inj, tn = [], []
                spec = local_fn(t) if local_fn else None
                if spec:
                    try:
                        import context
                        l_inj, l_tn, l_all = local_news(spec)
                        n_local.setdefault(spec[1], [0, 0, 0])
                        n_local[spec[1]][0] += 1
                        n_local[spec[1]][1] += len(l_all)
                        n_local[spec[1]][2] += len(l_inj)
                        if l_all and len(EXAMPLES) < 4:
                            EXAMPLES.append(f"{spec[0]}：{l_all[0]['title'][:60]}")
                        seen = {x.get("title") for x in inj + tn}
                        inj = sorted(inj + [x for x in l_inj if x["title"] not in seen], key=lambda x: x.get("published") or "", reverse=True)[:4]
                        tn = sorted(tn + [x for x in l_tn if x["title"] not in seen], key=lambda x: x.get("published") or "", reverse=True)[:4]
                        l_sig = context.team_signals(l_all, must=spec[3])
                        have = {x["kind"] for x in sig}
                        sig += [x for x in l_sig if x["kind"] not in have]
                    except Exception as e:  # noqa: BLE001
                        errors.append(f"{label} 當地新聞 {spec[0]} 失敗: {e!r}")
                if sig:
                    t["signals"] = sig
                    n_sig += 1
                if inj:
                    note = f"沒有官方傷兵名單，近 10 天新聞有提到傷兵相關消息（{len(inj)} 則，點進去看）"
                    n_team += 1
                else:
                    note = "沒有官方傷兵名單；近 10 天新聞沒有提到這隊的傷兵消息，通常代表陣容完整，但賽前仍可能臨時缺陣"
                t["injury_news"], t["injury_note"] = inj, note
                done[name] = (inj, note, tn, sig)
            for a in tn[:2]:
                picked.append(dict(a, team=side))
        if picked:
            picked.sort(key=lambda x: x.get("published") or "", reverse=True)
            g["news"] = picked[:4]
            n_news += 1
    log(f"[{label}] 新聞：{n_team} 隊有傷兵相關新聞，{n_sig} 隊有場外消息（換教練、欠薪、禁賽），{n_news} 場有一般新聞，呼叫 {STATS['calls']} 次、失敗 {STATS['fail']} 次")
    if n_local:
        log(f"[{label}] 當地語言新聞：" + "、".join(f"{LANG_ZH.get(k, k)} {v[0]} 隊 {v[1]} 則（傷兵 {v[2]}）" for k, v in n_local.items())
            + (f"；例：{' / '.join(EXAMPLES)}" if EXAMPLES else ""))
