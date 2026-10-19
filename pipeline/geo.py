# -*- coding: utf-8 -*-
"""客隊要跑多遠：每隊主場城市的經緯度，算這場客隊離家多遠、上一場在哪裡打、要移動幾公里。

老球迷會注意的：週中剛在伊斯坦堡打完歐冠、週末又要飛到加那利群島；NBA 背靠背還要從西岸飛東岸。
只當成提醒（不算分數），講得出「為什麼」才講。"""
from datetime import datetime
from math import asin, cos, radians, sin, sqrt

# 歐洲球隊：eurodom_names.TEAMS 的第一個關鍵字 -> (城市, 緯度, 經度)
EU = {
    # 西班牙
    "real madrid": ("馬德里", 40.42, -3.70), "estudiantes": ("馬德里", 40.42, -3.70), "barcelona": ("巴塞隆納", 41.39, 2.17),
    "baskonia": ("維多利亞", 42.85, -2.67), "valencia": ("瓦倫西亞", 39.47, -0.38), "1939 canarias": ("加那利群島的特內里費", 28.49, -16.32),
    "gran canaria": ("加那利群島", 28.10, -15.41), "joventut": ("巴達洛納", 41.45, 2.25), "unicaja": ("馬拉加", 36.72, -4.42),
    "manresa": ("曼雷薩", 41.73, 1.82), "breogan": ("盧戈", 43.01, -7.56), "lleida": ("萊里達", 41.61, 0.62), "burgos": ("布爾戈斯", 42.34, -3.70),
    "coruna": ("拉科魯尼亞", 43.36, -8.41), "bilbao": ("畢爾包", 43.26, -2.93), "obradoiro": ("聖地牙哥－德孔波斯特拉", 42.88, -8.54),
    "zaragoza": ("薩拉戈薩", 41.65, -0.88), "girona": ("赫羅納", 41.98, 2.82), "murcia": ("莫夕亞", 37.99, -1.13), "andorra": ("安道爾", 42.51, 1.52),
    "granada": ("格拉納達", 37.18, -3.60), "palma": ("馬約卡島", 39.57, 2.65),
    # 義大利
    "olimpia milano": ("米蘭", 45.46, 9.19), "virtus": ("波隆那", 44.49, 11.34), "fortitudo": ("波隆那", 44.49, 11.34), "venezia": ("威尼斯", 45.44, 12.32),
    "sassari": ("薩丁尼亞島", 40.73, 8.56), "trieste": ("的里雅斯特", 45.65, 13.78), "cantu": ("坎圖", 45.74, 9.13), "reggiana": ("雷焦艾米利亞", 44.70, 10.63),
    "verona": ("維洛納", 45.44, 10.99), "scafati": ("斯卡法蒂", 40.75, 14.53), "derthona": ("托爾托納", 44.90, 8.86), "trento": ("特倫托", 46.07, 11.12),
    "brescia": ("布雷西亞", 45.54, 10.21), "napoli": ("拿坡里", 40.85, 14.27), "varese": ("瓦雷澤", 45.82, 8.83), "pistoia": ("皮斯托亞", 43.93, 10.91),
    "treviso": ("特雷維索", 45.67, 12.24), "trapani": ("西西里島", 38.02, 12.51), "cremona": ("克雷莫納", 45.13, 10.02), "udine": ("烏迪內", 46.06, 13.24),
    "roma": ("羅馬", 41.90, 12.50), "pesaro": ("佩薩羅", 43.91, 12.91),
    # 土耳其
    "fenerbahce": ("伊斯坦堡", 41.01, 28.98), "efes": ("伊斯坦堡", 41.01, 28.98), "galatasaray": ("伊斯坦堡", 41.01, 28.98), "besiktas": ("伊斯坦堡", 41.01, 28.98),
    "bahcesehir": ("伊斯坦堡", 41.01, 28.98), "darussafaka": ("伊斯坦堡", 41.01, 28.98), "buyukcekmece": ("伊斯坦堡", 41.01, 28.98), "esenler": ("伊斯坦堡", 41.01, 28.98),
    "turk telekom": ("安卡拉", 39.93, 32.86), "tofas": ("布爾薩", 40.19, 29.06), "bursaspor": ("布爾薩", 40.19, 29.06), "karsiyaka": ("伊茲密爾", 38.42, 27.14),
    "petkim": ("伊茲密爾", 38.80, 26.97), "manisa": ("馬尼薩", 38.61, 27.43), "merkezefendi": ("代尼茲利", 37.78, 29.09), "trabzon": ("特拉布宗", 41.00, 39.72),
    "mersin": ("梅爾辛", 36.81, 34.64), "gaziantep": ("加濟安泰普", 37.07, 37.38), "yalova": ("亞洛瓦", 40.65, 29.27), "konya": ("科尼亞", 37.87, 32.48),
    # 希臘
    "olympiacos": ("比雷埃夫斯", 37.94, 23.65), "panathinaikos": ("雅典", 37.98, 23.73), "aek": ("雅典", 38.05, 23.70), "peristeri": ("雅典", 38.01, 23.69),
    "maroussi": ("雅典", 38.05, 23.81), "panionios": ("雅典", 37.95, 23.70), "ionikos": ("雅典", 37.97, 23.65), "paok": ("塞薩洛尼基", 40.64, 22.94),
    "aris": ("塞薩洛尼基", 40.64, 22.94), "iraklis": ("塞薩洛尼基", 40.64, 22.94), "promitheas": ("帕特雷", 38.25, 21.73), "apollon": ("帕特雷", 38.25, 21.73),
    "kolossos": ("羅德島", 36.43, 28.22), "lavrio": ("拉夫里奧", 37.71, 24.05), "karditsa": ("卡迪察", 39.36, 21.92), "mykonos": ("米科諾斯島", 37.45, 25.33),
    "vikos": ("約阿尼納", 39.66, 20.85),
    # 法國
    "monaco": ("摩納哥", 43.74, 7.42), "paris": ("巴黎", 48.86, 2.35), "nanterre": ("巴黎", 48.89, 2.21), "asvel": ("里昂", 45.77, 4.88),
    "bourg": ("布爾格", 46.21, 5.23), "le mans": ("勒芒", 48.00, 0.20), "strasbourg": ("史特拉斯堡", 48.58, 7.75), "cholet": ("紹萊", 47.06, -0.88),
    "limoges": ("利摩日", 45.83, 1.26), "dijon": ("第戎", 47.32, 5.04), "gravelines": ("格拉沃利訥", 51.00, 2.13), "le portel": ("勒波特爾", 50.71, 1.57),
    "saint-quentin": ("聖康坦", 49.85, 3.29), "chalon": ("夏龍", 46.78, 4.85), "boulazac": ("佩里格", 45.18, 0.72), "nancy": ("南錫", 48.69, 6.18),
    "roanne": ("羅阿訥", 46.04, 4.07), "elan bearnais": ("波城", 43.30, -0.37), "blois": ("布洛瓦", 47.59, 1.33),
    # 德國
    "bayern": ("慕尼黑", 48.14, 11.58), "alba": ("柏林", 52.52, 13.40), "ulm": ("烏爾姆", 48.40, 9.99), "bonn": ("波昂", 50.74, 7.10),
    "ludwigsburg": ("路德維希堡", 48.90, 9.19), "chemnitz": ("凱姆尼茲", 50.83, 12.92), "wurzburg": ("維爾茨堡", 49.79, 9.95), "oldenburg": ("奧登堡", 53.14, 8.21),
    "bamberg": ("班貝格", 49.89, 10.89), "hamburg": ("漢堡", 53.55, 9.99), "gottingen": ("哥廷根", 51.54, 9.92), "heidelberg": ("海德堡", 49.40, 8.67),
    "rostock": ("羅斯托克", 54.09, 12.10), "braunschweig": ("布倫瑞克", 52.27, 10.52), "vechta": ("費希塔", 52.73, 8.29), "frankfurt": ("法蘭克福", 50.11, 8.68),
    "weissenfels": ("魏森費爾斯", 51.20, 11.97), "bayreuth": ("拜羅伊特", 49.95, 11.58), "jena": ("耶拿", 50.93, 11.59), "trier": ("特里爾", 49.75, 6.64),
    # 立陶宛
    "zalgiris": ("考納斯", 54.90, 23.89), "rytas": ("維爾紐斯", 54.69, 25.28), "wolves": ("維爾紐斯", 54.69, 25.28), "lietkabelis": ("帕內韋日斯", 55.73, 24.36),
    "neptunas": ("克萊佩達", 55.70, 21.14), "siauliai": ("希奧利艾", 55.93, 23.31), "juventus": ("烏田納", 55.50, 25.60), "pieno": ("帕斯瓦利斯", 56.06, 24.40),
    "gargzdai": ("加爾日代", 55.71, 21.39), "jonava": ("約納瓦", 55.08, 24.28), "nevezis": ("凱代尼艾", 55.29, 23.97), "taurage": ("陶拉格", 55.25, 22.29),
    "mazeikiai": ("馬热伊基艾", 56.31, 22.34),
    # 以色列
    "maccabi tel aviv": ("特拉維夫", 32.08, 34.78), "hapoel tel aviv": ("特拉維夫", 32.08, 34.78), "jerusalem": ("耶路撒冷", 31.77, 35.21),
    "holon": ("霍隆", 32.01, 34.78), "herzliya": ("赫茲利亞", 32.16, 34.84), "rishon": ("里雄萊錫安", 31.97, 34.80), "haifa": ("海法", 32.79, 34.99),
    "ness ziona": ("內斯茲約納", 31.93, 34.80), "galil": ("以色列北邊的上加利利", 33.21, 35.57), "ramat gan": ("拉馬特甘", 32.08, 34.82),
    "beer sheva": ("貝爾謝巴", 31.25, 34.79), "eilat": ("以色列最南邊的埃拉特", 29.56, 34.95), "kiryat ata": ("基里亞特阿塔", 32.81, 35.11),
    "haemek": ("阿富拉", 32.61, 35.29), "ashdod": ("阿什杜德", 31.80, 34.65),
    # 亞得里亞海
    "crvena": ("貝爾格勒", 44.79, 20.45), "partizan": ("貝爾格勒", 44.79, 20.45), "mega": ("貝爾格勒", 44.79, 20.45), "fmp": ("貝爾格勒", 44.79, 20.45),
    "buducnost": ("波德戈里察", 42.44, 19.26), "sc derby": ("波德戈里察", 42.44, 19.26), "cedevita": ("盧比安納", 46.06, 14.51), "igokea": ("拉克塔希", 44.91, 17.30),
    "split": ("斯普利特", 43.51, 16.44), "zadar": ("札達爾", 44.12, 15.23), "krka": ("新梅斯托", 45.80, 15.17), "borac": ("恰恰克", 43.89, 20.35),
    "spartak": ("蘇博蒂察", 46.10, 19.67), "cluj": ("克盧日", 46.77, 23.59), "dubai": ("杜拜", 25.20, 55.27), "bosna": ("塞拉耶佛", 43.86, 18.41),
    "studentski": ("尼克希奇", 42.77, 18.94), "vienna": ("維也納", 48.21, 16.37),
    # 其他
    "balkan": ("保加利亞的博特夫格勒", 42.91, 23.79), "slask": ("弗羅茨瓦夫", 51.11, 17.04), "london lions": ("倫敦", 51.51, -0.13),
    "riga": ("里加", 56.95, 24.11), "sofia": ("索菲亞", 42.70, 23.32),
}
# NBA：ESPN 的隊名縮寫 -> (城市, 緯度, 經度, 時區（比 UTC 慢幾小時，不管夏令時間）)
NBA = {
    "ATL": ("亞特蘭大", 33.76, -84.39, 5), "BOS": ("波士頓", 42.37, -71.06, 5), "BKN": ("紐約", 40.68, -73.98, 5), "CHA": ("夏洛特", 35.23, -80.84, 5),
    "CHI": ("芝加哥", 41.88, -87.67, 6), "CLE": ("克里夫蘭", 41.50, -81.69, 5), "DAL": ("達拉斯", 32.79, -96.81, 6), "DEN": ("丹佛", 39.75, -105.01, 7),
    "DET": ("底特律", 42.34, -83.06, 5), "GS": ("舊金山", 37.77, -122.39, 8), "HOU": ("休士頓", 29.75, -95.36, 6), "IND": ("印第安納波利斯", 39.76, -86.16, 5),
    "LAC": ("洛杉磯", 33.94, -118.34, 8), "LAL": ("洛杉磯", 34.04, -118.27, 8), "MEM": ("曼菲斯", 35.14, -90.05, 6), "MIA": ("邁阿密", 25.78, -80.19, 5),
    "MIL": ("密爾瓦基", 43.05, -87.92, 6), "MIN": ("明尼亞波利斯", 44.98, -93.28, 6), "NO": ("紐奧良", 29.95, -90.08, 6), "NY": ("紐約", 40.75, -73.99, 5),
    "OKC": ("奧克拉荷馬市", 35.46, -97.52, 6), "ORL": ("奧蘭多", 28.54, -81.38, 5), "PHI": ("費城", 39.90, -75.17, 5), "PHX": ("鳳凰城", 33.45, -112.07, 7),
    "POR": ("波特蘭", 45.53, -122.67, 8), "SAC": ("沙加緬度", 38.58, -121.50, 8), "SA": ("聖安東尼奧", 29.43, -98.44, 6), "TOR": ("多倫多", 43.64, -79.38, 5),
    "UTAH": ("鹽湖城", 40.77, -111.90, 7), "WSH": ("華盛頓", 38.90, -77.02, 5),
}
NBA_ALIAS = {"GSW": "GS", "NYK": "NY", "NOP": "NO", "SAS": "SA", "UTA": "UTAH", "WAS": "WSH", "PHO": "PHX", "BRK": "BKN"}
# 移動多遠才值得講（公里）
FAR_TRIP = {"nba": 2500, "eu": 1500}
FAR_HOME = {"nba": 3500, "eu": 2500, "dom": 900}


def km(a, b):
    la1, lo1, la2, lo2 = map(radians, (a[1], a[2], b[1], b[2]))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(h))


def place(name=None, abbr=None, nba=False):
    """隊名或縮寫 -> (城市, 緯度, 經度[, 時區])；找不到就 None。"""
    if nba:
        ab = str(abbr or name or "").upper()
        return NBA.get(NBA_ALIAS.get(ab, ab))
    from eurodom_names import lookup
    _zh, _q, kw = lookup(name or "")
    return EU.get(kw) if kw else None


def _team_place(t, nba):
    if nba:
        return place(abbr=t.get("abbr"), nba=True)
    for nm in (t.get("name"), t.get("en_key"), t.get("short")):
        p = place(nm)
        if p:
            return p
    return None


def _dt(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _last_game(t, start, nba):
    """這場之前最後一場在哪裡打：(城市座標, 幾天前, 賽事)。"""
    rows = [r for r in (t.get("schedule") or t.get("form") or []) if r.get("date_iso") and "home" in r]
    best = None
    for r in rows:
        dt = _dt(r["date_iso"])
        if dt and dt < start and (not best or dt > best[0]):
            best = (dt, r)
    if not best:
        return None
    dt, r = best
    if r["home"]:
        where = _team_place(t, nba)
    else:
        where = place(abbr=r.get("opp"), nba=True) if nba else place(r.get("opp"))
    if not where:
        return None
    return where, (start - dt).total_seconds() / 86400, r.get("comp")


def travel(g):
    """g.analysis.travel：客隊離家多遠；兩隊上一場在哪裡打、到這裡要移動多遠。"""
    nba = g.get("league") == "nba"
    start = _dt(g.get("start"))
    H, A = g["home"], g["away"]
    venue, home_away = _team_place(H, nba), _team_place(A, nba)
    if not venue or not start or g.get("neutral"):
        return None
    out = dict(venue=venue[0])
    if home_away:
        out["away_home_km"] = round(km(home_away, venue))
        out["away_city"] = home_away[0]
        if nba:
            out["tz_shift"] = home_away[3] - venue[3]     # 正的：往東飛（時差吃虧）
    for side, t in (("home", H), ("away", A)):
        lg = _last_game(t, start, nba)
        if lg:
            where, days, comp = lg
            out[side + "_prev"] = dict(city=where[0], days=round(days, 1), comp=comp, km=round(km(where, venue)))
    return out


def lines(g, hn, an):
    """白話提醒：移動很遠、剛長途飛回來。沒什麼好講的就回 []。"""
    tr = (g.get("analysis") or {}).get("travel") or {}
    if not tr:
        return []
    kind = "nba" if g.get("league") == "nba" else "eu"
    out = []
    ap = tr.get("away_prev") or {}
    hp = tr.get("home_prev") or {}
    if ap and ap["days"] <= 3.5 and ap["km"] >= FAR_TRIP[kind]:
        when = "昨天" if ap["days"] < 1.5 else "前天" if ap["days"] < 2.5 else f"{int(ap['days'])} 天前"
        what = f"打完{ap['comp']}" if ap.get("comp") else "打完比賽"
        tz = f"，還有 {tr['tz_shift']} 小時時差" if kind == "nba" and (tr.get("tz_shift") or 0) >= 2 else ""
        out.append(f"{an}{when}才在{ap['city']}{what}，又要移動大概 {_round_km(ap['km'])} 公里到{tr['venue']}{tz}，舟車勞頓，後段體力可能吃虧。")
    elif tr.get("away_home_km") is not None:
        far = FAR_HOME["dom"] if g.get("league") == "eurodom" and kind == "eu" else FAR_HOME[kind]
        if tr["away_home_km"] >= far:
            out.append(f"{an}這場要大老遠跑到{tr['venue']}（離家大概 {_round_km(tr['away_home_km'])} 公里），客隊長途飛行通常比較吃虧。")
    if hp and hp["days"] <= 2.5 and hp["km"] >= FAR_TRIP[kind] and hp["city"] != tr["venue"]:
        when = "昨天" if hp["days"] < 1.5 else "前天"
        out.append(f"{hn}{when}還在{hp['city']}打客場，剛飛回來，主場優勢會打點折扣。")
    if kind == "nba" and (tr.get("tz_shift") or 0) >= 2 and ap and ap["days"] < 1.5 and not any(an in x and "移動" in x for x in out):
        out.append(f"{an}背靠背還從西岸飛到東岸，時差 {tr['tz_shift']} 小時，第四節常常腳軟。")
    return out


def _round_km(v):
    return f"{int(round(v, -2)):,}" if v >= 1000 else str(int(round(v, -1)))
