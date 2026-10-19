# -*- coding: utf-8 -*-
"""休賽季的陣容變動（簽了誰、交易走誰、換教練）：沒有官方名單可以比的聯盟（NBA、國內聯賽、日本籃球），看新聞。

只在新球季剛開始的那段時間查（9 到 12 月），一隊三天查一次（Google 新聞最近 150 天），存在 data/offseason.json。
新聞交給 AI 讀，寫成「今年補了誰、少了誰，新人跟球隊合不合」；每次最多查 MAX_CALLS 隊，慢慢補齊。"""
import json
import os
from datetime import datetime, timezone

UTC = timezone.utc
MAX_CALLS = 40
REFRESH_H = 72
MONTHS = (9, 10, 11, 12)
WORDS = {
    "en": '(signs OR signed OR acquires OR acquired OR traded OR "free agent" OR offseason OR "new coach" OR roster)',
    "ja": "(加入 OR 獲得 OR 移籍 OR 契約 OR 退団 OR 新加入)",
    "es": "(fichaje OR ficha OR incorpora OR renueva OR plantilla)", "it": "(acquisto OR firma OR ingaggio OR mercato)",
    "tr": "(transfer OR imza OR kadro)", "fr": "(recrue OR signe OR mercato OR effectif)",
    "de": "(verpflichtet OR Neuzugang OR Kader OR Abgang)", "lt": "(pasirašė OR naujokas OR sudėtis OR sutartį)",
    "el": "(μεταγραφή OR υπέγραψε OR ρόστερ OR αποκτά)", "he": "(החתמה OR חתם OR סגל OR עזב)",
}


def _queries(t, league):
    """這隊要查哪幾種語言：NBA 英文；日本籃球日文；歐洲球隊英文＋當地語言。"""
    from eurodom_names import local_query
    out = []
    if league == "nba":
        if t.get("name"):
            out.append((t["name"], "en", ""))
    elif league == "jpbasket":
        if t.get("jp_name"):
            out.append((t["jp_name"], "ja", ""))
    else:
        if t.get("en_key"):
            out.append((t["en_key"], "en", " basketball"))
        for nm in (t.get("name"), t.get("en_key")):
            spec = local_query(nm or "")
            if spec:
                out.append((spec[0], spec[1], (" " + spec[2]) if spec[2] else ""))
                break
    return out


def attach(games, path, log, errors, now=None):
    now = now or datetime.now(UTC)
    if now.month not in MONTHS:
        return
    import newsinj
    from newsread import relevant, team_words, NOISE
    try:
        with open(path, encoding="utf-8") as f:
            store = json.load(f)
    except (OSError, ValueError):
        store = {}
    calls = n_team = 0
    todo = {}
    for g in games:
        if g["status"]["state"] == "post" or g.get("far") or g["league"] not in ("nba", "jpbasket", "eurobasket", "eurodom"):
            continue
        for side in ("home", "away"):
            t = g[side]
            for q, lang, hint in _queries(t, g["league"]):
                todo.setdefault(f"{lang}:{q}", (q, lang, hint, []))[3].append(t)
    # 最久沒查的先查
    order = sorted(todo, key=lambda k: (store.get(k) or {}).get("at", 0))
    for key in order:
        q, lang, hint, teams = todo[key]
        ent = store.get(key) or {}
        if calls < MAX_CALLS and now.timestamp() - ent.get("at", 0) >= REFRESH_H * 3600:
            calls += 1
            fails = newsinj.STATS["fail"]
            try:
                items = newsinj._query(f'"{q}"{hint} {WORDS.get(lang, WORDS["en"])} when:150d', lang)
            except Exception as e:  # noqa: BLE001
                errors.append(f"休賽季新聞 {q} 失敗: {e!r}")
                items = None
            if newsinj.STATS["fail"] > fails:
                items = None          # 沒查到（連不上）就不存，下次再查
            if items is not None:
                ent = dict(at=int(now.timestamp()), items=[dict(title=x.get("title"), url=x.get("url"), published=x.get("published"),
                                                                 source=x.get("source"), lang=lang) for x in items[:30]])
                store[key] = ent
        for t in teams:
            words = team_words(t)
            keep = [x for x in ent.get("items") or [] if relevant(x, t, words) and not NOISE.search(x.get("title") or "")]
            if keep:
                have = {x["title"] for x in t.get("offseason") or []}
                t["offseason"] = (t.get("offseason") or []) + [x for x in keep[:6] if x["title"] not in have]
                n_team += 1
    # 舊的（半年前）清掉
    store = {k: v for k, v in store.items() if now.timestamp() - v.get("at", 0) < 180 * 86400}
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, separators=(",", ":"))
    except OSError as e:
        errors.append(f"休賽季新聞存不了: {e!r}")
    left = sum(1 for k in todo if now.timestamp() - (store.get(k) or {}).get("at", 0) >= REFRESH_H * 3600)
    log(f"休賽季陣容新聞：查了 {calls} 次，{n_team} 隊有簽約、交易、轉會的新聞" + (f"；還有 {left} 個沒查，下次繼續" if left else ""))
