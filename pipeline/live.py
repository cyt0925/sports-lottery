# -*- coding: utf-8 -*-
"""即時比分：玩運彩（歐洲籃球、日本籃球、CBA）和 SV.LEAGUE 不讓網頁直接抓，所以由 GitHub 這邊每分鐘抓一次，
寫成一個很小的 live.json，推到 live 分支（不會觸發網站重建）。網頁每 90 秒來讀一次。

只有在「有比賽正在打、或 25 分鐘內要開打」的時候才會一直跑；沒比賽就馬上結束。
NBA、NHL、足球不用這個，網頁直接跟 ESPN 拿，30 秒更新一次。
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taiwan_odds import fetch_livescore_ids, TW, fetch, parse_scale_page, attach_taiwan_odds, BASE  # noqa: E402
from playsport import _state_for  # noqa: E402

UTC = timezone.utc
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ALLIANCE = {"eurobasket": 8, "jpbasket": 97, "cba": 94}


def log(msg):
    print(msg, flush=True)


def _dt(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def targets(now):
    """從今天的資料找出要盯的比賽：開打前 25 分鐘到開打後 4 小時、還沒結束的。"""
    try:
        d = json.load(open(os.path.join(ROOT, "data", "today.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for g in d.get("games") or []:
        src = g.get("live_src") or ""
        if src not in ("playsport", "svleague"):
            continue
        st = _dt(g.get("start"))
        if not st or g["status"]["state"] == "post" and now - st > timedelta(hours=1):
            continue
        if st - timedelta(minutes=25) <= now <= st + timedelta(hours=4):
            out.append(dict(id=g["id"], league=g["league"], src=src, start=st, day=g.get("day_tw", "").replace("-", "")))
    return out


def playsport_scores(tg, now):
    res = {}
    for key, aid in ALLIANCE.items():
        days = sorted({t["day"] for t in tg if t["league"] == key})
        for d in days:
            ids = fetch_livescore_ids(aid, d) or {}
            for gid, ls in ids.items():
                try:
                    start_tw = datetime.strptime(ls.get("dateon") or "", "%Y-%m-%d %H:%M:%S").replace(tzinfo=TW)
                except ValueError:
                    continue
                state, detail, _ = _state_for(start_tw.astimezone(UTC), now, ls)
                hs, as_ = ls.get("hscore"), ls.get("ascore")
                if state == "pre" and not hs and not as_:
                    continue
                res[f"ps{gid}"] = dict(s=state, h=str(hs) if hs not in (None, "") else None, a=str(as_) if as_ not in (None, "") else None, d=detail)
    return res


def sv_scores(now):
    import svleague
    lg = dict(key="jpvolley", label="日本排球", sport="volleyball")
    errs = []
    games, _ = svleague.fetch_games(lg, lambda *_: None, errs, now=now)
    res = {}
    for g in games:
        if g["status"]["state"] == "pre":
            continue
        res[g["id"]] = dict(s=g["status"]["state"], h=g["home"].get("score"), a=g["away"].get("score"), d=g["status"]["detail"])
    return res


def refresh_odds(now):
    """台灣運彩的線：開打前的比賽重新抓一次（NBA、歐洲籃球、日本籃球）。台灣運彩通常比賽前一天下午才開盤。"""
    import copy
    try:
        d = json.load(open(os.path.join(ROOT, "data", "today.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    games = []
    for g in d.get("games") or []:
        st = _dt(g.get("start"))
        if g["status"]["state"] == "pre" and st and now - timedelta(minutes=10) <= st <= now + timedelta(hours=40):
            games.append(g)
    out = {}
    # 玩運彩當主幹的聯盟：直接用 gameid 對
    for key, aid in ALLIANCE.items():
        want = {g["id"] for g in games if g["league"] == key}
        for day in sorted({g["day_tw"].replace("-", "") for g in games if g["league"] == key}):
            text = fetch(f"{BASE}/predict/scale?allianceid={aid}&gametime={day}")
            if not text:
                continue
            try:
                rows = parse_scale_page(text)
            except Exception as e:  # noqa: BLE001
                log(f"{key} {day} 盤口解析失敗：{e!r}")
                continue
            for r in rows:
                gid = f"ps{r.get('gameid')}"
                if gid in want and (r.get("ml") or r.get("spread") or r.get("total")):
                    out[gid] = dict(ml=r.get("ml"), spread=r.get("spread"), total=r.get("total"))
    # NBA：跟 ESPN 的比賽配對（沿用主程式的配對規則）
    nba = [copy.deepcopy(g) for g in games if g["league"] == "nba"]
    for g in nba:
        g.pop("tw", None)
    if nba:
        try:
            attach_taiwan_odds(nba, [], lambda *_: None)
        except Exception as e:  # noqa: BLE001
            log(f"NBA 台灣盤口失敗：{e!r}")
        for g in nba:
            tw = g.get("tw") or {}
            if tw.get("ml") or tw.get("spread") or tw.get("total"):
                out[g["id"]] = dict(ml=tw.get("ml"), spread=tw.get("spread"), total=tw.get("total"))
    return out


def git(*args, inp=None):
    env = dict(os.environ, GIT_AUTHOR_NAME="github-actions[bot]", GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com",
               GIT_COMMITTER_NAME="github-actions[bot]", GIT_COMMITTER_EMAIL="41898282+github-actions[bot]@users.noreply.github.com")
    r = subprocess.run(["git", *args], input=inp, capture_output=True, text=True, cwd=ROOT, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def push(payload):
    """只放一個檔案、只留一個 commit，強制推到 live 分支，分支不會越長越大。"""
    blob = git("hash-object", "-w", "--stdin", inp=payload)
    tree = git("mktree", inp=f"100644 blob {blob}\tlive.json\n")
    commit = git("commit-tree", tree, "-m", "即時比分")
    git("push", "-f", "-q", "origin", f"{commit}:refs/heads/live")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=22)
    ap.add_argument("--every", type=int, default=60)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--selftest", action="store_true", help="推一個空的 live.json 試試看推得上去")
    args = ap.parse_args()
    if args.selftest:
        now = datetime.now(UTC)
        push(json.dumps(dict(updated=now.astimezone(TW).isoformat(timespec="seconds"), games={}, selftest=True), separators=(",", ":")))
        log("自我測試：live.json 推上 live 分支了")
        return
    t_end = time.time() + args.minutes * 60
    last = None
    loops = 0
    scores = {}
    t0 = datetime.now(UTC)
    try:
        odds = refresh_odds(t0)
    except Exception as e:  # noqa: BLE001
        log(f"台灣盤口更新失敗：{e!r}")
        odds = {}
    odds_at = t0.astimezone(TW).isoformat(timespec="minutes")
    n_tw = sum(1 for v in odds.values() if v.get("spread") or v.get("total"))
    log(f"台灣盤口：{len(odds)} 場有盤，其中 {n_tw} 場有讓分或大小")

    def payload(games, now):
        return json.dumps(dict(updated=now.astimezone(TW).isoformat(timespec="seconds"), games=games, odds=odds, odds_at=odds_at),
                          ensure_ascii=False, separators=(",", ":"))
    while True:
        now = datetime.now(UTC)
        tg = targets(now)
        if not tg:
            if odds and loops == 0 and not args.dry:
                try:
                    push(payload({}, now))
                    log("沒有比賽在打，只更新台灣盤口。")
                except Exception as e:  # noqa: BLE001
                    log(f"推送失敗：{e!r}")
            elif args.dry:
                log(payload({}, now)[:800])
            log("沒有正在打或快開打的比賽，結束。")
            break
        try:
            if any(t["src"] == "playsport" for t in tg):
                scores.update(playsport_scores([t for t in tg if t["src"] == "playsport"], now))
            if any(t["src"] == "svleague" for t in tg) and loops % 3 == 0:
                scores.update(sv_scores(now))
        except Exception as e:  # noqa: BLE001
            log(f"抓比分失敗：{e!r}")
        want = {t["id"] for t in tg}
        games = {k: v for k, v in scores.items() if k in want}
        body = json.dumps(games, ensure_ascii=False, sort_keys=True)
        if body != last and (games or loops == 0):
            pl = payload(games, now)
            if args.dry:
                log(pl[:600])
            else:
                try:
                    push(pl)
                    log(f"{now.astimezone(TW):%H:%M:%S} 更新 {len(games)} 場：" + "；".join(f"{k} {v['a']}:{v['h']} {v['d']}" for k, v in list(games.items())[:4]))
                except Exception as e:  # noqa: BLE001
                    log(f"推送失敗：{e!r}")
            last = body
        loops += 1
        if all(v.get("s") == "post" for v in games.values()) and len(games) == len(want):
            log("盯的比賽都打完了，結束。")
            break
        if time.time() + args.every > t_end:
            break
        time.sleep(args.every)


if __name__ == "__main__":
    main()
