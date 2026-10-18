# -*- coding: utf-8 -*-
"""暫時的查詢：台灣運彩官網的資料主機（blob3rd.sportslottery.com.tw）讀不讀得到。只寫 log，查完會拿掉。"""
import re

import requests

HOSTS = ["https://blob3rd.sportslottery.com.tw", "https://blob.sportslottery.com.tw"]
LIST = "/apidata?restype=container&comp=list&maxresults=400&prefix="
PATHS = ["Pre/34731.1-Games.zh.json", "Pre/Menu.zh.json", "Pre/Sports.zh.json", "Pre/Leagues.zh.json",
         "Pre/Categories.zh.json", "Pre/On.zh.json", "Pre/Tree.zh.json", "Pre/Index.zh.json", "Live/On.zh.json",
         "Live/On.json"]
HEAD = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
        "Accept": "application/json, text/plain, */*", "Referer": "https://www.sportslottery.com.tw/", "Origin": "https://www.sportslottery.com.tw",
        "Accept-Language": "zh-TW,zh;q=0.9"}
LOOK = ("尤文圖特", "托爾托納", "考納斯", "加拉塔薩雷", "勒芒", "的里雅斯特", "籃球", "NBA")


def _shape(d, depth=0):
    if depth > 2:
        return "…"
    if isinstance(d, dict):
        return "{" + ", ".join(f"{k}: {_shape(v, depth + 1)}" for k, v in list(d.items())[:14]) + "}"
    if isinstance(d, list):
        return f"[{len(d)} 個，例 {_shape(d[0], depth + 1) if d else ''}]"
    return repr(d)[:40]


def _get(url):
    try:
        return requests.get(url, headers=HEAD, timeout=25)
    except Exception as e:  # noqa: BLE001
        return type(e).__name__


def run(log):
    for h in HOSTS:
        for pre in ("Pre/", "Live/", ""):
            r = _get(h + LIST + pre)
            if isinstance(r, str):
                log(f"[查詢4] {h} 列表 {pre!r}：{r}")
                continue
            names = re.findall(r"<Name>([^<]+)</Name>", r.text)
            log(f"[查詢4] {h} 列表 {pre!r}：HTTP {r.status_code}，{len(names)} 個檔，{r.text[:160]!r}")
            if names:
                log(f"[查詢4]   檔名：{names[:250]}")
        for p in PATHS:
            r = _get(f"{h}/apidata/{p}")
            if isinstance(r, str):
                log(f"[查詢4] {h} {p}：{r}")
                continue
            txt = r.text
            hits = [w for w in LOOK if w in txt]
            msg = f"[查詢4] {h} {p}：HTTP {r.status_code}，{len(txt)} 字，類型 {r.headers.get('content-type')}，看到 {hits}"
            if r.status_code == 200:
                try:
                    msg += f"，結構 {_shape(r.json())[:1200]}"
                except ValueError:
                    msg += f"，內容 {txt[:300]!r}"
                log(msg)
                log(f"[查詢4]   開頭：{txt[:1500]}")
                if hits:
                    i = txt.find(hits[0])
                    log(f"[查詢4]   片段：{txt[max(0, i - 700): i + 700]}")
            else:
                log(msg)
