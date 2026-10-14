# -*- coding: utf-8 -*-
"""B.LEAGUE（日本職籃）官方網站的排名頁：東西地區排名、主客場戰績、近 5 場、連勝連敗。
網頁是伺服器端直接產生的表格，不用瀏覽器就能讀。玩運彩的中文隊名用城市漢字對到日文隊名。"""
import re
import time

from bs4 import BeautifulSoup

from taiwan_odds import fetch

URL = "https://www.bleague.jp/standings/?tab=1"

# 繁體中文 -> 日文新字體（只處理球隊城市會用到的字）
_KANJI = str.maketrans({"橫": "横", "濱": "浜", "廣": "広", "戶": "戸", "澤": "沢", "龍": "竜", "櫻": "桜", "會": "会", "國": "国", "島": "島", "縣": "県"})
# 同城市兩隊時的分辨關鍵字
_DISAMBIG = {
    "A千葉": ["阿爾提里", "阿提里", "阿爾蒂里", "Altiri", "ALTIRI"],
    "千葉J": ["噴射", "捷特", "傑特", "Jets", "JETS"],
    "A東京": ["阿爾瓦克", "阿爾巴克", "Alvark", "ALVARK"],
    "東京SR": ["太陽", "搖滾", "澀谷", "渋谷", "Sun", "SUN"],
}
ZH_NAMES = {  # 日文簡稱 -> 中文（給前端顯示用，玩運彩已有中文名時以玩運彩為主）
    "北海道": "北海道雷邦加", "仙台": "仙台89ers", "秋田": "秋田北部快樂", "茨城": "茨城機器人", "宇都宮": "宇都宮霹靂",
    "群馬": "群馬雷霆", "A千葉": "千葉阿爾提里", "千葉J": "千葉噴射機", "A東京": "東京阿爾瓦克", "東京SR": "東京太陽搖滾",
    "川崎": "川崎勇雷", "横浜BC": "橫濱海盜", "富山": "富山松雞", "信州": "信州勇士", "三遠": "三遠鳳凰", "三河": "三河海馬",
    "名古屋D": "名古屋鑽石海豚", "滋賀": "滋賀湖星", "京都": "京都漢納利", "大阪": "大阪福音", "神戸": "神戶鸛", "島根": "島根魔術",
    "広島": "廣島飛龍", "佐賀": "佐賀巴魯納", "長崎": "長崎維爾卡", "琉球": "琉球黃金國王",
}


class BLeague:
    def __init__(self, log, errors):
        self.log = log
        self.errors = errors
        self.rows = []       # 全部排名列
        self.groups = []
        self.loaded = False

    def load(self):
        if self.loaded:
            return
        self.loaded = True
        text = fetch(URL)
        if not text:
            self.errors.append("日籃 B.LEAGUE 排名頁抓不到")
            return
        try:
            self._parse(text)
        except Exception as e:  # noqa: BLE001
            self.errors.append(f"日籃 B.LEAGUE 排名解析失敗: {e!r}")
        if not self.rows:
            try:
                self._parse_text(text)
            except Exception as e:  # noqa: BLE001
                self.errors.append(f"日籃 B.LEAGUE 排名文字解析失敗: {e!r}")
            i = text.find("勝率")
            self.log("[jpbasket] 排名頁原始碼樣本: " + re.sub(r"\s+", " ", text[max(0, i - 600): i + 1800]))
        self.log(f"[jpbasket] B.LEAGUE 排名 {len(self.groups)} 區、{len(self.rows)} 隊")

    _ROW = re.compile(r"(\d{1,2})\s+(\S+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d?\.\d{3})\s+(--|-|\d+(?:\.\d+)?)\s+(\d+)\s+(\d+)\s+(-?\d+)\s+(\d+-\d+)\s+(\d+-\d+)\s+(\d+-\d+)\s+([WL]\d+|--|-)\s+(\d+)\s+[\d.]+%")

    def _parse_text(self, html):
        body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
        body = re.sub(r"<[^>]+>", " ", body)
        body = re.sub(r"\s+", " ", body)
        parts = re.split(r"(東地区|西地区)", body)
        groups = []
        label = ""
        for p in parts:
            if p in ("東地区", "西地区"):
                label = p
                continue
            rows = []
            for m in self._ROW.finditer(p):
                rank, name, abbr, w, l, pct, gb, pf, pa, diff, home, away, last5, streak, gp = m.groups()
                rows.append(dict(
                    team_id=abbr, team=name, abbr=abbr, name_zh=ZH_NAMES.get(abbr, name), logo=None,
                    w=int(w), l=int(l), d=None, otl=None, pct=pct, gb=gb if gb not in ("--", "-") else None,
                    streak=streak if re.match(r"^[WL]\d+$", streak) else None, points=None, gp=int(gp), rank=int(rank), pos=int(rank),
                    pf=round(int(pf) / max(1, int(gp)), 1), pa=round(int(pa) / max(1, int(gp)), 1), diff=int(diff), home=home, away=away, last5=last5,
                ))
            if rows and not any(r["abbr"] in {x["abbr"] for g in groups for x in g["rows"]} for r in rows):
                groups.append(dict(name=label, rows=rows))
                self.rows.extend(rows)
        self.groups = groups

    def _parse(self, text):
        soup = BeautifulSoup(text, "html.parser")
        groups = []
        for table in soup.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                cells = tr.find_all("td")
                tds = [td.get_text(" ", strip=True) for td in cells]
                if len(tds) < 12 or not re.match(r"^\d{1,2}$", tds[0]):
                    continue
                # 順位 | クラブ（全名 span + 簡稱 span + logo）| 勝 負 勝率 差 得点 失点 得失点差 ホーム アウェー 過去5試合 連勝/連敗 試合数 ...
                team_td = cells[1]
                full = team_td.select_one(".team-name-line")
                short = team_td.select_one(".pc-tab-dn")
                name = full.get_text(strip=True) if full else tds[1]
                abbr = short.get_text(strip=True) if short else (team_td.find("img").get("alt") if team_td.find("img") else tds[1])
                nums = tds[2:]
                try:
                    rank = int(tds[0])
                    w, l = int(nums[0]), int(nums[1])
                    pct = nums[2]
                    gb = nums[3]
                    pf, pa, diff = int(nums[4]), int(nums[5]), int(nums[6].replace("−", "-").replace("－", "-"))
                    home, away, last5, streak = nums[7], nums[8], nums[9], nums[10] if len(nums) > 10 else ""
                except (ValueError, IndexError):
                    continue
                logo = None
                img = tr.find("img")
                if img and img.get("src"):
                    logo = img["src"] if img["src"].startswith("http") else "https://www.bleague.jp" + img["src"]
                rows.append(dict(
                    team_id=abbr, team=name, abbr=abbr, name_zh=ZH_NAMES.get(abbr, name), logo=logo,
                    w=w, l=l, d=None, otl=None, pct=pct, gb=gb if gb not in ("--", "-") else None,
                    streak=streak if re.match(r"^[WL]\d+$", streak) else None,
                    points=None, gp=w + l, rank=rank, pos=rank, pf=round(pf / max(1, w + l), 1), pa=round(pa / max(1, w + l), 1), diff=diff,
                    home=home, away=away, last5=last5,
                ))
            if not rows:
                continue
            label = ""
            prev = table.find_previous(string=re.compile("地区|B\\.PREMIER|B\\.ONE|B1|B2"))
            if prev:
                label = str(prev).strip()[:12]
            if any(r["abbr"] in {x["abbr"] for g in groups for x in g["rows"]} for r in rows):
                continue  # 同一張表重複出現（手機版/電腦版）
            groups.append(dict(name=label, rows=rows))
            self.rows.extend(rows)
        self.groups = groups

    # ---------- 對隊名 ----------
    def find(self, zh_name):
        if not zh_name or not self.rows:
            return None
        z = zh_name.translate(_KANJI)
        hits = []
        for r in self.rows:
            city = re.sub(r"^A|[A-Z]+$", "", r["abbr"])  # A千葉 -> 千葉、名古屋D -> 名古屋、横浜BC -> 横浜
            if city and city in z:
                hits.append(r)
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            for r in hits:
                if any(k in zh_name for k in _DISAMBIG.get(r["abbr"], [])):
                    return r
            return None
        return None

    def enrich(self, games):
        if not self.rows:
            return 0
        hit = 0
        miss = []
        for g in games:
            for side in ("home", "away"):
                t = g[side]
                r = self.find(t["name"])
                if not r:
                    miss.append(t["name"])
                    continue
                hit += 1
                t["jp_name"] = r["team"]
                t["jp_abbr"] = r["abbr"]
                t["abbr"] = r["abbr"]
                t["name"] = r["team"]
                t["short"] = r["abbr"]
                if r.get("logo"):
                    t["logo"] = r["logo"]
                t["record"] = f"{r['w']}-{r['l']}"
                t["record_home"] = r.get("home")
                t["record_away"] = r.get("away")
                t["rank"] = r["pos"]
                t["rank_note"] = f"B.LEAGUE {('東區' if '東' in (self._group_of(r) or '') else '西區' if '西' in (self._group_of(r) or '') else '')}第 {r['pos']} 名".replace("  ", " ")
                if r.get("streak") and not t.get("streak"):
                    n = int(r["streak"][1:])
                    t["streak"] = ("連勝" if r["streak"][0] == "W" else "連敗") + str(n) if n >= 2 else None
                t["last5_official"] = r.get("last5")
        self.log(f"[jpbasket] B.LEAGUE 對到 {hit} 隊" + (f"；沒對到：{'、'.join(sorted(set(miss))[:10])}" if miss else ""))
        return hit

    def _group_of(self, r):
        for g in self.groups:
            if r in g["rows"]:
                return g["name"]
        return None

    def standings_payload(self):
        if not self.groups:
            return None
        return dict(groups=[dict(name=g["name"] or "B.PREMIER", rows=g["rows"]) for g in self.groups])
