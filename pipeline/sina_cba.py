# -*- coding: utf-8 -*-
"""新浪體育的 CBA 資料庫（cba.sports.sina.com.cn，GBK 編碼的網頁，美國的主機連得到）：
  排名表（這季、上季：勝敗、主客場戰績、場均得失分、連勝連敗）、整季賽程和比分（交手、這季從哪天開打）。

玩運彩的球隊歷史會把季前熱身賽也算進去，所以「這季幾勝幾敗」以新浪的排名表為準，開季前的比賽標成季前賽。"""
import re
import html as htmlmod
import time
from datetime import datetime, timedelta, timezone

import requests

BASE = "http://cba.sports.sina.com.cn"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
TW = timezone(timedelta(hours=8))
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)


def _text(s):
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def fetch(url, tries=2):
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=25)
            if r.status_code == 200:
                time.sleep(0.4)
                return r.content.decode("gbk", errors="replace")
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2 * (i + 1))
    return None


def seasons(text):
    """頁面上的「賽季」選單：[(qleagueid, '26-27'), ...]，第一個是這季。"""
    m = re.search(r'<select[^>]*name="qleagueid"[^>]*>(.*?)</select>', text or "", re.S)
    return re.findall(r'<option value="(\d+)"[^>]*>\s*([\d-]+)\s*</option>', m.group(1)) if m else []


def _wl(s):
    m = re.search(r"(\d+)\s*胜\s*(\d+)\s*负", s or "")
    return f"{m.group(1)}-{m.group(2)}" if m else None


def standings(league_id=None):
    """排名表 -> (列, 賽季選單)。列：dict(pos, team（簡體簡稱）, sina_id, w, l, home, away, pf, pa, streak)。"""
    url = f"{BASE}/cba/stats/teamrank/" + (f"?qleagueid={league_id}" if league_id else "")
    text = fetch(url)
    if not text:
        return [], []
    rows = []
    for tr in _ROW.findall(text):
        tds = _TD.findall(tr)
        if len(tds) < 10 or not re.match(r"\s*\d+\s*$", _text(tds[0])):
            continue
        sid = re.search(r"/team/show/(\d+)/", tds[1])
        try:
            w, l = int(_text(tds[2])), int(_text(tds[3]))
            pf, pa = float(_text(tds[7]) or 0), float(_text(tds[8]) or 0)
        except ValueError:
            continue
        st = re.match(r"(\d+)\s*连(胜|负)", _text(tds[9]))
        rows.append(dict(pos=int(_text(tds[0])), team=_text(tds[1]), sina_id=sid.group(1) if sid else None, w=w, l=l,
                         home=_wl(_text(tds[5])), away=_wl(_text(tds[6])), pf=pf, pa=pa,
                         streak=(("W" if st.group(2) == "胜" else "L") + st.group(1)) if st else None))
    return rows, seasons(text)


def schedule(league_id=None):
    """整季賽程 -> [dict(round, start（台灣時間）, home, away, hs, as_)]；還沒打的 hs、as_ 是 None。"""
    url = f"{BASE}/cba/schedule/all/" + (f"?qleagueid={league_id}&qmonth=&qteamid=" if league_id else "")
    text = fetch(url)
    if not text:
        return []
    out = []
    for tr in _ROW.findall(text):
        tds = _TD.findall(tr)
        if len(tds) < 5 or "轮" not in _text(tds[0]):
            continue
        m = re.search(r"(\d{4}-\d{2}-\d{2})\D+(\d{1,2}:\d{2})", _text(tds[1]))
        if not m:
            continue
        start = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M").replace(tzinfo=TW)
        sc = re.match(r"(\d+)\s*:\s*(\d+)", _text(tds[3]))
        out.append(dict(round=_text(tds[0]), start=start, home=_text(tds[2]), away=_text(tds[4]),
                        hs=int(sc.group(1)) if sc else None, as_=int(sc.group(2)) if sc else None))
    return out
