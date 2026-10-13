# -*- coding: utf-8 -*-
"""EuroLeague / EuroCup 官方公開 API（api-live.euroleague.net）：賽程比分、排名、隊徽、英文隊名。

用途：玩運彩的歐籃賽事只有中文隊名，對上官方資料後就有隊徽、排名、主客場分明的近況。
對不上的（籃球冠軍聯賽等）就維持玩運彩的資料。
"""
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from taiwan_odds import fetch, TW

BASE = "https://api-live.euroleague.net"
COMPS = {"E": "歐冠", "U": "歐盃"}
UTC = timezone.utc

# 玩運彩中文隊名裡的關鍵字 -> 官方英文隊名裡的關鍵字（小寫、去重音）
ALIASES = {
    # EuroLeague
    "費內巴切": ["fenerbahce"], "費倫巴治": ["fenerbahce"],
    "考納斯": ["zalgiris"], "薩拉基利斯": ["zalgiris"], "綠林": ["zalgiris"],
    "奧林匹亞科斯": ["olympiacos"], "奧林比亞高斯": ["olympiacos"],
    "帕納辛": ["panathinaikos"], "泛雅典": ["panathinaikos"],
    "皇家馬德里": ["real madrid"], "皇馬": ["real madrid"],
    "巴塞隆納": ["barcelona"], "巴塞羅那": ["barcelona"], "巴薩": ["barcelona"],
    "艾菲斯": ["efes"], "安納托利亞": ["efes"],
    "紅星": ["crvena", "zvezda"], "貝爾格勒紅星": ["crvena"],
    "游擊": ["partizan"], "帕蒂贊": ["partizan"], "柏迪遜": ["partizan"],
    "米蘭": ["milan", "milano"], "奧林匹亞米蘭": ["milan"],
    "維圖斯": ["virtus"], "博洛尼亞": ["virtus", "bologna"],
    "摩納哥": ["monaco"],
    "巴黎": ["paris"],
    "艾思維爾": ["asvel", "villeurbanne"], "維勒班": ["asvel", "villeurbanne"], "里昂": ["asvel", "villeurbanne"],
    "拜仁": ["bayern"], "慕尼黑": ["bayern"],
    "巴斯克尼亞": ["baskonia"], "維多利亞": ["baskonia"],
    "瓦倫西亞": ["valencia"], "華倫西亞": ["valencia"],
    "馬卡比": ["maccabi"], "特拉維夫": ["tel aviv"],
    "哈波": ["hapoel"], "夏普爾": ["hapoel"],
    "杜拜": ["dubai"], "迪拜": ["dubai"],
    # EuroCup
    "特倫托": ["trento"], "凱姆尼茲": ["chemnitz"], "謝姆尼茲": ["chemnitz"],
    "布爾格": ["bourg"], "布雷斯": ["bourg"],
    "克萊佩達": ["neptunas", "klaipeda"], "海王星": ["neptunas"], "海神": ["neptunas"],
    "曼雷薩": ["manresa"], "花園城市": ["bahcesehir"], "巴赫切": ["bahcesehir"],
    "貝西克塔斯": ["besiktas"], "土耳其電信": ["turk telekom"], "安卡拉": ["turk telekom"],
    "耶路撒冷": ["jerusalem"], "利特卡": ["lietkabelis"], "潘尼維斯": ["lietkabelis"],
    "采迪維塔": ["cedevita"], "盧布爾雅那": ["cedevita", "ljubljana"],
    "烏爾姆": ["ulm"], "漢堡": ["hamburg"], "威尼斯": ["venezia", "venice"],
    "格蘭卡納利亞": ["gran canaria"], "大加那利": ["gran canaria"],
    "尤文圖特": ["joventut"], "巴達洛納": ["joventut", "badalona"],
    "布雷西亞": ["brescia"], "克盧日": ["cluj"], "布達": ["buducnost"], "布杜克諾斯特": ["buducnost"],
    "倫敦": ["london"], "沃爾夫斯堡": ["wolves"], "維爾紐斯": ["rytas", "vilnius"], "里塔斯": ["rytas"],
    "索菲亞": ["sofia"], "斯洛萬": ["slask"], "弗羅茨瓦夫": ["slask", "wroclaw"],
    "特拉布宗": ["trabzon"], "貝爾格萊德": ["belgrade"], "薩格勒布": ["zagreb", "cibona"],
    "海法": ["haifa"], "阿拉里斯": ["aris"], "特內里費": ["tenerife"], "拉古納": ["tenerife"],
    "貝桑松": ["besancon"], "布魯塞爾": ["brussels"], "安特衛普": ["antwerp"],
    "塞德維塔": ["cedevita"], "里加": ["riga"], "希奧利艾": ["siauliai"], "烏姆": ["ulm"], "波士納": ["bosna"],
    "布爾戈斯": ["burgos"], "拿坡里": ["napoli"], "托法什": ["tofas"], "布爾薩": ["tofas", "bursa"], "德托納": ["derthona"],
    "托爾托納": ["derthona"], "羅馬": ["roma"], "威尼斯雷耶爾": ["venezia"], "薩格勒布": ["zagreb", "cibona"],
    "哈普爾": ["hapoel"], "阿里斯": ["aris"], "斯洛萬": ["slask"], "布拉格": ["prague"], "馬尼薩": ["manisa"],
    "巴塞羅納": ["barcelona"], "慕尼黑拜仁": ["bayern"], "維爾紐斯": ["rytas", "wolves"], "狼隊": ["wolves"],
}


# 查新聞用的名字（跟足球隊同名的要講清楚）
QUERY_NAME = {
    "milan": "Olimpia Milano", "roma": "Roma SPQR", "real madrid": "Real Madrid baloncesto", "barcelona": "Barça basket",
    "valencia": "Valencia Basket", "bayern": "Bayern Munich basketball", "monaco": "AS Monaco Basket", "paris": "Paris Basketball",
    "london": "London Lions", "venezia": "Reyer Venezia", "napoli": "Napoli Basket", "balkan": "Balkan Botevgrad", "dubai": "Dubai Basketball",
    "ulm": "ratiopharm Ulm", "bosna": "Bosna Sarajevo", "aris": "Aris Thessaloniki", "paok": "PAOK basketball", "cluj": "U-BT Cluj",
    "siauliai": "Siauliai basketball", "riga": "Riga Zelli", "cedevita": "Cedevita Olimpija", "hapoel tel": "Hapoel Tel Aviv basketball",
    "hapoel": "Hapoel Jerusalem basketball", "maccabi": "Maccabi Tel Aviv basketball", "partizan": "Partizan basketball",
    "crvena": "Crvena Zvezda basketball", "fenerbahce": "Fenerbahce Beko", "efes": "Anadolu Efes", "besiktas": "Besiktas basketball",
    "turk telekom": "Turk Telekom basketball", "tofas": "Tofas Bursa", "bahcesehir": "Bahcesehir College", "manresa": "Baxi Manresa",
    "trento": "Aquila Trento", "chemnitz": "Niners Chemnitz", "bourg": "JL Bourg", "neptunas": "Neptunas Klaipeda", "lietkabelis": "Lietkabelis",
    "zalgiris": "Zalgiris Kaunas", "olympiacos": "Olympiacos BC", "panathinaikos": "Panathinaikos BC", "asvel": "ASVEL", "baskonia": "Baskonia",
    "virtus": "Virtus Bologna", "derthona": "Derthona Basket", "burgos": "San Pablo Burgos", "tenerife": "Lenovo Tenerife", "wolves": "Wolves Vilnius",
    "slask": "Slask Wroclaw", "buducnost": "Buducnost VOLI", "hamburg": "Hamburg Towers", "joventut": "Joventut Badalona",
    "gran canaria": "Gran Canaria basketball", "brescia": "Germani Brescia", "jerusalem": "Hapoel Jerusalem basketball",
}


def query_name(norm, fallback):
    for k, v in QUERY_NAME.items():
        if k in norm:
            return v
    return fallback


def _norm_en(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s.lower()).strip()


def season_code(comp, now=None):
    now = now or datetime.now(TW)
    year = now.year if now.month >= 7 else now.year - 1
    return f"{comp}{year}"


class EuroLeague:
    def __init__(self, log, errors):
        self.log = log
        self.errors = errors
        self.clubs = {}      # code -> dict(code, name, abbr, editorial, crest, comp, norm)
        self.games = []      # 官方賽事（含未打）
        self.results = {}    # code -> [rows]
        self.standings = {}  # comp -> groups
        self.group_of = {}   # club code -> 分組字母（歐盃）
        self.zh = {}         # club code -> 玩運彩中文名（今天配到的）
        self.loaded = False

    def load(self):
        if self.loaded:
            return
        self.loaded = True
        for comp, label in COMPS.items():
            sc = season_code(comp)
            js = fetch(f"{BASE}/v2/competitions/{comp}/seasons/{sc}/games", as_json=True)
            if not isinstance(js, dict) or not js.get("data"):
                self.errors.append(f"歐籃 {label} 官方賽程抓不到")
                continue
            n = 0
            for g in js["data"]:
                try:
                    self._add_game(g, comp, label)
                    n += 1
                except Exception as e:  # noqa: BLE001
                    self.errors.append(f"歐籃 {label} 賽事解析失敗: {e!r}")
            self.log(f"[eurobasket] {label} 官方賽程 {n} 場，球隊 {sum(1 for c in self.clubs.values() if c['comp'] == comp)} 隊")
            time.sleep(0.3)
            try:
                self.standings[comp] = self._load_standings(comp, sc, label)
            except Exception as e:  # noqa: BLE001
                self.errors.append(f"歐籃 {label} 排名解析失敗: {e!r}")
        for code, rows in self.results.items():
            rows.sort(key=lambda r: r["ts"])

    def _club(self, c, comp):
        club = c.get("club") or {}
        code = club.get("code")
        if not code:
            return None
        if code not in self.clubs:
            name = club.get("name") or ""
            self.clubs[code] = dict(
                code=code, name=name, abbr=club.get("abbreviatedName") or name, editorial=club.get("editorialName") or name,
                crest=(club.get("images") or {}).get("crest"), comp=comp,
                norm=_norm_en(" | ".join([name, club.get("abbreviatedName") or "", club.get("editorialName") or ""])),
            )
        return code

    def _add_game(self, g, comp, label):
        hc = self._club(g.get("local") or {}, comp)
        ac = self._club(g.get("road") or {}, comp)
        if not hc or not ac:
            return
        dt = g.get("utcDate") or g.get("date")
        start = datetime.fromisoformat(dt.replace("Z", "+00:00")) if dt else None
        if start and start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        grp = (g.get("group") or {}).get("rawName")
        if grp and comp == "U":
            self.group_of.setdefault(hc, grp)
            self.group_of.setdefault(ac, grp)
        row = dict(comp=comp, label=label, home=hc, away=ac, start=start, played=bool(g.get("played")),
                   hs=(g.get("local") or {}).get("score"), as_=(g.get("road") or {}).get("score"),
                   round=g.get("roundAlias") or g.get("roundName"), group=(g.get("group") or {}).get("rawName"))
        self.games.append(row)
        if row["played"] and start and row["hs"] is not None and row["as_"] is not None:
            for me, opp, home in ((hc, ac, True), (ac, hc, False)):
                pf = row["hs"] if home else row["as_"]
                pa = row["as_"] if home else row["hs"]
                oc = self.clubs[opp]
                self.results.setdefault(me, []).append(dict(
                    date=start.astimezone(TW).strftime("%m/%d"), date_iso=start.isoformat(timespec="minutes"), ts=start.timestamp(),
                    opp=oc["abbr"], opp_zh=oc["abbr"], opp_logo=oc["crest"], home=home, pf=int(pf), pa=int(pa),
                    result="W" if pf > pa else ("L" if pf < pa else "D"), comp=label,
                ))

    def _load_standings(self, comp, sc, label):
        xml = fetch(f"{BASE}/v1/standings?seasonCode={sc}")
        if not xml:
            return None
        root = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
        groups = []
        for grp in root.iter("group"):
            rows = []
            for t in grp.findall("team"):
                def tx(tag):
                    el = t.find(tag)
                    return (el.text or "").strip() if el is not None else ""
                code = tx("code")
                club = self.clubs.get(code) or {}
                w, l = int(tx("wins") or 0), int(tx("losses") or 0)
                rows.append(dict(
                    team_id=code, team=tx("name") or club.get("name"), abbr=code,
                    name_zh=club.get("abbr") or tx("name"), logo=club.get("crest"),
                    w=w, l=l, d=None, otl=None, pct=f"{(w / (w + l)):.3f}".lstrip("0") if w + l else "", gb=None,
                    streak=None, points=None, gp=int(tx("totalgames") or 0), rank=int(tx("ranking") or 0),
                    pf=int(tx("ptsfavour") or 0), pa=int(tx("ptsagainst") or 0), diff=int(tx("difference") or 0),
                ))
            rows.sort(key=lambda r: (r["rank"] or 99))
            for i, r in enumerate(rows, 1):
                r["pos"] = i
            name = grp.get("name") or ""
            letters = sorted({self.group_of.get(r["team_id"]) for r in rows if self.group_of.get(r["team_id"])})
            if comp == "U" and len(letters) == 1:
                name = f"{letters[0]} 組"
            elif name == "Regular Season":
                name = "例行賽"
            groups.append(dict(name=f"{label} {name}".strip(), rows=rows))
        self.log(f"[eurobasket] {label} 排名 {len(groups)} 組")
        return groups

    # ---------- 配對 ----------
    def _alias_hit(self, zh, code):
        club = self.clubs.get(code)
        if not club or not zh:
            return 0
        for key, kws in ALIASES.items():
            if key in zh and any(kw in club["norm"] for kw in kws):
                return 1
        return 0

    def match(self, g):
        """回傳 (官方賽事, 是否主客對調)。"""
        start = datetime.fromisoformat(g["start"])
        src = (g.get("comp_source") or "").lower()
        want = None
        if "euroleague" in src:
            want = "E"
        elif "eurocup" in src:
            want = "U"
        hz, az = g["home"]["name"], g["away"]["name"]
        best, best_score, best_swap = None, 0, False
        cands = []
        for og in self.games:
            if not og["start"] or (want and og["comp"] != want):
                continue
            if abs((og["start"] - start).total_seconds()) > 45 * 60:
                continue
            cands.append(og)
            s1 = self._alias_hit(hz, og["home"]) + self._alias_hit(az, og["away"])
            s2 = self._alias_hit(hz, og["away"]) + self._alias_hit(az, og["home"])
            s, swap = (s1, False) if s1 >= s2 else (s2, True)
            if s > best_score:
                best, best_score, best_swap = og, s, swap
        if best:
            return best, best_swap, f"別名{best_score}"
        if want and len(cands) == 1:
            return cands[0], False, "同時段唯一"
        return None, False, None

    def enrich(self, games):
        """把官方資料掛到玩運彩賽事上：隊徽、英文名、近況（主客分明）、戰績。"""
        if not self.games:
            return 0
        hit = 0
        unmatched = []
        for g in games:
            og, swap, how = self.match(g)
            if not og:
                if (g.get("comp_source") or "").lower() in ("euroleague", "eurocup"):
                    unmatched.append(f"{g['away']['name']}@{g['home']['name']} {g['time_tw']}")
                continue
            hit += 1
            g["el_match"] = how
            g["comp"] = g["round"] = og["label"] + (f" {og['round']}" if og.get("round") else "")
            if og.get("group") and og["comp"] == "U":
                g["round"] += f"（{og['group']} 組）"
            pairs = ((g["home"], og["away"] if swap else og["home"]), (g["away"], og["home"] if swap else og["away"]))
            for t, code in pairs:
                club = self.clubs.get(code) or {}
                t["el_code"] = code
                t["name"] = club.get("name") or t["name"]
                t["short"] = club.get("abbr") or t["short"]
                t["abbr"] = code
                t["en_key"] = query_name(club.get("norm", ""), club.get("abbr") or club.get("editorial"))
                if club.get("crest"):
                    t["logo"] = club["crest"]
                self.zh[code] = t.get("name_zh") or t["name"]
                rows = [dict(r) for r in self.results.get(code) or []]
                if rows:
                    from playsport import summarize_form
                    # 官方只有歐戰；玩運彩的歷史紀錄可能還有其他賽事，日期不重複的補進來
                    dates = {r["date"] for r in rows}
                    extra = [dict(r, comp=r.get("comp") or "其他賽事") for r in (t.get("form") or []) if r.get("date") not in dates]
                    for r in extra:
                        r.setdefault("ts", 0)
                        if not r.get("ts") and r.get("date_iso"):
                            try:
                                r["ts"] = datetime.fromisoformat(r["date_iso"]).timestamp()
                            except ValueError:
                                pass
                    rows = sorted(rows + extra, key=lambda r: r.get("ts") or 0)
                    t["record"] = None
                    keep_ats = t.get("ats")
                    summarize_form(t, rows, note=f"{og['label']}官方賽果" + ("＋玩運彩紀錄" if extra else ""))
                    if keep_ats and not t.get("ats"):
                        t["ats"] = keep_ats
                    t["record_note"] = f"{og['label']}戰績"
                for grp in self.standings.get(og["comp"]) or []:
                    for r in grp["rows"]:
                        if r["team_id"] == code:
                            t["record"] = f"{r['w']}-{r['l']}"
                            t["rank"] = r["pos"]
                            t["rank_note"] = f"{og['label']}第 {r['pos']} 名"
        self.log(f"[eurobasket] 官方資料配對 {hit}/{len(games)} 場" + (f"；沒配到：{'；'.join(unmatched[:8])}" if unmatched else ""))
        return hit

    def standings_payload(self):
        groups = []
        for comp in ("E", "U"):
            for grp in self.standings.get(comp) or []:
                for r in grp["rows"]:
                    club = self.clubs.get(r["team_id"]) or {}
                    r["name_zh"] = self.zh.get(r["team_id"]) or _zh_static(club.get("norm", "")) or r["name_zh"]
                groups.append(grp)
        return dict(groups=groups) if groups else None


ZH_STATIC = {
    "panathinaikos": "帕納辛奈科斯", "valencia": "瓦倫西亞", "olympiacos": "奧林匹亞科斯", "fenerbahce": "費內巴切",
    "partizan": "貝爾格勒游擊隊", "crvena": "貝爾格勒紅星", "barcelona": "巴塞隆納", "zalgiris": "考納斯綠林",
    "asvel": "艾思維爾", "dubai": "杜拜", "real madrid": "皇家馬德里", "monaco": "摩納哥", "paris": "巴黎",
    "bayern": "拜仁慕尼黑", "efes": "艾菲斯", "maccabi": "馬卡比特拉維夫", "hapoel tel": "哈波特拉維夫", "hapoel": "哈波耶路撒冷",
    "baskonia": "巴斯克尼亞", "milan": "米蘭", "virtus": "維圖斯博洛尼亞", "trento": "特倫托", "chemnitz": "凱姆尼茲",
    "bourg": "布爾格", "neptunas": "克萊佩達海王星", "manresa": "曼雷薩", "bahcesehir": "花園城市學院", "besiktas": "貝西克塔斯",
    "turk telekom": "土耳其電信", "lietkabelis": "利特卡貝利斯", "cedevita": "采迪維塔", "ulm": "烏爾姆", "hamburg": "漢堡",
    "venezia": "威尼斯", "venice": "威尼斯", "gran canaria": "格蘭卡納利亞", "joventut": "尤文圖特", "brescia": "布雷西亞",
    "cluj": "克盧日", "buducnost": "布杜克諾斯特", "london": "倫敦獅", "wolves": "維爾紐斯狼", "rytas": "里塔斯",
    "aris": "阿里斯", "tenerife": "特內里費", "napoli": "拿坡里", "tofas": "托法什", "derthona": "德托納", "riga": "里加",
    "roma": "羅馬", "paok": "薩洛尼卡PAOK", "jerusalem": "哈波耶路撒冷", "jlm": "哈波耶路撒冷", "slask": "弗羅茨瓦夫",
}


def _zh_static(norm):
    for k, v in ZH_STATIC.items():
        if k in norm:
            return v
    return None
