# -*- coding: utf-8 -*-
"""老球迷會注意的場外消息：從新聞標題挖出來，變成白話提醒，也算一點分數（分數多少由 learn.py 自己學）。

  換教練：新教練頭幾場球員通常比較拚（新官上任），但戰術還在磨合
  欠薪、財務出問題：球員場上常常不夠拚
  禁賽、更衣室不和、打架：隊伍氣氛差
  德比戰：同城或宿敵碰面，火氣大，強弱常常不準（把兩隊的差距往中間拉一點）
新聞標題有各國語言（英、西、義、土、法、德、立陶宛、希臘、希伯來、日、中），關鍵字盡量都列。"""
import re
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
KINDS = {
    "coach": dict(days=14, pts=0.6, zh="換教練", re=re.compile(
        r"(?:coach|entrenador|allenatore|antren[öo]r|trainer|entra[iî]neur).{0,40}(?:fired|sacked|dismissed|let go|parts? ways|esonerat|destitu|cesad|g[öo]revden|entlassen|limog|remerci)"
        r"|(?:fired|sacked|dismissed|esonerat\w*|destitu\w*|cesad\w*|limog\w*|remerci\w*|parts? ways with).{0,40}(?:coach|entrenador|allenatore|antren|trainer|entra[iî]neur)"
        r"|new head coach|interim (?:head )?coach|appoint\w* .{0,40}coach|nuevo entrenador|nuovo allenatore|yeni ba[sş]antren[öo]r|nouvel entra[iî]neur|neuer trainer"
        r"|解任|新ヘッドコーチ|換帥|新教練"
        # 土、德、立陶宛、希臘、希伯來文（比對的是去掉重音、轉小寫的標題）
        r"|yollar[ıi]n[ıi] ay[ıi]rd|g[öo]revden al[ıi]nd|trennt sich von (?:trainer|coach|cheftrainer)|freigestellt|naujas treneris|trener\w* atleist|atleido trener"
        r"|(?:απολυ|απελυσ|λυση συνεργασιας|αποχωρ|τελος).{0,40}προπονητ|προπονητ.{0,40}(?:απολυ|απελυ|λυση συνεργασιας|αποχωρ)|νεος προπονητης|νεο προπονητη"
        r"|(?:פוטר|פיטר|פיטורי|נפרד).{0,30}מאמן|מאמן.{0,30}(?:פוטר|פיטר|נפרד)|מאמן חדש|המאמן החדש", re.I)),
    "money": dict(days=21, pts=-1.0, zh="欠薪、財務問題", re=re.compile(
        # 只說「薪水」不算，要「沒付、拖欠、財務出問題」才算
        r"(unpaid|not been paid|salar(?:y|ies) (?:delay|owed|unpaid|arrears)|wages (?:owed|unpaid|delay)|financial (?:trouble|problems|crisis|difficult)|bankrupt\w*|insolven\w*|"
        r"stipendi (?:non pagati|arretrati)|ritardo (?:nei|negli|degli) stipendi|impag\w*|sueldos (?:impagados|atrasados|pendientes)|"
        r"maa[sş]lar[ıi]n[ıi] alamad|maa[sş] (?:sorunu|krizi)|maa[sş]lar (?:odenmedi|yatmad)|finanzielle (?:probleme|schwierigkeiten)|"
        r"給料未払い|欠薪|財務危機|salaires impayes|difficultes financieres|ausstehende gehalter|gehalter (?:nicht|ausstehend)|"
        r"nesumoket\w* atlyginim|atlyginim\w* (?:skol|nemok|velu)|finansin\w* (?:problem|sunkum)|απληρωτ|οικονομικα προβληματα|"
        r"הלנת שכר|לא קיבלו משכורת|משכורות לא שולמו|קשיים כלכליים)", re.I)),
    "turmoil": dict(days=7, pts=-0.5, zh="禁賽、隊內不和", re=re.compile(
        r"(locker[- ]room (?:issue|problem|tension|drama)|\brift\b|\bfeud\b|\bsuspen(?:ded|sion)\b|\bbrawl\b|disciplinary|fight with (?:teammate|coach)|"
        r"squalifica|sanci[oó]n|ihra[cç]|出場停止|内紛|內鬨|禁賽|gesperrt|diskvalifik|τιμωρια|αποβολ|καβγα|הורחק|הרחקה|קטטה)", re.I)),
}
NOT = re.compile(r"fired up|suspended (?:game|match) (?:resumes|to resume)|coach of the (?:week|month|year)", re.I)
SIG_CAP = 1.5

# 德比：(關鍵字, 關鍵字, 中文名)
DERBIES = [
    ("olympiacos", "panathinaikos", "雅典永恆德比"), ("fenerbahce", "galatasaray", "伊斯坦堡德比"), ("fenerbahce", "efes", "伊斯坦堡德比"),
    ("fenerbahce", "besiktas", "伊斯坦堡德比"), ("galatasaray", "besiktas", "伊斯坦堡德比"), ("efes", "galatasaray", "伊斯坦堡德比"),
    ("efes", "besiktas", "伊斯坦堡德比"), ("crvena", "partizan", "貝爾格勒永恆德比"), ("zvezda", "partizan", "貝爾格勒永恆德比"),
    ("real madrid", "barcelona", "西班牙國家德比"), ("maccabi tel aviv", "hapoel tel aviv", "特拉維夫德比"), ("maccabi playtika", "hapoel", "特拉維夫德比"),
    ("zalgiris", "rytas", "立陶宛宿敵大戰"), ("virtus", "fortitudo", "波隆那德比"), ("aek", "panathinaikos", "雅典德比"),
    ("aek", "olympiacos", "雅典德比"), ("paok", "aris", "薩洛尼卡德比"), ("cedevita", "krka", "斯洛維尼亞德比"),
    ("buducnost", "sc derby", "波德戈里察德比"), ("asvel", "monaco", None), ("milano", "virtus", None),
]
NBA_DERBIES = [({"LAL", "LAC"}, "洛杉磯德比"), ({"NY", "NYK", "BKN"}, "紐約德比")]
DERBY_SHRINK = 0.15
EXAMPLES = []


def _ts(s):
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def must_words(name):
    """標題裡一定要出現的隊名字（避免「土耳其足球國家隊換教練」被當成艾菲斯換教練）。"""
    from eurodom_names import lookup
    _zh, _q, kw = lookup(name or "")
    if kw:
        return [kw]
    generic = {"basketball", "baloncesto", "basket", "basketbol", "club", "team", "the", "bc", "kk", "bk", "fc"}
    words = [w for w in re.findall(r"\w+", name or "") if w.lower() not in generic]
    return [words[-1]] if words else []


def team_signals(items, now=None, must=None):
    """新聞列表 -> [dict(kind, zh, title, url, published)]，每種只留最新一則。must：標題一定要有其中一個字。"""
    now = now or datetime.now(UTC)
    out = {}
    from eurodom_names import norm
    from newsinj import has_word
    must = [m for m in (must or []) if m]
    for it in items or []:
        title = " ".join(x for x in (it.get("title"), it.get("desc")) if x)
        if not title or NOT.search(title):
            continue
        if must and not has_word(title, must):
            continue
        pub = _ts(it.get("published"))
        flat = norm(title)       # 去掉重音再比一次（希臘文、土耳其文、立陶宛文）
        for k, spec in KINDS.items():
            if k in out or not (spec["re"].search(title) or spec["re"].search(flat)):
                continue
            if pub and now - pub > timedelta(days=spec["days"]):
                continue
            out[k] = dict(kind=k, zh=spec["zh"], title=it.get("title"), url=it.get("url"), published=it.get("published"), lang=it.get("lang"))
    return list(out.values())


def signal_pts(team):
    v = sum(KINDS[s["kind"]]["pts"] for s in team.get("signals") or [] if s.get("kind") in KINDS)
    return max(-SIG_CAP, min(SIG_CAP, v))


def derby(g):
    """這場是不是德比；是的話回傳中文名（沒有名字的就回「宿敵大戰」）。"""
    if g.get("league") == "nba":
        ab = {str(g["home"].get("abbr") or ""), str(g["away"].get("abbr") or "")}
        for pair, name in NBA_DERBIES:
            if len(ab & pair) == 2:
                return name
        return None
    from eurodom_names import norm, _hit
    hn = norm(" ".join(x for x in (g["home"].get("name"), g["home"].get("short")) if x))
    an = norm(" ".join(x for x in (g["away"].get("name"), g["away"].get("short")) if x))
    for a, b, name in DERBIES:
        if (_hit(hn, (a,)) and _hit(an, (b,))) or (_hit(hn, (b,)) and _hit(an, (a,))):
            return name or "宿敵大戰"
    return None


def apply(games, now=None):
    """NBA：用 ESPN 新聞（每場已經分好哪一隊）挖消息；其他聯盟在 newsinj 查新聞時就挖好了。每場標德比。"""
    now = now or datetime.now(UTC)
    n_sig = n_derby = 0
    for g in games:
        if g.get("tennis") or g["status"]["state"] == "post":
            continue
        if g.get("league") == "nba":
            for side in ("home", "away"):
                items = [x for x in g.get("news") or [] if x.get("team") == side]
                sig = team_signals(items, now)
                if sig:
                    g[side]["signals"] = sig
        for s in ("home", "away"):
            for sg in g[s].get("signals") or []:
                n_sig += 1
                if len(EXAMPLES) < 8:
                    EXAMPLES.append(f"{g[s].get('name_zh') or g[s].get('name')}：{sg['zh']}｜{(sg.get('title') or '')[:60]}")
        d = derby(g)
        if d:
            g.setdefault("analysis", {})["derby"] = d
            n_derby += 1
    return n_sig, n_derby
