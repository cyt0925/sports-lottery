# -*- coding: utf-8 -*-
"""暫時的查詢：台灣運彩官網的資料主機（blob.sportslottery.com.tw）讀不讀得到。只寫 log，查完會拿掉。"""
import json

import requests

B = "https://blob.sportslottery.com.tw/apidata"
PATHS = ["Live/On.json", "Pre/On.json", "Pre/Sports.json", "Pre/Leagues.json", "Pre/Menu.json", "Pre/442.json",
         "Pre/S442.json", "Pre/Sport/442.json", "Pre/ListByLeague.json", "Pre/Categories.json", "Pre/Tournaments.json",
         "Pre/Events.json", "Pre/Games.json", "Pre/Matches.json", "Pre/Today.json"]
HEAD = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
        "Accept": "application/json, text/plain, */*", "Referer": "https://www.sportslottery.com.tw/", "Origin": "https://www.sportslottery.com.tw",
        "Accept-Language": "zh-TW,zh;q=0.9"}
LOOK = ("尤文圖特", "托爾托納", "考納斯綠林", "加拉塔薩雷", "勒芒", "的里雅斯特")


def _shape(d, depth=0):
    if depth > 2:
        return "…"
    if isinstance(d, dict):
        return "{" + ", ".join(f"{k}: {_shape(v, depth + 1)}" for k, v in list(d.items())[:12]) + "}"
    if isinstance(d, list):
        return f"[{len(d)} 個，例 {_shape(d[0], depth + 1) if d else ''}]"
    return repr(d)[:40]


def run(log):
    for p in PATHS:
        url = f"{B}/{p}"
        try:
            r = requests.get(url, headers=HEAD, timeout=25)
        except Exception as e:  # noqa: BLE001
            log(f"[查詢3] {p}：{type(e).__name__}")
            continue
        txt = r.text
        hits = [w for w in LOOK if w in txt]
        msg = f"[查詢3] {p}：HTTP {r.status_code}，{len(txt)} 字，類型 {r.headers.get('content-type')}，看到 {hits}"
        if r.status_code == 200:
            try:
                d = r.json()
                msg += f"，結構 {_shape(d)[:900]}"
            except ValueError:
                msg += f"，內容 {txt[:300]!r}"
        log(msg)
        if r.status_code == 200 and hits:
            i = txt.find(hits[0])
            log(f"[查詢3]   片段：{txt[max(0, i - 600): i + 600]}")
