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
PROBE = {"done": False}
INJ_TERMS = {
    "en": '(injury OR injured OR sidelined OR "ruled out" OR "will miss" OR "out for" OR "out indefinitely" OR surgery)',
    "ja": "(怪我 OR 負傷 OR 欠場 OR 離脱 OR 復帰 OR 手術 OR 故障)",
    "zh": "(受傷 OR 傷兵 OR 缺陣 OR 傷退 OR 復出)",
}
_cache = {}
STATS = {"calls": 0, "fail": 0}


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


def injury_news(name, lang, days=10, limit=3, hint=None):
    if not name:
        return []
    hint = SPORT_HINT.get(lang, "") if hint is None else hint
    q = f'"{name}"{hint} {INJ_TERMS.get(lang, INJ_TERMS["en"])} when:{days}d'
    kw = TITLE_KW.get(lang, TITLE_KW["en"])
    ex = EXCLUDE.get(lang)
    items = [x for x in _query(q, lang) if kw.search(x.get("title") or "") and not (ex and ex.search(x.get("title") or ""))]
    return items[:limit]


def team_news(name, lang, days=4, limit=3, hint=None):
    if not name:
        return []
    hint = SPORT_HINT.get(lang, "") if hint is None else hint
    ex = EXCLUDE.get(lang)
    return [x for x in _query(f'"{name}"{hint} when:{days}d', lang) if not (ex and ex.search(x.get("title") or ""))][:limit]


def probe_injury_report(items, log):
    """探路：Google 新聞裡的「EuroLeague Injury Report」連結實際指到哪（下一步想直接解析那一頁）。"""
    if PROBE["done"]:
        return
    for x in items:
        if "Injury Report" in (x.get("title") or "") and x.get("url"):
            PROBE["done"] = True
            try:
                import requests
                r = requests.get(x["url"], timeout=20, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
                log(f"[news] 傷兵報告連結 {x['url'][:80]} -> {r.status_code} {r.url[:120]} len={len(r.text)}")
                m = re.search(r'<a[^>]+href="(https?://[^"]+basketnews[^"]+)"', r.text)
                if m:
                    log(f"[news] 頁內 basketnews 連結：{m.group(1)[:140]}")
                txt = re.sub(r"<[^>]+>", " ", r.text)
                txt = re.sub(r"\s+", " ", txt)
                i = txt.find("Injury")
                log(f"[news] 內容片段：{txt[max(0, i - 200): i + 1200]}")
            except Exception as e:  # noqa: BLE001
                log(f"[news] 傷兵報告探路失敗 {e!r}")
            break


def attach(games, name_fn, log, errors, label, hint=None):
    """name_fn(team) -> (查詢用隊名, 語言) 或 None。掛上 t["injury_news"]、t["injury_note"]、g["news"]。"""
    n_team = n_news = 0
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
                t["injury_news"], t["injury_note"], tn = done[name]
            else:
                try:
                    inj = injury_news(name, lang, hint=hint)
                    tn = team_news(name, lang, hint=hint)
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{label} 新聞 {name} 失敗: {e!r}")
                    inj, tn = [], []
                if inj:
                    note = f"沒有官方傷兵名單，近 10 天新聞有提到傷兵相關消息（{len(inj)} 則，點進去看）"
                    n_team += 1
                else:
                    note = "沒有官方傷兵名單；近 10 天新聞沒有提到這隊的傷兵消息，通常代表陣容完整，但賽前仍可能臨時缺陣"
                t["injury_news"], t["injury_note"] = inj, note
                done[name] = (inj, note, tn)
            for a in tn[:2]:
                picked.append(dict(a, team=side))
        if picked:
            picked.sort(key=lambda x: x.get("published") or "", reverse=True)
            g["news"] = picked[:4]
            n_news += 1
    log(f"[{label}] 新聞：{n_team} 隊有傷兵相關新聞，{n_news} 場有一般新聞，呼叫 {STATS['calls']} 次、失敗 {STATS['fail']} 次")
