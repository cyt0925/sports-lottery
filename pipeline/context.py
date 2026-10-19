# -*- coding: utf-8 -*-
"""老球迷會注意的場外消息：從新聞標題挖出來，變成白話提醒，也算一點分數（分數多少由 learn.py 自己學）。

  換教練：新教練頭幾場球員通常比較拚（新官上任），但戰術還在磨合
  欠薪、財務出問題：球員場上常常不夠拚
  禁賽、更衣室不和、打架：隊伍氣氛差
  德比戰：同城或宿敵碰面，火氣大，強弱常常不準（把兩隊的差距往中間拉一點）
新聞標題有各國語言（英、西、義、土、法、德、希臘字母以外的拼法、日、中），關鍵字盡量都列。"""
import re
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
KINDS = {
    "coach": dict(days=14, pts=0.6, zh="換教練", re=re.compile(
        r"(?:coach|entrenador|allenatore|antren[öo]r|trainer|entra[iî]neur).{0,40}(?:fired|sacked|dismissed|let go|parts? ways|esonerat|destitu|cesad|g[öo]revden|entlassen|limog|remerci)"
        r"|(?:fired|sacked|dismissed|esonerat\w*|destitu\w*|cesad\w*|limog\w*|remerci\w*|parts? ways with).{0,40}(?:coach|entrenador|allenatore|antren|trainer|entra[iî]neur)"
        r"|new head coach|interim (?:head )?coach|appoint\w* .{0,40}coach|nuevo entrenador|nuovo allenatore|yeni ba[sş]antren[öo]r|nouvel entra[iî]neur|neuer trainer"
        r"|解任|新ヘッドコーチ|換帥|新教練", re.I)),
    "money": dict(days=21, pts=-1.0, zh="欠薪、財務問題", re=re.compile(
        r"(unpaid|not been paid|salar(?:y|ies) (?:delay|owed|unpaid|arrears)|wages|financial (?:trouble|problems|crisis|difficult)|bankrupt\w*|insolven\w*|"
        r"stipendi|impag\w*|sueldos|maa[sş]|finanzielle|給料未払い|欠薪|財務危機)", re.I)),
    "turmoil": dict(days=7, pts=-0.5, zh="禁賽、隊內不和", re=re.compile(
        r"(locker[- ]room (?:issue|problem|tension|drama)|\brift\b|\bfeud\b|\bsuspen(?:ded|sion)\b|\bbrawl\b|disciplinary|fight with (?:teammate|coach)|"
        r"squalifica|sanci[oó]n|ihra[cç]|出場停止|内紛|內鬨|禁賽)", re.I)),
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


def _ts(s):
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def team_signals(items, now=None):
    """新聞列表 -> [dict(kind, zh, title, url, published)]，每種只留最新一則。"""
    now = now or datetime.now(UTC)
    out = {}
    for it in items or []:
        title = " ".join(x for x in (it.get("title"), it.get("desc")) if x)
        if not title or NOT.search(title):
            continue
        pub = _ts(it.get("published"))
        for k, spec in KINDS.items():
            if k in out or not spec["re"].search(title):
                continue
            if pub and now - pub > timedelta(days=spec["days"]):
                continue
            out[k] = dict(kind=k, zh=spec["zh"], title=it.get("title"), url=it.get("url"), published=it.get("published"))
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
        n_sig += sum(1 for s in ("home", "away") if g[s].get("signals"))
        d = derby(g)
        if d:
            g.setdefault("analysis", {})["derby"] = d
            n_derby += 1
    return n_sig, n_derby
